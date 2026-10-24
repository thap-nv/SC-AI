"""Per-camera loop: sample a frame, detect, track, apply zone rules, publish incidents."""

import base64
import logging
import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone

import numpy as np

from app.alignment import ViewAligner, ZoneView
from app.api_client import ApiClient
from app.config import Settings
from app.detectors import PPE_ITEMS, HintVehicleTyper, HogPersonDetector, NoHandwashDetector, UnknownPPEClassifier, build_detectors, build_handwash_detector, build_vehicle_typer, providers_for
from app.drawing import annotate, jpeg_bytes
from app.handpose import build_hand_pose
from app.handwash import HANDWASH_CONDITION, STEP_NAMES, Wash, WashTracker, missing_steps, wash_checks
from app.logging_utils import event
from app.metrics import camera_fps, camera_up, detections_total, dropped_frames, frames_processed, incidents_created, inference_latency
from app.rule_engine import ALLOWED_VEHICLES, PPE_CONDITIONS, Observation, RuleConfig, RuleEngine
from app.sources import FrameSource
from app.storage import ObjectStore
from app.tracker import PersonTracker
from app.zone_engine import bbox_center_in_polygon, bbox_foot_in_polygon

log = logging.getLogger("worker.runtime")
PPE_EVENTS = {"HELMET_VIOLATION", "CLOTHING_VIOLATION", "SHOES_VIOLATION", "MASK_VIOLATION"}
PPE_VOTE_WINDOW = 6
PPE_VOTES_NEEDED = 4
VEHICLE_EVENTS = {"VEHICLE_IN_RESTRICTED_AREA"}
# A vehicle's type is read this often and settles on the most common of its last reads.
VEHICLE_READ_EVERY_S = 0.5
VEHICLE_VOTE_WINDOW = 5
# A person this much inside a vehicle's box is taken to be riding it, such as a forklift driver.
IN_VEHICLE_SHARE = 0.6
# Hand joints are found again this often while a wash is in view: the overlay is drawn at most 10 times a second.
# About 16 ms each on the sink area.
HAND_POSE_EVERY_S = 0.1


def iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1) + max(0.0, bx2 - bx1) * max(0.0, by2 - by1) - inter
    if area <= 0:
        return 0.0
    return inter / area


def normalize(box: list[float], width: int, height: int) -> tuple[float, float, float, float]:
    return (box[0] / width, box[1] / height, box[2] / width, box[3] / height)


def rule_config(rule: dict) -> RuleConfig:
    return RuleConfig(
        id=rule["id"],
        zone_id=rule["zone_id"],
        condition_type=rule["condition_type"],
        event_type=rule["event_type"],
        severity=rule["severity"],
        min_duration_s=float(rule["min_duration_ms"]) / 1000.0,
        cooldown_s=float(rule["cooldown_ms"]) / 1000.0,
        grace_s=float(rule["grace_ms"]) / 1000.0,
    )


PPE_TEXT = {"helmet": "Helmet", "clothing": "Clothing", "shoes": "Safety shoes", "mask": "Mask"}
STATE_TEXT = {"YES": "Yes", "NO": "No", "UNKNOWN": "Unknown"}


def track_checks(
    rules: list[dict],
    zones: list[dict],
    box: tuple[float, float, float, float],
    ppe: dict[str, str],
    kind: str = "person",
    vehicle_type: str = "",
    in_vehicle: bool = False,
) -> list[dict]:
    """What each enabled rule says about one person or vehicle, for the overlay and the live panel.

    Only rules whose zone holds the feet, or the wheels, apply. State is violation, ok or unknown.
    """
    by_id = {zone["id"]: zone for zone in zones}
    checks: list[dict] = []
    for rule in rules:
        if not rule.get("enabled"):
            continue
        zone = by_id.get(rule["zone_id"])
        if zone is None or not bbox_foot_in_polygon(zone.get("polygon"), box):
            continue
        condition = rule["condition_type"]
        item = PPE_CONDITIONS.get(condition)
        zone_name = zone.get("name") or zone.get("zone_type")
        if condition == "VEHICLE_INSIDE":
            if kind != "vehicle":
                continue
            if not vehicle_type:
                check = {"item": "zone", "text": "Vehicle type unknown", "state": "unknown"}
            elif vehicle_type in ALLOWED_VEHICLES:
                check = {"item": "zone", "text": f"{vehicle_type.capitalize()} allowed", "state": "ok"}
            else:
                check = {"item": "zone", "text": f"In {zone_name}", "state": "violation"}
        elif kind != "person":
            continue
        elif condition == "PERSON_INSIDE":
            check = {"item": "zone", "text": "In a vehicle", "state": "ok"} if in_vehicle else {"item": "zone", "text": f"In {zone_name}", "state": "violation"}
        elif item is not None:
            state = ppe.get(item, "UNKNOWN")
            check = {"item": item, "text": f"{PPE_TEXT[item]}: {STATE_TEXT.get(state, 'Unknown')}", "state": {"NO": "violation", "YES": "ok"}.get(state, "unknown")}
        else:
            continue
        if check not in checks:
            checks.append(check)
    return checks


def place_zone(zone: dict, view: ZoneView | None) -> dict:
    """The zone as rules see it on this frame. A paused zone has no polygon, so nobody is inside it."""
    view = view or ZoneView("UNVERIFIED", zone.get("polygon"))
    return {**zone, "polygon": view.polygon, "drawn_polygon": zone.get("polygon"), "view_state": view.state, "shift_pct": view.shift_pct}


def crop_of(frame, box: list[float]):
    height, width = frame.shape[:2]
    x1 = max(0, min(width - 1, int(box[0])))
    y1 = max(0, min(height - 1, int(box[1])))
    x2 = max(x1 + 1, min(width, int(box[2])))
    y2 = max(y1 + 1, min(height, int(box[3])))
    return frame[y1:y2, x1:x2]


class CameraLoop:
    def __init__(self, camera_id: str, settings: Settings, stop: threading.Event):
        self.camera_id = camera_id
        self.settings = settings
        self.stop = stop
        self.api = ApiClient(settings)
        self.store = ObjectStore(settings)
        self.source = FrameSource(camera_id)
        self.engine = RuleEngine()
        self.tracker = None
        self.tracker_fps = None
        self.hold_until = 0.0
        self.frame_times = deque(maxlen=20)
        self.frames = 0
        self.dropped = 0
        self.last_preview = 0.0
        self.last_raw_preview = 0.0
        self.ppe_votes: dict[str, deque] = {}
        # Last settled PPE per track and when it was read. A person crop is read a few times a second, not every frame.
        self.ppe_seen: dict[str, tuple[float, dict[str, str], dict[str, float]]] = {}
        # Boxes as drawn, eased between frames so the overlay does not shake. Rules use the raw box.
        self.drawn_boxes: dict[str, list[float]] = {}
        # Incidents opened lately per rule, so a person the tracker loses and finds again under a new id
        # carries on the same incident instead of opening a second one.
        self.recent_incidents: dict[str, list[dict]] = {}
        self.aligner = ViewAligner(self.store.get_bytes)
        self.config: dict | None = None
        self.config_at = float("-inf")
        self.last_heartbeat_at = float("-inf")
        self.last_heartbeat_status = ""
        self.detector, self.ppe, self.person_name, self.person_version, self.ppe_name, self.ppe_version = self._load_models()
        self.vehicle_typer = self._load_vehicle_typer()
        self.vehicle_votes: dict[str, deque] = {}
        self.vehicle_seen: dict[str, tuple[float, str]] = {}
        # Loaded on first use: only a camera with a hand-wash rule needs the gesture model.
        self.gestures = None
        self.gestures_read_at = float("-inf")
        self.washes = WashTracker(gap_s=settings.handwash_gap_s)
        # Hand joints for the overlay, loaded with the gesture model. None when the files are missing.
        self.hand_pose = None
        self.hand_pose_at = float("-inf")

    def _load_models(self):
        try:
            return build_detectors(self.settings.ai_mode, self.settings.model_path, self.settings.ai_device, self.settings.ai_threads)
        except Exception:
            log.exception("model adapter failed; person detection uses HOG and PPE stays UNKNOWN")
            return HogPersonDetector(), UnknownPPEClassifier(), "person-detector", "hog-v1", "ppe-detector", "unloaded"

    def _load_vehicle_typer(self):
        try:
            return build_vehicle_typer(self.settings.ai_mode, self.settings.model_path, self.settings.ai_device, 1)
        except Exception:
            log.exception("vehicle typer failed; the detector's class is used and forklifts read as trucks")
            return HintVehicleTyper("coco-class", "no-forklift")

    def _load_gestures(self):
        try:
            gestures = build_handwash_detector(self.settings.ai_mode, self.settings.model_path, self.settings.ai_device, self.settings.ai_threads, self.settings.handwash_scale)
        except Exception:
            log.exception("hand-wash model failed; no wash is checked", extra={"camera_id": self.camera_id})
            return NoHandwashDetector()
        if isinstance(gestures, NoHandwashDetector):
            log.warning("handwash.onnx not found; no wash is checked", extra={"camera_id": self.camera_id})
        return gestures

    def close(self) -> None:
        self.source.close()
        self.api.http.close()
        camera_up.labels(camera_id=self.camera_id).set(0)

    def run(self) -> None:
        log.info("camera loop started", extra={"camera_id": self.camera_id})
        while not self.stop.is_set():
            camera = self._camera()
            if camera is None:
                camera_up.labels(camera_id=self.camera_id).set(0)
                self.stop.wait(2)
                continue
            if not camera.get("enabled"):
                self._heartbeat(camera, "DISABLED", [], 0, 0)
                self.stop.wait(2)
                continue
            started = time.perf_counter()
            try:
                self._step(camera)
            except Exception:
                log.exception("camera step failed", extra={"camera_id": self.camera_id})
                self.stop.wait(2)
                continue
            fps = max(1, int(camera.get("ai_fps") or self.settings.default_ai_fps))
            elapsed = time.perf_counter() - started
            interval = 1.0 / fps
            if elapsed > interval:
                self.dropped += 1
                dropped_frames.labels(camera_id=self.camera_id).inc()
            else:
                self.stop.wait(interval - elapsed)

    def _camera(self) -> dict | None:
        """Camera config, zones and rules, fetched about once a second instead of on every frame."""
        now = time.monotonic()
        if now - self.config_at < self.settings.config_refresh_s:
            return self.config
        try:
            cameras = self.api.list_cameras()
        except Exception:
            log.warning("camera config request failed", extra={"camera_id": self.camera_id})
            return None
        found = None
        for camera in cameras:
            if camera["id"] == self.camera_id:
                assigned = camera.get("assigned_worker")
                found = None if assigned and assigned != self.settings.worker_id else camera
                break
        self.config, self.config_at = found, now
        return found

    def _step(self, camera: dict) -> None:
        if camera.get("simulate_pending"):
            longest = max((float(rule["min_duration_ms"]) for rule in camera.get("rules") or []), default=1000.0)
            self.hold_until = time.time() + longest / 1000.0 + 1.5
            try:
                self.api.ack_simulate(camera["id"])
            except Exception:
                log.warning("simulate ack failed", extra={"camera_id": camera["id"]})
            camera["simulate_pending"] = False
        frame, source_state = self.source.read(camera, self.store, self.settings)
        if frame is None:
            camera_up.labels(camera_id=camera["id"]).set(0)
            # A wash cut off by the camera going offline cannot be judged. Kept, it would be reported
            # as soon as frames came back, from a different video.
            self.washes.forget(set())
            self._heartbeat(camera, "OFFLINE", [], 0, 0)
            return
        fps_setting = max(1, int(camera.get("ai_fps") or self.settings.default_ai_fps))
        if self.tracker is None or self.tracker_fps != fps_setting:
            self.tracker = PersonTracker(frame_rate=fps_setting)
            self.tracker_fps = fps_setting
        now = time.time()
        hold = now < self.hold_until
        infer_started = time.perf_counter()
        views = self.aligner.update(frame, camera.get("zones") or [], now, multi_view=bool(camera.get("multi_view")))
        camera = {**camera, "zones": [place_zone(zone, views.get(zone["id"])) for zone in camera.get("zones") or []]}
        # A camera whose rules are all hand-wash rules has no use for people or vehicles: skipping them saves
        # about 18 ms a frame and keeps a box round the whole person off the sink view.
        conditions = {rule["condition_type"] for rule in camera.get("rules") or [] if rule.get("enabled")}
        hands_only = conditions == {HANDWASH_CONDITION}
        detections = [] if hands_only else self.detector.detect(frame, camera.get("zones") or [], now, hold)
        tracks = self.tracker.update(detections)
        enriched = self._enrich(frame, camera, detections, tracks, now) + self._handwash(frame, camera, now, hold, self.source.take_rewound())
        latency = time.perf_counter() - infer_started
        inference_latency.labels(camera_id=camera["id"]).observe(latency)
        frames_processed.labels(camera_id=camera["id"]).inc()
        detections_total.labels(camera_id=camera["id"]).inc(len(detections))
        self.frames += 1
        self.frame_times.append(now)
        self._apply_rules(camera, frame, enriched, now)
        camera_up.labels(camera_id=camera["id"]).set(1)
        achieved = self._achieved_fps()
        camera_fps.labels(camera_id=camera["id"]).set(achieved)
        self._maybe_store_preview(
            camera["id"],
            frame,
            lambda: annotate(frame, camera.get("zones") or [], enriched),
            fps_setting,
        )
        self._heartbeat(camera, "AI_PROCESSING", enriched, latency * 1000.0, achieved, source_state)

    def _enrich(self, frame, camera: dict, detections: list[dict], tracks: list[dict], now: float) -> list[dict]:
        height, width = frame.shape[:2]
        zones = camera.get("zones") or []
        enriched = []
        vehicle_boxes = [track["bbox_xyxy"] for track in tracks if track["class_name"] == "vehicle"]
        for track in tracks:
            hint = _match_hint(track["bbox_xyxy"], detections)
            box = normalize(track["bbox_xyxy"], width, height)
            zone_types = [
                zone["zone_type"]
                for zone in zones
                if bbox_foot_in_polygon(zone.get("polygon"), box)
            ]
            ppe, ppe_scores, checks, vehicle_type, in_vehicle = {item: "UNKNOWN" for item in PPE_ITEMS}, {}, [], "", False
            if track["class_name"] == "person":
                ppe, ppe_scores = self._track_ppe(frame, track, hint, now)
                in_vehicle = any(_share_inside(track["bbox_xyxy"], other) >= IN_VEHICLE_SHARE for other in vehicle_boxes)
                checks = track_checks(camera.get("rules") or [], zones, box, ppe, "person", in_vehicle=in_vehicle)
            elif track["class_name"] == "vehicle":
                vehicle_type = self._vehicle_type(frame, track, hint, now)
                checks = track_checks(camera.get("rules") or [], zones, box, ppe, "vehicle", vehicle_type=vehicle_type)
            enriched.append({**track, "bbox_norm": box, "draw_box": self._ease(track), "ppe": ppe, "ppe_scores": ppe_scores, "vehicle_type": vehicle_type, "in_vehicle": in_vehicle, "zone_types": zone_types, "checks": checks})
        live = {track["track_id"] for track in tracks}
        for seen in (self.ppe_votes, self.ppe_seen, self.drawn_boxes, self.vehicle_votes, self.vehicle_seen):
            for track_id in set(seen) - live:
                seen.pop(track_id, None)
        return enriched

    def _handwash(self, frame, camera: dict, now: float, hold: bool, restarted: bool = False) -> list[dict]:
        """Follows the wash at each zone with a hand-wash rule and reports each one that ends.

        restarted is an uploaded video starting over: a cut to a new scene, so every wash ends there.
        Without it the wash at the end of a clip ran on into the first wash of the next play, and a wrong
        wash passed on the steps of the two together.
        Returns the hands in view as one track per wash, for the overlay and the live panel.
        """
        rules = [rule for rule in camera.get("rules") or [] if rule.get("enabled") and rule["condition_type"] == HANDWASH_CONDITION]
        zones = {zone["id"]: zone for zone in camera.get("zones") or []}
        watched = {rule["zone_id"]: zones[rule["zone_id"]] for rule in rules if rule["zone_id"] in zones}
        self.washes.forget(set(watched))
        if not watched:
            return []
        if self.gestures is None:
            self.gestures = self._load_gestures()
            self.hand_pose = self._load_hand_pose()
        skipped ={step.strip() for step in self.settings.handwash_skip_steps.split(",")}
        checked = set(self.gestures.steps) - skipped
        if restarted:
            for zone_id, wash in self.washes.finish_all():
                self._report_wash(camera, watched[zone_id], wash, [rule for rule in rules if rule["zone_id"] == zone_id], checked)
        if now - self.gestures_read_at >= self.settings.handwash_interval_s:
            self.gestures_read_at = now
            height, width = frame.shape[:2]
            found = self.gestures.detect(frame, list(watched.values()), now, hold)
            for zone_id, zone in watched.items():
                inside = [hit for hit in found if bbox_center_in_polygon(zone.get("polygon"), normalize(hit[2], width, height))]
                ended = self.washes.observe(zone_id, max(inside, key=lambda hit: hit[1]) if inside else None, now, frame)
                if ended is not None:
                    self._report_wash(camera, zone, ended, [rule for rule in rules if rule["zone_id"] == zone_id], checked)
        tracks = []
        pose_due = self.hand_pose is not None and now - self.hand_pose_at >= HAND_POSE_EVERY_S
        for zone_id, wash in self.washes.washes.items():
            # Hands gone a moment ago leave no box behind while the wash waits to see if they come back.
            if now - wash.last_seen_at > 1.0:
                continue
            if pose_due:
                wash.joints = self._joints_in(frame, watched[zone_id])
                self.hand_pose_at = now
            min_step_s = min(rule_config(rule).min_duration_s for rule in rules if rule["zone_id"] == zone_id)
            tracks.append(_wash_track(wash, frame, wash_checks(wash, checked, min_step_s)))
        return tracks

    def _joints_in(self, frame, zone: dict) -> list:
        """The joints of the hands within the zone's bounding box, in frame pixels."""
        height, width = frame.shape[:2]
        points = zone.get("polygon") or []
        if len(points) < 3:
            return []
        x1, y1 = int(min(point[0] for point in points) * width), int(min(point[1] for point in points) * height)
        x2, y2 = int(max(point[0] for point in points) * width), int(max(point[1] for point in points) * height)
        try:
            hands = self.hand_pose.find(frame[max(0, y1) : y2, max(0, x1) : x2])
        except Exception:
            log.exception("hand joints failed", extra={"camera_id": self.camera_id})
            return []
        return [joints + [max(0, x1), max(0, y1)] for joints in hands]

    def _load_hand_pose(self):
        try:
            return build_hand_pose(self.settings.ai_mode, self.settings.model_path, providers_for(self.settings.ai_device), 1)
        except Exception:
            log.exception("hand joints model failed; the overlay shows no joints", extra={"camera_id": self.camera_id})
            return None

    def _report_wash(self, camera: dict, zone: dict, wash: Wash, rules: list[dict], checked: set[str]) -> None:
        """A wash with a checked step not done is an incident already over: from the first hands seen to the last."""
        for rule in rules:
            min_step_s = rule_config(rule).min_duration_s
            missing = missing_steps(wash, checked, min_step_s)
            if not missing:
                event(log, "hand wash complete", camera_id=camera["id"], rule_id=rule["id"], track_id=wash.id)
                continue
            track = _wash_track(wash, wash.frame, wash_checks(wash, checked, min_step_s, finished=True))
            note = f"Wash {round(wash.seen_s)} s, missed: " + ", ".join(STEP_NAMES[step] for step in missing)
            crop = crop_of(wash.frame, wash.box)
            payload = {
                "factory_id": camera["factory_id"],
                "camera_id": camera["id"],
                "zone_id": zone["id"],
                "rule_id": rule["id"],
                "event_type": rule["event_type"],
                "severity": rule["severity"],
                "track_id": wash.id,
                "confidence": round(wash.confidence, 4),
                "started_at": iso(wash.started_at),
                "model_name": self.gestures.name,
                "model_version": self.gestures.version,
                "ai_mode": self.settings.ai_mode.upper(),
                "snapshot_base64": base64.b64encode(jpeg_bytes(annotate(wash.frame, camera.get("zones") or [], [track], note=note))).decode("ascii"),
                "crop_base64": base64.b64encode(jpeg_bytes(crop, 80)).decode("ascii") if crop.size else None,
            }
            try:
                body = self.api.open_incident(payload)
                if body.get("reason") != "created":
                    continue
                self.api.close_incident(body["id"], iso(wash.last_seen_at))
            except Exception:
                log.exception("hand wash incident failed", extra={"camera_id": camera["id"], "rule_id": rule["id"], "track_id": wash.id})
                continue
            incidents_created.labels(camera_id=camera["id"]).inc()
            event(log, f"hand wash incomplete, missed {', '.join(missing)}", camera_id=camera["id"], rule_id=rule["id"], track_id=wash.id, incident_id=body["id"])

    def _vehicle_type(self, frame, track: dict, hint: dict | None, now: float) -> str:
        """Read twice a second; the most common of the last reads. The first read counts at once."""
        seen = self.vehicle_seen.get(track["track_id"])
        if seen is not None and now - seen[0] < VEHICLE_READ_EVERY_S:
            return seen[1]
        x1, y1, x2, y2 = track["bbox_xyxy"]
        pad = 0.1 * max(x2 - x1, y2 - y1)
        label, _ = self.vehicle_typer.classify(crop_of(frame, [x1 - pad, y1 - pad, x2 + pad, y2 + pad]), (hint or {}).get("vehicle_type"))
        history = self.vehicle_votes.setdefault(track["track_id"], deque(maxlen=VEHICLE_VOTE_WINDOW))
        if label:
            history.append(label)
        settled = Counter(history).most_common(1)[0][0] if history else ""
        self.vehicle_seen[track["track_id"]] = (now, settled)
        return settled

    def _ease(self, track: dict) -> list[float]:
        previous = self.drawn_boxes.get(track["track_id"])
        box = track["bbox_xyxy"] if previous is None else [0.5 * new + 0.5 * old for new, old in zip(track["bbox_xyxy"], previous)]
        self.drawn_boxes[track["track_id"]] = box
        return box

    def _track_ppe(self, frame, track: dict, hint: dict | None, now: float) -> tuple[dict[str, str], dict[str, float]]:
        seen = self.ppe_seen.get(track["track_id"])
        if seen is not None and now - seen[0] < self.settings.ppe_interval_s:
            return seen[1], seen[2]
        context = {"outfit": (hint or {}).get("outfit"), "frame": frame, "box": track["bbox_xyxy"]}
        reading = self.ppe.classify(crop_of(frame, track["bbox_xyxy"]), context)
        ppe, scores = self._stable_ppe(track["track_id"], reading)
        self.ppe_seen[track["track_id"]] = (now, ppe, scores)
        return ppe, scores

    def _stable_ppe(self, track_id: str, reading: dict[str, tuple[str, float]]) -> tuple[dict[str, str], dict[str, float]]:
        """An item settles on YES or NO once four of the last six reads agree. Until then it is UNKNOWN.

        On the workshop test clip this kept every wrong NO under 1 s, short of a rule's 2 s, while
        the worker without a helmet and the one in a T-shirt stayed NO for over 10 s.
        """
        history = self.ppe_votes.setdefault(track_id, deque(maxlen=PPE_VOTE_WINDOW))
        history.append(reading)
        ppe: dict[str, str] = {}
        scores: dict[str, float] = {}
        for item in PPE_ITEMS:
            votes = [entry[item] for entry in history if entry.get(item, ("UNKNOWN", 0.0))[0] in {"YES", "NO"}]
            label, count = Counter(state for state, _ in votes).most_common(1)[0] if votes else ("UNKNOWN", 0)
            if count < PPE_VOTES_NEEDED:
                ppe[item], scores[item] = "UNKNOWN", 0.0
                continue
            agreeing = [score for state, score in votes if state == label]
            ppe[item], scores[item] = label, round(sum(agreeing) / len(agreeing), 3)
        return ppe, scores

    def _apply_rules(self, camera: dict, frame, tracks: list[dict], now: float) -> None:
        rules = [rule for rule in camera.get("rules") or [] if rule.get("enabled")]
        configs = {rule["id"]: rule_config(rule) for rule in rules}
        zones = {zone["id"]: zone for zone in camera.get("zones") or []}
        visible: set[str] = set()
        actions = []
        for track in tracks:
            if track["class_name"] not in ("person", "vehicle"):
                continue
            visible.add(track["track_id"])
            for rule in rules:
                zone = zones.get(rule["zone_id"])
                if zone is None:
                    continue
                inside = bbox_foot_in_polygon(zone.get("polygon"), track["bbox_norm"])
                item = PPE_CONDITIONS.get(rule["condition_type"])
                confidence = track["ppe_scores"].get(item) if item else track["confidence"]
                actions.extend(
                    self.engine.update(
                        configs[rule["id"]],
                        Observation(
                            track_id=track["track_id"],
                            timestamp=now,
                            inside=inside,
                            ppe=track["ppe"],
                            confidence=float(confidence or 0.0),
                            bbox=track["bbox_norm"],
                            class_name=track["class_name"],
                            vehicle_type=track.get("vehicle_type") or "",
                            in_vehicle=bool(track.get("in_vehicle")),
                        ),
                    )
                )
        actions.extend(self.engine.expire_missing(configs, now, visible))
        annotated = None
        for action in actions:
            if action.kind == "open":
                if self._carry_on(camera, action, configs[action.rule_id].cooldown_s, now, visible):
                    continue
                if annotated is None:
                    annotated = annotate(frame, camera.get("zones") or [], tracks)
                self._open(camera, frame, action, annotated_frame=annotated)
            elif action.kind == "close" and action.incident_id:
                self._remember(action.rule_id, action.incident_id, action.track_id, action.bbox, now)
                try:
                    self.api.close_incident(action.incident_id, iso(action.ended_at or now))
                    event(log, "incident closed", camera_id=camera["id"], track_id=action.track_id, rule_id=action.rule_id, incident_id=action.incident_id)
                except Exception:
                    log.exception("incident close failed", extra={"camera_id": camera["id"], "incident_id": action.incident_id, "rule_id": action.rule_id, "track_id": action.track_id})

    def _carry_on(self, camera: dict, action, window_s: float, now: float, visible: set[str]) -> bool:
        """A new track standing where a lost one left off, under the same rule, keeps that incident."""
        for entry in self.recent_incidents.get(action.rule_id, []):
            if entry["track_id"] in visible or now - entry["seen_at"] > window_s or not _near(entry["bbox"], action.bbox):
                continue
            self.engine.attach_incident(action.rule_id, action.track_id, entry["incident_id"])
            event(log, "incident carried to a new track", camera_id=camera["id"], track_id=action.track_id, rule_id=action.rule_id, incident_id=entry["incident_id"])
            entry.update(track_id=action.track_id, bbox=action.bbox, seen_at=now)
            return True
        return False

    def _remember(self, rule_id: str, incident_id: str, track_id: str, bbox, now: float) -> None:
        kept = [entry for entry in self.recent_incidents.get(rule_id, []) if entry["incident_id"] != incident_id and now - entry["seen_at"] <= 600]
        self.recent_incidents[rule_id] = kept + [{"incident_id": incident_id, "track_id": track_id, "bbox": bbox, "seen_at": now}]

    def _open(self, camera: dict, frame, action, annotated_frame) -> None:
        use_ppe = action.event_type in PPE_EVENTS
        snapshot = jpeg_bytes(annotated_frame)
        crop = crop_of(frame, [action.bbox[0] * frame.shape[1], action.bbox[1] * frame.shape[0], action.bbox[2] * frame.shape[1], action.bbox[3] * frame.shape[0]])
        payload = {
            "factory_id": camera["factory_id"],
            "camera_id": camera["id"],
            "zone_id": action.zone_id,
            "rule_id": action.rule_id,
            "event_type": action.event_type,
            "severity": action.severity,
            "track_id": action.track_id,
            "confidence": round(float(action.confidence), 4),
            "started_at": iso(action.started_at),
            "model_name": self.ppe_name if use_ppe else self.vehicle_typer.name if action.event_type in VEHICLE_EVENTS else self.person_name,
            "model_version": self.ppe_version if use_ppe else self.vehicle_typer.version if action.event_type in VEHICLE_EVENTS else self.person_version,
            "ai_mode": self.settings.ai_mode.upper(),
            "snapshot_base64": base64.b64encode(snapshot).decode("ascii"),
            "crop_base64": base64.b64encode(jpeg_bytes(crop, 80)).decode("ascii") if crop is not None and crop.size else None,
        }
        try:
            body = self.api.open_incident(payload)
        except Exception:
            log.exception("incident create failed", extra={"camera_id": camera["id"], "rule_id": action.rule_id, "track_id": action.track_id})
            return
        reason = body.get("reason")
        if reason == "cooldown":
            self.engine.force_cooldown(action.rule_id, action.track_id, time.time() + 1.0)
            return
        self.engine.attach_incident(action.rule_id, action.track_id, body["id"])
        self._remember(action.rule_id, body["id"], action.track_id, action.bbox, time.time())
        if reason == "created":
            incidents_created.labels(camera_id=camera["id"]).inc()
            event(
                log,
                "incident opened",
                camera_id=camera["id"],
                track_id=action.track_id,
                rule_id=action.rule_id,
                incident_id=body["id"],
            )

    def _maybe_store_preview(self, camera_id: str, raw, render, fps: int) -> None:
        """Draws the overlay only when a preview is due, at most ten times a second."""
        now = time.time()
        preview_every = 1.0 / min(max(fps, 1), 10)
        try:
            if now - self.last_preview >= preview_every:
                self.last_preview = now
                self.store.put_bytes(f"cameras/{camera_id}/latest.jpg", jpeg_bytes(render()), "image/jpeg")
            if now - self.last_raw_preview >= 1.0:
                self.last_raw_preview = now
                self.store.put_bytes(f"cameras/{camera_id}/latest_raw.jpg", jpeg_bytes(raw), "image/jpeg")
        except Exception:
            log.warning("preview upload failed", extra={"camera_id": camera_id})

    def _heartbeat(self, camera: dict, status: str, tracks: list[dict], inference_ms: float, achieved: float, source_state: str = "") -> None:
        """The dashboard polls once a second, so a few heartbeats a second are enough. A status change goes out at once."""
        now = time.monotonic()
        if status == self.last_heartbeat_status and now - self.last_heartbeat_at < self.settings.heartbeat_every_s:
            return
        self.last_heartbeat_at, self.last_heartbeat_status = now, status
        payload = {
            "status": status,
            "frames_processed": self.frames,
            "dropped_frames": self.dropped,
            "inference_ms": round(inference_ms, 2),
            "detections": len(tracks),
            "ai_fps": round(achieved, 2),
            "ai_mode": self.settings.ai_mode.upper(),
            "source_state": source_state,
            "tracks": [
                {
                    "track_id": track["track_id"],
                    "bbox": list(track["bbox_norm"]),
                    "class_name": track["class_name"],
                    "confidence": round(float(track["confidence"]), 3),
                    "ppe": track.get("ppe"),
                    "vehicle_type": track.get("vehicle_type") or None,
                    "checks": track.get("checks") or [],
                    "wash_s": track.get("wash_s"),
                }
                for track in tracks
            ],
            "zones": [
                {"id": zone["id"], "name": zone.get("name"), "state": zone["view_state"], "shift_pct": zone.get("shift_pct", 0.0)}
                for zone in camera.get("zones") or []
                if "view_state" in zone
            ],
        }
        try:
            self.api.heartbeat(camera["id"], payload)
        except Exception:
            log.warning("heartbeat failed", extra={"camera_id": camera["id"]})

    def _achieved_fps(self) -> float:
        if len(self.frame_times) < 2:
            return 0.0
        span = self.frame_times[-1] - self.frame_times[0]
        if span <= 0:
            return 0.0
        return (len(self.frame_times) - 1) / span


def _wash_track(wash: Wash, frame, checks: list[dict]) -> dict:
    """The hands of a wash under way, shaped like a person track so the overlay and live panel can show them.

    With hand joints the box closes round them, so the tag sits over the hands rather than the whole sink.
    """
    height, width = frame.shape[:2]
    box = wash.box
    if wash.joints:
        points = np.concatenate(wash.joints)
        margin = 0.08 * max(float(np.ptp(points[:, 0])), float(np.ptp(points[:, 1])), 1.0)
        box = [float(points[:, 0].min() - margin), float(points[:, 1].min() - margin), float(points[:, 0].max() + margin), float(points[:, 1].max() + margin)]
    return {
        "track_id": wash.id,
        "class_name": "hands",
        "class_id": -1,
        "confidence": wash.scores[-1] if wash.scores else 0.0,
        "bbox_xyxy": box,
        "draw_box": box,
        "joints": wash.joints,
        "bbox_norm": normalize(box, width, height),
        "ppe": {},
        "ppe_scores": {},
        "vehicle_type": "",
        "in_vehicle": False,
        "zone_types": [],
        "checks": checks,
        "wash_s": round(wash.seen_s),
    }


def _match_hint(box: list[float], detections: list[dict]) -> dict | None:
    best = None
    best_score = 0.3
    for detection in detections:
        score = iou(box, detection["bbox_xyxy"])
        if score > best_score:
            best = detection
            best_score = score
    return best


def _near(a, b) -> bool:
    """Two normalised boxes close enough to be the same person a moment apart."""
    centre_a = ((a[0] + a[2]) / 2, (a[1] + a[3]) / 2)
    centre_b = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    reach = 1.5 * max(a[2] - a[0], b[2] - b[0])
    return ((centre_a[0] - centre_b[0]) ** 2 + (centre_a[1] - centre_b[1]) ** 2) ** 0.5 <= reach


def _share_inside(inner: list[float], outer: list[float]) -> float:
    """How much of the inner box lies within the outer one, from 0 to 1."""
    width = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    height = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    area = max(1e-6, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return width * height / area

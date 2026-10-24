import threading
from pathlib import Path

import numpy as np
import pytest

from app.config import Settings
from app.detectors import build_detectors
from app.runtime import CameraLoop

CAMERA = {
    "id": "cam-1",
    "factory_id": "f-1",
    "code": "CAM-1",
    "name": "Camera 1",
    "stream_type": "FILE",
    "stream_url": "",
    "enabled": True,
    "ai_fps": 5,
    "assigned_worker": None,
    "simulate_pending": False,
    "zones": [],
    "rules": [],
}


class FakeApi:
    def __init__(self, cameras: list[dict]):
        self.cameras = cameras
        self.config_calls = 0
        self.heartbeats: list[str] = []
        self.acks = 0
        self.closed: list[str] = []

    def list_cameras(self) -> list[dict]:
        self.config_calls += 1
        return self.cameras

    def heartbeat(self, camera_id: str, payload: dict) -> None:
        self.heartbeats.append(payload["status"])

    def ack_simulate(self, camera_id: str) -> None:
        self.acks += 1

    def close_incident(self, incident_id: str, ended_at: str) -> None:
        self.closed.append(incident_id)


def loop_with(cameras: list[dict]) -> tuple[CameraLoop, FakeApi]:
    settings = Settings(ai_mode="DEMO", config_refresh_s=60, heartbeat_every_s=60)
    loop = CameraLoop("cam-1", settings, threading.Event())
    fake = FakeApi(cameras)
    loop.api = fake
    loop.store.put_bytes = lambda *args, **kwargs: None
    return loop, fake


def test_camera_config_is_fetched_once_per_refresh_period():
    loop, api = loop_with([CAMERA])
    for _ in range(5):
        assert loop._camera()["id"] == "cam-1"
    assert api.config_calls == 1
    loop.config_at = float("-inf")
    loop._camera()
    assert api.config_calls == 2


def test_heartbeats_are_throttled_but_a_status_change_goes_out_at_once():
    loop, api = loop_with([CAMERA])
    for _ in range(5):
        loop._heartbeat(CAMERA, "AI_PROCESSING", [], 0, 0)
    loop._heartbeat(CAMERA, "OFFLINE", [], 0, 0)
    assert api.heartbeats == ["AI_PROCESSING", "OFFLINE"]


def test_simulate_is_acknowledged_once_while_the_config_is_cached():
    loop, api = loop_with([{**CAMERA, "simulate_pending": True}])
    for _ in range(3):
        loop._step(loop._camera())
    assert api.acks == 1


def test_ppe_is_read_a_few_times_a_second_and_settles_after_four_agreeing_reads():
    loop, _ = loop_with([CAMERA])
    reads = []

    class Fixed:
        def classify(self, crop, context=None):
            reads.append(crop.shape)
            return {"helmet": ("NO", 0.8), "clothing": ("YES", 0.9), "shoes": ("UNKNOWN", 0.0), "mask": ("UNKNOWN", 0.0)}

    loop.ppe = Fixed()
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    track = {"track_id": "1", "class_name": "person", "confidence": 0.9, "bbox_xyxy": [100, 100, 160, 300]}
    seen = {when: loop._track_ppe(frame, track, None, when)[0] for when in (0.0, 0.1, 0.2, 0.35, 0.5, 0.7, 0.8, 1.05, 1.1)}
    assert len(reads) == 4
    assert seen[0.7]["helmet"] == "UNKNOWN"
    assert seen[1.05] == {"helmet": "NO", "clothing": "YES", "shoes": "UNKNOWN", "mask": "UNKNOWN"}
    assert seen[1.1] == seen[1.05]


def test_a_person_found_again_under_a_new_id_keeps_the_incident():
    from app.rule_engine import Observation, RuleConfig

    loop, _ = loop_with([CAMERA])
    config = RuleConfig(id="rule-1", zone_id="z", condition_type="HELMET_MISSING", event_type="HELMET_VIOLATION", severity="HIGH", min_duration_s=0.0, cooldown_s=30.0, grace_s=1.0)
    loop._remember("rule-1", "inc-1", "7", (0.40, 0.30, 0.48, 0.70), 100.0)

    def opening(track_id, box):
        return loop.engine.update(config, Observation(track_id=track_id, timestamp=105.0, inside=True, ppe={"helmet": "NO"}, confidence=0.8, bbox=box))[0]

    assert loop._carry_on(CAMERA, opening("9", (0.42, 0.31, 0.50, 0.71)), 30.0, 105.0, {"9"})
    assert loop.engine._states[("rule-1", "9")].incident_id == "inc-1"
    loop._remember("rule-1", "inc-1", "9", (0.42, 0.31, 0.50, 0.71), 106.0)
    assert not loop._carry_on(CAMERA, opening("11", (0.80, 0.30, 0.88, 0.70)), 30.0, 107.0, {"11"}), "too far away"
    assert not loop._carry_on(CAMERA, opening("12", (0.43, 0.31, 0.51, 0.71)), 30.0, 107.0, {"9", "12"}), "the earlier track is still in view"
    assert not loop._carry_on(CAMERA, opening("13", (0.43, 0.31, 0.51, 0.71)), 30.0, 140.0, {"13"}), "past the cooldown"


PEOPLE_RULE = {"id": "people", "zone_id": "z1", "condition_type": "PERSON_INSIDE", "event_type": "RESTRICTED_AREA_INTRUSION", "severity": "HIGH", "min_duration_ms": 0, "cooldown_ms": 30000, "grace_ms": 1000, "enabled": True}


def with_open_incident(loop: CameraLoop) -> None:
    """Person 5 in the zone with incident inc-1 open, as a clip ends."""
    from app.rule_engine import Observation
    from app.runtime import rule_config

    seen = Observation(track_id="5", timestamp=100.0, inside=True, confidence=0.9, bbox=(0.40, 0.30, 0.48, 0.70))
    assert [action.kind for action in loop.engine.update(rule_config(PEOPLE_RULE), seen)] == ["open"]
    loop.engine.attach_incident("people", "5", "inc-1")
    loop._remember("people", "inc-1", "5", seen.bbox, 100.0)


def test_a_looping_video_starting_over_ends_its_incidents_so_the_next_play_alerts_again():
    from app.rule_engine import Observation
    from app.runtime import rule_config

    camera = {**CAMERA, "rules": [PEOPLE_RULE]}
    loop, api = loop_with([camera])
    with_open_incident(loop)
    loop.source.rewound = True
    loop._step(camera)
    assert api.closed == ["inc-1"]
    assert loop.recent_incidents == {}
    # Someone at the same spot as the clip starts again opens a new incident instead of carrying on inc-1.
    now = 200.0
    opening = loop.engine.update(rule_config(PEOPLE_RULE), Observation(track_id="9", timestamp=now, inside=True, confidence=0.9, bbox=(0.41, 0.30, 0.49, 0.70)))
    assert [action.kind for action in opening] == ["open"]
    assert not loop._carry_on(camera, opening[0], 30.0, now, {"9"})


def test_a_looping_video_alerts_once_per_rule_per_cooldown(monkeypatch):
    import app.runtime

    monkeypatch.setattr(app.runtime, "annotate", lambda frame, zones, tracks, **kwargs: frame)
    zone = {"id": "z1", "name": "Lane", "zone_type": "RESTRICTED_AREA", "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]}
    camera = {**CAMERA, "stream_url": "videos/cam-1/clip.mp4", "zones": [zone], "rules": [PEOPLE_RULE]}
    loop, _ = loop_with([camera])
    opened = []

    def open_incident(camera_, frame, action, annotated_frame):
        opened.append(action.track_id)
        loop.engine.attach_incident(action.rule_id, action.track_id, f"inc-{action.track_id}")

    loop._open = open_incident
    frame = np.zeros((540, 960, 3), dtype=np.uint8)

    def person(track_id: str, box=(0.40, 0.30, 0.48, 0.70)) -> dict:
        return {"track_id": track_id, "class_name": "person", "confidence": 0.9, "bbox_norm": box, "ppe": {}, "ppe_scores": {}}

    loop._apply_rules(camera, frame, [person("1")], 100.0)
    loop._apply_rules(camera, frame, [person("1"), person("2")], 100.5)
    assert opened == ["1", "2"], "the first play alerts for everyone"
    loop._end_scene(camera, 101.0)
    loop.looped_url = camera["stream_url"]
    loop._apply_rules(camera, frame, [person("3")], 111.0)
    loop._apply_rules(camera, frame, [person("3")], 125.0)
    assert opened == ["1", "2"], "later plays repeat it: nothing until 30 s after the last incident ended at 100.5"
    loop._apply_rules(camera, frame, [person("3")], 131.0)
    assert opened == ["1", "2", "3"]
    loop._apply_rules(camera, frame, [person("4")], 140.0)
    assert opened == ["1", "2", "3"], "inc-3 closes on this frame at 131: the cooldown runs from there"
    assert loop._quiet_until(camera, "people", 30.0, 140.0) == 161.0
    assert loop._quiet_until(camera, "people", 0.0, 140.0) is None, "a cooldown of 0 turns the limit off"
    loop.looped_url = None
    # Away from where person 3 was lost, so not carried on as the same person.
    loop._apply_rules(camera, frame, [person("5", (0.80, 0.30, 0.88, 0.70))], 141.0)
    assert opened == ["1", "2", "3", "5"], "a camera that is not replaying a video alerts as before"


def test_turning_a_camera_off_ends_its_incidents():
    camera = {**CAMERA, "enabled": False, "rules": [PEOPLE_RULE]}
    loop, api = loop_with([camera])
    with_open_incident(loop)
    api.heartbeat = lambda camera_id, payload: loop.stop.set()
    loop.run()
    assert api.closed == ["inc-1"]
    assert loop.recent_incidents == {}


@pytest.mark.skipif(not (Path("/models") / "person.onnx").exists(), reason="person.onnx is not installed")
def test_onnx_sessions_use_a_few_threads_that_do_not_spin():
    detector, *_ = build_detectors("REAL", "/models", "cpu", threads=2)
    options = detector.session.get_session_options()
    assert options.intra_op_num_threads == 2
    assert options.get_session_config_entry("session.intra_op.allow_spinning") == "0"


def test_forklifts_are_looked_for_only_on_cameras_with_a_person_or_vehicle_zone_rule():
    def rule(condition: str) -> dict:
        return {"id": condition, "zone_id": "z1", "condition_type": condition, "event_type": "E", "severity": "HIGH", "min_duration_ms": 1000, "cooldown_ms": 30000, "grace_ms": 1000, "enabled": True}

    class StubForklifts:
        calls = 0

        def detect(self, frame):
            self.calls += 1
            return []

    loop, _ = loop_with([CAMERA])
    loop._step({**CAMERA, "rules": [rule("HELMET_MISSING")]})
    assert loop.forklifts is None
    loop.forklifts = StubForklifts()
    loop._step({**CAMERA, "rules": [rule("HELMET_MISSING"), rule("PERSON_INSIDE")]})
    loop._step({**CAMERA, "rules": [rule("VEHICLE_INSIDE")]})
    assert loop.forklifts.calls == 2


def test_a_forklift_driver_is_exempt_and_a_car_is_flagged_in_a_restricted_area():
    zone = {"id": "z1", "name": "Lane", "zone_type": "RESTRICTED_AREA", "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.98], [0.0, 0.98]]}
    rules = [
        {"id": "people", "zone_id": "z1", "condition_type": "PERSON_INSIDE", "enabled": True},
        {"id": "cars", "zone_id": "z1", "condition_type": "VEHICLE_INSIDE", "enabled": True},
    ]
    loop, _ = loop_with([CAMERA])
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    forklift_box, driver_box = [100.0, 200.0, 260.0, 380.0], [150.0, 210.0, 200.0, 330.0]
    car_box, walker_box = [500.0, 300.0, 700.0, 420.0], [800.0, 200.0, 840.0, 400.0]
    detections = [
        {"class_name": "vehicle", "vehicle_type": "forklift", "bbox_xyxy": forklift_box},
        {"class_name": "vehicle", "vehicle_type": "car", "bbox_xyxy": car_box},
    ]
    tracks = [
        {"track_id": "1", "class_name": "vehicle", "confidence": 0.9, "bbox_xyxy": forklift_box},
        {"track_id": "2", "class_name": "person", "confidence": 0.9, "bbox_xyxy": driver_box},
        {"track_id": "3", "class_name": "vehicle", "confidence": 0.9, "bbox_xyxy": car_box},
        {"track_id": "4", "class_name": "person", "confidence": 0.9, "bbox_xyxy": walker_box},
    ]
    enriched = {track["track_id"]: track for track in loop._enrich(frame, {**CAMERA, "zones": [zone], "rules": rules}, detections, tracks, 0.0)}
    assert enriched["1"]["vehicle_type"] == "forklift" and enriched["1"]["checks"][0]["state"] == "ok"
    assert enriched["2"]["in_vehicle"] is True and enriched["2"]["checks"][0]["text"] == "In a vehicle"
    assert enriched["3"]["vehicle_type"] == "car" and enriched["3"]["checks"][0]["state"] == "violation"
    assert enriched["4"]["in_vehicle"] is False and enriched["4"]["checks"][0]["state"] == "violation"

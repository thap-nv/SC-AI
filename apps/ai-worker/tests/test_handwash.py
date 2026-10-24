import threading

import numpy as np

from app.config import Settings
from app.detectors import DemoHandwashDetector, OnnxHandwashClassifier, OnnxHandwashDetector, zone_square
from app.drawing import annotate, track_tag
from app.handwash import MIN_WASH_S, WASH_GAP_S, WashTracker, missing_steps, wash_checks
from app.runtime import CameraLoop
from app.scenes import WASH_PERIOD_S, WASH_STEPS, scripted_objects, scripted_wash

SINK = {"id": "sink", "name": "Sink", "zone_type": "HANDWASH_STATION", "polygon": [[0.3, 0.2], [0.7, 0.2], [0.7, 0.7], [0.3, 0.7]]}
RULE = {
    "id": "rule-wash",
    "zone_id": "sink",
    "name": "WHO hand washing",
    "event_type": "HANDWASH_INCOMPLETE",
    "condition_type": "HANDWASH_STEPS_MISSING",
    "min_duration_ms": 3000,
    "cooldown_ms": 30000,
    "grace_ms": 1000,
    "severity": "MEDIUM",
    "enabled": True,
}
CAMERA = {
    "id": "cam-wash",
    "factory_id": "f-1",
    "code": "CAM-HANDWASH-01",
    "name": "Handwash",
    "stream_type": "FILE",
    "stream_url": "",
    "enabled": True,
    "ai_fps": 10,
    "assigned_worker": None,
    "simulate_pending": False,
    "zones": [SINK],
    "rules": [RULE],
}
BOX = [100.0, 100.0, 200.0, 180.0]
REFERENCE_STEPS = {"backs", "thumbs", "fingertips"}


def _wash(tracker: WashTracker, plan: list[tuple[str | None, float]], start: float = 1000.0, every: float = 0.2):
    """Feeds reads every 0.2 s: each (step, seconds) holds that step, None is no hands. Returns the washes that ended."""
    ended = []
    now = start
    for step, seconds in plan:
        for _ in range(round(seconds / every)):
            finished = tracker.observe("sink", (step, 0.8, BOX) if step else None, now)
            if finished is not None:
                ended.append(finished)
            now += every
    return ended


def test_a_full_wash_misses_nothing_and_ends_after_the_gap():
    tracker = WashTracker()
    ended = _wash(tracker, [("backs", 5), ("thumbs", 5), ("fingertips", 5), (None, WASH_GAP_S + 1)])
    assert len(ended) == 1
    assert missing_steps(ended[0], REFERENCE_STEPS, 3.0) == []
    assert 14.0 <= ended[0].seen_s <= 15.0
    assert tracker.washes == {}


def test_steps_not_done_are_missing_in_who_order():
    tracker = WashTracker()
    ended = _wash(tracker, [("backs", 5), (None, WASH_GAP_S + 1)])
    assert missing_steps(ended[0], REFERENCE_STEPS, 3.0) == ["thumbs", "fingertips"]


def test_a_step_done_too_briefly_is_missing():
    tracker = WashTracker()
    ended = _wash(tracker, [("backs", 5), ("thumbs", 1.6), ("fingertips", 5), (None, WASH_GAP_S + 1)])
    assert missing_steps(ended[0], REFERENCE_STEPS, 3.0) == ["thumbs"]


def test_a_single_misread_does_not_count_for_its_step():
    tracker = WashTracker()
    ended = _wash(tracker, [("backs", 2), ("thumbs", 0.2), ("backs", 2), (None, WASH_GAP_S + 1)])
    assert "thumbs" not in ended[0].step_s


def test_hands_away_for_less_than_the_gap_keep_the_same_wash():
    tracker = WashTracker()
    ended = _wash(tracker, [("backs", 4), (None, WASH_GAP_S - 1), ("thumbs", 4), (None, WASH_GAP_S + 1)])
    assert len(ended) == 1
    assert ended[0].step_s.keys() == {"backs", "thumbs"}


def test_hands_passing_the_sink_are_not_a_wash():
    tracker = WashTracker()
    assert _wash(tracker, [("backs", MIN_WASH_S - 1), (None, WASH_GAP_S + 1)]) == []


def test_only_checked_steps_are_shown_and_missing_ones_turn_red_when_the_wash_ends():
    tracker = WashTracker()
    _wash(tracker, [("backs", 5), ("thumbs", 1)])
    wash = tracker.washes["sink"]
    during = wash_checks(wash, REFERENCE_STEPS, 3.0)
    assert [(check["item"], check["state"]) for check in during] == [("step2", "ok"), ("step5", "unknown"), ("step6", "unknown")]
    after = wash_checks(wash, REFERENCE_STEPS, 3.0, finished=True)
    assert [check["state"] for check in after] == ["ok", "violation", "violation"]


def test_hands_tag_shows_the_wash_time_and_one_number_per_checked_step():
    tracker = WashTracker()
    _wash(tracker, [("backs", 5)])
    track = {"track_id": "W1", "class_name": "hands", "wash_s": 5, "checks": wash_checks(tracker.washes["sink"], REFERENCE_STEPS, 3.0)}
    assert [text for text, _ in track_tag(track)] == ["Wash 5s", "2", "5", "6"]
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    drawn = annotate(frame, [SINK], [{**track, "bbox_xyxy": BOX}], note="Wash 5 s, missed: Thumbs")
    assert drawn.any()


class _Session:
    def __init__(self, output):
        self.output = output

    def run(self, names, feeds):
        return [self.output]


def test_a_segmentation_export_is_read_by_its_class_scores_and_sides_are_merged():
    detector = _detector()
    # One anchor in the 64x64 letterbox of a 64x36 frame, 14 pixels of padding above and below:
    # 4 box values, 8 class scores, then 32 mask channels.
    output = np.zeros((1, 44, 2), dtype=np.float32)
    output[0, :4, 0] = [32, 32, 16, 8]
    output[0, 4 + 5, 0] = 0.9  # thumbs, second side
    output[0, 4 + 8 :, :] = 5.0  # mask channels never count as a class
    detector.session = _Session(output)
    found = detector.detect(np.zeros((36, 64, 3), dtype=np.uint8), [], 0.0, False)
    assert [(step, round(score, 2)) for step, score, _ in found] == [("thumbs", 0.9)]
    assert np.allclose(found[0][2], [24, 14, 40, 22])


def _detector(scale: float = 1.0) -> OnnxHandwashDetector:
    detector = object.__new__(OnnxHandwashDetector)
    detector.input_name, detector.input_w, detector.input_h, detector.classes, detector.threshold, detector.scale = "images", 64, 64, 8, 0.35, scale
    return detector


class _Recording(_Session):
    def run(self, names, feeds):
        self.image = next(iter(feeds.values()))
        return [self.output]


def test_a_scaled_frame_goes_in_smaller_and_boxes_come_back_in_frame_pixels():
    detector = _detector(scale=0.5)
    # 64x36 at half the letterbox gain is 32x18, centred: 16 pixels of grey left and right, 23 above and below.
    output = np.zeros((1, 12, 2), dtype=np.float32)
    output[0, :4, 0] = [32, 32, 16, 8]
    output[0, 4 + 6, 0] = 0.9  # fingertips
    detector.session = _Recording(output)
    found = detector.detect(np.full((36, 64, 3), 255, dtype=np.uint8), [], 0.0, False)
    seen = detector.session.image[0, 0]
    assert np.isclose(seen[32, 32], 1.0) and np.isclose(seen[32, 10], 114 / 255) and np.isclose(seen[10, 32], 114 / 255)
    assert [(step, round(score, 2)) for step, score, _ in found] == [("fingertips", 0.9)]
    assert np.allclose(found[0][2], [16, 10, 48, 26])


def _classifier(logits: list[float]) -> OnnxHandwashClassifier:
    classifier = object.__new__(OnnxHandwashClassifier)
    classifier.input_name, classifier.classes = "image", list(OnnxHandwashClassifier.CLASSES)
    classifier.session = _Recording(np.array([logits], dtype=np.float32))
    return classifier


def test_the_site_classifier_reads_the_zone_box_and_names_one_class():
    # Zone: x 0.25-0.75 of a 200x100 frame, full height. A white sink area on a black frame.
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[:, 50:150] = 255
    zone = {**SINK, "polygon": [[0.25, 0.0], [0.75, 0.0], [0.75, 1.0], [0.25, 1.0]]}
    classifier = _classifier([0, 0, 0, 0, 0, 0, 5, 0])  # thumbs
    found = classifier.detect(frame, [zone], 0.0, False)
    assert [(step, box) for step, _, box in found] == [("thumbs", [50.0, 0.0, 150.0, 100.0])]
    assert found[0][1] > 0.9
    seen = classifier.session.image
    assert seen.shape == (1, 3, 224, 224)
    # The 100x100 box is square already: no grey padding, only the white sink.
    assert np.allclose(seen[0, :, 112, 112], (1.0 - OnnxHandwashClassifier.MEAN) / OnnxHandwashClassifier.STD, atol=1e-3)


def test_the_site_classifier_gives_no_hit_without_hands_and_other_keeps_the_wash_going():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    assert _classifier([5, 0, 0, 0, 0, 0, 0, 0]).detect(frame, [SINK], 0.0, False) == []
    assert [step for step, _, _ in _classifier([0, 5, 0, 0, 0, 0, 0, 0]).detect(frame, [SINK], 0.0, False)] == ["other"]
    tracker = WashTracker()
    _wash(tracker, [("other", 4)])
    assert tracker.washes["sink"].step_s.keys() <= {"other"}


def test_a_wide_zone_is_padded_square_on_grey():
    square = zone_square(np.full((100, 200, 3), 255, dtype=np.uint8), [0, 0, 200, 100], 224)
    assert square.shape == (224, 224, 3)
    assert (square[5, 112] == 127).all() and (square[112, 112] == 255).all()


def test_demo_station_runs_a_full_wash_then_a_short_one():
    full = [scripted_wash(SINK, second + 0.5, False) for second in range(0, 30)]
    assert [step for step, _ in full[::5]] == list(WASH_STEPS)
    assert scripted_wash(SINK, 35.0, False) is None
    short = [scripted_wash(SINK, second + 0.5, False)[0] for second in range(40, 55, 5)]
    assert short == list(WASH_STEPS[:3])
    assert scripted_wash(SINK, 60.0, False) is None
    assert scripted_wash(SINK, 60.0, True)[0] == WASH_STEPS[0]
    assert scripted_objects([SINK], 10.0, False) == []


class FakeApi:
    def __init__(self):
        self.opened: list[dict] = []
        self.closed: list[tuple[str, str]] = []

    def list_cameras(self) -> list[dict]:
        return [CAMERA]

    def heartbeat(self, camera_id: str, payload: dict) -> None:
        pass

    def open_incident(self, payload: dict) -> dict:
        self.opened.append(payload)
        return {"id": f"inc-{len(self.opened)}", "reason": "created"}

    def close_incident(self, incident_id: str, ended_at: str) -> None:
        self.closed.append((incident_id, ended_at))


def test_demo_loop_reports_the_short_wash_only_and_closes_it_at_once():
    loop = CameraLoop("cam-wash", Settings(ai_mode="DEMO", handwash_skip_steps=""), threading.Event())
    api = FakeApi()
    loop.api = api
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    start = 7000.0 * WASH_PERIOD_S
    tracks_seen = 0
    for tick in range(int(WASH_PERIOD_S / 0.2)):
        tracks_seen += len(loop._handwash(frame, CAMERA, start + tick * 0.2, False))
    assert tracks_seen > 0
    assert len(api.opened) == 1
    incident = api.opened[0]
    assert (incident["event_type"], incident["zone_id"], incident["rule_id"]) == ("HANDWASH_INCOMPLETE", "sink", "rule-wash")
    assert api.closed == [("inc-1", api.closed[0][1])]
    assert incident["started_at"] < api.closed[0][1]


def test_a_wash_cut_off_by_the_camera_going_offline_is_dropped_not_reported():
    loop = CameraLoop("cam-wash", Settings(ai_mode="REAL", model_path="/nowhere"), threading.Event())
    api = FakeApi()
    loop.api = api
    loop.gestures = DemoHandwashDetector()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    start = 7000.0 * WASH_PERIOD_S + 40.0
    for tick in range(25):
        loop._handwash(frame, CAMERA, start + tick * 0.2, False)
    assert "sink" in loop.washes.washes
    loop._step({**CAMERA, "stream_url": ""})
    assert loop.washes.washes == {}
    loop._handwash(frame, {**CAMERA, "zones": [{**SINK, "polygon": [[0.0, 0.0], [0.01, 0.0], [0.01, 0.01]]}]}, start + 600.0, False)
    assert api.opened == []


def test_an_uploaded_video_starting_over_ends_the_wash_there():
    loop = CameraLoop("cam-wash", Settings(ai_mode="REAL", model_path="/nowhere", handwash_skip_steps=""), threading.Event())
    api = FakeApi()
    loop.api = api
    loop.gestures = DemoHandwashDetector()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    start = 7000.0 * WASH_PERIOD_S + 40.0  # the short wash: three steps, then the hands leave
    for tick in range(60):
        loop._handwash(frame, CAMERA, start + tick * 0.2, False)
    assert api.opened == []
    loop._handwash(frame, CAMERA, start + 12.0, False, restarted=True)
    assert len(api.opened) == 1 and api.closed[0][0] == "inc-1"


def test_without_a_hand_wash_rule_the_gesture_model_is_never_loaded():
    loop = CameraLoop("cam-wash", Settings(ai_mode="DEMO"), threading.Event())
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert loop._handwash(frame, {**CAMERA, "rules": []}, 0.0, False) == []
    assert loop.gestures is None


def test_skipped_steps_are_not_checked():
    loop = CameraLoop("cam-wash", Settings(ai_mode="DEMO", handwash_skip_steps="fingers, palms"), threading.Event())
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    tracks = loop._handwash(frame, CAMERA, 7000.0 * WASH_PERIOD_S + 0.5, False)
    assert [check["item"] for check in tracks[0]["checks"]] == ["step2", "step3", "step5", "step6"]
    assert isinstance(loop.gestures, DemoHandwashDetector)

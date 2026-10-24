import threading

import numpy as np

from app.config import Settings
from app.detectors import DemoHandwashDetector
from app.drawing import FINGERTIP_COLOR, SKELETON_COLOR, annotate
from app.handpose import HandPose, palm_anchors
from app.runtime import CameraLoop
from app.scenes import WASH_PERIOD_S


class _Input:
    name = "input_1"


class _Session:
    def __init__(self, outputs):
        self.outputs = outputs

    def get_inputs(self):
        return [_Input()]

    def run(self, names, feeds):
        return self.outputs


# A 400x400 image fills the 192 px palm input exactly: 1 model pixel is 400/192 image pixels.
PALM_CELL = (12 * 24 + 12) * 2  # the anchor at the centre of cell (12, 12) of the 24x24 grid
# Palm points in model pixels from the anchor: the wrist below, the middle finger's base above, so the hand points up.
PALM_POINTS = [(0, 20), (-15, 0), (0, -20), (15, 0), (-10, 10), (10, 10), (0, 0)]


def _pose(confidence: float = 0.95) -> HandPose:
    pose = object.__new__(HandPose)
    pose.anchors, pose.max_hands = palm_anchors(), 2
    deltas = np.zeros((1, 2016, 18), dtype=np.float32)
    deltas[0, PALM_CELL, 2:4] = [40, 40]
    deltas[0, PALM_CELL, 4:] = np.array(PALM_POINTS, dtype=np.float32).reshape(-1)
    scores = np.full((1, 2016, 1), -10.0, dtype=np.float32)
    scores[0, PALM_CELL, 0] = 10.0
    pose.palm = _Session([deltas, scores])
    # Every joint at the centre of the landmark model's 224 px input.
    pose.joints = _Session([np.full((1, 63), 112.0, dtype=np.float32), np.array([[confidence]], dtype=np.float32), np.zeros((1, 1)), np.zeros((1, 63))])
    return pose


def test_anchors_match_the_palm_detector_grid():
    anchors = palm_anchors()
    assert anchors.shape == (2016, 2)
    assert np.allclose(anchors[0], [0.5 / 24, 0.5 / 24]) and np.allclose(anchors[1], anchors[0])
    assert np.allclose(anchors[1152], [0.5 / 12, 0.5 / 12])


def test_joints_come_back_in_image_pixels():
    hands = _pose().find(np.zeros((400, 400, 3), dtype=np.uint8))
    assert len(hands) == 1 and hands[0].shape == (21, 2)
    # The palm points' box is centred on the anchor, 208 px; the hand crop is moved up 0.4 of the box height (83 px).
    centre = 12.5 / 24 * 400
    assert np.allclose(hands[0], [centre, centre - 0.4 * 40 / 192 * 400], atol=2.0)


def test_a_hand_the_landmark_model_doubts_is_dropped():
    assert _pose(confidence=0.5).find(np.zeros((400, 400, 3), dtype=np.uint8)) == []


def test_hands_are_drawn_as_a_skeleton_with_scanner_corners():
    # A hand spread wide on a black frame: wrist at the bottom, each finger a straight line going up from its base.
    joints = np.zeros((21, 2), dtype=np.float32)
    joints[0] = [150, 280]
    for finger, base_x in enumerate((70, 110, 150, 190, 230)):
        for step in range(4):
            joints[1 + 4 * finger + step] = [base_x, 220 - 40 * step]
    track = {"track_id": "W1", "class_name": "hands", "wash_s": 4, "checks": [], "bbox_xyxy": [40, 60, 260, 290], "joints": [joints]}
    drawn = annotate(np.zeros((300, 300, 3), dtype=np.uint8), [], [track])
    # The index finger's bone between its 2nd and 3rd joints, away from the dots, then its tip.
    assert (np.abs(drawn[150:170, 110].astype(int) - SKELETON_COLOR).sum(axis=1) < 40).any()
    assert (np.abs(drawn[100, 104:116].astype(int) - FINGERTIP_COLOR).sum(axis=1) < 40).any()
    # Corners, not a full box: the middle of the box's left edge stays dark.
    assert drawn[175, 40].max() < 60


class _NoPeople:
    calls = 0

    def detect(self, frame, zones, now, hold_inside):
        self.calls += 1
        return []


def test_a_camera_with_only_hand_wash_rules_skips_the_person_detector():
    sink = {"id": "sink", "name": "Sink", "zone_type": "HANDWASH_STATION", "polygon": [[0.25, 0.0], [0.75, 0.0], [0.75, 1.0], [0.25, 1.0]]}
    wash = {"id": "rule", "zone_id": "sink", "condition_type": "HANDWASH_STEPS_MISSING", "event_type": "HANDWASH_INCOMPLETE", "min_duration_ms": 3000, "cooldown_ms": 30000, "grace_ms": 1000, "severity": "MEDIUM", "enabled": True}
    camera = {"id": "cam", "factory_id": "f", "stream_type": "FILE", "stream_url": "", "enabled": True, "ai_fps": 10, "simulate_pending": False, "zones": [sink], "rules": [wash]}
    loop = CameraLoop("cam", Settings(ai_mode="DEMO", heartbeat_every_s=60), threading.Event())
    loop.store.put_bytes = lambda *args, **kwargs: None
    loop.api.heartbeat = lambda *args, **kwargs: None
    loop.detector = _NoPeople()
    loop._step(camera)
    assert loop.detector.calls == 0
    loop._step({**camera, "rules": [wash, {**wash, "id": "people", "condition_type": "PERSON_INSIDE"}]})
    assert loop.detector.calls == 1


class _FakePose:
    def find(self, image):
        self.seen = image.shape
        return [np.array([[10.0 + k, 20.0 + k] for k in range(21)])]


def test_joints_are_found_in_the_sink_area_and_moved_into_the_frame():
    sink = {"id": "sink", "name": "Sink", "zone_type": "HANDWASH_STATION", "polygon": [[0.25, 0.0], [0.75, 0.0], [0.75, 1.0], [0.25, 1.0]]}
    rule = {"id": "rule", "zone_id": "sink", "condition_type": "HANDWASH_STEPS_MISSING", "event_type": "HANDWASH_INCOMPLETE", "min_duration_ms": 3000, "cooldown_ms": 30000, "grace_ms": 1000, "severity": "MEDIUM", "enabled": True}
    loop = CameraLoop("cam", Settings(ai_mode="REAL", model_path="/nowhere"), threading.Event())
    loop.gestures, loop.hand_pose = DemoHandwashDetector(), _FakePose()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    tracks = loop._handwash(frame, {"id": "cam", "zones": [sink], "rules": [rule]}, 7000.0 * WASH_PERIOD_S + 0.5, False)
    assert loop.hand_pose.seen == (720, 640, 3)
    joints = tracks[0]["joints"][0]
    assert np.allclose(joints[0], [320 + 10, 20]) and np.allclose(joints[20], [320 + 30, 40])
    x1, y1, x2, y2 = tracks[0]["bbox_xyxy"]
    assert x1 < 330 and x2 > 350 and y1 < 20 and y2 > 40

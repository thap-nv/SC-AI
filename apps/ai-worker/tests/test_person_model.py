import numpy as np

from app.detectors import HogPersonDetector, YoloxDetector, _letterbox, join_cut, tile_spans


def test_yolox_preprocessing_preserves_bgr_and_top_left_padding():
    image = np.full((100, 200, 3), (10, 80, 230), dtype=np.uint8)
    padded, scale, x, y = _letterbox(image, 416)
    assert scale == 2.08
    assert (x, y) == (0, 0)
    np.testing.assert_array_equal(padded[0, 0], [10, 80, 230])
    np.testing.assert_array_equal(padded[207, 415], [10, 80, 230])
    np.testing.assert_array_equal(padded[208, 0], [114, 114, 114])
    assert padded.dtype == np.float32


def test_a_wide_frame_is_detected_in_overlapping_frame_high_squares():
    assert tile_spans(1280, 720) == [(0, 720), (560, 1280)]
    assert tile_spans(1920, 720) == [(0, 720), (600, 1320), (1200, 1920)]
    assert tile_spans(800, 720) == [(0, 800)]


def box(kind: str, score: float, xyxy: list[float], tile: int, cut: bool) -> dict:
    return {"class_name": kind, "confidence": score, "bbox_xyxy": xyxy, "tile": tile, "cut": cut}


def test_an_object_cut_by_the_shared_edge_is_joined_with_the_rest_of_it():
    # The rear of a car cut at the left square's right edge, and the whole car seen by the right square.
    rear = box("vehicle", 0.8, [638.0, 397.0, 719.0, 485.0], 0, True)
    whole = box("vehicle", 0.9, [632.0, 380.0, 925.0, 536.0], 1, False)
    joined = join_cut([rear, whole])
    assert len(joined) == 1
    assert joined[0]["bbox_xyxy"] == [632.0, 380.0, 925.0, 536.0] and joined[0]["confidence"] == 0.9
    # A car across the whole overlap, cut in both squares.
    left = box("vehicle", 0.7, [500.0, 300.0, 719.0, 450.0], 0, True)
    right = box("vehicle", 0.6, [560.0, 305.0, 800.0, 445.0], 1, True)
    assert [item["bbox_xyxy"] for item in join_cut([left, right])] == [[500.0, 300.0, 800.0, 450.0]]


def test_people_side_by_side_at_the_shared_edge_stay_apart():
    cut = box("person", 0.7, [690.0, 200.0, 719.0, 320.0], 0, True)
    neighbour = box("person", 0.8, [712.0, 205.0, 760.0, 325.0], 1, False)
    other_class = box("vehicle", 0.9, [680.0, 190.0, 760.0, 330.0], 1, False)
    assert len(join_cut([cut, neighbour, other_class])) == 3


def test_yolox_runs_each_square_and_maps_boxes_back_to_the_frame():
    detector = YoloxDetector.__new__(YoloxDetector)
    detector.tiles = True
    seen = []

    def infer(image, offset_x):
        seen.append((image.shape[1], offset_x))
        if offset_x == 0:
            return [{"class_name": "person", "confidence": 0.8, "bbox_xyxy": [430.0, 240.0, 465.0, 305.0]}, {"class_name": "vehicle", "confidence": 0.7, "bbox_xyxy": [638.0, 397.0, 719.0, 485.0]}]
        return [{"class_name": "person", "confidence": 0.75, "bbox_xyxy": [1000.0, 300.0, 1040.0, 400.0]}, {"class_name": "vehicle", "confidence": 0.9, "bbox_xyxy": [632.0, 380.0, 925.0, 536.0]}]

    detector._infer = infer
    found = detector.detect(np.zeros((720, 1280, 3), dtype=np.uint8), [], 0, False)
    assert seen == [(720, 0), (720, 560)]
    assert sorted(item["bbox_xyxy"][0] for item in found) == [430.0, 632.0, 1000.0]
    assert all("tile" not in item and "cut" not in item for item in found)


def test_hog_detection_does_not_require_visible_skin_or_face():
    # A valid full-body HOG result must survive even on a back-facing crop.
    class StubHog:
        def detectMultiScale(self, image, **kwargs):
            return [(100, 30, 64, 128)], [0.8]

    detector = HogPersonDetector.__new__(HogPersonDetector)
    detector.hog = StubHog()
    image = np.full((360, 640, 3), 40, dtype=np.uint8)
    people = detector.detect(image, [], 0, False)
    assert len(people) == 1
    assert people[0]['bbox_xyxy'] == [100, 30, 164, 158]


def test_tracker_ignores_a_one_frame_flicker_and_confirms_a_steady_person():
    from app.tracker import PersonTracker

    tracker = PersonTracker(frame_rate=10)
    person = {"class_id": 0, "confidence": 0.9, "bbox_xyxy": [100.0, 100.0, 160.0, 300.0]}
    flicker = {"class_id": 0, "confidence": 0.9, "bbox_xyxy": [400.0, 100.0, 460.0, 300.0]}
    assert tracker.update([person, flicker]) == []
    assert tracker.update([person]) == []
    assert tracker.update([person]) == []
    confirmed = tracker.update([person])
    assert [track["bbox_xyxy"][0] for track in confirmed] == [100.0]
    assert all(int(track["track_id"]) >= 0 for track in confirmed)

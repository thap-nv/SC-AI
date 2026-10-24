import numpy as np

from app.detectors import DemoPPEClassifier, decode_boxes, ppe_from_boxes

# A 100x250 person crop.
WIDTH, HEIGHT = 100, 250


def test_nx6_rows_are_assigned_to_the_matching_band():
    rows = np.array(
        [
            [35, 0, 65, 25, 0.9, 1],  # no helmet, on the head
            [20, 60, 80, 150, 0.8, 2],  # vest, on the torso
            [30, 230, 70, 250, 0.7, 5],  # no safety shoes, at the feet
            [40, 230, 60, 250, 0.95, 6],  # a mask at the feet is not a mask on this person
        ],
        dtype=np.float32,
    )
    result = ppe_from_boxes(decode_boxes(rows[None], 8, WIDTH, HEIGHT), WIDTH, HEIGHT)
    assert result["helmet"] == ("NO", 0.9)
    assert result["clothing"] == ("YES", 0.8)
    assert result["shoes"] == ("NO", 0.7)
    assert result["mask"] == ("UNKNOWN", 0.0)


def test_the_stronger_box_wins_between_worn_and_missing():
    rows = np.array([[35, 0, 65, 25, 0.5, 0], [35, 0, 65, 25, 0.8, 1]], dtype=np.float32)
    assert ppe_from_boxes(decode_boxes(rows, 8, WIDTH, HEIGHT), WIDTH, HEIGHT)["helmet"] == ("NO", 0.8)


def test_yolo_head_is_decoded_through_the_letterbox():
    # One anchor in a 64x64 letterbox of a 32x64 crop: gain 1, 16 pixels of padding left and right.
    head = np.zeros((1, 12, 3), dtype=np.float32)
    head[0, :4, 0] = [32, 4, 8, 8]
    head[0, 4 + 0, 0] = 0.9  # helmet worn
    head[0, :4, 1] = [32, 60, 8, 8]
    head[0, 4 + 5, 1] = 0.2  # below the threshold
    boxes = decode_boxes(head, 8, 64, 64, 1.0, 1.0, 16.0, 0.0)
    assert len(boxes) == 1
    class_id, score, box = boxes[0]
    assert class_id == 0 and abs(score - 0.9) < 1e-6
    assert box == [12.0, 0.0, 20.0, 8.0]
    result = ppe_from_boxes(boxes, 32, 64)
    assert result["helmet"][0] == "YES"
    assert result["shoes"] == ("UNKNOWN", 0.0)


def test_demo_outfit_is_returned_and_missing_items_stay_unknown():
    result = DemoPPEClassifier().classify(None, {"outfit": {"helmet": "NO", "clothing": "YES"}})
    assert result["helmet"][0] == "NO"
    assert result["clothing"][0] == "YES"
    assert result["shoes"] == ("UNKNOWN", 0.0)
    assert DemoPPEClassifier().classify(None, {})["mask"] == ("UNKNOWN", 0.0)

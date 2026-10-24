import numpy as np

from app.detectors import ForkliftDetector, with_forklifts


def vehicle(kind: str, score: float, box: list[float]) -> dict:
    return {"class_name": "vehicle", "class_id": 2, "vehicle_type": kind, "confidence": score, "bbox_xyxy": box}


FORKLIFT = vehicle("forklift", 0.9, [100.0, 200.0, 260.0, 380.0])


def test_a_truck_on_a_forklift_gives_way_and_the_driver_stays():
    driver = {"class_name": "person", "class_id": 0, "confidence": 0.6, "bbox_xyxy": [150.0, 210.0, 200.0, 330.0]}
    merged = with_forklifts([vehicle("truck", 0.5, [105.0, 195.0, 255.0, 385.0]), driver], [FORKLIFT])
    assert [item["vehicle_type"] for item in merged if item["class_name"] == "vehicle"] == ["forklift"]
    assert driver in merged


def test_a_sure_car_keeps_its_box_and_a_forklift_read_on_it_is_dropped():
    car = vehicle("car", 0.9, [500.0, 300.0, 800.0, 450.0])
    on_car = vehicle("forklift", 0.89, [510.0, 305.0, 790.0, 445.0])
    # The car and the forklift behind it boxed as one forklift: most of the car lies inside it.
    car_and_forklift = vehicle("forklift", 0.6, [480.0, 150.0, 760.0, 440.0])
    merged = with_forklifts([car], [on_car, car_and_forklift, FORKLIFT])
    assert [item["vehicle_type"] for item in merged] == ["car", "forklift"]
    assert merged[1] is FORKLIFT


def test_a_weak_car_read_on_a_forklift_is_the_forklift_misread():
    merged = with_forklifts([vehicle("car", 0.36, [102.0, 205.0, 250.0, 375.0])], [FORKLIFT])
    assert merged == [FORKLIFT]


def test_without_forklifts_the_detections_are_unchanged():
    detections = [vehicle("truck", 0.7, [0.0, 0.0, 50.0, 50.0])]
    assert with_forklifts(detections, []) == detections


class StubSession:
    def __init__(self, output):
        self.output = output

    def run(self, names, feeds):
        assert feeds["images"].shape == (1, 3, 384, 640)
        return [self.output]


def test_forklift_boxes_come_back_in_frame_pixels_and_people_are_left_out():
    detector = ForkliftDetector.__new__(ForkliftDetector)
    detector.input_name, detector.input_h, detector.input_w = "images", 384, 640
    detector.forklift_class, detector.classes, detector.threshold = 0, 2, 0.3
    # A 1280x720 frame letterboxes into 640x384 at half size with 12 rows of padding above and below.
    head = np.zeros((1, 6, 3), dtype=np.float32)
    head[0, :4, 0] = [100, 112, 40, 60]
    head[0, 4, 0] = 0.8
    head[0, :4, 1] = [300, 200, 20, 60]
    head[0, 5, 1] = 0.9  # a person
    head[0, :4, 2] = [500, 200, 40, 40]
    head[0, 4, 2] = 0.1  # below the threshold
    detector.session = StubSession(head)
    found = detector.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
    assert len(found) == 1
    assert found[0]["vehicle_type"] == "forklift" and found[0]["class_name"] == "vehicle"
    np.testing.assert_allclose(found[0]["bbox_xyxy"], [160.0, 140.0, 240.0, 260.0])

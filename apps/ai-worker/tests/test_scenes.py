import numpy as np

from app.detectors import DemoDetector
from app.scenes import FULL_KIT, PPE_CREW, UNREADABLE, scripted_objects
from app.zone_engine import bbox_foot_in_polygon, point_in_polygon

RESTRICTED = {
    "zone_type": "RESTRICTED_AREA",
    "polygon": [[0.48, 0.12], [0.92, 0.10], [0.94, 0.62], [0.46, 0.66]],
}
FLOOR = {
    "zone_type": "PPE_ZONE",
    "polygon": [[0.04, 0.42], [0.96, 0.40], [0.98, 0.90], [0.02, 0.92]],
}


def _boxes_overlap(a: list[float], b: list[float]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def test_walker_starts_outside_and_stands_inside():
    outside = scripted_objects([RESTRICTED], 0.0, False)[0]
    inside = scripted_objects([RESTRICTED], 18.0, False)[0]
    assert point_in_polygon(RESTRICTED["polygon"], outside["nx"], outside["ny"]) is False
    assert point_in_polygon(RESTRICTED["polygon"], inside["nx"], inside["ny"]) is True
    assert inside["outfit"] == FULL_KIT


def test_hold_inside_places_the_walker_in_the_zone():
    person = scripted_objects([RESTRICTED], 0.0, True)[0]
    assert point_in_polygon(RESTRICTED["polygon"], person["nx"], person["ny"]) is True


def test_demo_person_box_stands_in_the_zone():
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    person = DemoDetector().detect(frame, [RESTRICTED], 0.0, True)[0]
    x1, y1, x2, y2 = person["bbox_xyxy"]
    assert bbox_foot_in_polygon(RESTRICTED["polygon"], (x1 / 960, y1 / 540, x2 / 960, y2 / 540)) is True


def test_ppe_floor_has_one_worker_per_outfit_all_inside_on_simulate():
    crew = scripted_objects([FLOOR], 0.0, True)
    assert [person["outfit"] for person in crew] == PPE_CREW
    assert all(point_in_polygon(FLOOR["polygon"], person["nx"], person["ny"]) for person in crew)


def test_ppe_crew_boxes_never_overlap_while_walking():
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    for second in range(0, 36):
        boxes = [person["bbox_xyxy"] for person in DemoDetector().detect(frame, [FLOOR], float(second), False)]
        assert len(boxes) == len(PPE_CREW)
        for index, box in enumerate(boxes):
            assert not any(_boxes_overlap(box, other) for other in boxes[index + 1 :]), second


def test_unreadable_worker_stands_still_and_the_others_come_and_go():
    early = scripted_objects([FLOOR], 0.0, False)
    late = scripted_objects([FLOOR], 18.0, False)
    unreadable = [person for person in early + late if person["outfit"] is UNREADABLE]
    assert len({(person["nx"], person["ny"]) for person in unreadable}) == 1
    walkers = [index for index, outfit in enumerate(PPE_CREW) if outfit is not UNREADABLE]
    assert any((early[index]["nx"], early[index]["ny"]) != (late[index]["nx"], late[index]["ny"]) for index in walkers)


def test_restricted_area_demo_has_a_walker_a_car_coming_and_going_and_a_parked_forklift():
    early = scripted_objects([RESTRICTED], 0.0, False)
    assert [(item["class_name"], item.get("vehicle_type")) for item in early] == [("person", None), ("vehicle", "car"), ("vehicle", "forklift")]
    forklift = early[2]
    assert point_in_polygon(RESTRICTED["polygon"], forklift["nx"], forklift["ny"]) is True
    held = scripted_objects([RESTRICTED], 0.0, True)
    assert all(point_in_polygon(RESTRICTED["polygon"], item["nx"], item["ny"]) for item in held)
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    detected = DemoDetector().detect(frame, [RESTRICTED], 0.0, True)
    assert [item["class_id"] for item in detected] == [0, 2, 2]

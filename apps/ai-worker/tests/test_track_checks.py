import numpy as np

from app.drawing import CHECK_COLORS, NO_RULE_COLOR, _tag, track_color, track_tag
from app.runtime import track_checks

RESTRICTED = {
    "id": "zone-restricted",
    "name": "Restricted Zone A",
    "zone_type": "RESTRICTED_AREA",
    "polygon": [[0.48, 0.12], [0.92, 0.10], [0.94, 0.62], [0.46, 0.66]],
}
FLOOR = {
    "id": "zone-floor",
    "name": "Workshop floor",
    "zone_type": "PPE_ZONE",
    "polygon": [[0.0, 0.0], [0.4, 0.0], [0.4, 1.0], [0.0, 1.0]],
}
ZONES = [RESTRICTED, FLOOR]

FEET_IN_RESTRICTED = (0.6, 0.2, 0.7, 0.5)
FEET_ON_FLOOR = (0.1, 0.2, 0.2, 0.8)
FEET_IN_NO_ZONE = (0.6, 0.6, 0.7, 0.9)
KITTED = {"helmet": "YES", "clothing": "YES", "mask": "YES"}


def rule(zone: dict, condition: str, enabled: bool = True) -> dict:
    return {"id": f"{zone['id']}-{condition}", "zone_id": zone["id"], "condition_type": condition, "enabled": enabled}


def test_person_in_restricted_zone_is_a_violation_even_with_full_ppe():
    checks = track_checks([rule(RESTRICTED, "PERSON_INSIDE")], ZONES, FEET_IN_RESTRICTED, KITTED)
    assert checks == [{"item": "zone", "text": "In Restricted Zone A", "state": "violation"}]
    assert track_color({"class_name": "person", "checks": checks}) == CHECK_COLORS["violation"]


def test_ppe_is_reported_only_where_a_ppe_rule_applies():
    rules = [rule(RESTRICTED, "PERSON_INSIDE"), rule(FLOOR, "HELMET_MISSING")]
    assert track_checks(rules, ZONES, FEET_ON_FLOOR, {**KITTED, "helmet": "NO"}) == [{"item": "helmet", "text": "Helmet: No", "state": "violation"}]
    assert track_checks(rules, ZONES, FEET_ON_FLOOR, KITTED) == [{"item": "helmet", "text": "Helmet: Yes", "state": "ok"}]
    assert track_checks(rules, ZONES, FEET_ON_FLOOR, {**KITTED, "helmet": "UNKNOWN"}) == [{"item": "helmet", "text": "Helmet: Unknown", "state": "unknown"}]
    assert track_checks(rules, ZONES, FEET_IN_NO_ZONE, {**KITTED, "helmet": "NO"}) == []


def test_each_ppe_rule_on_the_floor_gives_one_check_and_one_tag_letter():
    rules = [rule(FLOOR, condition) for condition in ("HELMET_MISSING", "CLOTHING_MISSING", "MASK_MISSING")]
    checks = track_checks(rules, ZONES, FEET_ON_FLOOR, {**KITTED, "clothing": "NO", "mask": "UNKNOWN"})
    assert checks == [
        {"item": "helmet", "text": "Helmet: Yes", "state": "ok"},
        {"item": "clothing", "text": "Clothing: No", "state": "violation"},
        {"item": "mask", "text": "Mask: Unknown", "state": "unknown"},
    ]
    person = {"class_name": "person", "track_id": "4", "checks": checks}
    assert track_tag(person) == [
        ("#4", CHECK_COLORS["violation"]),
        ("H", CHECK_COLORS["ok"]),
        ("C", CHECK_COLORS["violation"]),
        ("M", CHECK_COLORS["unknown"]),
    ]


def test_disabled_rules_are_ignored():
    assert track_checks([rule(RESTRICTED, "PERSON_INSIDE", enabled=False)], ZONES, FEET_IN_RESTRICTED, KITTED) == []


def test_box_colour_follows_the_worst_check():
    ok = {"item": "helmet", "text": "Helmet: Yes", "state": "ok"}
    unknown = {"item": "mask", "text": "Mask: Unknown", "state": "unknown"}
    violation = {"item": "zone", "text": "In Restricted Zone A", "state": "violation"}
    assert track_color({"class_name": "person", "checks": [ok, violation]}) == CHECK_COLORS["violation"]
    assert track_color({"class_name": "person", "checks": [ok, unknown]}) == CHECK_COLORS["unknown"]
    assert track_color({"class_name": "person", "checks": [ok]}) == CHECK_COLORS["ok"]
    assert track_color({"class_name": "person", "checks": []}) == NO_RULE_COLOR


def test_person_outside_every_rule_gets_only_an_id_and_forklifts_keep_their_name():
    assert track_tag({"class_name": "person", "track_id": "2", "checks": []}) == [("#2", NO_RULE_COLOR)]
    assert track_tag({"class_name": "vehicle", "vehicle_type": "forklift", "track_id": "9"})[0][0] == "Forklift 9"


def test_tags_of_people_side_by_side_do_not_cover_each_other():
    canvas = np.zeros((400, 600, 3), dtype=np.uint8)
    taken: list = []
    segments = [("#1", CHECK_COLORS["ok"]), ("H", CHECK_COLORS["ok"]), ("C", CHECK_COLORS["violation"])]
    for _ in range(3):
        _tag(canvas, segments, 100, 120, 380, taken)
    assert len(taken) == 3
    for index, box in enumerate(taken):
        for other in taken[index + 1 :]:
            assert not (box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3])


def test_vehicles_in_a_restricted_area_read_by_type():
    rules = [rule(RESTRICTED, "PERSON_INSIDE"), rule(RESTRICTED, "VEHICLE_INSIDE")]
    car = track_checks(rules, ZONES, FEET_IN_RESTRICTED, {}, "vehicle", vehicle_type="car")
    assert car == [{"item": "zone", "text": "In Restricted Zone A", "state": "violation"}]
    forklift = track_checks(rules, ZONES, FEET_IN_RESTRICTED, {}, "vehicle", vehicle_type="forklift")
    assert forklift == [{"item": "zone", "text": "Forklift allowed", "state": "ok"}]
    assert track_checks(rules, ZONES, FEET_IN_RESTRICTED, {}, "vehicle")[0]["state"] == "unknown"
    driver = track_checks(rules, ZONES, FEET_IN_RESTRICTED, KITTED, "person", in_vehicle=True)
    assert driver == [{"item": "zone", "text": "In a vehicle", "state": "ok"}]
    car_tag = track_tag({"class_name": "vehicle", "vehicle_type": "car", "track_id": "12", "checks": car})
    assert car_tag == [("Car 12", CHECK_COLORS["violation"])]
    assert track_tag({"class_name": "vehicle", "vehicle_type": "forklift", "track_id": "5", "checks": forklift}) == [("Forklift 5", CHECK_COLORS["ok"])]

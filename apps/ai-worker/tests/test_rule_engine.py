from app.rule_engine import Observation, RuleConfig, RuleEngine


def rule(**overrides) -> RuleConfig:
    base = dict(
        id="rule-1",
        zone_id="zone-1",
        condition_type="PERSON_INSIDE",
        event_type="RESTRICTED_AREA_INTRUSION",
        severity="HIGH",
        min_duration_s=2.0,
        cooldown_s=10.0,
        grace_s=1.0,
    )
    base.update(overrides)
    return RuleConfig(**base)


KITTED = {"helmet": "YES", "clothing": "YES", "shoes": "YES", "mask": "YES"}


def see(engine, config, t, inside=True, ppe=None, track="7", klass="person"):
    return engine.update(
        config,
        Observation(
            track_id=track,
            timestamp=t,
            inside=inside,
            ppe={**KITTED, **(ppe or {})},
            confidence=0.9,
            bbox=(0.4, 0.4, 0.5, 0.7),
            class_name=klass,
        ),
    )


def test_duration_opens_one_incident_and_suppresses_duplicates():
    engine = RuleEngine()
    config = rule()
    assert see(engine, config, 0.0) == []
    opened = see(engine, config, 2.0)
    assert len(opened) == 1
    assert opened[0].kind == "open"
    assert opened[0].started_at == 0.0
    engine.attach_incident("rule-1", "7", "inc-1")
    assert see(engine, config, 2.5) == []
    assert see(engine, config, 4.0) == []


def test_brief_loss_does_not_reset_the_timer():
    engine = RuleEngine()
    config = rule()
    see(engine, config, 0.0)
    see(engine, config, 1.0)
    assert see(engine, config, 1.5, inside=False) == []
    opened = see(engine, config, 2.0)
    assert len(opened) == 1
    assert opened[0].kind == "open"


def test_long_gap_resets_pending_duration():
    engine = RuleEngine()
    config = rule(grace_s=0.4)
    see(engine, config, 0.0)
    assert see(engine, config, 0.5, inside=False) == []
    assert see(engine, config, 1.0) == []
    assert see(engine, config, 2.9) == []
    opened = see(engine, config, 3.0)
    assert len(opened) == 1
    assert opened[0].started_at == 1.0


def test_leave_closes_then_cooldown_blocks_reentry():
    engine = RuleEngine()
    config = rule()
    see(engine, config, 0.0)
    see(engine, config, 2.0)
    engine.attach_incident("rule-1", "7", "inc-1")
    see(engine, config, 4.0)
    closed = see(engine, config, 5.5, inside=False)
    assert len(closed) == 1
    assert closed[0].kind == "close"
    assert closed[0].incident_id == "inc-1"
    assert closed[0].ended_at == 4.0
    assert see(engine, config, 6.0) == []
    assert see(engine, config, 16.0) == []
    opened = see(engine, config, 18.0)
    assert len(opened) == 1
    assert opened[0].kind == "open"


def test_unknown_ppe_does_not_violate():
    engine = RuleEngine()
    config = rule(condition_type="HELMET_MISSING", event_type="HELMET_VIOLATION")
    assert see(engine, config, 0.0, ppe={"helmet": "UNKNOWN"}) == []
    assert see(engine, config, 5.0, ppe={"helmet": "UNKNOWN"}) == []
    assert see(engine, config, 0.0, ppe={"helmet": "YES"}, track="8") == []
    assert see(engine, config, 3.0, ppe={"helmet": "YES"}, track="8") == []


def test_each_missing_item_opens_only_its_own_rule():
    conditions = {
        "helmet": ("HELMET_MISSING", "HELMET_VIOLATION"),
        "clothing": ("CLOTHING_MISSING", "CLOTHING_VIOLATION"),
        "shoes": ("SHOES_MISSING", "SHOES_VIOLATION"),
        "mask": ("MASK_MISSING", "MASK_VIOLATION"),
    }
    for missing in conditions:
        engine = RuleEngine()
        for item, (condition, event_type) in conditions.items():
            config = rule(id=f"rule-{item}", condition_type=condition, event_type=event_type)
            see(engine, config, 0.0, ppe={missing: "NO"})
            opened = see(engine, config, 2.0, ppe={missing: "NO"})
            if item == missing:
                assert [action.event_type for action in opened] == [event_type]
            else:
                assert opened == []


def test_missing_ppe_outside_the_zone_does_not_violate():
    engine = RuleEngine()
    config = rule(condition_type="MASK_MISSING", event_type="MASK_VIOLATION")
    assert see(engine, config, 0.0, inside=False, ppe={"mask": "NO"}) == []
    assert see(engine, config, 5.0, inside=False, ppe={"mask": "NO"}) == []


def test_forklift_track_does_not_open_person_rule():
    engine = RuleEngine()
    config = rule()
    assert see(engine, config, 0.0, klass="forklift") == []
    assert see(engine, config, 5.0, klass="forklift") == []


def test_missing_track_closes_after_grace():
    engine = RuleEngine()
    config = rule()
    see(engine, config, 0.0)
    see(engine, config, 2.0)
    engine.attach_incident("rule-1", "7", "inc-9")
    assert engine.expire_missing({config.id: config}, 2.5, set()) == []
    closed = engine.expire_missing({config.id: config}, 4.5, set())
    assert len(closed) == 1
    assert closed[0].kind == "close"


def vehicle(engine, config, t, vehicle_type, track="v1", inside=True):
    return engine.update(config, Observation(track_id=track, timestamp=t, inside=inside, confidence=0.9, class_name="vehicle", vehicle_type=vehicle_type))


def test_a_car_in_a_restricted_area_opens_and_a_forklift_does_not():
    config = rule(condition_type="VEHICLE_INSIDE", event_type="VEHICLE_IN_RESTRICTED_AREA", min_duration_s=1.0)
    engine = RuleEngine()
    vehicle(engine, config, 0.0, "car")
    assert [action.kind for action in vehicle(engine, config, 1.0, "car")] == ["open"]
    for allowed_or_unknown in ("forklift", ""):
        engine = RuleEngine()
        vehicle(engine, config, 0.0, allowed_or_unknown)
        assert vehicle(engine, config, 5.0, allowed_or_unknown) == []


def test_vehicle_rules_ignore_people_and_person_rules_ignore_vehicles():
    engine = RuleEngine()
    cars = rule(condition_type="VEHICLE_INSIDE", event_type="VEHICLE_IN_RESTRICTED_AREA", min_duration_s=0.0)
    people = rule(id="rule-2", min_duration_s=0.0)
    assert see(engine, cars, 0.0) == []
    assert vehicle(engine, people, 0.0, "car") == []


def test_a_person_riding_a_vehicle_does_not_open_the_person_rule():
    engine = RuleEngine()
    config = rule(min_duration_s=0.0)
    driver = Observation(track_id="d1", timestamp=0.0, inside=True, confidence=0.9, in_vehicle=True)
    assert engine.update(config, driver) == []
    walker = Observation(track_id="w1", timestamp=0.0, inside=True, confidence=0.9)
    assert [action.kind for action in engine.update(config, walker)] == ["open"]

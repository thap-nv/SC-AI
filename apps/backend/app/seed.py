from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AIModel, AIModelDeployment, Camera, Factory, Incident, OperatorFeedback, Rule, User, Zone
from app.security import hash_password
from app.services import delete_camera_data

FACTORY_CODE = "factory-poc"
FACTORY_NAME = "Factory POC"
WORKSHOP_CAMERA = "CAM-WORKSHOP-01"
WORKSHOP_FLOOR = [[0.04, 0.42], [0.96, 0.40], [0.98, 0.90], [0.02, 0.92]]
RESTRICTED_CAMERA = "CAM-RESTRICTED-01"
# A placeholder lane in the middle of the frame. Redraw it on the uploaded video.
RESTRICTED_LANE = [[0.34, 0.38], [0.60, 0.38], [0.80, 0.92], [0.22, 0.92]]
# Nobody may walk in. Vehicles may not drive in, except forklifts.
RESTRICTED_RULES = [
    ("No entry for people", "RESTRICTED_AREA_INTRUSION", "PERSON_INSIDE", "HIGH"),
    ("No entry for vehicles except forklifts", "VEHICLE_IN_RESTRICTED_AREA", "VEHICLE_INSIDE", "HIGH"),
]
HANDWASH_CAMERA = "CAM-HANDWASH-01"
# A placeholder sink in the middle of the frame. Redraw it on the uploaded video, around where hands are washed.
HANDWASH_SINK = [[0.30, 0.15], [0.70, 0.15], [0.70, 0.65], [0.30, 0.65]]
# Checked once per wash. The rule's minimum duration is how long each step must be seen.
HANDWASH_RULE = ("WHO 6-step hand washing", "HANDWASH_INCOMPLETE", "HANDWASH_STEPS_MISSING", "MEDIUM")
HANDWASH_MODEL = "handwash-detector"
# name, event type, condition, severity. Safety shoes are left out: they cannot be told apart on CCTV without a trained model.
PPE_RULES = [
    ("Helmet required", "HELMET_VIOLATION", "HELMET_MISSING", "HIGH"),
    ("Protective clothing required", "CLOTHING_VIOLATION", "CLOTHING_MISSING", "HIGH"),
    ("Mask required", "MASK_VIOLATION", "MASK_MISSING", "MEDIUM"),
]
MODELS = [
    ("person-detector", "v1.0", "PERSON_DETECTOR", "ACTIVE", "OpenCV HOG people detector (Apache-2.0). Used in REAL mode when person.onnx is not mounted. DEMO mode uses a scripted person instead."),
    (
        "ppe-detector",
        "v0.2",
        "PPE_DETECTOR",
        "DEMO",
        "Helmet, protective clothing and mask on each person. DEMO mode reads the scripted outfit. "
        "Without ppe.onnx, REAL mode reads colours: a hard hat above the face, a coverall from torso to legs, and a mask over the chin when face.onnx finds the face.",
    ),
    ("forklift-detector", "v0.1", "FORKLIFT_DETECTOR", "DEMO", "Optional forklift box. The forklift-lane alert is raised from a person inside the lane and does not need this model."),
    (
        HANDWASH_MODEL,
        "v0.1",
        "HANDWASH_DETECTOR",
        "DEMO",
        "WHO hand-washing steps, seen from above the sink. DEMO mode scripts the washes. "
        "REAL mode uses handwash_steps.onnx, a classifier of all six steps trained on the site's own clips, "
        "else handwash.onnx, the reference YOLOv8n-seg of Özakar and Gedikli (2025), which checks backs of hands, thumbs and fingertips.",
    ),
]

# The coffee-plant demo this POC started from. Its cameras and models are retired on first start.
LEGACY_FACTORY_CODE = "coffee-poc"
LEGACY_CAMERAS = ("CAM-PACK-01", "CAM-PROD-01", "CAM-MACHINE-01", "CAM-WAREHOUSE-01", "CAM-BEAN-01")
LEGACY_MODELS = ("coffee-line", "ppe-classifier")


def seed(db: Session) -> None:
    existing = db.query(Factory).filter(Factory.code == FACTORY_CODE).first()
    if existing is not None:
        _add_handwash_once(db, existing)
        return
    legacy = db.query(Factory).filter(Factory.code == LEGACY_FACTORY_CODE).first()
    if legacy is not None:
        _leave_coffee_demo(db, legacy)
        return
    settings = get_settings()
    factory = Factory(name=FACTORY_NAME, code=FACTORY_CODE, timezone="Asia/Ho_Chi_Minh")
    db.add(factory)
    db.flush()

    users = {
        "admin": User(username="admin", full_name="Factory Admin", role="ADMIN", password_hash=hash_password(settings.demo_admin_password)),
        "safety": User(username="safety", full_name="Safety Manager", role="SAFETY_MANAGER", password_hash=hash_password(settings.demo_safety_password)),
        "viewer": User(username="viewer", full_name="Shift Viewer", role="VIEWER", password_hash=hash_password(settings.demo_viewer_password)),
    }
    db.add_all(users.values())
    _ensure_models(db, factory)
    camera, zone, rules = _add_workshop_camera(db, factory)
    _add_restricted_camera(db, factory)
    _add_handwash_camera(db, factory)
    by_event = {rule.event_type: rule for rule in rules}

    now = datetime.now(timezone.utc)
    samples = [
        ("HELMET_VIOLATION", "NEW", 0.4, 0.88, "seed-track-1"),
        ("CLOTHING_VIOLATION", "CONFIRMED", 1.2, 0.84, "seed-track-2"),
        ("MASK_VIOLATION", "FALSE_POSITIVE", 2.0, 0.61, "seed-track-3"),
        ("MASK_VIOLATION", "NEW", 3.1, 0.79, "seed-track-4"),
        ("HELMET_VIOLATION", "RESOLVED", 4.5, 0.9, "seed-track-5"),
        ("MASK_VIOLATION", "CONFIRMED", 6.0, 0.81, "seed-track-6"),
        ("HELMET_VIOLATION", "NEW", 8.0, 0.86, "seed-track-7"),
        ("CLOTHING_VIOLATION", "RESOLVED", 20.0, 0.72, "seed-track-8"),
        ("CLOTHING_VIOLATION", "FALSE_POSITIVE", 26.0, 0.55, "seed-track-9"),
    ]
    for event_type, status, hours, confidence, track in samples:
        rule = by_event[event_type]
        started = now - timedelta(hours=hours)
        incident = Incident(
            factory_id=factory.id,
            camera_id=camera.id,
            zone_id=zone.id,
            rule_id=rule.id,
            event_type=event_type,
            severity=rule.severity,
            track_id=track,
            confidence=confidence,
            started_at=started,
            ended_at=started + timedelta(seconds=18),
            status=status,
            model_name="ppe-detector",
            model_version="v0-demo",
            ai_mode="DEMO",
            created_at=started,
            updated_at=started,
        )
        db.add(incident)
        db.flush()
        if status == "FALSE_POSITIVE":
            db.add(OperatorFeedback(incident_id=incident.id, decision=status, comment="Operator marked this sample as a false positive.", user_id=users["safety"].id, created_at=started + timedelta(minutes=5)))
        elif status in {"CONFIRMED", "RESOLVED"}:
            db.add(OperatorFeedback(incident_id=incident.id, decision=status, comment="Sample review recorded at startup.", user_id=users["safety"].id, created_at=started + timedelta(minutes=3)))
    db.commit()


def _leave_coffee_demo(db: Session, factory: Factory) -> None:
    """Turns a database seeded for the coffee plant into the general factory demo. Runs once.

    The five seeded coffee cameras go, with their zones, rules, incidents and reviews.
    Cameras added by hand stay. Renaming the factory marks the move as done.
    """
    for camera in db.query(Camera).filter(Camera.factory_id == factory.id, Camera.code.in_(LEGACY_CAMERAS)).all():
        delete_camera_data(db, camera)
    for model in db.query(AIModel).filter(AIModel.name.in_(LEGACY_MODELS)).all():
        db.query(AIModelDeployment).filter(AIModelDeployment.model_id == model.id).delete(synchronize_session=False)
        db.delete(model)
    db.flush()
    factory.code, factory.name = FACTORY_CODE, FACTORY_NAME
    _ensure_models(db, factory)
    if db.query(Camera).filter(Camera.code == WORKSHOP_CAMERA).first() is None:
        _add_workshop_camera(db, factory)
    if db.query(Camera).filter(Camera.code == RESTRICTED_CAMERA).first() is None:
        _add_restricted_camera(db, factory)
    if db.query(Camera).filter(Camera.code == HANDWASH_CAMERA).first() is None:
        _add_handwash_camera(db, factory)
    db.commit()


def _add_handwash_once(db: Session, factory: Factory) -> None:
    """A database seeded before the hand-wash camera existed gets it on the next start.

    The hand-wash model row marks that this has run, so a hand-wash camera deleted later stays deleted.
    """
    if db.query(AIModel).filter(AIModel.name == HANDWASH_MODEL).first() is not None:
        return
    _ensure_models(db, factory)
    if db.query(Camera).filter(Camera.code == HANDWASH_CAMERA).first() is None:
        _add_handwash_camera(db, factory)
    db.commit()


def _ensure_models(db: Session, factory: Factory) -> None:
    for name, version, model_type, status, description in MODELS:
        if db.query(AIModel).filter(AIModel.name == name, AIModel.version == version).first():
            continue
        model = AIModel(name=name, version=version, model_type=model_type, status=status, description=description)
        db.add(model)
        db.flush()
        db.add(AIModelDeployment(model_id=model.id, factory_id=factory.id, status="ACTIVE", notes="POC deployment"))


def _add_workshop_camera(db: Session, factory: Factory) -> tuple[Camera, Zone, list[Rule]]:
    """One camera over a workshop floor where helmet, protective clothing and mask are required."""
    camera = Camera(factory_id=factory.id, code=WORKSHOP_CAMERA, name="Workshop Camera 01", area="Workshop floor", stream_type="FILE", stream_url="", enabled=True, ai_fps=25)
    db.add(camera)
    db.flush()
    zone = Zone(factory_id=factory.id, camera_id=camera.id, name="Workshop floor", zone_type="PPE_ZONE", polygon=WORKSHOP_FLOOR)
    db.add(zone)
    db.flush()
    rules = [_rule(factory, camera, zone, name, event_type, condition, 2000, severity) for name, event_type, condition, severity in PPE_RULES]
    db.add_all(rules)
    db.flush()
    return camera, zone, rules


def _add_restricted_camera(db: Session, factory: Factory) -> Camera:
    """One camera over a restricted lane. People may not enter; vehicles may not, except forklifts."""
    camera = Camera(factory_id=factory.id, code=RESTRICTED_CAMERA, name="Restricted Area Camera 01", area="Restricted lane", stream_type="FILE", stream_url="", enabled=True, ai_fps=25)
    db.add(camera)
    db.flush()
    zone = Zone(factory_id=factory.id, camera_id=camera.id, name="Restricted lane", zone_type="RESTRICTED_AREA", polygon=RESTRICTED_LANE)
    db.add(zone)
    db.flush()
    db.add_all([_rule(factory, camera, zone, name, event_type, condition, 1000, severity) for name, event_type, condition, severity in RESTRICTED_RULES])
    db.flush()
    return camera


def _add_handwash_camera(db: Session, factory: Factory) -> Camera:
    """One camera above a sink, looking down. Each wash must show the WHO steps, each for at least 1.5 s."""
    camera = Camera(factory_id=factory.id, code=HANDWASH_CAMERA, name="Handwash Station Camera 01", area="Handwash station", stream_type="FILE", stream_url="", enabled=True, ai_fps=10)
    db.add(camera)
    db.flush()
    zone = Zone(factory_id=factory.id, camera_id=camera.id, name="Sink", zone_type="HANDWASH_STATION", polygon=HANDWASH_SINK)
    db.add(zone)
    db.flush()
    name, event_type, condition, severity = HANDWASH_RULE
    db.add(_rule(factory, camera, zone, name, event_type, condition, 1500, severity))
    db.flush()
    return camera


def _rule(factory, camera, zone, name, event_type, condition, duration_ms, severity, extensions: dict | None = None) -> Rule:
    return Rule(
        factory_id=factory.id,
        camera_id=camera.id,
        zone_id=zone.id,
        name=name,
        event_type=event_type,
        condition_type=condition,
        min_duration_ms=duration_ms,
        cooldown_ms=30000,
        grace_ms=1000,
        severity=severity,
        enabled=True,
        extensions=extensions or {},
    )

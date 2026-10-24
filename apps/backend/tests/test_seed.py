from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AIModel, AIModelDeployment, Camera, Factory, Incident, IncidentEvidence, OperatorFeedback, Rule, User, Zone
from app.seed import seed

PPE_CONDITIONS = {"HELMET_MISSING", "CLOTHING_MISSING", "MASK_MISSING"}
SQUARE = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _counts(db):
    return (db.query(Factory).count(), db.query(Camera).count(), db.query(Zone).count(), db.query(Rule).count(), db.query(AIModel).count(), db.query(Incident).count())


def test_fresh_seed_has_a_workshop_camera_a_restricted_area_camera_and_a_handwash_camera():
    db = _session()
    seed(db)
    factory = db.query(Factory).one()
    assert (factory.code, factory.name) == ("factory-poc", "Factory POC")
    assert {camera.code for camera in db.query(Camera)} == {"CAM-WORKSHOP-01", "CAM-RESTRICTED-01", "CAM-HANDWASH-01"}
    sink = db.query(Zone).join(Camera, Camera.id == Zone.camera_id).filter(Camera.code == "CAM-HANDWASH-01").one()
    assert sink.zone_type == "HANDWASH_STATION"
    assert [(rule.condition_type, rule.zone_id) for rule in db.query(Rule).filter(Rule.camera_id == sink.camera_id)] == [("HANDWASH_STEPS_MISSING", sink.id)]
    workshop = db.query(Camera).filter(Camera.code == "CAM-WORKSHOP-01").one()
    zone = db.query(Zone).filter(Zone.camera_id == workshop.id).one()
    assert zone.zone_type == "PPE_ZONE"
    assert {rule.condition_type for rule in db.query(Rule).filter(Rule.camera_id == workshop.id)} == PPE_CONDITIONS
    assert all(rule.zone_id == zone.id for rule in db.query(Rule).filter(Rule.camera_id == workshop.id))
    restricted = db.query(Camera).filter(Camera.code == "CAM-RESTRICTED-01").one()
    lane = db.query(Zone).filter(Zone.camera_id == restricted.id).one()
    assert lane.zone_type == "RESTRICTED_AREA"
    assert {rule.condition_type for rule in db.query(Rule).filter(Rule.camera_id == restricted.id)} == {"PERSON_INSIDE", "VEHICLE_INSIDE"}
    assert {incident.event_type for incident in db.query(Incident)} == {"HELMET_VIOLATION", "CLOTHING_VIOLATION", "MASK_VIOLATION"}
    assert db.query(AIModel).filter(AIModel.name == "ppe-detector").count() == 1
    before = _counts(db)
    seed(db)
    assert _counts(db) == before
    db.close()


def _legacy_database(db):
    factory = Factory(name="Coffee Factory POC", code="coffee-poc", timezone="Asia/Ho_Chi_Minh")
    db.add(factory)
    db.flush()
    user = User(username="safety", full_name="Safety Manager", role="SAFETY_MANAGER", password_hash="x")
    db.add(user)
    db.flush()
    for code in ("CAM-PACK-01", "CAM-PROD-01", "CAM-MACHINE-01", "CAM-WAREHOUSE-01", "CAM-BEAN-01", "CAM-DOCK-07"):
        camera = Camera(factory_id=factory.id, code=code, name=code, area="Area", stream_type="FILE", stream_url="")
        db.add(camera)
        db.flush()
        zone = Zone(factory_id=factory.id, camera_id=camera.id, name="Zone", zone_type="RESTRICTED_AREA", polygon=SQUARE)
        db.add(zone)
        db.flush()
        rule = Rule(factory_id=factory.id, camera_id=camera.id, zone_id=zone.id, name="Rule", event_type="RESTRICTED_AREA_INTRUSION", condition_type="PERSON_INSIDE", severity="HIGH")
        db.add(rule)
        db.flush()
        incident = Incident(factory_id=factory.id, camera_id=camera.id, zone_id=zone.id, rule_id=rule.id, event_type=rule.event_type, severity="HIGH", started_at=datetime.now(timezone.utc), status="CONFIRMED")
        db.add(incident)
        db.flush()
        db.add(IncidentEvidence(incident_id=incident.id, kind="snapshot", object_key=f"incidents/{incident.id}/snapshot.jpg"))
        db.add(OperatorFeedback(incident_id=incident.id, decision="CONFIRMED", user_id=user.id))
    for name, version in (("coffee-line", "v0-demo"), ("ppe-classifier", "v0.1"), ("person-detector", "v1.0")):
        model = AIModel(name=name, version=version, model_type="X", status="DEMO")
        db.add(model)
        db.flush()
        db.add(AIModelDeployment(model_id=model.id, factory_id=factory.id))
    db.commit()


def test_coffee_database_loses_the_seeded_cameras_and_keeps_hand_added_ones():
    db = _session()
    _legacy_database(db)
    seed(db)
    factory = db.query(Factory).one()
    assert (factory.code, factory.name) == ("factory-poc", "Factory POC")
    assert {camera.code for camera in db.query(Camera)} == {"CAM-DOCK-07", "CAM-WORKSHOP-01", "CAM-RESTRICTED-01", "CAM-HANDWASH-01"}
    kept = db.query(Camera).filter(Camera.code == "CAM-DOCK-07").one()
    assert {incident.camera_id for incident in db.query(Incident)} == {kept.id}
    assert db.query(IncidentEvidence).count() == 1
    assert db.query(OperatorFeedback).count() == 1
    workshop = db.query(Camera).filter(Camera.code == "CAM-WORKSHOP-01").one()
    assert {rule.condition_type for rule in db.query(Rule).filter(Rule.camera_id == workshop.id)} == PPE_CONDITIONS
    names = {model.name for model in db.query(AIModel)}
    assert "coffee-line" not in names and "ppe-classifier" not in names
    assert {"person-detector", "ppe-detector", "forklift-detector"} <= names
    assert db.query(AIModel).filter(AIModel.name == "person-detector").count() == 1
    assert db.query(AIModelDeployment).count() == db.query(AIModel).count()
    assert db.query(User).count() == 1
    db.close()


def test_the_move_runs_once_so_a_deleted_workshop_camera_stays_deleted():
    db = _session()
    _legacy_database(db)
    seed(db)
    workshop = db.query(Camera).filter(Camera.code == "CAM-WORKSHOP-01").one()
    db.query(Rule).filter(Rule.camera_id == workshop.id).delete()
    db.query(Zone).filter(Zone.camera_id == workshop.id).delete()
    db.delete(workshop)
    db.commit()
    seed(db)
    assert {camera.code for camera in db.query(Camera)} == {"CAM-DOCK-07", "CAM-RESTRICTED-01", "CAM-HANDWASH-01"}
    db.close()


def _seeded_before_the_handwash_camera(db):
    seed(db)
    camera = db.query(Camera).filter(Camera.code == "CAM-HANDWASH-01").one()
    db.query(Rule).filter(Rule.camera_id == camera.id).delete()
    db.query(Zone).filter(Zone.camera_id == camera.id).delete()
    db.delete(camera)
    model = db.query(AIModel).filter(AIModel.name == "handwash-detector").one()
    db.query(AIModelDeployment).filter(AIModelDeployment.model_id == model.id).delete()
    db.delete(model)
    db.commit()


def test_a_database_seeded_before_the_handwash_camera_gets_it_once():
    db = _session()
    _seeded_before_the_handwash_camera(db)
    incidents = db.query(Incident).count()
    seed(db)
    camera = db.query(Camera).filter(Camera.code == "CAM-HANDWASH-01").one()
    assert [zone.zone_type for zone in db.query(Zone).filter(Zone.camera_id == camera.id)] == ["HANDWASH_STATION"]
    assert [rule.event_type for rule in db.query(Rule).filter(Rule.camera_id == camera.id)] == ["HANDWASH_INCOMPLETE"]
    assert db.query(AIModel).filter(AIModel.name == "handwash-detector").count() == 1
    assert db.query(AIModelDeployment).count() == db.query(AIModel).count()
    assert db.query(Incident).count() == incidents
    db.query(Rule).filter(Rule.camera_id == camera.id).delete()
    db.query(Zone).filter(Zone.camera_id == camera.id).delete()
    db.delete(camera)
    db.commit()
    seed(db)
    assert db.query(Camera).filter(Camera.code == "CAM-HANDWASH-01").count() == 0
    db.close()

from fastapi.testclient import TestClient

from app.main import app
from app.mask import mask_stream_url
from app.validators import validate_polygon


def client():
    return TestClient(app)


def auth(api: TestClient, username: str, password: str) -> dict:
    response = api.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health_and_seed_login():
    with client() as api:
        assert api.get("/health").json()["status"] == "ok"
        assert api.get("/ready").status_code == 200
        headers = auth(api, "admin", "admin123")
        cameras = api.get("/api/cameras", headers=headers)
        assert cameras.status_code == 200
        codes = {item["code"] for item in cameras.json()}
        assert codes == {"CAM-WORKSHOP-01", "CAM-RESTRICTED-01", "CAM-HANDWASH-01"}
        rules = api.get("/api/rules", headers=headers).json()
        assert {item["event_type"] for item in rules} == {
            "HELMET_VIOLATION",
            "CLOTHING_VIOLATION",
            "MASK_VIOLATION",
            "RESTRICTED_AREA_INTRUSION",
            "VEHICLE_IN_RESTRICTED_AREA",
            "HANDWASH_INCOMPLETE",
        }
        assert api.get("/api/incidents", headers=headers).json()["total"] >= 9


def test_viewer_cannot_configure_and_safety_can_review():
    with client() as api:
        viewer = auth(api, "viewer", "viewer123")
        denied = api.post(
            "/api/cameras",
            headers=viewer,
            json={"code": "CAM-X", "name": "Extra", "area": "Workshop", "stream_type": "FILE"},
        )
        assert denied.status_code == 403
        safety = auth(api, "safety", "safety123")
        incidents = api.get("/api/incidents?status=NEW", headers=safety).json()["items"]
        assert incidents
        updated = api.post(f"/api/incidents/{incidents[0]['id']}/confirm", headers=safety, json={"comment": "Checked on the floor"})
        assert updated.status_code == 200
        assert updated.json()["status"] == "CONFIRMED"
        again = api.post(f"/api/incidents/{incidents[0]['id']}/confirm", headers=safety, json={"comment": "again"})
        assert again.status_code == 409


def test_helmet_incident_is_reviewable_and_live_returns_ppe(monkeypatch):
    stored: dict[str, dict] = {}
    monkeypatch.setattr("app.routers.internal.write_live", lambda camera_id, payload: stored.__setitem__(camera_id, payload))
    monkeypatch.setattr("app.routers.catalog.read_live", lambda camera_id: stored.get(camera_id))
    with client() as api:
        headers = auth(api, "admin", "admin123")
        cameras = api.get("/api/internal/cameras", headers={"X-Internal-Token": "test-internal"}).json()
        workshop = next(item for item in cameras if item["code"] == "CAM-WORKSHOP-01")
        rule = next(item for item in workshop["rules"] if item["condition_type"] == "HELMET_MISSING")
        opened = api.post(
            "/api/internal/incidents",
            headers={"X-Internal-Token": "test-internal"},
            json={
                "factory_id": workshop["factory_id"],
                "camera_id": workshop["id"],
                "zone_id": rule["zone_id"],
                "rule_id": rule["id"],
                "event_type": "HELMET_VIOLATION",
                "severity": "HIGH",
                "track_id": "17",
                "confidence": 0.84,
                "started_at": "2026-10-13T01:00:00Z",
                "model_name": "ppe-detector",
                "model_version": "v0-demo",
                "ai_mode": "DEMO",
            },
        )
        assert opened.status_code == 200, opened.text
        body = opened.json()
        assert body["reason"] == "created"
        safety = auth(api, "safety", "safety123")
        confirmed = api.post(f"/api/incidents/{body['id']}/confirm", headers=safety, json={"comment": "No helmet near the press"})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "CONFIRMED"
        assert confirmed.json()["event_type"] == "HELMET_VIOLATION"
        ppe = {"helmet": "NO", "clothing": "YES", "shoes": "YES", "mask": "UNKNOWN"}
        checks = [{"text": "Helmet: No", "state": "violation"}, {"text": "Mask: Unknown", "state": "unknown"}]
        beat = api.post(
            f"/api/internal/cameras/{workshop['id']}/heartbeat",
            headers={"X-Internal-Token": "test-internal"},
            json={
                "status": "ONLINE",
                "ai_mode": "DEMO",
                "tracks": [{"track_id": "17", "bbox": [0.1, 0.4, 0.18, 0.8], "class_name": "person", "confidence": 0.9, "ppe": ppe, "checks": checks}],
            },
        )
        assert beat.status_code == 200, beat.text
        live = api.get(f"/api/cameras/{workshop['id']}/live", headers=headers)
        assert live.status_code == 200, live.text
        assert "coffee" not in live.json()
        track = live.json()["tracks"][0]
        assert track["ppe"] == ppe
        assert track["checks"] == checks


def test_ppe_rule_can_be_added_and_old_coffee_types_are_rejected():
    with client() as api:
        headers = auth(api, "admin", "admin123")
        zone = next(item for item in api.get("/api/zones", headers=headers).json() if item["zone_type"] == "PPE_ZONE")
        rule = {"zone_id": zone["id"], "name": "Mask at the paint booth", "event_type": "MASK_VIOLATION", "condition_type": "MASK_MISSING", "min_duration_ms": 2000, "cooldown_ms": 30000, "severity": "MEDIUM"}
        created = api.post("/api/rules", headers=headers, json=rule)
        assert created.status_code == 200, created.text
        assert created.json()["condition_type"] == "MASK_MISSING"
        assert api.delete(f"/api/rules/{created.json()['id']}", headers=headers).status_code == 200
        hairnet = api.post("/api/rules", headers=headers, json={**rule, "event_type": "HAIRNET_VIOLATION", "condition_type": "HAIRNET_MISSING"})
        assert hairnet.status_code == 400
        belt = api.post("/api/zones", headers=headers, json={"camera_id": zone["camera_id"], "name": "Belt", "zone_type": "GREEN_COFFEE_LINE", "polygon": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5]]})
        assert belt.status_code == 400


def test_worker_token_and_masking():
    with client() as api:
        denied = api.get("/api/internal/cameras", headers={"X-Internal-Token": "nope"})
        assert denied.status_code == 401
        allowed = api.get("/api/internal/cameras", headers={"X-Internal-Token": "test-internal"})
        assert allowed.status_code == 200
        assert len(allowed.json()) == 3
        workshop = next(item for item in allowed.json() if item["code"] == "CAM-WORKSHOP-01")
        lane = next(item for item in allowed.json() if item["code"] == "CAM-RESTRICTED-01")
        assert {rule["condition_type"] for rule in lane["rules"]} == {"PERSON_INSIDE", "VEHICLE_INSIDE"}
        assert [zone["zone_type"] for zone in workshop["zones"]] == ["PPE_ZONE"]
        assert {rule["condition_type"] for rule in workshop["rules"]} == {"HELMET_MISSING", "CLOTHING_MISSING", "MASK_MISSING"}
        sink = next(item for item in allowed.json() if item["code"] == "CAM-HANDWASH-01")
        assert [zone["zone_type"] for zone in sink["zones"]] == ["HANDWASH_STATION"]
        assert [(rule["condition_type"], rule["min_duration_ms"]) for rule in sink["rules"]] == [("HANDWASH_STEPS_MISSING", 3000)]
    assert mask_stream_url("rtsp://operator:s3cret@10.0.0.5/live") == "rtsp://operator:***@10.0.0.5/live"
    assert "s3cret" not in mask_stream_url("rtsp://operator:s3cret@10.0.0.5/live")


def test_camera_ai_fps_saves_25_and_rejects_31():
    with client() as api:
        headers = auth(api, "admin", "admin123")
        camera = next(item for item in api.get("/api/cameras", headers=headers).json() if item["code"] == "CAM-WORKSHOP-01")
        assert camera["ai_fps"] == 25
        lowered = api.patch(f"/api/cameras/{camera['id']}", headers=headers, json={"ai_fps": 8})
        assert lowered.status_code == 200, lowered.text
        assert lowered.json()["ai_fps"] == 8
        raised = api.patch(f"/api/cameras/{camera['id']}", headers=headers, json={"ai_fps": 25})
        assert raised.status_code == 200, raised.text
        assert raised.json()["ai_fps"] == 25
        rejected = api.patch(f"/api/cameras/{camera['id']}", headers=headers, json={"ai_fps": 31})
        assert rejected.status_code == 422


def test_polygon_must_be_normalized():
    try:
        validate_polygon([[0.1, 0.1], [1.2, 0.2], [0.2, 0.8]])
    except ValueError as exc:
        assert "between 0 and 1" in str(exc)
    else:
        raise AssertionError("expected a validation error")


def test_polygon_takes_any_number_of_corners_but_no_crossing_edges():
    l_shape = [[0.1, 0.1], [0.6, 0.1], [0.6, 0.4], [0.3, 0.4], [0.3, 0.9], [0.1, 0.9]]
    assert validate_polygon(l_shape) == l_shape
    assert len(validate_polygon(l_shape[:3] + [[0.45, 0.4]] + l_shape[3:])) == 7
    assert validate_polygon([[0.1, 0.1], [0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.1]]) == [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5]]
    for points, message in (
        ([[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]], "cross"),
        ([[0.1, 0.1], [0.5, 0.5], [0.9, 0.9]], "no area"),
        ([[0.2, 0.2], [0.2, 0.2], [0.2, 0.2]], "3 different points"),
    ):
        try:
            validate_polygon(points)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"expected a validation error for {points}")


def test_admin_redraws_a_zone_in_place_and_its_rules_stay():
    with client() as api:
        headers = auth(api, "admin", "admin123")
        rule = next(item for item in api.get("/api/rules", headers=headers).json() if item["event_type"] == "HELMET_VIOLATION")
        shape = [[0.5, 0.4], [0.7, 0.38], [0.8, 0.5], [0.72, 0.62], [0.55, 0.6], [0.48, 0.5]]
        redrawn = api.patch(f"/api/zones/{rule['zone_id']}", headers=headers, json={"polygon": shape})
        assert redrawn.status_code == 200, redrawn.text
        assert redrawn.json()["id"] == rule["zone_id"]
        assert redrawn.json()["polygon"] == shape
        assert redrawn.json()["name"] == rule["zone_name"]
        still = next(item for item in api.get("/api/rules", headers=headers).json() if item["id"] == rule["id"])
        assert still["zone_id"] == rule["zone_id"]
        crossing = api.patch(f"/api/zones/{rule['zone_id']}", headers=headers, json={"polygon": [[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]]})
        assert crossing.status_code == 400
        assert "cross" in crossing.json()["detail"]
        viewer = auth(api, "viewer", "viewer123")
        assert api.patch(f"/api/zones/{rule['zone_id']}", headers=viewer, json={"polygon": shape}).status_code == 403


def test_zone_keeps_the_frame_it_was_drawn_on(monkeypatch):
    from app.routers import catalog

    objects: dict[str, bytes] = {}
    monkeypatch.setattr(catalog, "get_bytes", lambda key: objects.get(key))
    monkeypatch.setattr(catalog, "put_bytes", lambda key, data, content_type: objects.__setitem__(key, data))
    with client() as api:
        headers = auth(api, "admin", "admin123")
        camera = next(item for item in api.get("/api/cameras", headers=headers).json() if item["code"] == "CAM-WORKSHOP-01")
        frames = f"/api/cameras/{camera['id']}/reference-frames"
        assert api.post(frames, headers=headers).status_code == 404
        objects[f"cameras/{camera['id']}/latest_raw.jpg"] = b"frame drawn on"
        frozen = api.post(frames, headers=headers).json()["id"]
        objects[f"cameras/{camera['id']}/latest_raw.jpg"] = b"a later frame"
        assert api.get(f"{frames}/{frozen}", headers=headers).content == b"frame drawn on"

        shape = [[0.1, 0.6], [0.4, 0.6], [0.4, 0.9], [0.1, 0.9]]
        zone = api.post("/api/zones", headers=headers, json={"camera_id": camera["id"], "name": "Dock", "zone_type": "RESTRICTED_AREA", "polygon": shape, "reference_id": frozen}).json()
        key = f"cameras/{camera['id']}/references/{frozen}.jpg"
        assert zone["reference_key"] == key
        worker = api.get("/api/internal/cameras", headers={"X-Internal-Token": "test-internal"}).json()
        assert next(item for cam in worker for item in cam["zones"] if item["id"] == zone["id"])["reference_key"] == key

        url = f"/api/zones/{zone['id']}"
        assert api.patch(url, headers=headers, json={"name": "Dock A"}).json()["reference_key"] == key
        assert api.patch(url, headers=headers, json={"polygon": shape}).json()["reference_key"] is None
        assert api.patch(url, headers=headers, json={"reference_id": frozen}).json()["reference_key"] == key
        # An explicit null unlinks without touching the shape; leaving the field out keeps the link.
        unlinked = api.patch(url, headers=headers, json={"reference_id": None}).json()
        assert unlinked["reference_key"] is None and unlinked["polygon"] == shape
        assert api.patch(url, headers=headers, json={"name": "Dock B"}).json()["reference_key"] is None
        assert api.patch(url, headers=headers, json={"reference_id": frozen}).json()["reference_key"] == key
        assert api.patch(url, headers=headers, json={"reference_id": "../latest_raw"}).status_code == 400
        assert api.patch(url, headers=headers, json={"reference_id": "0" * 32}).status_code == 400
        api.delete(url, headers=headers)


def test_multi_view_is_off_by_default_and_reaches_the_worker():
    with client() as api:
        headers = auth(api, "admin", "admin123")
        camera = next(item for item in api.get("/api/cameras", headers=headers).json() if item["code"] == "CAM-WORKSHOP-01")
        assert camera["multi_view"] is False
        updated = api.patch(f"/api/cameras/{camera['id']}", headers=headers, json={"multi_view": True})
        assert updated.status_code == 200 and updated.json()["multi_view"] is True
        worker = api.get("/api/internal/cameras", headers={"X-Internal-Token": "test-internal"}).json()
        assert next(item for item in worker if item["id"] == camera["id"])["multi_view"] is True
        api.patch(f"/api/cameras/{camera['id']}", headers=headers, json={"multi_view": False})


def test_overview_splits_the_trend_by_severity_and_names_the_peak():
    with client() as api:
        headers = auth(api, "admin", "admin123")
        data = api.get("/api/system/overview", headers=headers).json()
        assert len(data["trend"]) == 24
        assert all(0 <= item["critical"] <= item["count"] for item in data["trend"])
        assert sum(item["count"] for item in data["trend"]) == data["incidents_today"]
        assert sum(item["critical"] for item in data["trend"]) == data["critical_incidents"]
        assert sum(data["camera_incidents_today"].values()) == data["incidents_today"]
        assert data["new_incidents"] == api.get("/api/incidents?status=NEW", headers=headers).json()["total"]
        if data["incidents_today"]:
            busiest = max(item["count"] for item in data["trend"])
            assert data["peak"]["count"] == busiest
            assert data["peak"]["hour"] == next(item["hour"] for item in data["trend"] if item["count"] == busiest)
            assert data["peak"]["camera_name"]
        else:
            assert data["peak"] is None
        report = api.get("/api/system/evaluation", headers=headers).json()
        assert set(report["by_event_severity"]) == set(report["by_event_type"])


def test_a_new_video_or_stream_unlinks_zones_from_the_old_view(monkeypatch):
    from app.routers import catalog

    objects: dict[str, bytes] = {}
    monkeypatch.setattr(catalog, "get_bytes", lambda key: objects.get(key))
    monkeypatch.setattr(catalog, "put_bytes", lambda key, data, content_type: objects.__setitem__(key, data))
    with client() as api:
        headers = auth(api, "admin", "admin123")
        camera = next(item for item in api.get("/api/cameras", headers=headers).json() if item["code"] == "CAM-WORKSHOP-01")
        objects[f"cameras/{camera['id']}/latest_raw.jpg"] = b"old video frame"
        frozen = api.post(f"/api/cameras/{camera['id']}/reference-frames", headers=headers).json()["id"]
        shape = [[0.1, 0.6], [0.4, 0.6], [0.4, 0.9], [0.1, 0.9]]
        zone = api.post("/api/zones", headers=headers, json={"camera_id": camera["id"], "name": "Bench", "zone_type": "PPE_ZONE", "polygon": shape, "reference_id": frozen}).json()
        linked = lambda: next(item for item in api.get(f"/api/zones?camera_id={camera['id']}", headers=headers).json() if item["id"] == zone["id"])["reference_key"]
        relink = lambda: api.patch(f"/api/zones/{zone['id']}", headers=headers, json={"reference_id": frozen})

        api.patch(f"/api/cameras/{camera['id']}", headers=headers, json={"stream_url": camera["stream_url"] or "", "ai_fps": 20})
        assert linked() is not None, "saving the same source keeps the link"
        api.patch(f"/api/cameras/{camera['id']}", headers=headers, json={"stream_type": "RTSP", "stream_url": "rtsp://10.0.0.9/live"})
        assert linked() is None
        relink()
        uploaded = api.post(f"/api/cameras/{camera['id']}/video", headers=headers, files={"file": ("new.mp4", b"\x00\x00", "video/mp4")})
        assert uploaded.status_code == 200, uploaded.text
        assert linked() is None
        zones = api.get(f"/api/zones?camera_id={camera['id']}", headers=headers).json()
        assert next(item for item in zones if item["id"] == zone["id"])["polygon"] == shape, "the zone stays where it was drawn"
        api.delete(f"/api/zones/{zone['id']}", headers=headers)
        api.patch(f"/api/cameras/{camera['id']}", headers=headers, json={"stream_type": "FILE", "stream_url": "", "ai_fps": 25})

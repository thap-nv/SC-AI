"""Scripted DEMO paths. People walk into the configured polygons so every rule can be shown."""

from app.zone_engine import point_in_polygon, representative_point

PERIOD_S = 36.0

FULL_KIT = {"helmet": "YES", "clothing": "YES", "mask": "YES"}
UNREADABLE = {item: "UNKNOWN" for item in FULL_KIT}
# On a PPE floor: one worker fully kitted, one missing each item, and one the classifier cannot read.
PPE_CREW = [
    FULL_KIT,
    {**FULL_KIT, "helmet": "NO"},
    {**FULL_KIT, "clothing": "NO"},
    {**FULL_KIT, "mask": "NO"},
    UNREADABLE,
]


def _lerp(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _outside(polygon: list[list[float]], anchor: tuple[float, float]) -> tuple[float, float]:
    candidates = [
        (max(0.02, min(0.98, anchor[0] - 0.4)), anchor[1]),
        (0.03, anchor[1]),
        (0.03, 0.06),
        (0.97, 0.06),
    ]
    for point in candidates:
        if not point_in_polygon(polygon, point[0], point[1]):
            return point
    return (0.03, 0.06)


def walk(
    now: float,
    polygon: list[list[float]],
    anchor: tuple[float, float],
    hold_inside: bool,
    phase: float,
    start: tuple[float, float] | None = None,
) -> tuple[float, float]:
    if hold_inside:
        return anchor
    outside = start or _outside(polygon, anchor)
    progress = ((now + phase) % PERIOD_S) / PERIOD_S
    if progress < 0.4:
        return _lerp(outside, anchor, progress / 0.4)
    if progress < 0.7:
        return anchor
    return _lerp(anchor, outside, (progress - 0.7) / 0.3)


def _spots(polygon: list[list[float]], count: int) -> list[tuple[float, float]]:
    """Standing places spread across the zone, alternating between a near and a far row."""
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    spots = []
    for index in range(count):
        x = left + (right - left) * (index + 0.5) / count
        rows = (0.85, 0.6, 0.7, 0.45) if index % 2 == 0 else (0.6, 0.85, 0.7, 0.45)
        for row in rows:
            y = top + (bottom - top) * row
            if point_in_polygon(polygon, x, y):
                spots.append((x, y))
                break
    return spots


def _entry(polygon: list[list[float]], spot: tuple[float, float]) -> tuple[float, float] | None:
    """Straight below the spot, or straight above it. Lanes stay apart, so boxes never cross."""
    for y in (0.99, min(spot[1], min(point[1] for point in polygon)) - 0.04):
        if 0.26 <= y <= 0.99 and not point_in_polygon(polygon, spot[0], y):
            return (spot[0], y)
    return None


def _ppe_crew(polygon: list[list[float]], now: float, hold_inside: bool, phase: float) -> list[dict]:
    people = []
    for index, (outfit, spot) in enumerate(zip(PPE_CREW, _spots(polygon, len(PPE_CREW)))):
        entry = _entry(polygon, spot)
        if outfit is UNREADABLE or entry is None:
            position = spot
        else:
            position = walk(now, polygon, spot, hold_inside, phase + index * PERIOD_S / len(PPE_CREW), start=entry)
        people.append({"class_name": "person", "outfit": outfit, "nx": position[0], "ny": position[1]})
    return people


def scripted_objects(zones: list[dict], now: float, hold_inside: bool) -> list[dict]:
    objects: list[dict] = []
    for index, zone in enumerate(zones):
        polygon = zone.get("polygon") or []
        anchor = representative_point(polygon)
        if anchor is None:
            continue
        zone_type = zone.get("zone_type")
        if zone_type == "HANDWASH_STATION":
            # Seen from above the sink: the hands are scripted by scripted_wash, not as a person.
            continue
        if zone_type == "PPE_ZONE":
            objects.extend(_ppe_crew(polygon, now, hold_inside, phase=index * 3.0))
            continue
        if zone_type == "RESTRICTED_AREA":
            objects.extend(_restricted_traffic(polygon, now, hold_inside, phase=index * 3.0))
            continue
        position = walk(now, polygon, anchor, hold_inside, phase=index * 3.0)
        objects.append({"class_name": "person", "outfit": FULL_KIT, "nx": position[0], "ny": position[1]})
        if zone_type == "FORKLIFT_LANE":
            parked = (min(0.96, anchor[0] + 0.16), anchor[1])
            if not point_in_polygon(polygon, parked[0], parked[1]):
                parked = anchor
            objects.append({"class_name": "vehicle", "vehicle_type": "forklift", "outfit": None, "nx": parked[0], "ny": parked[1]})
    return objects


def _restricted_traffic(polygon: list[list[float]], now: float, hold_inside: bool, phase: float) -> list[dict]:
    """A person and a car come and go; a forklift, which is allowed, stays parked inside."""
    spots = _spots(polygon, 3)
    if len(spots) < 3:
        return []
    walker, car, parked = spots
    objects = []
    position = walk(now, polygon, walker, hold_inside, phase, start=_entry(polygon, walker))
    objects.append({"class_name": "person", "outfit": FULL_KIT, "nx": position[0], "ny": position[1]})
    position = walk(now, polygon, car, hold_inside, phase + PERIOD_S / 2, start=_entry(polygon, car))
    objects.append({"class_name": "vehicle", "vehicle_type": "car", "outfit": None, "nx": position[0], "ny": position[1]})
    objects.append({"class_name": "vehicle", "vehicle_type": "forklift", "outfit": None, "nx": parked[0], "ny": parked[1]})
    return objects


# The six WHO hand-washing steps, in order.
WASH_STEPS = ("palms", "backs", "interlaced", "fingers", "thumbs", "fingertips")
WASH_STEP_S = 5.0
# At each hand-wash station: a full wash, a pause, a wash that stops after three steps, a longer pause.
WASH_PLAN = [(0.0, WASH_STEPS), (40.0, WASH_STEPS[:3])]
WASH_PERIOD_S = 70.0


def scripted_wash(zone: dict, now: float, hold_inside: bool) -> tuple[str, tuple[float, float]] | None:
    """The step being done at a hand-wash station now and where the hands are, or None between washes.

    Simulate holds the hands in the sink doing only the first step, so the wash ends short.
    """
    if zone.get("zone_type") != "HANDWASH_STATION":
        return None
    spot = representative_point(zone.get("polygon"))
    if spot is None:
        return None
    if hold_inside:
        return WASH_STEPS[0], spot
    moment = now % WASH_PERIOD_S
    for start, steps in WASH_PLAN:
        index = int((moment - start) // WASH_STEP_S)
        if 0 <= index < len(steps):
            return steps[index], spot
    return None

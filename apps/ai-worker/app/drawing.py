import cv2
import numpy as np

from app.handpose import FINGERTIPS, HAND_BONES

# Hand joints are drawn in a deep teal, whatever the wash's state, with the fingertips in amber. Both read on skin
# and on the white sink, and neither is taken by the done, missed or not-yet colours. BGR.
SKELETON_COLOR = (136, 148, 13)
FINGERTIP_COLOR = (11, 158, 245)

ZONE_COLORS = {
    "PPE_ZONE": (200, 80, 140),
    "RESTRICTED_AREA": (40, 70, 210),
    "MACHINE_DANGER_ZONE": (30, 30, 180),
    "FORKLIFT_LANE": (20, 140, 220),
    "PRODUCTION_ZONE": (160, 110, 20),
    "PACKING_ZONE": (80, 140, 40),
    "HANDWASH_STATION": (190, 150, 30),
}

CHECK_COLORS = {
    "violation": (40, 60, 200),
    "unknown": (120, 120, 120),
    "ok": (40, 140, 70),
}
NO_RULE_COLOR = (150, 110, 60)
VEHICLE_COLOR = (30, 130, 230)


def track_color(track: dict) -> tuple[int, int, int]:
    """A person or vehicle takes the colour of their worst rule check; with no rule in play they stay neutral."""
    states = {check.get("state") for check in track.get("checks") or []}
    for state in ("violation", "unknown", "ok"):
        if state in states:
            return CHECK_COLORS[state]
    return NO_RULE_COLOR if track.get("class_name") == "person" else VEHICLE_COLOR


# One letter per PPE item on a person's tag. Its colour is the state: green worn, red missing, grey unknown.
ITEM_LETTERS = {"helmet": "H", "clothing": "C", "shoes": "S", "mask": "M"}
ITEM_NAMES = {"helmet": "helmet", "clothing": "clothing", "shoes": "shoes", "mask": "mask"}


def track_tag(track: dict) -> list[tuple[str, tuple[int, int, int]]]:
    """One line of segments above a box: the id, then a coloured letter per PPE check, then any zone breach.
    A vehicle shows its type, coloured by whether it may be there. Hands at a sink show how long they have
    washed, then the number of each checked WHO step."""
    if track.get("class_name") == "hands":
        segments = [(f"Wash {track.get('wash_s', 0)}s", track_color(track))]
        return segments + [(check["item"].removeprefix("step"), CHECK_COLORS.get(check.get("state"), CHECK_COLORS["unknown"])) for check in track.get("checks") or []]
    if track.get("class_name") != "person":
        return [(f"{(track.get('vehicle_type') or 'vehicle').capitalize()} {track['track_id']}", track_color(track))]
    segments = [(f"#{track['track_id']}", track_color(track))]
    for check in track.get("checks") or []:
        color = CHECK_COLORS.get(check.get("state"), CHECK_COLORS["unknown"])
        segments.append((ITEM_LETTERS.get(check.get("item"), check.get("text", "")), color))
    return segments


def synthetic_frame(width: int, height: int, title: str) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:] = (196, 202, 206)
    cv2.rectangle(image, (0, int(height * 0.62)), (width, height), (176, 182, 186), -1)
    cv2.putText(image, title, (20, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (45, 52, 58), 2, cv2.LINE_AA)
    return image


def jpeg_bytes(image: np.ndarray, quality: int = 70) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return b""
    return encoded.tobytes()


def annotate(image: np.ndarray, zones: list[dict], tracks: list[dict], note: str = "") -> np.ndarray:
    """note is a line for the top left of an incident snapshot, such as the steps a wash missed."""
    canvas = image.copy()
    height, width = canvas.shape[:2]
    for zone in zones:
        name = zone.get("name") or zone.get("zone_type") or "Zone"
        points = zone.get("polygon") or []
        if len(points) < 3:
            # A paused zone has no place in this view, so it is not drawn. The camera page lists it.
            continue
        contour = np.array([[int(x * width), int(y * height)] for x, y in points], dtype=np.int32)
        color = ZONE_COLORS.get(zone.get("zone_type"), (80, 80, 80))
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [contour], color)
        cv2.addWeighted(overlay, 0.18, canvas, 0.82, 0, canvas)
        cv2.polylines(canvas, [contour], True, color, 2)
        label_at = contour[0]
        suffix = " (auto-aligned)" if zone.get("view_state") == "SHIFTED" else ""
        _label(canvas, name + suffix, int(label_at[0]), int(label_at[1]) - 6, color)
    taken: list[tuple[int, int, int, int]] = []
    items: set[str] = set()
    steps: dict[str, str] = {}
    # People nearer the camera are drawn last, so their tags sit on top.
    for track in sorted(tracks, key=lambda item: (item.get("draw_box") or item["bbox_xyxy"])[3]):
        x1, y1, x2, y2 = [int(v) for v in track.get("draw_box") or track["bbox_xyxy"]]
        checks = track.get("checks") or []
        if track.get("class_name") == "hands":
            steps.update((check["item"], check["text"]) for check in checks)
        else:
            items.update(check.get("item") for check in checks if check.get("item") in ITEM_LETTERS)
        if track.get("joints"):
            _hand_scan(canvas, track["joints"])
            _corners(canvas, (x1, y1, x2, y2), track_color(track))
        else:
            cv2.rectangle(canvas, (x1, y1), (x2, y2), track_color(track), 2 if checks or track.get("class_name") != "person" else 1)
        _tag(canvas, track_tag(track), x1, y1, y2, taken)
    rows = 0
    if items:
        _legend(canvas, [(f"{ITEM_LETTERS[item]} {ITEM_NAMES[item]}", (60, 60, 60)) for item in ITEM_LETTERS if item in items], ("worn", "missing", "unknown"), rows)
        rows += 1
    if steps:
        _legend(canvas, [(steps[item], (60, 60, 60)) for item in sorted(steps)], ("done", "missed", "not yet"), rows)
    if note:
        _label(canvas, note, 8, 26, CHECK_COLORS["violation"])
    return canvas


def _tag(image: np.ndarray, segments: list[tuple[str, tuple[int, int, int]]], x: int, top: int, bottom: int, taken: list) -> None:
    """Draws the tag just above the box, or lower down inside it when another tag already holds that spot."""
    font, scale = cv2.FONT_HERSHEY_SIMPLEX, 0.5
    sizes = [cv2.getTextSize(text, font, scale, 1)[0] for text, _ in segments]
    width = sum(size[0] + 10 for size in sizes)
    height = max(size[1] for size in sizes) + 10
    x = max(0, min(x, image.shape[1] - width))
    spot = None
    for y in [top - height - 2] + [top + 2 + step * (height + 2) for step in range(4)]:
        box = (x, max(0, y), x + width, max(0, y) + height)
        if box[3] <= max(bottom, top + height) and not any(_overlap(box, other) for other in taken):
            spot = box
            break
    spot = spot or (x, max(0, top - height - 2), x + width, max(0, top - height - 2) + height)
    taken.append(spot)
    cursor = spot[0]
    for (text, color), size in zip(segments, sizes):
        cv2.rectangle(image, (cursor, spot[1]), (cursor + size[0] + 10, spot[3]), color, -1)
        cv2.putText(image, text, (cursor + 5, spot[3] - 5), font, scale, (255, 255, 255), 1, cv2.LINE_AA)
        cursor += size[0] + 10


def _hand_scan(image: np.ndarray, hands: list) -> None:
    """Each hand's skeleton in thin lines, with a white-centred dot per joint and a bigger amber one per fingertip."""
    for joints in hands:
        points = [(int(x), int(y)) for x, y in joints]
        for a, b in HAND_BONES:
            cv2.line(image, points[a], points[b], SKELETON_COLOR, 2, cv2.LINE_AA)
        for index, point in enumerate(points):
            tip = index in FINGERTIPS
            cv2.circle(image, point, 6 if tip else 4, FINGERTIP_COLOR if tip else SKELETON_COLOR, -1, cv2.LINE_AA)
            cv2.circle(image, point, 2, (250, 250, 250), -1, cv2.LINE_AA)


def _corners(image: np.ndarray, box: tuple[int, int, int, int], color: tuple[int, int, int]) -> None:
    """Scanner corners round a box instead of a full rectangle."""
    x1, y1, x2, y2 = box
    reach = max(8, int(0.18 * min(x2 - x1, y2 - y1)))
    for x, y, dx, dy in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        cv2.line(image, (x, y), (x + dx * reach, y), color, 3, cv2.LINE_AA)
        cv2.line(image, (x, y), (x, y + dy * reach), color, 3, cv2.LINE_AA)


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _legend(image: np.ndarray, lines: list[tuple[str, tuple[int, int, int]]], states: tuple[str, str, str], row: int = 0) -> None:
    """One row in the bottom right corner: what each letter or number means, then the ok, violation and unknown colours."""
    lines = lines + [(text, CHECK_COLORS[state]) for text, state in zip(states, ("ok", "violation", "unknown"))]
    font, scale = cv2.FONT_HERSHEY_SIMPLEX, 0.42
    widths = [cv2.getTextSize(text, font, scale, 1)[0][0] for text, _ in lines]
    x = image.shape[1] - sum(widths) - 10 * len(lines) - 8
    y = image.shape[0] - 10 - 24 * row
    for (text, color), text_width in zip(lines, widths):
        cv2.rectangle(image, (x, y - 16), (x + text_width + 8, y + 4), color, -1)
        cv2.putText(image, text, (x + 4, y - 2), font, scale, (255, 255, 255), 1, cv2.LINE_AA)
        x += text_width + 10


def _label(image: np.ndarray, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.45
    (width, height), _ = cv2.getTextSize(text, font, scale, 1)
    y = max(height + 4, y)
    x = max(0, min(x, image.shape[1] - width - 8))
    cv2.rectangle(image, (x, y - height - 6), (x + width + 8, y + 4), color, -1)
    cv2.putText(image, text, (x + 4, y - 2), font, scale, (255, 255, 255), 1, cv2.LINE_AA)

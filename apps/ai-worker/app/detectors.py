"""Model adapters.

DEMO_MODE uses scripted detections so the workflow can be shown without weights.
REAL_AI_MODE uses an installed ONNX detector for people and vehicles, with HOG (people only) as the fallback.
COCO has no forklift, so a separate forklift detector adds them on cameras with zone rules.
Every detection is a person or a vehicle. A vehicle carries a vehicle_type: car, truck, bus, motorcycle or forklift.
Hand-washing gestures are a separate detector, run only on cameras with a hand-wash rule.
"""

import ast
from pathlib import Path

import cv2
import numpy as np

from app.handpose import build_hand_pose, hand_square, hands_box
from app.handwash import step_of
from app.scenes import WASH_STEPS, scripted_objects, scripted_wash

PERSON_CLASS = 0
VEHICLE_CLASS = 2
# COCO ids the official YOLOX models detect, other than person. There is no forklift class: forklifts come out as trucks.
COCO_VEHICLES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

PPE_ITEMS = ("helmet", "clothing", "shoes", "mask")
# ppe.onnx class ids. Each item has one id for worn and one for missing.
PPE_CLASSES = {
    0: ("helmet", "YES"),
    1: ("helmet", "NO"),
    2: ("clothing", "YES"),
    3: ("clothing", "NO"),
    4: ("shoes", "YES"),
    5: ("shoes", "NO"),
    6: ("mask", "YES"),
    7: ("mask", "NO"),
}
# Where on the person box each item is looked for, as fractions of its height from the top.
PPE_BANDS = {"helmet": (0.0, 0.25), "mask": (0.05, 0.35), "clothing": (0.15, 0.80), "shoes": (0.75, 1.0)}


def unknown_ppe() -> dict[str, tuple[str, float]]:
    return {item: ("UNKNOWN", 0.0) for item in PPE_ITEMS}


def _box(nx: float, ny: float, width: int, height: int, bw: float, bh: float) -> list[float]:
    """(nx, ny) is where the object stands on the floor, so it is the bottom centre of the box."""
    x1 = max(0.0, nx - bw / 2) * width
    y1 = max(0.0, ny - bh) * height
    x2 = min(1.0, nx + bw / 2) * width
    y2 = min(1.0, ny) * height
    return [x1, y1, x2, y2]


class DemoDetector:
    def detect(self, frame, zones: list[dict], now: float, hold_inside: bool) -> list[dict]:
        height, width = frame.shape[:2]
        detections = []
        for item in scripted_objects(zones, now, hold_inside):
            vehicle = item["class_name"] == "vehicle"
            size = {"forklift": (0.14, 0.16), "car": (0.16, 0.12)}.get(item.get("vehicle_type"), (0.08, 0.24))
            detections.append(
                {
                    "class_name": item["class_name"],
                    "class_id": VEHICLE_CLASS if vehicle else PERSON_CLASS,
                    "confidence": 0.93 if vehicle else 0.9,
                    "bbox_xyxy": _box(item["nx"], item["ny"], width, height, *size),
                    "outfit": item.get("outfit"),
                    "vehicle_type": item.get("vehicle_type"),
                }
            )
        return detections


class HogPersonDetector:
    def __init__(self):
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame, zones: list[dict], now: float, hold_inside: bool) -> list[dict]:
        del zones, now, hold_inside
        scale = 640.0 / max(frame.shape[1], 1)
        small = cv2.resize(frame, (640, max(64, int(frame.shape[0] * scale))))
        rects, weights = self.hog.detectMultiScale(small, hitThreshold=0.2, winStride=(8, 8), padding=(8, 8), scale=1.05)
        inverse = 1.0 / scale
        detections = []
        for (x, y, w, h), weight in zip(rects, weights):
            box = [x * inverse, y * inverse, (x + w) * inverse, (y + h) * inverse]
            detections.append(
                {
                    "class_name": "person",
                    "class_id": PERSON_CLASS,
                    "confidence": float(min(0.99, max(0.35, weight))),
                    "bbox_xyxy": box,
                }
            )
        return detections


class ForkliftDetector:
    """forklift.onnx: a YOLOv8 detector trained on forklifts, exported by tools/forklift_yolo/export_forklift_onnx.py.

    COCO has no forklift class. On the port clip YOLOX-Nano read the forklift as a truck at 0.55 or more, enough to
    start a track, in 6 of 55 frames, and not at all while it was far off; this model found it in 52, and at 0.3 or
    more, enough to keep a track going, in all 55. The whole frame goes in, letterboxed: the file is exported at
    512x896, the shape of a 16:9 frame, about 60 ms on 2 threads. Input size and class names are read from the file.
    Only forklift boxes are kept; people come from the person detector.
    """

    def __init__(self, path: str, providers: list[str], threads: int = 2, threshold: float = 0.30):
        self.session = onnx_session(path, providers, threads)
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        self.input_h = int(shape[2]) if isinstance(shape[2], int) else 640
        self.input_w = int(shape[3]) if isinstance(shape[3], int) else 640
        meta = self.session.get_modelmeta().custom_metadata_map
        names = ast.literal_eval(meta["names"]) if "names" in meta else {}
        forklift = [index for index, name in names.items() if name == "forklift"]
        if not forklift:
            raise ValueError("forklift.onnx names no forklift class")
        self.forklift_class = forklift[0]
        self.classes = len(names)
        self.threshold = threshold

    def detect(self, frame) -> list[dict]:
        height, width = frame.shape[:2]
        canvas, transform = _model_canvas(frame, self.input_w, self.input_h, True)
        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        output = np.asarray(self.session.run(None, {self.input_name: np.transpose(rgb, (2, 0, 1))[None]})[0])
        found = []
        for class_id, score, (x1, y1, x2, y2) in decode_boxes(output, self.classes, self.input_w, self.input_h, *transform, threshold=self.threshold):
            if class_id != self.forklift_class:
                continue
            found.append(
                {
                    "class_name": "vehicle",
                    "class_id": VEHICLE_CLASS,
                    "vehicle_type": "forklift",
                    "confidence": score,
                    "bbox_xyxy": [float(np.clip(x1, 0, width - 1)), float(np.clip(y1, 0, height - 1)), float(np.clip(x2, 0, width - 1)), float(np.clip(y2, 0, height - 1))],
                }
            )
        return _nms(found, 0.45, by_confidence=True)


class NoForkliftDetector:
    """DEMO scripts its forklifts, and REAL mode without forklift.onnx has only the person detector's trucks."""

    def detect(self, frame) -> list[dict]:
        del frame
        return []


# COCO vehicles the person detector knows well, and the score from which its read wins over the forklift model's.
# The forklift model, trained on photos with no cars in them, read the port clip's white car as a forklift at up to
# 0.89, and once boxed the car and the forklift behind it as one forklift. The person detector read that car at 0.8
# or more in every frame, and the forklift as a car at most 0.61, while it left the frame.
NOT_FORKLIFTS = {"car", "bus"}
SURE_CAR = 0.7


def with_forklifts(detections: list[dict], forklifts: list[dict]) -> list[dict]:
    """The person detector's boxes plus the forklifts.

    A forklift box on a sure COCO car or bus is dropped. Any other COCO vehicle on a forklift box, such as a truck,
    a motorcycle or a weak car, is the forklift misread, and gives way to it. People are kept: a driver sits inside
    the forklift's box.
    """
    cars = [
        detection["bbox_xyxy"]
        for detection in detections
        if detection["class_name"] == "vehicle" and detection.get("vehicle_type") in NOT_FORKLIFTS and detection["confidence"] >= SURE_CAR
    ]
    forklifts = [forklift for forklift in forklifts if not any(_iou(forklift["bbox_xyxy"], car) >= 0.3 or share_inside(car, forklift["bbox_xyxy"]) >= 0.5 for car in cars)]
    kept = [
        detection
        for detection in detections
        if detection["class_name"] != "vehicle"
        or detection["bbox_xyxy"] in cars
        or all(_iou(detection["bbox_xyxy"], forklift["bbox_xyxy"]) < 0.3 for forklift in forklifts)
    ]
    return kept + forklifts


def build_forklift_detector(mode: str, model_path: str, device: str, threads: int = 2):
    path = Path(model_path) / "forklift.onnx"
    if mode.upper() == "DEMO" or not path.exists():
        return NoForkliftDetector()
    return ForkliftDetector(str(path), providers_for(device), threads)


class DemoPPEClassifier:
    """Returns the outfit the scripted scene gave the person. The pixels are not read."""

    def classify(self, crop, context: dict | None = None) -> dict[str, tuple[str, float]]:
        del crop
        outfit = (context or {}).get("outfit") or {}
        result = unknown_ppe()
        for item in PPE_ITEMS:
            state = outfit.get(item, "UNKNOWN")
            if state in {"YES", "NO"}:
                result[item] = (state, 0.9 if state == "YES" else 0.84)
        return result


class UnknownPPEClassifier:
    def classify(self, crop, context: dict | None = None) -> dict[str, tuple[str, float]]:
        del crop, context
        return unknown_ppe()


# Bands of a standing person's box, as fractions of its height from the top, for a raised CCTV view.
HEAD_BAND = (0.0, 0.06)
TORSO_BAND = (0.18, 0.48)
LEGS_BAND = (0.55, 0.88)


class FaceFinder:
    """YuNet face detector from the OpenCV Zoo (MIT). Finds a person's face with eye, nose and mouth points.

    It runs on the head region of the person box, enlarged so a CCTV-sized face is big enough to find.
    A face turned away is not found, and then helmet and mask fall back or stay UNKNOWN.
    """

    HEAD_SIDE = 160

    def __init__(self, path: str):
        self.detector = cv2.FaceDetectorYN.create(str(path), "", (self.HEAD_SIDE, self.HEAD_SIDE), 0.5, 0.3, 5)

    def find(self, frame: np.ndarray, box: list[float]) -> dict | None:
        x1, y1, x2, y2 = box
        width, height = x2 - x1, y2 - y1
        left, right = max(0, int(x1 - 0.1 * width)), min(frame.shape[1], int(x2 + 0.1 * width))
        top, bottom = max(0, int(y1 - 0.03 * height)), min(frame.shape[0], int(y1 + 0.28 * height))
        head = frame[top:bottom, left:right]
        if head.shape[0] < 12 or head.shape[1] < 12:
            return None
        scale = self.HEAD_SIDE / max(head.shape[:2])
        image = cv2.resize(head, (max(1, round(head.shape[1] * scale)), max(1, round(head.shape[0] * scale))), interpolation=cv2.INTER_CUBIC)
        self.detector.setInputSize((image.shape[1], image.shape[0]))
        _, faces = self.detector.detect(image)
        if faces is None:
            return None
        # Another worker's face can sit in the margin. Keep faces centred inside this person's box.
        inside = [face for face in faces if (x1 - left) * scale <= face[0] + face[2] / 2 <= (x2 - left) * scale]
        if not inside:
            return None
        best = max(inside, key=lambda face: face[14])
        return {"image": image, "box": [float(v) for v in best[:4]], "points": best[4:14].reshape(5, 2).astype(float), "score": float(best[14])}


class ColorPPEClassifier:
    """Fallback when ppe.onnx is missing. It reads colours, so it only suits POC testing on a clear view.

    Helmet: a white, yellow, orange or red hard hat just above the face, or on top of the box when the
    person faces away. Dark hair or bare skin there is none.
    Clothing: a coverall. Grey, beige, white or blue workwear on the torso that carries on down the legs.
    A brightly coloured top, or a work-coloured top over dark trousers, is not one.
    Mask: needs a face. With mask.onnx a trained classifier reads it, which also catches a mask pulled
    under the chin and bare faces seen side on. Without it, skin over the chin that matches the
    forehead on a face turned to the camera is no mask.
    Shoes cannot be judged by colour and stay UNKNOWN.
    """

    def __init__(self, faces: FaceFinder | None = None, masks: "MaskClassifier | None" = None):
        self.faces = faces
        self.masks = masks

    def classify(self, crop, context: dict | None = None) -> dict[str, tuple[str, float]]:
        context = context or {}
        result = unknown_ppe()
        if crop is None or getattr(crop, "size", 0) == 0 or crop.shape[0] < 100 or crop.shape[1] < 30:
            return result
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        face = None
        if self.faces is not None and context.get("frame") is not None and context.get("box") is not None:
            face = self.faces.find(context["frame"], context["box"])
        if face is not None:
            result["helmet"] = _helmet_above_face(face)
            result["mask"] = self.masks.judge(face) if self.masks is not None else _mask_on_face(face)
        else:
            result["helmet"] = _helmet_from_head(_band(hsv, HEAD_BAND, 0.25, 0.75))
        legs_visible = crop.shape[0] >= 2.0 * crop.shape[1]
        result["clothing"] = _clothing_from_body(crop, hsv, legs_visible)
        return result


class MaskClassifier:
    """mask.onnx: MobileNetV3-Small trained on face crops by tools/mask_classifier/train_mask.py.

    Input 1x3x96x96 RGB, ImageNet-normalised. Logits for: mask worn incorrectly, mask worn, no mask.
    Worn incorrectly, such as under the chin or below the nose, counts as NO. Under the confidence
    floor the face stays UNKNOWN. A floor of 0.7 was the lowest with no wrong alert on four test clips:
    at 0.6 two masked workers looking down were flagged.
    """

    SIZE = 96
    MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def __init__(self, path: str, providers: list[str], threads: int = 1, floor: float = 0.7):
        self.session = onnx_session(path, providers, threads)
        self.input_name = self.session.get_inputs()[0].name
        self.floor = floor

    def judge(self, face: dict) -> tuple[str, float]:
        crop = face_crop(face, self.SIZE)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = ((rgb - self.MEAN) / self.STD).transpose(2, 0, 1)[None]
        incorrect, worn, bare = _softmax(np.asarray(self.session.run(None, {self.input_name: tensor})[0]).reshape(-1)[:3])
        if worn >= self.floor:
            return "YES", round(float(worn), 3)
        if incorrect + bare >= self.floor:
            return "NO", round(float(incorrect + bare), 3)
        return "UNKNOWN", 0.0


def face_crop(face: dict, size: int) -> np.ndarray:
    """The face box with some forehead and chin around it, padded square, as the classifier was trained."""
    image = face["image"]
    x, y, width, height = face["box"]
    x1, y1 = int(max(0, x - 0.15 * width)), int(max(0, y - 0.2 * height))
    x2, y2 = int(min(image.shape[1], x + 1.15 * width)), int(min(image.shape[0], y + 1.15 * height))
    crop = image[y1:y2, x1:x2]
    side = max(crop.shape[:2])
    canvas = np.full((side, side, 3), 127, dtype=np.uint8)
    top, left = (side - crop.shape[0]) // 2, (side - crop.shape[1]) // 2
    canvas[top : top + crop.shape[0], left : left + crop.shape[1]] = crop
    return cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA)


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = np.exp(values - values.max())
    return shifted / shifted.sum()


def _band(image: np.ndarray, rows: tuple[float, float], left: float = 0.2, right: float = 0.8) -> np.ndarray:
    height, width = image.shape[:2]
    top, bottom = int(height * rows[0]), max(int(height * rows[0]) + 1, int(height * rows[1]))
    x1, x2 = int(width * left), max(int(width * left) + 1, int(width * right))
    return image[top:bottom, x1:x2]


def _skin(hsv: np.ndarray) -> np.ndarray:
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    return (hue <= 20) & (sat >= 40) & (sat <= 160) & (val >= 60)


def _hard_hat(hsv: np.ndarray) -> np.ndarray:
    # Blue is left out: blue bins and racks behind a bare head would read as a helmet.
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    white = (sat < 45) & (val >= 165)
    yellow = (hue >= 18) & (hue <= 34) & (sat >= 90) & (val >= 110)
    orange = (hue >= 5) & (hue < 18) & (sat > 160) & (val >= 110)
    red = ((hue < 5) | (hue >= 165)) & (sat >= 140) & (val >= 80)
    return white | yellow | orange | red


def head_stats(head: np.ndarray) -> dict[str, float]:
    if head.size == 0:
        return {"hat": 0.0, "hair": 0.0, "skin": 0.0}
    sat, val = head[:, :, 1], head[:, :, 2]
    hat = _hard_hat(head)
    return {
        "hat": float(hat.mean()),
        "hair": float(((val < 75) & (sat < 120) & ~hat).mean()),
        "skin": float((_skin(head) & ~hat).mean()),
    }


def _helmet_from_head(head: np.ndarray) -> tuple[str, float]:
    """Seen from behind, the top of the box. A light floor or wall can sit beside the head, so only strong evidence counts."""
    stats = head_stats(head)
    if stats["hat"] >= 0.35 and stats["hair"] < 0.15:
        return "YES", round(min(0.9, 0.5 + stats["hat"] * 0.4), 3)
    if stats["hair"] >= 0.45 and stats["hat"] < 0.20:
        return "NO", round(min(0.9, 0.5 + stats["hair"] * 0.4), 3)
    return "UNKNOWN", 0.0


def helmet_region(face: dict) -> np.ndarray:
    """The band just above the face: the brim and shell of a helmet, or the hair of a bare head."""
    x, y, width, height = face["box"]
    image = face["image"]
    return image[max(0, int(y - 0.5 * height)) : max(0, int(y)), max(0, int(x - 0.1 * width)) : max(0, int(x + 1.1 * width))]


def _helmet_above_face(face: dict) -> tuple[str, float]:
    """Hair is dark; a hard hat of any colour is not. Measured on two clips with white, yellow and ochre
    helmets: bare heads were 66-92% dark just above the face, helmets 0-15%. A black helmet would read as hair.
    """
    region = helmet_region(face)
    if region.shape[0] < 3 or region.shape[1] < 3:
        return "UNKNOWN", 0.0
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    dark = float(((hsv[:, :, 2] < 80) & (hsv[:, :, 1] < 130)).mean())
    if dark >= 0.45:
        return "NO", round(min(0.9, 0.5 + dark * 0.4), 3)
    if dark <= 0.20:
        return "YES", round(min(0.9, 0.9 - dark), 3)
    return "UNKNOWN", 0.0


def _mask_colour(hsv: np.ndarray) -> np.ndarray:
    # Surgical blue or green, and white or grey cloth. Skin is never this blue or this grey.
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    surgical = (hue >= 80) & (hue <= 125) & (sat >= 20) & (val >= 70)
    plain = (sat < 30) & (val >= 120)
    return surgical | plain


def mask_stats(face: dict) -> dict[str, float]:
    """The chin strip of the face box, where a mask shows even when the head is tilted, against the forehead."""
    right_eye, left_eye, nose = face["points"][:3]
    x, y, width, height = face["box"]
    eyes = float(np.linalg.norm(left_eye - right_eye))
    empty = {"frontal": 0.0, "forehead_skin": 0.0, "mask_colour": 0.0, "bare": 0.0}
    if eyes < 4 or width < 8 or height < 8:
        return empty
    image = face["image"]
    middle = (right_eye + left_eye) / 2
    reach = 0.2 * eyes
    forehead = image[max(0, int(middle[1] - 0.25 * eyes - reach)) : max(0, int(middle[1] - 0.25 * eyes + reach)), max(0, int(middle[0] - reach)) : max(0, int(middle[0] + reach))]
    chin = image[max(0, int(y + 0.65 * height)) : max(0, int(y + 1.05 * height)), max(0, int(x + 0.2 * width)) : max(0, int(x + 0.8 * width))]
    if forehead.size == 0 or chin.size == 0:
        return empty
    reference = np.median(cv2.cvtColor(forehead, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32), axis=0)
    chin_lab = cv2.cvtColor(chin, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    distance = np.sqrt(((chin_lab[:, 0] - reference[0]) * 0.5) ** 2 + (chin_lab[:, 1] - reference[1]) ** 2 + (chin_lab[:, 2] - reference[2]) ** 2)
    # Facing the camera: the nose sits between the eyes, and the eyes span much of the face.
    frontal = abs(float(nose[0] - middle[0])) <= 0.25 * eyes and eyes >= 0.35 * width
    return {
        "frontal": 1.0 if frontal else 0.0,
        "forehead_skin": float(_skin(cv2.cvtColor(forehead, cv2.COLOR_BGR2HSV)).mean()),
        "mask_colour": float(_mask_colour(cv2.cvtColor(chin, cv2.COLOR_BGR2HSV)).mean()),
        "bare": float((distance <= 18).mean()),
    }


def _mask_on_face(face: dict) -> tuple[str, float]:
    stats = mask_stats(face)
    if stats["mask_colour"] >= 0.25:
        return "YES", round(min(0.9, 0.5 + stats["mask_colour"] * 0.5), 3)
    # No is only called on a face turned to the camera with skin to compare against, never on a profile.
    if stats["frontal"] and stats["forehead_skin"] >= 0.3 and stats["bare"] >= 0.55 and stats["mask_colour"] < 0.08:
        return "NO", round(min(0.9, 0.5 + stats["bare"] * 0.4), 3)
    return "UNKNOWN", 0.0


def _workwear(hsv: np.ndarray) -> np.ndarray:
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    plain = (sat < 60) & (val >= 70) & (val <= 245)
    blue = (hue >= 95) & (hue <= 125) & (sat >= 60) & (val >= 40) & (val <= 200)
    return plain | blue


def clothing_stats(crop: np.ndarray, hsv: np.ndarray) -> dict[str, float]:
    torso = _band(hsv, TORSO_BAND)
    work = _workwear(torso)
    sat, val = torso[:, :, 1], torso[:, :, 2]
    loud = (sat >= 90) & (val >= 60) & ~work & ~_skin(torso)
    legs_hsv = _band(hsv, LEGS_BAND, 0.25, 0.75)
    stats = {"work": float(work.mean()), "loud": float(loud.mean()), "legs_match": 0.0, "legs_dark": 0.0}
    if not work.any() or legs_hsv.size == 0:
        return stats
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    reference = np.median(_band(lab, TORSO_BAND)[work], axis=0)
    legs = _band(lab, LEGS_BAND, 0.25, 0.75)
    # Lightness counts half, so a coverall leg in shadow still matches its sleeve.
    distance = np.sqrt(((legs[:, :, 0] - reference[0]) * 0.5) ** 2 + (legs[:, :, 1] - reference[1]) ** 2 + (legs[:, :, 2] - reference[2]) ** 2)
    stats["legs_match"] = float((distance <= 25).mean())
    stats["legs_dark"] = float(((legs_hsv[:, :, 2] < 70) & (legs_hsv[:, :, 1] < 100)).mean())
    return stats


def _clothing_from_body(crop: np.ndarray, hsv: np.ndarray, legs_visible: bool) -> tuple[str, float]:
    stats = clothing_stats(crop, hsv)
    if stats["loud"] >= 0.35:
        return "NO", round(min(0.9, 0.5 + stats["loud"] * 0.4), 3)
    if stats["work"] < 0.5 or not legs_visible:
        return "UNKNOWN", 0.0
    if stats["legs_match"] >= 0.30:
        return "YES", round(min(0.9, 0.5 + stats["legs_match"] * 0.4), 3)
    if stats["legs_dark"] >= 0.50 and stats["legs_match"] < 0.25:
        return "NO", round(min(0.9, 0.5 + stats["legs_dark"] * 0.4), 3)
    return "UNKNOWN", 0.0


class OnnxPPEDetector:
    """ppe.onnx: a detector for worn and missing PPE, run on each person crop.

    Output is Nx6 rows (x1, y1, x2, y2, score, class_id) in model pixels, or a YOLO
    head (1, 12, anchors): cx, cy, w, h, then one score per class id in PPE_CLASSES.
    An item takes the best box whose centre lies in that item's band of the person.
    With no such box the item stays UNKNOWN.
    """

    def __init__(self, path: str, providers: list[str], threads: int = 2):
        self.session = onnx_session(path, providers, threads)
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        self.input_h = int(shape[2]) if isinstance(shape[2], int) else 640
        self.input_w = int(shape[3]) if isinstance(shape[3], int) else 640
        self._letterbox: bool | None = None

    def classify(self, crop, context: dict | None = None) -> dict[str, tuple[str, float]]:
        del context
        if crop is None or getattr(crop, "size", 0) == 0:
            return unknown_ppe()
        letterbox = bool(self._letterbox)
        output, transform = self._infer(crop, letterbox)
        if self._letterbox is None:
            # A YOLO head is trained on letterboxed images. Nx6 exports take a plain resize.
            self._letterbox = _is_yolo_head(output, len(PPE_CLASSES))
            if self._letterbox:
                output, transform = self._infer(crop, True)
        boxes = decode_boxes(output, len(PPE_CLASSES), self.input_w, self.input_h, *transform)
        return ppe_from_boxes(boxes, crop.shape[1], crop.shape[0])

    def _infer(self, image: np.ndarray, letterbox: bool):
        canvas, transform = _model_canvas(image, self.input_w, self.input_h, letterbox)
        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = np.transpose(rgb, (2, 0, 1))[None, :, :, :]
        return np.asarray(self.session.run(None, {self.input_name: tensor})[0]), transform


def _is_yolo_head(output, classes: int) -> bool:
    """(anchors, 4+classes) or (4+classes, anchors). Nx6 rows are never a head."""
    rows = np.squeeze(np.asarray(output))
    channels = 4 + classes
    return rows.ndim == 2 and (rows.shape[1] == channels or (rows.shape[0] == channels and rows.shape[1] != 6))


def _model_canvas(image: np.ndarray, input_w: int, input_h: int, letterbox: bool, scale: float = 1.0):
    """The model image, and how to map its pixels back: image = (model - pad) / gain.

    A scale under 1 letterboxes the image smaller, centred on grey, as if the camera were further away.
    """
    height, width = image.shape[:2]
    if not letterbox:
        return cv2.resize(image, (input_w, input_h)), (input_w / max(width, 1), input_h / max(height, 1), 0.0, 0.0)
    gain = min(input_w / max(width, 1), input_h / max(height, 1)) * min(1.0, max(0.1, scale))
    resized = cv2.resize(image, (max(int(round(width * gain)), 1), max(int(round(height * gain)), 1)))
    canvas = np.full((input_h, input_w, 3), 114, dtype=np.uint8)
    pad_x = (input_w - resized.shape[1]) // 2
    pad_y = (input_h - resized.shape[0]) // 2
    canvas[pad_y : pad_y + resized.shape[0], pad_x : pad_x + resized.shape[1]] = resized
    return canvas, (gain, gain, float(pad_x), float(pad_y))


def decode_boxes(
    output,
    classes: int,
    input_w: int,
    input_h: int,
    gain_x: float = 1.0,
    gain_y: float = 1.0,
    pad_x: float = 0.0,
    pad_y: float = 0.0,
    threshold: float = 0.35,
) -> list[tuple[int, float, list[float]]]:
    """(class_id, score, [x1, y1, x2, y2]) in image pixels, from Nx6 rows or a YOLO head."""
    rows = np.squeeze(np.asarray(output, dtype=np.float32))
    if rows.ndim == 1:
        rows = rows[None, :]
    if rows.ndim != 2:
        return []
    channels = 4 + classes
    if _is_yolo_head(rows, classes):
        if rows.shape[1] != channels:
            rows = rows.T
        centre_x, centre_y, box_w, box_h = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3]
        if rows.size and float(np.abs(rows[:, :4]).max()) <= 1.5:
            centre_x, centre_y, box_w, box_h = centre_x * input_w, centre_y * input_h, box_w * input_w, box_h * input_h
        class_ids = np.argmax(rows[:, 4:channels], axis=1)
        scores = rows[np.arange(len(rows)), 4 + class_ids]
        corners = np.stack([centre_x - box_w / 2, centre_y - box_h / 2, centre_x + box_w / 2, centre_y + box_h / 2], axis=1)
    elif rows.shape[1] >= 6:
        corners, scores, class_ids = rows[:, :4], rows[:, 4], rows[:, 5].astype(int)
    else:
        return []
    found = []
    for index in np.where(scores >= threshold)[0]:
        x1, y1, x2, y2 = (float(value) for value in corners[index])
        box = [(x1 - pad_x) / gain_x, (y1 - pad_y) / gain_y, (x2 - pad_x) / gain_x, (y2 - pad_y) / gain_y]
        found.append((int(class_ids[index]), float(scores[index]), box))
    return found


def ppe_from_boxes(boxes: list[tuple[int, float, list[float]]], width: int, height: int) -> dict[str, tuple[str, float]]:
    result = unknown_ppe()
    for class_id, score, (x1, y1, x2, y2) in boxes:
        named = PPE_CLASSES.get(class_id)
        if named is None:
            continue
        item, state = named
        top, bottom = PPE_BANDS[item]
        centre_x = (x1 + x2) / 2.0 / max(width, 1)
        centre_y = (y1 + y2) / 2.0 / max(height, 1)
        if not (0.0 <= centre_x <= 1.0 and top <= centre_y <= bottom):
            continue
        if score > result[item][1]:
            result[item] = (state, round(score, 3))
    return result


def _nms(detections: list[dict], threshold: float, by_confidence: bool = False) -> list[dict]:
    key = (lambda item: item["confidence"]) if by_confidence else (lambda item: item["bbox_xyxy"][3] - item["bbox_xyxy"][1])
    ordered = sorted(detections, key=key, reverse=True)
    kept = []
    for detection in ordered:
        if all(_iou(detection["bbox_xyxy"], other["bbox_xyxy"]) < threshold for other in kept):
            kept.append(detection)
    return kept


def _iou(a: list[float], b: list[float]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1]) + max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]) - inter
    return inter / area if area else 0.0


def share_inside(inner: list[float], outer: list[float]) -> float:
    """How much of the inner box lies within the outer one, from 0 to 1."""
    width = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    height = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    return width * height / max(1e-6, (inner[2] - inner[0]) * (inner[3] - inner[1]))


def onnx_session(path: str, providers: list[str], threads: int):
    """A small thread pool that sleeps between frames.

    By default ONNX Runtime gives every session a thread per core and keeps those
    threads spinning between runs. With one session per camera that pins most cores
    even when idle, and cameras slow each other down.
    """
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, threads)
    options.inter_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return ort.InferenceSession(str(path), sess_options=options, providers=providers)


def providers_for(device: str) -> list[str]:
    if device.lower() in {"cuda", "gpu"}:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


class YoloxDetector:
    """Official YOLOX ONNX models, Apache-2.0, trained on COCO. Nano and Tiny take 416 pixels, S and up take 640;
    the size is read from the model. People and vehicles (COCO_VEHICLES) are kept.

    A wide frame goes in as overlapping squares across it, two for 16:9. Squeezed whole into Nano's square, a worker
    65 px tall in the 1280x720 port clip came out 19 px tall and scored 0.55 or more, enough to start a track, in 2 of
    49 frames; on two squares, in 44. It takes twice as long, 36 ms for Nano on 2 threads. A box cut by the edge two
    squares share is joined with the rest of it from the other square.

    Boxes down to 0.30 are kept so the tracker can hold on to a partly hidden person.
    The tracker only starts a new person or vehicle from a confident box.
    """

    def __init__(self, path: str, providers: list[str], threads: int = 2, threshold: float = 0.30, tiles: bool = True):
        self.session = onnx_session(path, providers, threads)
        self.input_name = self.session.get_inputs()[0].name
        size = self.session.get_inputs()[0].shape[2]
        self.input_size = int(size) if isinstance(size, int) else 416
        self.threshold = threshold
        self.tiles = tiles

    def detect(self, frame, zones: list[dict], now: float, hold_inside: bool) -> list[dict]:
        del zones, now, hold_inside
        height, width = frame.shape[:2]
        found = []
        for index, (left, right) in enumerate(tile_spans(width, height) if self.tiles else [(0, width)]):
            for detection in self._infer(frame[:, left:right], left):
                x1, _, x2, _ = detection["bbox_xyxy"]
                detection["tile"] = index
                detection["cut"] = (left > 0 and x1 <= left + CUT_EDGE_PX) or (right < width and x2 >= right - 1 - CUT_EDGE_PX)
                found.append(detection)
        joined = join_cut(found)
        for detection in joined:
            del detection["tile"], detection["cut"]
        return _nms(joined, 0.45, by_confidence=True)

    def _infer(self, frame, offset_x: int = 0) -> list[dict]:
        """Boxes in frame pixels, offset_x added back for a square cut from a wider frame."""
        height, width = frame.shape[:2]
        canvas, scale, pad_x, pad_y = _letterbox(frame, self.input_size)
        tensor = np.transpose(canvas, (2, 0, 1))[None, :, :, :]
        output = np.asarray(self.session.run(None, {self.input_name: tensor})[0])[0]
        detections = []
        offset = 0
        for stride in (8, 16, 32):
            grid = self.input_size // stride
            count = grid * grid
            feature = output[offset : offset + count]
            offset += count
            gy, gx = np.meshgrid(np.arange(grid), np.arange(grid), indexing="ij")
            gx = gx.reshape(-1)
            gy = gy.reshape(-1)
            center_x = (feature[:, 0] + gx) * stride
            center_y = (feature[:, 1] + gy) * stride
            box_w = np.exp(np.clip(feature[:, 2], -6, 6)) * stride
            box_h = np.exp(np.clip(feature[:, 3], -6, 6)) * stride
            kept = [0] + list(COCO_VEHICLES)
            class_scores = feature[:, 4:5] * feature[:, [5 + cls for cls in kept]]
            best = np.argmax(class_scores, axis=1)
            score = class_scores[np.arange(len(best)), best]
            for index in np.where(score > self.threshold)[0]:
                coco = kept[int(best[index])]
                x1 = (center_x[index] - box_w[index] / 2 - pad_x) / scale
                y1 = (center_y[index] - box_h[index] / 2 - pad_y) / scale
                x2 = (center_x[index] + box_w[index] / 2 - pad_x) / scale
                y2 = (center_y[index] + box_h[index] / 2 - pad_y) / scale
                detections.append(
                    {
                        "class_name": "person" if coco == 0 else "vehicle",
                        "class_id": PERSON_CLASS if coco == 0 else VEHICLE_CLASS,
                        "vehicle_type": COCO_VEHICLES.get(coco),
                        "confidence": float(score[index]),
                        "bbox_xyxy": [
                            float(np.clip(x1, 0, width - 1)) + offset_x,
                            float(np.clip(y1, 0, height - 1)),
                            float(np.clip(x2, 0, width - 1)) + offset_x,
                            float(np.clip(y2, 0, height - 1)),
                        ],
                    }
                )
        return _nms(detections, 0.45, by_confidence=True)


# A box this close to the edge two squares share may carry on into the other square.
CUT_EDGE_PX = 8


def tile_spans(width: int, height: int) -> list[tuple[int, int]]:
    """Columns [left, right) of the squares a frame is detected in: one frame-high square per started height of
    width, evenly overlapping. A frame not much wider than tall stays whole."""
    if width <= 1.2 * height:
        return [(0, width)]
    count = int(np.ceil(width / height))
    step = (width - height) / (count - 1)
    return [(round(index * step), round(index * step) + height) for index in range(count)]


def join_cut(found: list[dict]) -> list[dict]:
    """Each box cut by a shared edge, joined with the same object's box from the other square.

    The other box is the same class from a different square and covers at least half of the smaller of the two.
    The joined box spans both and keeps the higher score. A cut box with no such partner, such as an object only
    one square found, is kept as it is.
    """
    kept = list(found)
    for cut in sorted((item for item in found if item["cut"]), key=lambda item: -item["confidence"]):
        if not any(item is cut for item in kept):
            continue
        partners = [item for item in kept if item["tile"] != cut["tile"] and item["class_name"] == cut["class_name"] and _covers_half(cut["bbox_xyxy"], item["bbox_xyxy"])]
        if not partners:
            continue
        partner = max(partners, key=lambda item: item["confidence"])
        a, b = cut["bbox_xyxy"], partner["bbox_xyxy"]
        best = cut if cut["confidence"] >= partner["confidence"] else partner
        joined = {**best, "bbox_xyxy": [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])], "cut": False}
        kept = [item for item in kept if item is not cut and item is not partner] + [joined]
    return kept


def _covers_half(a: list[float], b: list[float]) -> bool:
    """The two boxes share at least half of the smaller one. The cut end of a car can be lower than its roof, so
    rows alone do not tell: the port clip's car, cut at the shared edge, spanned 56% of the whole car's rows."""
    smaller, larger = sorted((a, b), key=lambda box: (box[2] - box[0]) * (box[3] - box[1]))
    return share_inside(smaller, larger) >= 0.5


def _letterbox(frame: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    height, width = frame.shape[:2]
    scale = min(size / width, size / height)
    resized = cv2.resize(frame, (int(width * scale), int(height * scale)))
    canvas = np.full((size, size, 3), 114, dtype=np.float32)
    # Official YOLOX ONNX preprocessing keeps BGR values in 0..255 and
    # places the resized image at the top left, padding bottom/right.
    canvas[: resized.shape[0], : resized.shape[1]] = resized
    return canvas, scale, 0, 0


def build_detectors(mode: str, model_path: str, device: str, threads: int = 2):
    root = Path(model_path)
    providers = providers_for(device)
    person_onnx = root / "person.onnx"
    ppe_onnx = root / "ppe.onnx"
    face_onnx = root / "face.onnx"
    mask_onnx = root / "mask.onnx"
    person_name, person_version = "person-detector", "hog-v1"
    if mode.upper() == "DEMO":
        detector = DemoDetector()
        ppe = DemoPPEClassifier()
        return detector, ppe, "person-detector", "v0-demo", "ppe-detector", "v0-demo"
    if person_onnx.exists():
        detector = YoloxDetector(str(person_onnx), providers, threads)
        person_name, person_version = f"yolox-{detector.input_size}", "apache-2.0"
    else:
        detector = HogPersonDetector()
        person_version = "hog-v1"
    ppe_name, ppe_version = "ppe-detector", "unloaded"
    if ppe_onnx.exists():
        ppe = OnnxPPEDetector(str(ppe_onnx), providers, threads)
        ppe_version = "onnx"
    else:
        # Without face.onnx the helmet is read from the top of the box only, and the mask stays UNKNOWN.
        faces = FaceFinder(str(face_onnx)) if face_onnx.exists() else None
        masks = MaskClassifier(str(mask_onnx), providers, 1) if faces is not None and mask_onnx.exists() else None
        ppe = ColorPPEClassifier(faces, masks)
        ppe_version = "color-v3" + ("+face" if faces else "") + ("+mask" if masks else "")
    return detector, ppe, person_name, person_version, ppe_name, ppe_version


class VehicleTyper:
    """Zero-shot vehicle type from CLIP ViT-B/32: the image vector of a vehicle crop against one text vector per type.

    clip_vision.onnx is the image encoder; vehicle_types.npz holds the text vectors, made by
    tools/vehicle_types/export_vehicle_types.py with the matching text encoder. No training.
    On the port reference image forklifts scored 0.97 and 0.99 and cars 0.00 to 0.02.
    """

    name, version = "clip-vit-b32", "zero-shot"
    MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
    STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)

    def __init__(self, vision_path: str, types_path: str, providers: list[str], threads: int = 1):
        self.session = onnx_session(vision_path, providers, threads)
        self.input_name = self.session.get_inputs()[0].name
        types = np.load(types_path)
        self.labels = [str(label) for label in types["labels"]]
        self.vectors = types["vectors"].astype(np.float32)

    def classify(self, crop, hint: str | None = None) -> tuple[str, float]:
        del hint
        if crop is None or getattr(crop, "size", 0) == 0:
            return "", 0.0
        height, width = crop.shape[:2]
        side = max(height, width)
        canvas = np.full((side, side, 3), 124, dtype=np.uint8)
        canvas[(side - height) // 2 : (side - height) // 2 + height, (side - width) // 2 : (side - width) // 2 + width] = crop
        rgb = cv2.cvtColor(cv2.resize(canvas, (224, 224), interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        vector = np.asarray(self.session.run(None, {self.input_name: ((rgb - self.MEAN) / self.STD).transpose(2, 0, 1)[None]})[0]).reshape(-1)
        chances = _softmax(100.0 * self.vectors @ (vector / np.linalg.norm(vector)))
        best = int(np.argmax(chances))
        return self.labels[best], round(float(chances[best]), 3)


class HintVehicleTyper:
    """Takes the type the detector gave. DEMO scripts it. Without the CLIP files it is the COCO class,
    and COCO has no forklift, so a forklift comes out as a truck and is not allowed."""

    def __init__(self, name: str, version: str):
        self.name, self.version = name, version

    def classify(self, crop, hint: str | None = None) -> tuple[str, float]:
        del crop
        return (hint or "", 0.9 if hint else 0.0)


def build_vehicle_typer(mode: str, model_path: str, device: str, threads: int = 1):
    if mode.upper() == "DEMO":
        return HintVehicleTyper("vehicle-typer", "v0-demo")
    vision, types = Path(model_path) / "clip_vision.onnx", Path(model_path) / "vehicle_types.npz"
    if vision.exists() and types.exists():
        return VehicleTyper(str(vision), str(types), providers_for(device), threads)
    return HintVehicleTyper("coco-class", "no-forklift")


# handwash.onnx class ids, as in the reference model: four WHO movements, each done once per side.
# Sides are not told apart here. 8 and 9 are for a model trained on all six steps.
HANDWASH_CLASSES = {
    0: "backs",
    1: "backs",
    2: "fingers",
    3: "fingers",
    4: "thumbs",
    5: "thumbs",
    6: "fingertips",
    7: "fingertips",
    8: "palms",
    9: "interlaced",
}


class OnnxHandwashDetector:
    """handwash.onnx: hand-washing gestures from YOLOv8, exported by tools/handwash_yolo/export_handwash_onnx.py.

    The reference model was trained on whole 960x540 frames from a camera above the sink, so the whole
    frame goes in, letterboxed. A camera closer to the sink shows bigger hands than the model learned;
    scale shrinks the frame to make up for it. Detection and segmentation exports both work: the class
    count comes from the names Ultralytics writes into the file, and mask channels after the class
    scores are ignored. Each hit is (step, score, box in frame pixels). steps holds the steps the model
    has a class for.
    """

    def __init__(self, path: str, providers: list[str], threads: int = 2, threshold: float = 0.35, scale: float = 1.0):
        self.session = onnx_session(path, providers, threads)
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        self.input_h = int(shape[2]) if isinstance(shape[2], int) else 640
        self.input_w = int(shape[3]) if isinstance(shape[3], int) else 640
        meta = self.session.get_modelmeta().custom_metadata_map
        names = ast.literal_eval(meta["names"]) if "names" in meta else None
        self.classes = len(names) if names else int(self.session.get_outputs()[0].shape[1]) - 4
        self.steps = {HANDWASH_CLASSES[index] for index in range(self.classes) if index in HANDWASH_CLASSES}
        self.threshold = threshold
        self.scale = scale
        self.name, self.version = "handwash-yolov8n", meta.get("task", "detect")

    def detect(self, frame, zones: list[dict], now: float, hold_inside: bool) -> list[tuple[str, float, list[float]]]:
        del zones, now, hold_inside
        canvas, transform = _model_canvas(frame, self.input_w, self.input_h, True, self.scale)
        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        output = np.asarray(self.session.run(None, {self.input_name: np.transpose(rgb, (2, 0, 1))[None]})[0])
        boxes = decode_boxes(output[:, : 4 + self.classes], self.classes, self.input_w, self.input_h, *transform, threshold=self.threshold)
        return [(HANDWASH_CLASSES[class_id], score, box) for class_id, score, box in boxes if class_id in HANDWASH_CLASSES]


class OnnxHandwashClassifier:
    """handwash_steps.onnx: the site's own step classifier, built by tools/handwash_classifier/train_handwash.py.

    It names one class for the hands at each hand-wash zone: none, other (hands, but no step: wetting, soap,
    rinsing) or one of the six steps, steps 2, 5 and 6 per hand when its classes say so. A model trained on hand crops (metadata crop=hands) looks at the square
    round the palms found in the zone, so the zone only has to cover the sink. An older one looks at the zone's
    bounding box, which then has to be drawn exactly as it was for training: drawn wider on the site's wrong
    clip, it read backs of hands and nothing else.
    No hands gives no hit; other keeps a wash going without crediting a step.
    """

    SIZE = 224
    STORED = 256
    MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    CLASSES = ("none", "other", "palms", "backs", "interlaced", "fingers", "thumbs", "fingertips")

    def __init__(self, path: str, providers: list[str], threads: int = 1, hands=None):
        self.session = onnx_session(path, providers, threads)
        self.input_name = self.session.get_inputs()[0].name
        meta = self.session.get_modelmeta().custom_metadata_map
        self.classes = meta["classes"].split(",") if "classes" in meta else list(self.CLASSES)
        # Steps it reads, or parts per hand such as thumbs_left for a model that tells the hands apart.
        self.steps = {name for name in self.classes if step_of(name) in WASH_STEPS}
        self.name, self.version = "handwash-steps", meta.get("trained_on", "site")
        self.crop = meta.get("crop", "zone")
        # The palm detector, for a model trained on hand crops.
        self.hands = hands

    def detect(self, frame, zones: list[dict], now: float, hold_inside: bool) -> list[tuple]:
        """(class, chance, box, chance of each step) per zone with hands. The wash credits steps by the last."""
        del now, hold_inside
        found = []
        for zone in zones:
            read = self.chances(frame, zone)
            if read is None:
                continue
            chances, box = read
            best = int(np.argmax(chances))
            if self.classes[best] != "none":
                steps = {name: float(chances[index]) for index, name in enumerate(self.classes) if name in self.steps}
                found.append((self.classes[best], round(float(chances[best]), 3), box, steps))
        return found

    def chances(self, frame, zone: dict) -> tuple[np.ndarray, list[float]] | None:
        """The chance of each class at this zone and the box looked at, or None when no hands are found there."""
        height, width = frame.shape[:2]
        points = zone.get("polygon") or []
        if len(points) < 3:
            return None
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        box = [min(xs) * width, min(ys) * height, max(xs) * width, max(ys) * height]
        if self.crop == "hands":
            left, top = max(0, int(box[0])), max(0, int(box[1]))
            square = hands_box(self.hands.palms(frame[top : max(0, int(box[3])), left : max(0, int(box[2]))]))
            if square is None:
                return None
            square = [square[0] + left, square[1] + top, square[2] + left, square[3] + top]
            image = cv2.resize(hand_square(frame, square, self.STORED), (self.SIZE, self.SIZE), interpolation=cv2.INTER_AREA)
            box = [max(0.0, square[0]), max(0.0, square[1]), min(float(width), square[2]), min(float(height), square[3])]
        else:
            image = zone_square(frame, box, self.SIZE)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        logits = np.asarray(self.session.run(None, {self.input_name: ((rgb - self.MEAN) / self.STD).transpose(2, 0, 1)[None]})[0]).reshape(-1)
        return _softmax(logits), box


def zone_square(frame: np.ndarray, box: list[float], size: int) -> np.ndarray:
    """The box, padded square on grey 127 and resized, as tools/handwash_classifier/train_handwash.py crops it."""
    x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
    region = frame[max(0, y1) : max(0, y2), max(0, x1) : max(0, x2)]
    side = max(region.shape[:2]) if region.size else 1
    canvas = np.full((side, side, 3), 127, dtype=np.uint8)
    top, left = (side - region.shape[0]) // 2, (side - region.shape[1]) // 2
    canvas[top : top + region.shape[0], left : left + region.shape[1]] = region
    stored = cv2.resize(canvas, (256, 256), interpolation=cv2.INTER_AREA)
    return cv2.resize(stored, (size, size), interpolation=cv2.INTER_AREA)


class DemoHandwashDetector:
    """Scripted gestures at each hand-wash station. It knows all six steps."""

    name, version = "handwash-detector", "v0-demo"
    steps = set(WASH_STEPS)

    def detect(self, frame, zones: list[dict], now: float, hold_inside: bool) -> list[tuple[str, float, list[float]]]:
        height, width = frame.shape[:2]
        found = []
        for zone in zones:
            scripted = scripted_wash(zone, now, hold_inside)
            if scripted is None:
                continue
            step, (nx, ny) = scripted
            found.append((step, 0.86, [(nx - 0.08) * width, (ny - 0.07) * height, (nx + 0.08) * width, (ny + 0.07) * height]))
        return found


class NoHandwashDetector:
    """REAL mode without handwash.onnx: no hands are ever found, so no wash is checked."""

    name, version = "handwash-detector", "unloaded"
    steps: set[str] = set()

    def detect(self, frame, zones: list[dict], now: float, hold_inside: bool) -> list[tuple[str, float, list[float]]]:
        del frame, zones, now, hold_inside
        return []


def build_handwash_detector(mode: str, model_path: str, device: str, threads: int = 2, scale: float = 1.0):
    """The site's step classifier when it is installed, else the reference gesture detector."""
    if mode.upper() == "DEMO":
        return DemoHandwashDetector()
    steps = Path(model_path) / "handwash_steps.onnx"
    if steps.exists():
        classifier = OnnxHandwashClassifier(str(steps), providers_for(device), threads)
        if classifier.crop == "hands":
            classifier.hands = build_hand_pose(mode, model_path, providers_for(device), threads)
            if classifier.hands is None:
                raise FileNotFoundError("handwash_steps.onnx looks at the hands and needs hand_palm.onnx and hand_pose.onnx")
        return classifier
    path = Path(model_path) / "handwash.onnx"
    if path.exists():
        return OnnxHandwashDetector(str(path), providers_for(device), threads, scale=scale)
    return NoHandwashDetector()

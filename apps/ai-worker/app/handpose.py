"""Hand joints for the overlay: MediaPipe Hands from the OpenCV Zoo (Apache-2.0).

A palm detector finds each hand, then a landmark model gives its 21 joints. They are drawn on the
camera view to show the hands being followed. They do not judge the wash; the step classifier does.

Ported from the zoo's mp_palmdet.py and mp_handpose.py, run through ONNX Runtime like the other models.
"""

import cv2
import numpy as np

# Joint pairs drawn as bones: the palm, then each finger from its base to its tip.
HAND_BONES = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
)
FINGERTIPS = (4, 8, 12, 16, 20)


def build_hand_pose(mode: str, model_path: str, providers: list[str], threads: int = 1) -> "HandPose | None":
    """hand_palm.onnx and hand_pose.onnx from the OpenCV Zoo, or None without them or in DEMO, whose hands are drawn boxes."""
    from pathlib import Path

    palm, joints = Path(model_path) / "hand_palm.onnx", Path(model_path) / "hand_pose.onnx"
    if mode.upper() == "DEMO" or not (palm.exists() and joints.exists()):
        return None
    return HandPose(str(palm), str(joints), providers, threads)


def palm_anchors() -> np.ndarray:
    """The palm detector's 2016 SSD anchor centres: 24x24 cells with 2 anchors, then 12x12 with 6."""
    anchors = []
    for size, per_cell in ((24, 2), (12, 6)):
        for y in range(size):
            for x in range(size):
                anchors += [[(x + 0.5) / size, (y + 0.5) / size]] * per_cell
    return np.array(anchors, dtype=np.float32)


class HandPose:
    PALM_SIZE = 192
    JOINT_SIZE = 224

    def __init__(self, palm_path: str, joints_path: str, providers: list[str], threads: int = 1, max_hands: int = 2):
        from app.detectors import onnx_session

        self.palm = onnx_session(palm_path, providers, threads)
        self.joints = onnx_session(joints_path, providers, threads)
        self.anchors = palm_anchors()
        self.max_hands = max_hands

    def find(self, image: np.ndarray) -> list[np.ndarray]:
        """Each hand found, as 21 (x, y) joints in image pixels."""
        if image is None or image.size == 0:
            return []
        hands = []
        for palm in self._palms(image)[: self.max_hands]:
            joints = self._joints(image, palm)
            if joints is not None:
                hands.append(joints)
        return hands

    def _palms(self, image: np.ndarray, score_floor: float = 0.5, overlap: float = 0.3) -> list[np.ndarray]:
        """Palms as [x1, y1, x2, y2, 7 palm points as x, y, score], best first."""
        height, width = image.shape[:2]
        ratio = self.PALM_SIZE / max(height, width)
        resized = cv2.resize(image, (int(width * ratio), int(height * ratio)))
        left, top = (self.PALM_SIZE - resized.shape[1]) // 2, (self.PALM_SIZE - resized.shape[0]) // 2
        canvas = np.zeros((self.PALM_SIZE, self.PALM_SIZE, 3), dtype=np.uint8)
        canvas[top : top + resized.shape[0], left : left + resized.shape[1]] = resized
        blob = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32)[None] / 255.0
        boxes_out, scores_out = self.palm.run(None, {self.palm.get_inputs()[0].name: blob})
        scores = 1.0 / (1.0 + np.exp(-scores_out[0, :, 0].astype(np.float64)))
        keep = np.where(scores >= score_floor)[0]
        if keep.size == 0:
            return []
        scale = max(height, width)
        pad = np.array([left, top], dtype=np.float32) / ratio
        deltas = boxes_out[0, keep]
        centres = deltas[:, :2] / self.PALM_SIZE + self.anchors[keep]
        sizes = deltas[:, 2:4] / self.PALM_SIZE
        corners = np.concatenate([centres - sizes / 2, centres + sizes / 2], axis=1) * scale - np.tile(pad, 2)
        points = (deltas[:, 4:].reshape(-1, 7, 2) / self.PALM_SIZE + self.anchors[keep][:, None, :]) * scale - pad
        order = np.argsort(-scores[keep])
        kept: list[int] = []
        for index in order:
            if all(_iou(corners[index], corners[other]) < overlap for other in kept):
                kept.append(index)
        return [np.r_[corners[index], points[index].reshape(-1), scores[keep][index]] for index in kept]

    def _joints(self, image: np.ndarray, palm: np.ndarray, floor: float = 0.8) -> np.ndarray | None:
        """The 21 joints of the hand at this palm, or None when the landmark model is not sure it is a hand.

        The crop around the palm is turned so the hand points up, as the model expects, then the joints are
        turned back.
        """
        crop, box, offset = _crop_square(image, palm[0:4].reshape(2, 2), shift=(0.0, 0.0), enlarge=4.0, diagonal=True)
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        box = box - offset
        palm_points = palm[4:18].reshape(7, 2) - offset
        wrist, middle = palm_points[0], palm_points[2]
        radians = np.pi / 2 - np.arctan2(-(middle[1] - wrist[1]), middle[0] - wrist[0])
        radians -= 2 * np.pi * np.floor((radians + np.pi) / (2 * np.pi))
        angle = float(np.rad2deg(radians))
        rotation = cv2.getRotationMatrix2D(tuple(float(v) for v in box.sum(axis=0) / 2), angle, 1.0)
        turned = cv2.warpAffine(crop, rotation, (crop.shape[1], crop.shape[0]))
        turned_points = np.c_[palm_points, np.ones(7)] @ rotation.T
        turned_box = np.array([turned_points.min(axis=0), turned_points.max(axis=0)])
        hand, hand_box, _ = _crop_square(turned, turned_box, shift=(0.0, -0.4), enlarge=3.0, diagonal=False)
        blob = cv2.resize(hand, (self.JOINT_SIZE, self.JOINT_SIZE), interpolation=cv2.INTER_AREA).astype(np.float32)[None] / 255.0
        landmarks, confidence, _, _ = self.joints.run(None, {self.joints.get_inputs()[0].name: blob})
        if float(confidence[0][0]) < floor:
            return None
        joints = landmarks[0].reshape(21, 3)[:, :2]
        scale = max((hand_box[1] - hand_box[0]) / self.JOINT_SIZE)
        joints = (joints - self.JOINT_SIZE / 2) * scale
        joints = joints @ cv2.getRotationMatrix2D((0, 0), angle, 1.0)[:, :2]
        inverse = cv2.invertAffineTransform(rotation)
        centre = np.append(hand_box.sum(axis=0) / 2, 1.0) @ inverse.T
        return joints + centre + offset


def _crop_square(image: np.ndarray, box: np.ndarray, shift: tuple[float, float], enlarge: float, diagonal: bool):
    """The box moved by shift and grown by enlarge, cropped and padded square on black.

    diagonal pads to the crop's diagonal, so turning it later cuts no corner off.
    Returns the square, the box used, and the square's top left corner in the image.
    """
    size = box[1] - box[0]
    box = box + np.array(shift) * size
    centre = box.sum(axis=0) / 2
    half = (box[1] - box[0]) * enlarge / 2
    box = np.array([centre - half, centre + half]).astype(np.int32)
    box[:, 0] = np.clip(box[:, 0], 0, image.shape[1])
    box[:, 1] = np.clip(box[:, 1], 0, image.shape[0])
    crop = image[box[0][1] : box[1][1], box[0][0] : box[1][0]]
    side = int(np.linalg.norm(crop.shape[:2])) if diagonal else max(crop.shape[:2])
    side = max(side, 1)
    top, left = (side - crop.shape[0]) // 2, (side - crop.shape[1]) // 2
    square = cv2.copyMakeBorder(crop, top, side - crop.shape[0] - top, left, side - crop.shape[1] - left, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    return square, box, box[0] - np.array([left, top])


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / union) if union > 0 else 0.0

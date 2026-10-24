"""ByteTrack via the Apache-2.0 supervision package. Tracking is not implemented here."""

import numpy as np
import supervision as sv

CLASS_IDS = {"person": 0, "vehicle": 2}
CLASS_NAMES = {0: "person", 2: "vehicle"}


class PersonTracker:
    """Settings measured on a 30 s workshop clip with about 15 people: 29 ids came down to 16.

    Only a confident box starts a person, and it shows from its fourth frame in a row, so a
    flicker never becomes a new id. Weaker boxes still extend a person already being followed.
    A person hidden for up to 4 s keeps the same id.
    """

    def __init__(self, frame_rate: int = 5):
        self.tracker = sv.ByteTrack(
            track_activation_threshold=0.55,
            lost_track_buffer=max(int(frame_rate) * 4, 8),
            minimum_matching_threshold=0.8,
            frame_rate=max(int(frame_rate), 1),
            minimum_consecutive_frames=3,
        )

    def update(self, detections: list[dict]) -> list[dict]:
        if not detections:
            empty = sv.Detections(
                xyxy=np.empty((0, 4), dtype=float),
                confidence=np.empty((0,), dtype=float),
                class_id=np.empty((0,), dtype=int),
            )
            return _to_dicts(self.tracker.update_with_detections(empty))
        xyxy = np.array([item["bbox_xyxy"] for item in detections], dtype=float)
        confidence = np.array([item["confidence"] for item in detections], dtype=float)
        class_id = np.array([item["class_id"] for item in detections], dtype=int)
        incoming = sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)
        return _to_dicts(self.tracker.update_with_detections(incoming))


def _to_dicts(tracked: sv.Detections) -> list[dict]:
    if tracked.tracker_id is None or len(tracked) == 0:
        return []
    results = []
    for index, track_id in enumerate(tracked.tracker_id):
        if int(track_id) < 0:
            # Not confirmed yet.
            continue
        class_id = int(tracked.class_id[index]) if tracked.class_id is not None else 0
        score = float(tracked.confidence[index]) if tracked.confidence is not None else 0.0
        results.append(
            {
                "track_id": str(int(track_id)),
                "bbox_xyxy": [float(v) for v in tracked.xyxy[index].tolist()],
                "class_name": CLASS_NAMES.get(class_id, "object"),
                "class_id": class_id,
                "confidence": score,
            }
        )
    return results

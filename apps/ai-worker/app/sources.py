import logging
import time
from pathlib import Path

import cv2
import numpy as np

from app.drawing import synthetic_frame

log = logging.getLogger("worker.source")


def fit(frame, width: int, height: int):
    """The frame scaled to fit width x height with its shape kept, centred on black.

    A 16:9 source fills it exactly. A portrait phone video stretched to 16:9 came out three times
    too wide, and the hand-wash model found no hands in it at all; padded, it found them in 42 of 198 reads.
    """
    gain = min(width / frame.shape[1], height / frame.shape[0])
    size = (max(1, round(frame.shape[1] * gain)), max(1, round(frame.shape[0] * gain)))
    if size == (width, height):
        return cv2.resize(frame, size)
    canvas = np.zeros((height, width, 3), dtype=frame.dtype)
    left, top = (width - size[0]) // 2, (height - size[1]) // 2
    canvas[top : top + size[1], left : left + size[0]] = cv2.resize(frame, size)
    return canvas


class FrameSource:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.capture = None
        self.kind = None
        self.key = None
        # Set when an uploaded video starts over, until take_rewound() reads it.
        self.rewound = False
        self._restart_clock()

    def take_rewound(self) -> bool:
        rewound, self.rewound = self.rewound, False
        return rewound

    def close(self) -> None:
        if self.capture is not None:
            self.capture.release()
        self.capture = None
        self.kind = None
        self.key = None

    def read(self, camera: dict, store, settings) -> tuple[object | None, str]:
        stream_type = (camera.get("stream_type") or "").upper()
        stream_url = camera.get("stream_url") or ""
        frame = None
        try:
            if stream_type == "RTSP" and stream_url:
                frame = self._read_rtsp(stream_url)
            elif stream_type == "FILE" and stream_url:
                frame = self._read_file(stream_url, store)
        except Exception:
            log.warning("camera source failed", extra={"camera_id": self.camera_id})
            self.close()
            frame = None
        if frame is None:
            if settings.ai_mode.upper() == "DEMO":
                return synthetic_frame(settings.frame_width, settings.frame_height, camera.get("name") or camera.get("code") or "Camera"), "synthetic"
            return None, "offline"
        return fit(frame, settings.frame_width, settings.frame_height), "video"

    def _read_rtsp(self, url: str):
        if self.kind != "rtsp" or self.key != url or self.capture is None or not self.capture.isOpened():
            self.close()
            self.capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            try:
                self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            self.kind = "rtsp"
            self.key = url
        if self.capture is None or not self.capture.isOpened():
            self.close()
            return None
        ok, frame = self.capture.read()
        if not ok:
            self.close()
            return None
        return frame

    def _read_file(self, object_key: str, store):
        local = Path("/tmp/safety-videos") / f"{self.camera_id}.mp4"
        if self.kind != "file" or self.key != object_key or self.capture is None or not self.capture.isOpened():
            self.close()
            store.download(object_key, local)
            self.capture = cv2.VideoCapture(str(local))
            self.kind = "file"
            self.key = object_key
            self._restart_clock()
            log.info("opened uploaded video", extra={"camera_id": self.camera_id})
        if self.capture is None or not self.capture.isOpened():
            log.warning("uploaded video could not be opened", extra={"camera_id": self.camera_id})
            self.close()
            return None
        frame = self._frame_due()
        if frame is None:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._restart_clock()
            self.rewound = True
            frame = self._frame_due()
        if frame is None:
            self.close()
            return None
        return frame

    def _restart_clock(self) -> None:
        self.started = time.monotonic()
        self.position = 0
        self.last = None

    def _frame_due(self):
        """The frame a live camera would show now, so the video plays at its own speed like a real camera.

        Read one frame per step, a 30 fps video played at the loop's 16 fps, about half speed, and every
        rule saw actions last twice as long: a rushed hand wash passed the per-step minimum. Frames the
        loop was too slow for are skipped; a loop faster than the video gets the same frame again.
        After a stall of more than 2 s the video carries on from where it was instead of racing ahead.
        """
        fps = self.capture.get(cv2.CAP_PROP_FPS) or 0.0
        if fps > 0:
            due = int((time.monotonic() - self.started) * fps + 1e-6)
            if due - self.position > 2 * fps:
                self.started = time.monotonic() - self.position / fps
                due = self.position
            if due < self.position and self.last is not None:
                return self.last
            while self.position < due and self.capture.grab():
                self.position += 1
        ok, frame = self.capture.read()
        if not ok:
            return None
        self.position += 1
        self.last = frame
        return frame

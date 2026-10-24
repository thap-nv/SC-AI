import numpy as np

from app import sources
from app.sources import FrameSource, fit


class _Video:
    """A 30 fps clip of 90 frames whose pixels hold the frame number."""

    def __init__(self):
        self.next = 0

    def get(self, prop):
        return 30.0

    def grab(self):
        if self.next >= 90:
            return False
        self.next += 1
        return True

    def read(self):
        if self.next >= 90:
            return False, None
        frame = np.full((2, 2, 3), self.next, dtype=np.uint8)
        self.next += 1
        return True, frame


def _source_at(clock: list[float], monkeypatch) -> FrameSource:
    monkeypatch.setattr(sources.time, "monotonic", lambda: clock[0])
    source = FrameSource("cam")
    source.capture = _Video()
    return source


def test_a_slow_loop_skips_frames_so_the_video_keeps_its_own_speed(monkeypatch):
    clock = [100.0]
    source = _source_at(clock, monkeypatch)
    seen = []
    for step in range(5):
        clock[0] = 100.0 + step * 0.1  # the loop runs at 10 fps, the video at 30
        seen.append(int(source._frame_due()[0, 0, 0]))
    assert seen == [0, 3, 6, 9, 12]


def test_a_fast_loop_gets_the_same_frame_until_the_next_is_due(monkeypatch):
    clock = [100.0]
    source = _source_at(clock, monkeypatch)
    seen = []
    for step in range(4):
        clock[0] = 100.0 + step * 0.02  # 50 fps loop
        seen.append(int(source._frame_due()[0, 0, 0]))
    assert seen == [0, 0, 1, 1]


def test_a_video_that_starts_over_says_so_once(monkeypatch):
    clock = [100.0]
    source = _source_at(clock, monkeypatch)
    source.capture.isOpened = lambda: True
    source.capture.set = lambda prop, value: setattr(source.capture, "next", 0)
    source.kind, source.key = "file", "videos/clip.mp4"
    for step in range(30):
        clock[0] = 100.0 + step * 0.1
        source._read_file("videos/clip.mp4", None)
    clock[0] = 102.9  # frame 87 of 90
    assert int(source._read_file("videos/clip.mp4", None)[0, 0, 0]) == 87
    assert source.take_rewound() is False
    clock[0] = 103.5  # past the end
    assert int(source._read_file("videos/clip.mp4", None)[0, 0, 0]) == 0
    assert source.take_rewound() is True
    assert source.take_rewound() is False


def test_after_a_stall_the_video_carries_on_instead_of_racing_ahead(monkeypatch):
    clock = [100.0]
    source = _source_at(clock, monkeypatch)
    source._frame_due()
    clock[0] = 110.0
    assert int(source._frame_due()[0, 0, 0]) == 1


def test_a_wide_frame_fills_the_output():
    frame = np.full((1080, 1920, 3), 200, dtype=np.uint8)
    out = fit(frame, 1280, 720)
    assert out.shape == (720, 1280, 3)
    assert (out == 200).all()


def test_a_portrait_frame_keeps_its_shape_between_black_bars():
    frame = np.full((1280, 720, 3), 200, dtype=np.uint8)
    out = fit(frame, 1280, 720)
    assert out.shape == (720, 1280, 3)
    # 720x1280 scaled to 405x720, centred: 437 black columns on each side.
    assert (out[:, :437] == 0).all() and (out[:, -438:] == 0).all()
    assert (out[:, 437:842] == 200).all()

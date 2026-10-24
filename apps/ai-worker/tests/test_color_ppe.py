import numpy as np
import pytest

pytest.importorskip("cv2")

from app.detectors import ColorPPEClassifier, _helmet_above_face, _mask_on_face

SKIN = (120, 160, 210)
SURGICAL_BLUE = (220, 200, 160)
GREY_COVERALL = (150, 160, 165)
DARK = (40, 40, 45)
HAIR = (25, 25, 25)
WHITE = (235, 235, 235)


def _person(head, torso, legs, height=300, width=100) -> np.ndarray:
    image = np.full((height, width, 3), (90, 90, 90), dtype=np.uint8)
    image[: int(height * 0.06)] = head
    image[int(height * 0.06) : int(height * 0.18)] = SKIN
    image[int(height * 0.18) : int(height * 0.52)] = torso
    image[int(height * 0.52) :] = legs
    return image


def test_coverall_from_torso_to_legs_is_protective_clothing():
    result = ColorPPEClassifier().classify(_person(WHITE, GREY_COVERALL, GREY_COVERALL))
    assert result["clothing"][0] == "YES"


def test_work_coloured_shirt_over_dark_trousers_is_not():
    result = ColorPPEClassifier().classify(_person(WHITE, GREY_COVERALL, DARK))
    assert result["clothing"][0] == "NO"


def test_bright_shirt_is_not_protective_clothing():
    result = ColorPPEClassifier().classify(_person(WHITE, (40, 40, 200), DARK))
    assert result["clothing"][0] == "NO"


def test_clothing_stays_unknown_when_the_legs_are_hidden():
    result = ColorPPEClassifier().classify(_person(WHITE, GREY_COVERALL, GREY_COVERALL, height=150))
    assert result["clothing"][0] == "UNKNOWN"


def test_without_a_face_the_helmet_is_read_from_the_top_of_the_box():
    assert ColorPPEClassifier().classify(_person((0, 210, 240), GREY_COVERALL, GREY_COVERALL))["helmet"][0] == "YES"
    assert ColorPPEClassifier().classify(_person(HAIR, GREY_COVERALL, GREY_COVERALL))["helmet"][0] == "NO"


def test_without_a_face_the_mask_and_shoes_are_never_judged():
    result = ColorPPEClassifier().classify(_person(WHITE, GREY_COVERALL, GREY_COVERALL))
    assert result["mask"] == ("UNKNOWN", 0.0)
    assert result["shoes"] == ("UNKNOWN", 0.0)


def test_empty_or_small_crop_stays_unknown():
    assert {state for state, _ in ColorPPEClassifier().classify(np.zeros((0, 0, 3), dtype=np.uint8)).values()} == {"UNKNOWN"}
    assert {state for state, _ in ColorPPEClassifier().classify(np.zeros((60, 30, 3), dtype=np.uint8)).values()} == {"UNKNOWN"}


def _face(above=WHITE, chin=SURGICAL_BLUE, nose_x=50.0) -> dict:
    """A 100x100 head image. Face box x 30..80, y 40..90; eyes 20 px apart at y 55."""
    image = np.full((100, 100, 3), (90, 90, 90), dtype=np.uint8)
    image[15:40, 25:85] = above
    image[40:72, 30:80] = SKIN
    image[72:95, 30:80] = chin
    points = np.array([[40, 55], [60, 55], [nose_x, 65], [43, 78], [57, 78]], dtype=float)
    return {"image": image, "box": [30.0, 40.0, 50.0, 50.0], "points": points, "score": 0.9}


def test_hard_hat_above_the_face_is_a_helmet_and_hair_is_not():
    assert _helmet_above_face(_face(above=WHITE))[0] == "YES"
    assert _helmet_above_face(_face(above=(0, 210, 240)))[0] == "YES"
    assert _helmet_above_face(_face(above=HAIR))[0] == "NO"


def test_mask_colour_over_the_chin_is_a_mask():
    assert _mask_on_face(_face(chin=SURGICAL_BLUE))[0] == "YES"
    assert _mask_on_face(_face(chin=WHITE))[0] == "YES"


def test_bare_chin_on_a_face_turned_to_the_camera_is_no_mask():
    assert _mask_on_face(_face(chin=SKIN))[0] == "NO"


def test_bare_chin_in_profile_is_not_judged():
    assert _mask_on_face(_face(chin=SKIN, nose_x=62.0))[0] == "UNKNOWN"


class _FixedLogits:
    def __init__(self, logits):
        self.logits = np.array([logits], dtype=np.float32)

    def run(self, outputs, feeds):
        assert feeds["image"].shape == (1, 3, 96, 96)
        return [self.logits]


def _mask_model(logits):
    from app.detectors import MaskClassifier

    model = MaskClassifier.__new__(MaskClassifier)
    model.session, model.input_name, model.floor = _FixedLogits(logits), "image", 0.7
    return model


def test_mask_model_reads_worn_as_yes_and_bare_or_misworn_as_no():
    face = _face()
    assert _mask_model([0.0, 4.0, 0.0]).judge(face)[0] == "YES"
    assert _mask_model([0.0, 0.0, 4.0]).judge(face)[0] == "NO"
    assert _mask_model([4.0, 0.0, 0.0]).judge(face)[0] == "NO", "a mask under the chin is not worn"
    assert _mask_model([2.0, 0.0, 2.0]).judge(face)[0] == "NO", "incorrect and bare together outweigh worn"
    assert _mask_model([0.0, 0.6931, 0.0]).judge(face) == ("UNKNOWN", 0.0), "worn 0.5 against 0.5: neither side is sure"


def test_classifier_uses_the_mask_model_only_when_a_face_is_found():
    from app.detectors import ColorPPEClassifier

    class OneFace:
        def find(self, frame, box):
            return _face()

    frame = _person(WHITE, GREY_COVERALL, GREY_COVERALL)
    context = {"frame": frame, "box": [0, 0, frame.shape[1], frame.shape[0]]}
    assert ColorPPEClassifier(OneFace(), _mask_model([0.0, 0.0, 4.0])).classify(frame, context)["mask"][0] == "NO"
    assert ColorPPEClassifier(None, _mask_model([0.0, 0.0, 4.0])).classify(frame, context)["mask"] == ("UNKNOWN", 0.0)

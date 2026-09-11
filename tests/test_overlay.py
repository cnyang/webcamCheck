import numpy as np

from webcamcheck.landmarks import (
    LEFT_EAR,
    LEFT_ELBOW,
    LEFT_SHOULDER,
    RIGHT_EAR,
    RIGHT_ELBOW,
    RIGHT_SHOULDER,
    RawLandmark,
)
from webcamcheck.overlay import draw_posture
from webcamcheck.ports import Frame
from webcamcheck.posture import UNKNOWN_VERDICT, Baseline, PostureSample, PostureStatus, Verdict

BASELINE = Baseline(neck_angle_deg=11.0, shoulder_tilt_deg=17.0, shoulder_width=0.60)
SAMPLE = PostureSample(neck_angle_deg=14.0, shoulder_tilt_deg=17.0, shoulder_width=0.60)
GOOD = Verdict(status=PostureStatus.GOOD)


def _frame() -> Frame:
    return np.zeros((480, 640, 3), dtype=np.uint8)


def _landmarks() -> list[RawLandmark]:
    marks = [RawLandmark(x=0.5, y=0.5, visibility=0.0) for _ in range(33)]
    marks[LEFT_SHOULDER] = RawLandmark(x=0.40, y=0.60, visibility=0.9)
    marks[RIGHT_SHOULDER] = RawLandmark(x=0.60, y=0.60, visibility=0.9)
    marks[LEFT_EAR] = RawLandmark(x=0.46, y=0.30, visibility=0.9)
    marks[RIGHT_EAR] = RawLandmark(x=0.54, y=0.30, visibility=0.9)
    marks[LEFT_ELBOW] = RawLandmark(x=0.33, y=0.85, visibility=0.9)
    marks[RIGHT_ELBOW] = RawLandmark(x=0.67, y=0.85, visibility=0.9)
    return marks


def test_draws_something_on_the_frame() -> None:
    frame = _frame()
    canvas = draw_posture(frame, _landmarks(), SAMPLE, GOOD, BASELINE)
    assert canvas.shape == frame.shape
    assert canvas.any(), "應該要畫出線條和文字"


def test_does_not_mutate_the_original_frame() -> None:
    frame = _frame()
    draw_posture(frame, _landmarks(), SAMPLE, GOOD, BASELINE)
    assert not frame.any(), "原始影格不能被改到"


def test_handles_missing_landmarks() -> None:
    # 沒偵測到人的時候只畫文字,不能因為沒有關鍵點就爆掉
    canvas = draw_posture(_frame(), None, None, UNKNOWN_VERDICT, BASELINE)
    assert canvas.any()


def test_handles_invisible_landmarks() -> None:
    marks = [RawLandmark(x=0.5, y=0.5, visibility=0.0) for _ in range(33)]
    canvas = draw_posture(_frame(), marks, None, UNKNOWN_VERDICT, BASELINE)
    assert canvas.any()


def test_bad_and_good_render_differently() -> None:
    good = draw_posture(_frame(), _landmarks(), SAMPLE, GOOD, BASELINE)
    bad = draw_posture(_frame(), _landmarks(), SAMPLE, Verdict(status=PostureStatus.BAD, forward_slouch=True), BASELINE)
    assert not np.array_equal(good, bad), "狀態不同,顏色與文字應該不同"


def test_draws_too_close_warning() -> None:
    sample = PostureSample(neck_angle_deg=11.0, shoulder_tilt_deg=17.0, shoulder_width=0.70)
    verdict = Verdict(status=PostureStatus.BAD, too_close=True)
    canvas = draw_posture(_frame(), _landmarks(), sample, verdict, BASELINE)
    assert canvas.any()

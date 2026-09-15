import pytest

from webcamcheck.landmarks import (
    LEFT_EAR,
    LEFT_SHOULDER,
    NOSE,
    RIGHT_EAR,
    RIGHT_SHOULDER,
    RawLandmark,
    sample_from_landmarks,
)


def _landmarks(overrides: dict[int, RawLandmark]) -> list[RawLandmark]:
    base = [RawLandmark(x=0.5, y=0.5, visibility=0.9) for _ in range(33)]
    for index, landmark in overrides.items():
        base[index] = landmark
    return base


def _facing(ear_y: float = 0.3, visibility: float = 0.9) -> list[RawLandmark]:
    return _landmarks(
        {
            LEFT_SHOULDER: RawLandmark(x=0.4, y=0.6, visibility=0.9),
            RIGHT_SHOULDER: RawLandmark(x=0.6, y=0.6, visibility=0.9),
            LEFT_EAR: RawLandmark(x=0.5, y=ear_y, visibility=visibility),
            RIGHT_EAR: RawLandmark(x=0.5, y=ear_y, visibility=visibility),
        }
    )


class TestSampleFromLandmarks:
    def test_both_ears_visible_averages_angle(self) -> None:
        sample = sample_from_landmarks(_facing())
        assert sample is not None
        assert sample.neck_angle_deg == 0.0

    def test_reports_shoulder_width(self) -> None:
        sample = sample_from_landmarks(_facing())
        assert sample is not None
        assert sample.shoulder_width == pytest.approx(0.2)

    def test_aspect_ratio_widens_shoulder_width(self) -> None:
        sample = sample_from_landmarks(_facing(), aspect_ratio=16 / 9)
        assert sample is not None
        assert sample.shoulder_width == pytest.approx(0.2 * 16 / 9)

    def test_low_visibility_ear_is_excluded(self) -> None:
        landmarks = _facing()
        landmarks[LEFT_EAR] = RawLandmark(x=0.5, y=0.3, visibility=0.1)
        assert sample_from_landmarks(landmarks) is not None

    def test_low_visibility_shoulders_returns_none(self) -> None:
        landmarks = _facing()
        landmarks[LEFT_SHOULDER] = RawLandmark(x=0.4, y=0.6, visibility=0.1)
        assert sample_from_landmarks(landmarks) is None

    def test_no_ears_visible_returns_none(self) -> None:
        assert sample_from_landmarks(_facing(visibility=0.1)) is None

    def test_head_dropped_below_shoulders_reports_large_angle(self) -> None:
        sample = sample_from_landmarks(_facing(ear_y=0.75))
        assert sample is not None
        assert sample.neck_angle_deg > 90.0

    def test_nose_offset_ratio_is_zero_when_facing_camera(self) -> None:
        sample = sample_from_landmarks(_facing())
        assert sample is not None
        assert sample.nose_offset_ratio == pytest.approx(0.0)

    def test_turned_head_reports_nonzero_nose_offset_ratio(self) -> None:
        landmarks = _facing()
        landmarks[NOSE] = RawLandmark(x=0.58, y=0.3, visibility=0.9)
        # 轉頭時遠側耳朵常常同時不可見,只留單耳,重現使用者「轉頭看旁邊螢幕」的情境
        landmarks[LEFT_EAR] = RawLandmark(x=0.5, y=0.3, visibility=0.1)
        sample = sample_from_landmarks(landmarks)
        assert sample is not None
        assert sample.nose_offset_ratio == pytest.approx(0.08 / 0.2)

    def test_nose_not_visible_returns_none(self) -> None:
        landmarks = _facing()
        landmarks[NOSE] = RawLandmark(x=0.5, y=0.5, visibility=0.1)
        assert sample_from_landmarks(landmarks) is None

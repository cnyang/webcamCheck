import pytest

from webcamcheck.geometry import (
    Point,
    ear_shoulder_angle,
    nose_shoulder_offset_ratio,
    shoulder_tilt_angle,
    shoulder_width,
)


class TestEarShoulderAngle:
    def test_perfectly_upright_is_zero(self) -> None:
        assert ear_shoulder_angle(Point(0.5, 0.2), Point(0.5, 0.5)) == pytest.approx(0.0)

    def test_level_with_shoulder_is_ninety(self) -> None:
        assert ear_shoulder_angle(Point(0.8, 0.5), Point(0.5, 0.5)) == pytest.approx(90.0)

    def test_forty_five_degrees(self) -> None:
        assert ear_shoulder_angle(Point(0.6, 0.4), Point(0.5, 0.5)) == pytest.approx(45.0)

    def test_symmetric_regardless_of_side(self) -> None:
        left = ear_shoulder_angle(Point(0.4, 0.4), Point(0.5, 0.5))
        right = ear_shoulder_angle(Point(0.6, 0.4), Point(0.5, 0.5))
        assert left == pytest.approx(right)

    def test_head_below_shoulder_exceeds_ninety_instead_of_folding_back(self) -> None:
        # 頭垂到肩膀線以下(趴在桌上)必須繼續往 90 度以上長,不能折返回小角度被當成坐姿良好
        collapsed = ear_shoulder_angle(Point(0.52, 0.75), Point(0.50, 0.60))
        assert collapsed > 90.0

    def test_angle_increases_monotonically_as_head_drops(self) -> None:
        shoulder = Point(0.50, 0.60)
        angles = [ear_shoulder_angle(Point(0.52, y), shoulder) for y in (0.30, 0.50, 0.58, 0.60, 0.65, 0.75)]
        assert angles == sorted(angles)

    def test_aspect_ratio_scales_horizontal_offset(self) -> None:
        ear, shoulder = Point(0.6, 0.4), Point(0.5, 0.5)
        square = ear_shoulder_angle(ear, shoulder, aspect_ratio=1.0)
        widescreen = ear_shoulder_angle(ear, shoulder, aspect_ratio=16 / 9)
        assert widescreen > square


class TestShoulderTiltAngle:
    def test_level_shoulders_is_zero(self) -> None:
        assert shoulder_tilt_angle(Point(0.3, 0.5), Point(0.7, 0.5)) == pytest.approx(0.0)

    def test_fully_vertical_is_ninety(self) -> None:
        assert shoulder_tilt_angle(Point(0.5, 0.3), Point(0.5, 0.7)) == pytest.approx(90.0)

    def test_tilt_direction_does_not_affect_magnitude(self) -> None:
        left_low = shoulder_tilt_angle(Point(0.3, 0.6), Point(0.7, 0.4))
        right_low = shoulder_tilt_angle(Point(0.3, 0.4), Point(0.7, 0.6))
        assert left_low == pytest.approx(right_low)


class TestShoulderWidth:
    def test_measures_horizontal_distance(self) -> None:
        assert shoulder_width(Point(0.3, 0.5), Point(0.7, 0.5)) == pytest.approx(0.4)

    def test_applies_aspect_ratio(self) -> None:
        assert shoulder_width(Point(0.3, 0.5), Point(0.7, 0.5), aspect_ratio=2.0) == pytest.approx(0.8)

    def test_shrinks_when_shoulders_foreshorten(self) -> None:
        facing = shoulder_width(Point(0.25, 0.5), Point(0.75, 0.5))
        turned = shoulder_width(Point(0.45, 0.5), Point(0.60, 0.5))
        assert turned < facing


class TestShoulderWidthAsDistance:
    def test_grows_when_torso_leans_in(self) -> None:
        # 實測:上身前傾時肩寬從基準的 100% 漲到 113~117%
        upright = shoulder_width(Point(0.40, 0.6), Point(0.60, 0.6))
        leaning = shoulder_width(Point(0.37, 0.6), Point(0.63, 0.6))
        assert leaning > upright


class TestNoseShoulderOffsetRatio:
    def test_nose_above_shoulder_mid_is_zero(self) -> None:
        assert nose_shoulder_offset_ratio(Point(0.5, 0.3), Point(0.5, 0.6), shoulder_width=0.2) == pytest.approx(0.0)

    def test_offset_scales_with_shoulder_width(self) -> None:
        narrow = nose_shoulder_offset_ratio(Point(0.55, 0.3), Point(0.5, 0.6), shoulder_width=0.1)
        wide = nose_shoulder_offset_ratio(Point(0.55, 0.3), Point(0.5, 0.6), shoulder_width=0.2)
        assert narrow == pytest.approx(wide * 2)

    def test_turning_head_increases_ratio(self) -> None:
        # 轉頭看側邊螢幕時鼻子明顯偏離肩膀中點,比值要比面向鏡頭時大
        facing = nose_shoulder_offset_ratio(Point(0.50, 0.3), Point(0.5, 0.6), shoulder_width=0.2)
        turned = nose_shoulder_offset_ratio(Point(0.62, 0.3), Point(0.5, 0.6), shoulder_width=0.2)
        assert turned > facing

    def test_zero_shoulder_width_does_not_divide_by_zero(self) -> None:
        assert nose_shoulder_offset_ratio(Point(0.6, 0.3), Point(0.5, 0.6), shoulder_width=0.0) == 0.0

    def test_aspect_ratio_scales_horizontal_offset(self) -> None:
        nose, mid = Point(0.6, 0.3), Point(0.5, 0.6)
        square = nose_shoulder_offset_ratio(nose, mid, shoulder_width=0.2, aspect_ratio=1.0)
        widescreen = nose_shoulder_offset_ratio(nose, mid, shoulder_width=0.2, aspect_ratio=16 / 9)
        assert widescreen > square

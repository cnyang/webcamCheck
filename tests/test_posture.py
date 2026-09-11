import pytest

from webcamcheck.posture import Baseline, PostureSample, PostureStatus, Verdict, classify, is_facing_camera

FACING_RATIO = 0.7


@pytest.fixture
def baseline() -> Baseline:
    return Baseline(neck_angle_deg=10.0, shoulder_tilt_deg=2.0, shoulder_width=0.50)


def _sample(neck: float = 10.0, tilt: float = 2.0, width: float = 0.50) -> PostureSample:
    return PostureSample(neck_angle_deg=neck, shoulder_tilt_deg=tilt, shoulder_width=width)


def _classify(sample: PostureSample, baseline: Baseline, check_tilt: bool = False) -> Verdict:
    return classify(
        sample,
        baseline,
        neck_tolerance_deg=8.0,
        tilt_tolerance_deg=6.0,
        facing_ratio=FACING_RATIO,
        check_tilt=check_tilt,
    )


class TestClassify:
    def test_matches_baseline_is_good(self, baseline: Baseline) -> None:
        verdict = _classify(_sample(), baseline)
        assert verdict.status is PostureStatus.GOOD
        assert verdict.is_good
        assert not verdict.forward_slouch

    def test_within_tolerance_is_good(self, baseline: Baseline) -> None:
        assert _classify(_sample(neck=17.0), baseline).status is PostureStatus.GOOD

    def test_neck_angle_over_tolerance_is_bad(self, baseline: Baseline) -> None:
        verdict = _classify(_sample(neck=30.0), baseline)
        assert verdict.status is PostureStatus.BAD
        assert verdict.forward_slouch
        assert not verdict.side_lean

    def test_slumped_onto_desk_is_bad_not_good(self, baseline: Baseline) -> None:
        # 頭垂到肩膀線以下,角度超過 90 度,必須是最糟的判定而不是「良好」
        assert _classify(_sample(neck=115.0), baseline).status is PostureStatus.BAD

    def test_neck_angle_below_baseline_never_flags(self, baseline: Baseline) -> None:
        assert _classify(_sample(neck=1.0), baseline).status is PostureStatus.GOOD

    def test_shoulder_tilt_ignored_by_default(self, baseline: Baseline) -> None:
        # 單顆前視鏡頭分不出轉身與歪斜,預設不看肩膀傾斜,免得一直誤報
        verdict = _classify(_sample(tilt=40.0), baseline)
        assert verdict.status is PostureStatus.GOOD
        assert not verdict.side_lean

    def test_shoulder_tilt_flags_when_opted_in(self, baseline: Baseline) -> None:
        verdict = _classify(_sample(tilt=40.0), baseline, check_tilt=True)
        assert verdict.status is PostureStatus.BAD
        assert verdict.side_lean

    def test_turned_away_is_unknown_not_bad(self, baseline: Baseline) -> None:
        # 轉身去用另一台電腦:肩寬被壓扁,這時候姿勢再怎麼「歪」都不該告警
        verdict = _classify(_sample(neck=60.0, width=0.20), baseline)
        assert verdict.status is PostureStatus.UNKNOWN
        assert not verdict.forward_slouch

    def test_slightly_reduced_shoulder_width_still_judged(self, baseline: Baseline) -> None:
        # 只是稍微動一下(肩寬 90%)不該被當成轉身而停止監控
        assert _classify(_sample(neck=30.0, width=0.45), baseline).status is PostureStatus.BAD


class TestIsFacingCamera:
    def test_full_width_is_facing(self, baseline: Baseline) -> None:
        assert is_facing_camera(_sample(width=0.50), baseline, FACING_RATIO)

    def test_at_threshold_is_facing(self, baseline: Baseline) -> None:
        assert is_facing_camera(_sample(width=0.35), baseline, FACING_RATIO)

    def test_below_threshold_is_not_facing(self, baseline: Baseline) -> None:
        assert not is_facing_camera(_sample(width=0.34), baseline, FACING_RATIO)

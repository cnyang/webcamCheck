import numpy as np

from webcamcheck.monitor import check_once
from webcamcheck.ports import Frame
from webcamcheck.posture import Baseline, PostureSample, PostureStatus
from webcamcheck.state import PostureMonitorState

BASELINE = Baseline(neck_angle_deg=10.0, shoulder_tilt_deg=2.0, shoulder_width=0.50)
FRAME = np.zeros((1, 1, 3), dtype=np.uint8)

GOOD_SAMPLE = PostureSample(neck_angle_deg=10.0, shoulder_tilt_deg=2.0, shoulder_width=0.50)
SLOUCH_SAMPLE = PostureSample(neck_angle_deg=30.0, shoulder_tilt_deg=2.0, shoulder_width=0.50)
TURNED_SAMPLE = PostureSample(neck_angle_deg=60.0, shoulder_tilt_deg=2.0, shoulder_width=0.20)


class _FixedCamera:
    def __init__(self, frame: Frame | None) -> None:
        self._frame = frame

    def read(self) -> Frame | None:
        return self._frame


class _FixedEstimator:
    def __init__(self, sample: PostureSample | None) -> None:
        self._sample = sample

    def detect(self, frame: Frame) -> PostureSample | None:
        return self._sample

    def close(self) -> None:
        pass


class _Harness:
    """把 camera/estimator/state 綁在一起,測試裡只要指定「這一刻偵測到什麼」和時間。"""

    def __init__(self, check_tilt: bool = False) -> None:
        self.state = PostureMonitorState()
        self.notified: list[str] = []
        self.check_tilt = check_tilt

    def tick(self, sample: PostureSample | None, now: float, frame: Frame | None = FRAME) -> PostureStatus:
        verdict = check_once(
            camera=_FixedCamera(frame),
            estimator=_FixedEstimator(sample),
            baseline=BASELINE,
            state=self.state,
            neck_tolerance_deg=8.0,
            tilt_tolerance_deg=6.0,
            sustain_seconds=5.0,
            cooldown_seconds=60.0,
            now=now,
            facing_ratio=0.7,
            check_tilt=self.check_tilt,
            notify_fn=lambda title, message: self.notified.append(message),
        )
        return verdict.status


class TestCheckOnce:
    def test_no_frame_is_unknown(self) -> None:
        h = _Harness()
        assert h.tick(None, 0.0, frame=None) is PostureStatus.UNKNOWN
        assert h.notified == []

    def test_no_pose_detected_is_unknown(self) -> None:
        h = _Harness()
        assert h.tick(None, 0.0) is PostureStatus.UNKNOWN
        assert h.notified == []

    def test_good_posture_never_notifies(self) -> None:
        h = _Harness()
        for t in (0.0, 10.0, 20.0):
            assert h.tick(GOOD_SAMPLE, t) is PostureStatus.GOOD
        assert h.notified == []

    def test_sustained_slouch_notifies(self) -> None:
        h = _Harness()
        h.tick(SLOUCH_SAMPLE, 0.0)
        h.tick(SLOUCH_SAMPLE, 6.0)
        assert h.notified == ["頭往前垂了,調整一下吧"]

    def test_turning_to_the_other_computer_does_not_notify(self) -> None:
        # 轉身去用旁邊那台電腦,肩寬被壓扁 -> 不判斷,長時間也不該跳通知
        h = _Harness()
        for t in (0.0, 10.0, 60.0, 300.0):
            assert h.tick(TURNED_SAMPLE, t) is PostureStatus.UNKNOWN
        assert h.notified == []

    def test_leaving_desk_then_returning_restarts_the_sustain_window(self) -> None:
        # 舊 bug:離開座位期間狀態沒更新,回座才歪 2 秒就立刻跳通知
        h = _Harness()
        h.tick(SLOUCH_SAMPLE, 0.0)
        for t in (60.0, 300.0, 600.0):
            h.tick(None, t)
        assert h.tick(SLOUCH_SAMPLE, 602.0) is PostureStatus.BAD
        assert h.notified == [], "回座才 2 秒不該通知"
        h.tick(SLOUCH_SAMPLE, 607.5)
        assert h.notified == ["頭往前垂了,調整一下吧"]

    def test_message_mentions_both_problems(self) -> None:
        h = _Harness(check_tilt=True)
        both = PostureSample(neck_angle_deg=30.0, shoulder_tilt_deg=40.0, shoulder_width=0.50)
        h.tick(both, 0.0)
        h.tick(both, 6.0)
        assert h.notified == ["頭往前垂、肩膀也歪了,調整一下吧"]

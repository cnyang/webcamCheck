import time
from collections.abc import Sequence

import numpy as np
import pytest

from webcamcheck.calibration import calibrate
from webcamcheck.ports import Frame
from webcamcheck.posture import PostureSample


class _FakeCamera:
    def read(self) -> Frame:
        return np.zeros((1, 1, 3), dtype=np.uint8)


class _DeadCamera:
    def read(self) -> Frame | None:
        return None


class _FakeEstimator:
    def __init__(self, samples: Sequence[PostureSample | None]) -> None:
        self._samples = iter(samples)

    def detect(self, frame: Frame) -> PostureSample | None:
        return next(self._samples, None)

    def close(self) -> None:
        pass


def _sample(neck: float, tilt: float, width: float) -> PostureSample:
    return PostureSample(neck_angle_deg=neck, shoulder_tilt_deg=tilt, shoulder_width=width)


def test_calibrate_averages_detected_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter([0.0, 1.0, 2.0, 6.0])  # 最後一個 tick 超過 5 秒期限,迴圈結束
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))

    samples = [_sample(10.0, 2.0, 0.40), _sample(20.0, 4.0, 0.60)]
    baseline = calibrate(_FakeCamera(), _FakeEstimator(samples), duration_seconds=5.0, sleep_fn=lambda _: None)

    assert baseline.neck_angle_deg == pytest.approx(15.0)
    assert baseline.shoulder_tilt_deg == pytest.approx(3.0)
    assert baseline.shoulder_width == pytest.approx(0.50)


def test_calibrate_raises_when_nothing_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter([0.0, 6.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))

    with pytest.raises(RuntimeError):
        calibrate(_FakeCamera(), _FakeEstimator([]), duration_seconds=5.0, sleep_fn=lambda _: None)


def test_calibrate_paces_itself_when_camera_yields_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    # 鏡頭開得起來卻拿不到影格時,必須靠 sleep 讓出 CPU,不能 100% 空轉
    ticks = iter([0.0, 1.0, 2.0, 6.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    slept: list[float] = []

    with pytest.raises(RuntimeError):
        calibrate(
            _DeadCamera(),
            _FakeEstimator([]),
            duration_seconds=5.0,
            sleep_fn=slept.append,
        )

    assert slept, "每次迴圈都要 sleep"
    assert all(s > 0 for s in slept)

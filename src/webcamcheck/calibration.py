"""坐正後錄一段時間,取平均角度當作個人化基準值。"""

from __future__ import annotations

import time
from collections.abc import Callable

from webcamcheck.ports import FrameSource, PoseDetector
from webcamcheck.posture import Baseline, PostureSample

# 每幀之間稍微歇一下:校準只需要幾十個樣本取平均,不必把 CPU 燒滿;
# 鏡頭卡住一直回傳不了影格時,也不會變成 100% 空轉。
SAMPLE_INTERVAL_SECONDS = 0.1


def calibrate(
    camera: FrameSource,
    estimator: PoseDetector,
    duration_seconds: float = 5.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Baseline:
    samples: list[PostureSample] = []
    deadline = time.monotonic() + duration_seconds
    while time.monotonic() < deadline:
        frame = camera.read()
        if frame is not None:
            sample = estimator.detect(frame)
            if sample is not None:
                samples.append(sample)
        sleep_fn(SAMPLE_INTERVAL_SECONDS)
    if not samples:
        raise RuntimeError("校準期間沒偵測到姿勢,確認鏡頭有拍到臉和肩膀再重試。")
    return Baseline(
        neck_angle_deg=sum(s.neck_angle_deg for s in samples) / len(samples),
        shoulder_tilt_deg=sum(s.shoulder_tilt_deg for s in samples) / len(samples),
        shoulder_width=sum(s.shoulder_width for s in samples) / len(samples),
        nose_offset_ratio=sum(s.nose_offset_ratio for s in samples) / len(samples),
    )

"""主監控迴圈:每隔一段時間拍一幀、判斷姿勢,壞姿勢持續夠久就跳系統通知。"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable

from webcamcheck.camera import Camera
from webcamcheck.notifier import DEFAULT_SOUND, notify
from webcamcheck.ports import FrameSource, PoseDetector
from webcamcheck.pose_estimator import PoseEstimator
from webcamcheck.posture import UNKNOWN_VERDICT, Baseline, Verdict, classify
from webcamcheck.state import PostureMonitorState

logger = logging.getLogger(__name__)


def evaluate(
    camera: FrameSource,
    estimator: PoseDetector,
    baseline: Baseline,
    neck_tolerance_deg: float,
    tilt_tolerance_deg: float,
    facing_ratio: float,
    check_tilt: bool,
    near_ratio: float,
    check_distance: bool,
) -> Verdict:
    """拍一幀並判斷這一刻的姿勢。拍不到影格或偵測不到人(離開座位)一律回 UNKNOWN,
    絕對不能直接 return 不理它,否則狀態機不知道中斷過,回座後會被舊的計時立刻觸發通知。"""
    frame = camera.read()
    if frame is None:
        return UNKNOWN_VERDICT
    sample = estimator.detect(frame)
    if sample is None:
        return UNKNOWN_VERDICT
    return classify(
        sample,
        baseline,
        neck_tolerance_deg=neck_tolerance_deg,
        tilt_tolerance_deg=tilt_tolerance_deg,
        facing_ratio=facing_ratio,
        check_tilt=check_tilt,
        near_ratio=near_ratio,
        check_distance=check_distance,
    )


def check_once(
    camera: FrameSource,
    estimator: PoseDetector,
    baseline: Baseline,
    state: PostureMonitorState,
    neck_tolerance_deg: float,
    tilt_tolerance_deg: float,
    sustain_seconds: float,
    cooldown_seconds: float,
    now: float,
    facing_ratio: float,
    check_tilt: bool = False,
    near_ratio: float = 1.2,
    check_distance: bool = True,
    notify_fn: Callable[[str, str], None] = notify,
) -> Verdict:
    """跑一次「拍一幀 -> 判斷 -> 節流通知」,抽出來是為了能在測試裡直接呼叫,不用真的等待或開鏡頭。"""
    verdict = evaluate(
        camera,
        estimator,
        baseline,
        neck_tolerance_deg=neck_tolerance_deg,
        tilt_tolerance_deg=tilt_tolerance_deg,
        facing_ratio=facing_ratio,
        check_tilt=check_tilt,
        near_ratio=near_ratio,
        check_distance=check_distance,
    )
    should_notify = state.update(
        status=verdict.status,
        now=now,
        sustain_seconds=sustain_seconds,
        cooldown_seconds=cooldown_seconds,
    )
    if should_notify:
        notify_fn("坐姿提醒", f"{_reason(verdict)},調整一下吧")
    return verdict


def _reason(verdict: Verdict) -> str:
    """把所有成立的問題串成一句話。同時駝背又坐太近時,只講其中一個會讓人改了還是一直被提醒。"""
    problems = [
        text
        for flagged, text in (
            (verdict.forward_slouch, "頭往前垂"),
            (verdict.side_lean, "肩膀歪掉"),
            (verdict.too_close, "離螢幕太近"),
        )
        if flagged
    ]
    return "、".join(problems) + "了"


def run(
    camera: Camera,
    baseline: Baseline,
    neck_tolerance_deg: float = 8.0,
    tilt_tolerance_deg: float = 6.0,
    check_interval_seconds: float = 2.0,
    sustain_seconds: float = 8.0,
    cooldown_seconds: float = 120.0,
    facing_ratio: float = 0.7,
    check_tilt: bool = False,
    near_ratio: float = 1.2,
    check_distance: bool = True,
    sound_name: str | None = DEFAULT_SOUND,
) -> None:
    state = PostureMonitorState()
    notify_fn = functools.partial(notify, sound_name=sound_name)
    with camera:
        estimator = PoseEstimator()
        try:
            logger.info("開始監控坐姿,Ctrl+C 結束。")
            while True:
                check_once(
                    camera=camera,
                    estimator=estimator,
                    baseline=baseline,
                    state=state,
                    neck_tolerance_deg=neck_tolerance_deg,
                    tilt_tolerance_deg=tilt_tolerance_deg,
                    sustain_seconds=sustain_seconds,
                    cooldown_seconds=cooldown_seconds,
                    now=time.monotonic(),
                    facing_ratio=facing_ratio,
                    check_tilt=check_tilt,
                    near_ratio=near_ratio,
                    check_distance=check_distance,
                    notify_fn=notify_fn,
                )
                time.sleep(check_interval_seconds)
        except KeyboardInterrupt:
            logger.info("結束監控。")
        finally:
            estimator.close()

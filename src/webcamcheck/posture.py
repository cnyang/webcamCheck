"""坐姿判斷邏輯:純函式,吃已算好的角度樣本與基準值,不碰攝影機。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PostureStatus(Enum):
    GOOD = "good"
    BAD = "bad"
    # 判斷不了:離開座位、鏡頭拍不到肩膀,或轉身去用另一台電腦。這種時候不能當成姿勢良好,
    # 也不能當成歪掉,必須讓計時歸零暫停,否則回座後會被之前累積的秒數立刻觸發通知。
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PostureSample:
    neck_angle_deg: float
    shoulder_tilt_deg: float
    shoulder_width: float


@dataclass(frozen=True)
class Baseline:
    neck_angle_deg: float
    shoulder_tilt_deg: float
    shoulder_width: float


@dataclass(frozen=True)
class Verdict:
    status: PostureStatus
    forward_slouch: bool = False
    side_lean: bool = False

    @property
    def is_good(self) -> bool:
        return self.status is PostureStatus.GOOD


UNKNOWN_VERDICT = Verdict(status=PostureStatus.UNKNOWN)


def is_facing_camera(sample: PostureSample, baseline: Baseline, facing_ratio: float) -> bool:
    """肩寬縮到基準值的一定比例以下,代表人轉身了(例如轉去用旁邊那台電腦),這時候不該判斷坐姿。"""
    return sample.shoulder_width >= baseline.shoulder_width * facing_ratio


def classify(
    sample: PostureSample,
    baseline: Baseline,
    neck_tolerance_deg: float,
    tilt_tolerance_deg: float,
    facing_ratio: float,
    check_tilt: bool = False,
) -> Verdict:
    """與校準基準比較,只在角度「變大」超過容許值時才算歪掉;
    比基準更挺直不算異常,避免使用者坐得更端正反而被誤判。"""
    if not is_facing_camera(sample, baseline, facing_ratio):
        return UNKNOWN_VERDICT

    forward_slouch = sample.neck_angle_deg > baseline.neck_angle_deg + neck_tolerance_deg
    # 肩膀傾斜在單顆前視鏡頭下分不出「轉身」和「真的歪斜」,預設不啟用,避免一直誤報。
    side_lean = check_tilt and sample.shoulder_tilt_deg > baseline.shoulder_tilt_deg + tilt_tolerance_deg
    status = PostureStatus.BAD if (forward_slouch or side_lean) else PostureStatus.GOOD
    return Verdict(status=status, forward_slouch=forward_slouch, side_lean=side_lean)

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
    too_close: bool = False

    @property
    def is_good(self) -> bool:
        return self.status is PostureStatus.GOOD


UNKNOWN_VERDICT = Verdict(status=PostureStatus.UNKNOWN)


def is_facing_camera(sample: PostureSample, baseline: Baseline, facing_ratio: float) -> bool:
    """肩寬縮到基準值的一定比例以下,代表人轉身了(例如轉去用旁邊那台電腦),這時候不該判斷坐姿。"""
    return sample.shoulder_width >= baseline.shoulder_width * facing_ratio


def is_too_close(sample: PostureSample, baseline: Baseline, near_ratio: float) -> bool:
    """肩寬比校準時大太多,代表上身往螢幕前傾了(肩膀靠近鏡頭,投影變大)。

    實測(基準 = 坐正校準值):正常坐著 99~107%、背打直往前傾 109~117%。同階段內抖動只有
    ±1.5%,所以 1.12 的門檻有 5% 緩衝,坐著不動不會誤報。
    """
    return sample.shoulder_width > baseline.shoulder_width * near_ratio


def classify(
    sample: PostureSample,
    baseline: Baseline,
    neck_tolerance_deg: float,
    tilt_tolerance_deg: float,
    facing_ratio: float,
    check_tilt: bool = False,
    near_ratio: float = 1.12,
    check_distance: bool = True,
) -> Verdict:
    """與校準基準比較,只在角度「變大」超過容許值時才算歪掉;
    比基準更挺直不算異常,避免使用者坐得更端正反而被誤判。"""
    if not is_facing_camera(sample, baseline, facing_ratio):
        return UNKNOWN_VERDICT

    forward_slouch = sample.neck_angle_deg > baseline.neck_angle_deg + neck_tolerance_deg
    # 肩膀傾斜在單顆前視鏡頭下分不出「轉身」和「真的歪斜」,預設不啟用,避免一直誤報。
    side_lean = check_tilt and sample.shoulder_tilt_deg > baseline.shoulder_tilt_deg + tilt_tolerance_deg
    # 駝背也會把肩膀帶向鏡頭(實測 111~119%,和前傾的 109~117% 重疊),肩寬分不出這兩者。
    # 但 neck 角度分得出來(前傾 20~23°、駝背 27~48°),所以駝背成立時就不另外報「太近」:
    # 該修的是駝背,兩個一起報只是噪音。
    too_close = check_distance and not forward_slouch and is_too_close(sample, baseline, near_ratio)
    status = PostureStatus.BAD if (forward_slouch or side_lean or too_close) else PostureStatus.GOOD
    return Verdict(status=status, forward_slouch=forward_slouch, side_lean=side_lean, too_close=too_close)

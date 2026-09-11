"""把 mediapipe BlazePose 的 33 個關鍵點,轉成 posture.py 看得懂的角度樣本。"""

from __future__ import annotations

from dataclasses import dataclass

from webcamcheck.geometry import Point, ear_shoulder_angle, shoulder_tilt_angle, shoulder_width
from webcamcheck.posture import PostureSample

# BlazePose 33 點拓樸中固定的索引。
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14

VISIBILITY_THRESHOLD = 0.5


@dataclass(frozen=True)
class RawLandmark:
    x: float
    y: float
    visibility: float


def sample_from_landmarks(landmarks: list[RawLandmark], aspect_ratio: float = 1.0) -> PostureSample | None:
    """可見度不足的關鍵點會被忽略;肩膀兩點缺一,或兩耳都不可見,直接回傳 None
    (代表這一幀不夠可靠,例如人不在座位上,呼叫端應該當成「判斷不了」而不是姿勢良好)。"""

    def visible(index: int) -> bool:
        return landmarks[index].visibility >= VISIBILITY_THRESHOLD

    def point(index: int) -> Point:
        landmark = landmarks[index]
        return Point(x=landmark.x, y=landmark.y)

    if not (visible(LEFT_SHOULDER) and visible(RIGHT_SHOULDER)):
        return None

    left_shoulder = point(LEFT_SHOULDER)
    right_shoulder = point(RIGHT_SHOULDER)
    shoulder_mid = Point(
        x=(left_shoulder.x + right_shoulder.x) / 2,
        y=(left_shoulder.y + right_shoulder.y) / 2,
    )

    ear_angles = [
        ear_shoulder_angle(point(index), shoulder_mid, aspect_ratio)
        for index in (LEFT_EAR, RIGHT_EAR)
        if visible(index)
    ]
    if not ear_angles:
        return None

    return PostureSample(
        neck_angle_deg=sum(ear_angles) / len(ear_angles),
        shoulder_tilt_deg=shoulder_tilt_angle(left_shoulder, right_shoulder, aspect_ratio),
        shoulder_width=shoulder_width(left_shoulder, right_shoulder, aspect_ratio),
    )

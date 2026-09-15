"""把耳朵/肩膀/手肘的連線和角度畫在影像上。

cv2.putText 畫不出中文(會變成問號方塊),所以畫面上的文字一律用英數。
"""

from __future__ import annotations

import cv2

from webcamcheck.geometry import Point, angle_at_vertex
from webcamcheck.landmarks import (
    LEFT_EAR,
    LEFT_ELBOW,
    LEFT_SHOULDER,
    RIGHT_EAR,
    RIGHT_ELBOW,
    RIGHT_SHOULDER,
    VISIBILITY_THRESHOLD,
    RawLandmark,
)
from webcamcheck.ports import Frame
from webcamcheck.posture import Baseline, PostureSample, PostureStatus, Verdict

GREEN = (120, 220, 120)
RED = (80, 80, 240)
GREY = (170, 170, 170)
WHITE = (245, 245, 245)
CYAN = (230, 200, 90)
ARM = (90, 200, 250)

STATUS_COLORS = {
    PostureStatus.GOOD: GREEN,
    PostureStatus.BAD: RED,
    PostureStatus.UNKNOWN: GREY,
}
STATUS_LABELS = {
    PostureStatus.GOOD: "GOOD",
    PostureStatus.BAD: "FIX YOUR POSTURE",
    PostureStatus.UNKNOWN: "PAUSED (away / turned)",
}

FONT = cv2.FONT_HERSHEY_SIMPLEX


def _to_pixels(landmark: RawLandmark, width: int, height: int) -> tuple[int, int]:
    return int(landmark.x * width), int(landmark.y * height)


def _visible(landmark: RawLandmark) -> bool:
    return landmark.visibility >= VISIBILITY_THRESHOLD


def _label(frame: Frame, text: str, at: tuple[int, int], color: tuple[int, int, int]) -> None:
    """先畫一層黑色粗體當外框,文字在淺色背景上才看得清楚。"""
    cv2.putText(frame, text, at, FONT, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, text, at, FONT, 0.6, color, 1, cv2.LINE_AA)


def draw_posture(
    frame: Frame,
    landmarks: list[RawLandmark] | None,
    sample: PostureSample | None,
    verdict: Verdict,
    baseline: Baseline,
) -> Frame:
    """回傳畫好連線與角度的影像副本,不改動原始影格。landmarks 為 None(沒偵測到人)時只畫文字。"""
    canvas = frame.copy()
    height, width = canvas.shape[:2]
    aspect = width / height
    color = STATUS_COLORS[verdict.status]

    if landmarks is not None and all(_visible(landmarks[i]) for i in (LEFT_SHOULDER, RIGHT_SHOULDER)):
        left_px = _to_pixels(landmarks[LEFT_SHOULDER], width, height)
        right_px = _to_pixels(landmarks[RIGHT_SHOULDER], width, height)
        cv2.line(canvas, left_px, right_px, color, 2, cv2.LINE_AA)

        mid_px = ((left_px[0] + right_px[0]) // 2, (left_px[1] + right_px[1]) // 2)
        # 垂直參考線:耳朵應該落在這條線上(書上說的「耳朵和肩膀的連線呈筆直」)
        cv2.line(canvas, mid_px, (mid_px[0], max(0, mid_px[1] - int(height * 0.45))), CYAN, 1, cv2.LINE_AA)
        cv2.circle(canvas, mid_px, 4, color, -1, cv2.LINE_AA)

        for ear_index, elbow_index, shoulder_index, side in (
            (LEFT_EAR, LEFT_ELBOW, LEFT_SHOULDER, "L"),
            (RIGHT_EAR, RIGHT_ELBOW, RIGHT_SHOULDER, "R"),
        ):
            shoulder_px = _to_pixels(landmarks[shoulder_index], width, height)
            cv2.circle(canvas, shoulder_px, 6, color, -1, cv2.LINE_AA)

            if _visible(landmarks[ear_index]):
                ear_px = _to_pixels(landmarks[ear_index], width, height)
                cv2.line(canvas, ear_px, mid_px, color, 2, cv2.LINE_AA)
                cv2.circle(canvas, ear_px, 6, color, -1, cv2.LINE_AA)

            if _visible(landmarks[elbow_index]):
                elbow_px = _to_pixels(landmarks[elbow_index], width, height)
                cv2.line(canvas, shoulder_px, elbow_px, ARM, 2, cv2.LINE_AA)
                cv2.circle(canvas, elbow_px, 6, ARM, -1, cv2.LINE_AA)

                if _visible(landmarks[ear_index]):
                    opening = angle_at_vertex(
                        Point(landmarks[shoulder_index].x, landmarks[shoulder_index].y),
                        Point(landmarks[ear_index].x, landmarks[ear_index].y),
                        Point(landmarks[elbow_index].x, landmarks[elbow_index].y),
                        aspect,
                    )
                    midpoint = ((shoulder_px[0] + elbow_px[0]) // 2, (shoulder_px[1] + elbow_px[1]) // 2)
                    _label(canvas, f"{side} ear-sh-elbow {opening:.0f}deg", midpoint, ARM)

        if sample is not None:
            _label(canvas, f"neck {sample.neck_angle_deg:.0f}deg", (mid_px[0] + 12, mid_px[1] - 34), color)

    _draw_readout(canvas, landmarks, sample, verdict, baseline, color)
    return canvas


def _elbows_visible(landmarks: list[RawLandmark] | None) -> bool:
    if landmarks is None:
        return False
    return any(_visible(landmarks[index]) for index in (LEFT_ELBOW, RIGHT_ELBOW))


def _draw_readout(
    canvas: Frame,
    landmarks: list[RawLandmark] | None,
    sample: PostureSample | None,
    verdict: Verdict,
    baseline: Baseline,
    color: tuple[int, int, int],
) -> None:
    lines = [STATUS_LABELS[verdict.status]]
    if sample is None:
        lines.append("no person detected")
    else:
        delta = sample.neck_angle_deg - baseline.neck_angle_deg
        ratio = sample.shoulder_width / baseline.shoulder_width
        lines.append(f"neck {sample.neck_angle_deg:5.1f}deg  (base {baseline.neck_angle_deg:.1f}, {delta:+.1f})")
        lines.append(f"shoulder tilt {sample.shoulder_tilt_deg:5.1f}deg")
        # 同一個比例兩個意思:掉太多 = 轉身,漲太多 = 上身前傾靠太近
        lines.append(f"shoulder width {ratio:.0%} of calibrated")
        nose_delta = sample.nose_offset_ratio - baseline.nose_offset_ratio
        lines.append(
            f"nose offset {sample.nose_offset_ratio:.3f}  (base {baseline.nose_offset_ratio:.3f}, {nose_delta:+.3f})"
        )
        if verdict.too_close:
            lines.append("TOO CLOSE - sit back")
        if not _elbows_visible(landmarks):
            # 坐太近時手肘會掉出取景範圍,講清楚是取景問題,不是偵測壞掉
            lines.append("elbows out of frame - sit back or tilt camera down")

    for row, text in enumerate(lines):
        _label(canvas, text, (16, 34 + row * 28), color if row == 0 else WHITE)

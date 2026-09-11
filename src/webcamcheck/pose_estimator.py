"""包住 mediapipe 的姿勢偵測。

原本想用 mediapipe 1.x 的新版 Tasks API(PoseLandmarker),但在這台 macOS(Apple Silicon)
上,不管是否指定 CPU delegate,都會在 TensorsToDetectionsCalculator::Open() 因為
DrishtiMetalHelper 找不到 GPU calculator service 而直接 crash(F0000 ... Service is
unavailable)。改鎖 mediapipe==0.10.21,改用舊版的 mp.solutions.pose,已用 Brio 100
實測正常偵測到 33 個關鍵點,不用額外下載模型檔也更穩定。
"""

from __future__ import annotations

import cv2
import mediapipe as mp

from webcamcheck.landmarks import RawLandmark, sample_from_landmarks
from webcamcheck.ports import Frame
from webcamcheck.posture import PostureSample


class PoseEstimator:
    def __init__(self) -> None:
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def detect_landmarks(self, frame: Frame) -> list[RawLandmark] | None:
        """回傳 33 個原始關鍵點,畫面疊圖需要實際座標,不能只拿算好的角度。"""
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb_frame)
        if result.pose_landmarks is None:
            return None
        return [RawLandmark(x=lm.x, y=lm.y, visibility=lm.visibility) for lm in result.pose_landmarks.landmark]

    def detect(self, frame: Frame) -> PostureSample | None:
        landmarks = self.detect_landmarks(frame)
        if landmarks is None:
            return None
        # mediapipe 的 x 除以寬、y 除以高,基準不同,要把畫面長寬比傳下去才能還原成真實角度。
        height, width = frame.shape[:2]
        return sample_from_landmarks(landmarks, aspect_ratio=width / height)

    def close(self) -> None:
        self._pose.close()

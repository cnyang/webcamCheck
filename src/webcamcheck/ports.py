"""calibration.py / monitor.py 用的最小介面,讓測試可以塞假的攝影機與姿勢估計器,不必真的開鏡頭。"""

from __future__ import annotations

from typing import Any, Protocol

import numpy.typing as npt

from webcamcheck.posture import PostureSample

# cv2 的回傳型別(Mat 或不同 dtype 的 ndarray)不只一種,這裡只在意「是張影像」,dtype 用 Any 放寬。
Frame = npt.NDArray[Any]


class FrameSource(Protocol):
    def read(self) -> Frame | None: ...


class PoseDetector(Protocol):
    def detect(self, frame: Frame) -> PostureSample | None: ...

    def close(self) -> None: ...


class CameraHandle(FrameSource, Protocol):
    """常駐模式需要自己管開關,還要看得到連續讀取失敗次數才分得出「鏡頭掉了」和「人不在」。"""

    consecutive_read_failures: int

    def close(self) -> None: ...

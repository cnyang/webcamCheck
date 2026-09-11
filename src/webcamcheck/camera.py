"""攝影機擷取,直接走 AVFoundation,用名稱或 uniqueID 指定裝置。

為什麼不用 cv2.VideoCapture(index):**OpenCV 的裝置順序和 AVFoundation 對不上**。
實測(Brio 100 + iPhone 接續互通攝影機同時存在):

    AVFoundation devicesWithMediaType  ->  0=Brio 100, 1=iPhone
    OpenCV VideoCapture                ->  0=iPhone,   1=Brio 100

兩邊是反的,所以任何「用 AVFoundation 查名稱、再把序號交給 OpenCV」的做法都會開到錯的鏡頭。
改成自己開 AVCaptureSession,裝置用 uniqueID 指定,就沒有序號位移的問題了。
"""

from __future__ import annotations

import logging
import threading
import time
from types import TracebackType

import AVFoundation as avf
import CoreMedia
import dispatch
import numpy as np
import objc
import Quartz
from Foundation import NSObject

from webcamcheck.devices import DEFAULT_CAMERA_NAME, PERMISSION_HINT, CameraDevice, camera_is_authorized, find_device
from webcamcheck.ports import Frame

logger = logging.getLogger(__name__)

# 32BGRA:AVFoundation 直接吐 BGRA,取前三個 channel 就是 OpenCV 慣用的 BGR,不用再轉色。
PIXEL_FORMAT_32BGRA = 1111970369

FIRST_FRAME_TIMEOUT_SECONDS = 5.0
# 超過這個時間沒有新影格,就當作鏡頭掉了(被拔掉、被其他程式搶走)。
STALE_FRAME_SECONDS = 2.0


def frame_from_bgra(buffer: memoryview | bytes, width: int, height: int, stride: int) -> Frame:
    """CVPixelBuffer 的 BGRA 位元組轉成 BGR 影像。

    每一列的長度是 stride,通常大於 width*4(記憶體對齊的 padding),
    所以要照 stride 還原每列再把多的裁掉,不能直接 reshape 成 width,否則畫面會斜掉。
    取前三個 channel 就是 OpenCV 慣用的 BGR,不用再轉色。
    """
    raw = np.frombuffer(buffer, dtype=np.uint8)
    return raw.reshape(height, stride // 4, 4)[:, :width, :3].copy()


def is_fresh(frame: Frame | None, captured_at: float, now: float, stale_after: float = STALE_FRAME_SECONDS) -> bool:
    """影格是背景一直推進來的,所以「舊」代表鏡頭掉了,不是畫面裡沒有人。"""
    if frame is None:
        return False
    return (now - captured_at) <= stale_after


class _SampleBufferDelegate(NSObject):  # type: ignore[misc]
    """AVFoundation 在自己的 dispatch queue 上呼叫這裡,所以存取共用狀態要上鎖。"""

    def init(self) -> _SampleBufferDelegate:
        self = objc.super(_SampleBufferDelegate, self).init()
        if self is None:
            return None
        self._lock = threading.Lock()
        self._frame: Frame | None = None
        self._captured_at = 0.0
        return self

    def captureOutput_didOutputSampleBuffer_fromConnection_(
        self, _output: object, sample_buffer: object, _connection: object
    ) -> None:
        pixel_buffer = CoreMedia.CMSampleBufferGetImageBuffer(sample_buffer)
        if pixel_buffer is None:
            return
        Quartz.CVPixelBufferLockBaseAddress(pixel_buffer, Quartz.kCVPixelBufferLock_ReadOnly)
        try:
            width = Quartz.CVPixelBufferGetWidth(pixel_buffer)
            height = Quartz.CVPixelBufferGetHeight(pixel_buffer)
            stride = Quartz.CVPixelBufferGetBytesPerRow(pixel_buffer)
            base = Quartz.CVPixelBufferGetBaseAddress(pixel_buffer)
            if base is None:
                return
            frame = frame_from_bgra(base.as_buffer(stride * height), width, height, stride)
        finally:
            Quartz.CVPixelBufferUnlockBaseAddress(pixel_buffer, Quartz.kCVPixelBufferLock_ReadOnly)

        with self._lock:
            self._frame = frame
            self._captured_at = time.monotonic()

    def latest(self) -> tuple[Frame | None, float]:
        with self._lock:
            frame: Frame | None = self._frame
            return frame, self._captured_at


class Camera:
    """介面和先前的 OpenCV 版本相同:read() / close() / context manager / consecutive_read_failures。"""

    def __init__(self, name: str = DEFAULT_CAMERA_NAME, unique_id: str | None = None) -> None:
        self.consecutive_read_failures = 0
        if camera_is_authorized() is False:
            raise RuntimeError(PERMISSION_HINT)

        self.device: CameraDevice = find_device(name=name, unique_id=unique_id)
        device = avf.AVCaptureDevice.deviceWithUniqueID_(self.device.unique_id)
        if device is None:
            raise RuntimeError(f"攝影機「{self.device.name}」突然不見了,請重新接上。")

        device_input, error = avf.AVCaptureDeviceInput.deviceInputWithDevice_error_(device, None)
        if device_input is None:
            raise RuntimeError(f"無法開啟攝影機「{self.device.name}」:{error}")

        self._delegate = _SampleBufferDelegate.alloc().init()
        self._queue = dispatch.dispatch_queue_create(b"webcamcheck.capture", None)
        self._session = avf.AVCaptureSession.alloc().init()
        self._session.beginConfiguration()
        self._session.addInput_(device_input)
        output = avf.AVCaptureVideoDataOutput.alloc().init()
        output.setVideoSettings_({Quartz.kCVPixelBufferPixelFormatTypeKey: PIXEL_FORMAT_32BGRA})
        # 只要最新的一張,處理不及的直接丟掉,不要累積延遲
        output.setAlwaysDiscardsLateVideoFrames_(True)
        output.setSampleBufferDelegate_queue_(self._delegate, self._queue)
        self._session.addOutput_(output)
        self._session.commitConfiguration()
        self._session.startRunning()

        if not self._wait_for_first_frame():
            self.close()
            raise RuntimeError(f"攝影機「{self.device.name}」打開了卻拿不到畫面,確認沒有其他程式正在使用它。")
        logger.info("使用攝影機:%s", self.device.name)

    def _wait_for_first_frame(self) -> bool:
        deadline = time.monotonic() + FIRST_FRAME_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            frame, _ = self._delegate.latest()
            if frame is not None:
                return True
            time.sleep(0.05)
        return False

    def read(self) -> Frame | None:
        """回傳最新的一張影格。影格是持續推進來的,所以這裡不會擋住;
        太久沒有新影格才算讀取失敗,呼叫端靠這個計數分辨「鏡頭掉了」和「畫面裡沒有人」。"""
        latest: tuple[Frame | None, float] = self._delegate.latest()
        frame, captured_at = latest
        if not is_fresh(frame, captured_at, time.monotonic()):
            self.consecutive_read_failures += 1
            return None
        self.consecutive_read_failures = 0
        return frame

    def close(self) -> None:
        if self._session.isRunning():
            self._session.stopRunning()

    def __enter__(self) -> Camera:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

"""AVFoundation 擷取層的測試。

開實體鏡頭的部分靠實機驗證,這裡測的是不需要硬體的判斷:影格新鮮度、失敗計數、
以及開不起來時的錯誤訊息。
"""

import time

import numpy as np
import pytest

import webcamcheck.camera as camera_module
from webcamcheck.camera import STALE_FRAME_SECONDS, Camera, frame_from_bgra, is_fresh
from webcamcheck.devices import CameraDevice
from webcamcheck.ports import Frame

FRAME = np.zeros((4, 4, 3), dtype=np.uint8)
BRIO = CameraDevice(index=0, name="Brio 100", unique_id="0x3123000046d094c")


class _FakeDelegate:
    def __init__(self, frame: Frame | None, captured_at: float) -> None:
        self.frame = frame
        self.captured_at = captured_at

    def latest(self) -> tuple[Frame | None, float]:
        return self.frame, self.captured_at


def _camera_with(delegate: _FakeDelegate) -> Camera:
    """略過 __init__ 的硬體初始化,只測 read() 的判斷。"""
    camera = object.__new__(Camera)
    camera.consecutive_read_failures = 0
    camera._delegate = delegate
    return camera


class TestFrameFromBgra:
    def test_converts_bgra_to_bgr(self) -> None:
        # 一個像素:B=10 G=20 R=30 A=255,轉出來要是 BGR 三個 channel
        frame = frame_from_bgra(bytes([10, 20, 30, 255]), width=1, height=1, stride=4)
        assert frame.shape == (1, 1, 3)
        assert list(frame[0, 0]) == [10, 20, 30]

    def test_drops_row_padding(self) -> None:
        # stride 比 width*4 大(記憶體對齊),多出來的位元組必須裁掉,否則畫面會斜掉
        width, height, stride = 2, 2, 12  # 每列 2 像素 = 8 bytes,但 stride 是 12
        row = bytes([1, 2, 3, 255, 4, 5, 6, 255]) + bytes([99, 99, 99, 99])
        frame = frame_from_bgra(row * height, width, height, stride)
        assert frame.shape == (height, width, 3)
        assert list(frame[0, 0]) == [1, 2, 3]
        assert list(frame[0, 1]) == [4, 5, 6]
        assert 99 not in frame, "padding 不該出現在影像裡"

    def test_rows_are_not_shifted(self) -> None:
        width, height, stride = 2, 3, 12
        rows = b""
        for r in range(height):
            rows += bytes([r, r, r, 255, r, r, r, 255]) + bytes([77, 77, 77, 77])
        frame = frame_from_bgra(rows, width, height, stride)
        for r in range(height):
            assert list(frame[r, 0]) == [r, r, r], "每一列都要對齊到自己的資料"


class TestIsFresh:
    def test_no_frame_is_not_fresh(self) -> None:
        assert is_fresh(None, 0.0, 0.0) is False

    def test_just_captured_is_fresh(self) -> None:
        assert is_fresh(FRAME, 100.0, 100.0) is True

    def test_within_window_is_fresh(self) -> None:
        assert is_fresh(FRAME, 100.0, 100.0 + STALE_FRAME_SECONDS) is True

    def test_older_than_window_is_stale(self) -> None:
        # 影格是背景推進來的,太舊代表鏡頭掉了,而不是畫面裡沒有人
        assert is_fresh(FRAME, 100.0, 100.0 + STALE_FRAME_SECONDS + 0.1) is False


class TestRead:
    def test_returns_fresh_frame_and_resets_failures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(time, "monotonic", lambda: 100.0)
        camera = _camera_with(_FakeDelegate(FRAME, 100.0))
        camera.consecutive_read_failures = 3
        assert camera.read() is not None
        assert camera.consecutive_read_failures == 0

    def test_counts_failures_when_no_frame_yet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(time, "monotonic", lambda: 100.0)
        camera = _camera_with(_FakeDelegate(None, 0.0))
        assert camera.read() is None
        assert camera.read() is None
        assert camera.consecutive_read_failures == 2

    def test_counts_failures_when_frames_go_stale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 鏡頭被拔掉:delegate 還留著最後一張,但不再更新
        monkeypatch.setattr(time, "monotonic", lambda: 200.0)
        camera = _camera_with(_FakeDelegate(FRAME, 100.0))
        assert camera.read() is None
        assert camera.consecutive_read_failures == 1


class TestOpenFailures:
    def test_missing_permission_is_reported_as_permission(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(camera_module, "camera_is_authorized", lambda: False)
        with pytest.raises(RuntimeError, match="攝影機權限"):
            Camera()

    def test_missing_device_error_is_propagated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(camera_module, "camera_is_authorized", lambda: True)

        def not_found(name: str, unique_id: str | None) -> CameraDevice:
            raise RuntimeError("找不到名稱包含「Brio 100」的攝影機。目前接上的是:cnyangPhone16 Camera")

        monkeypatch.setattr(camera_module, "find_device", not_found)
        with pytest.raises(RuntimeError, match="cnyangPhone16"):
            Camera()

    def test_device_that_vanishes_between_lookup_and_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 列舉時還在,真的要開的時候已經被拔掉
        monkeypatch.setattr(camera_module, "camera_is_authorized", lambda: True)
        monkeypatch.setattr(camera_module, "find_device", lambda name, unique_id: BRIO)

        class _NoDevice:
            class AVCaptureDevice:
                @staticmethod
                def deviceWithUniqueID_(unique_id: str) -> None:
                    return None

        # pyobjc 會驗證 selector 簽章,不能直接 patch ObjC class method,改成換掉整個模組參照
        monkeypatch.setattr(camera_module, "avf", _NoDevice)
        with pytest.raises(RuntimeError, match="突然不見了"):
            Camera()

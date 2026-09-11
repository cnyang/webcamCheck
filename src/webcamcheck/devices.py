"""用名稱找攝影機,而不是靠寫死的編號。

編號會位移:iPhone 接續互通攝影機一連上就插進序列,拔掉又整個往前挪(實測 Brio 100 會在
index 0 和 index 1 之間跳)。OpenCV 的 macOS backend 是照 AVFoundation 的
`devicesWithMediaType:AVMediaTypeVideo` 順序給編號,所以這裡用同一份清單做「名稱 -> 編號」對應。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_CAMERA_NAME = "Brio 100"


AUTHORIZED = 3
PERMISSION_HINT = (
    "攝影機權限沒有開。到「系統設定 > 隱私權與安全性 > 相機」把這個程式打開;"
    "從 launchd 自動啟動時的授權和從終端機執行是分開算的,兩邊都要允許。"
)


@dataclass(frozen=True)
class CameraDevice:
    index: int
    name: str
    unique_id: str


def camera_is_authorized() -> bool | None:
    """回傳 None 代表查不出來(拿不到 AVFoundation),不要拿 None 當成沒授權。"""
    try:
        import AVFoundation as avf
    except ImportError:  # pragma: no cover - 只有非 macOS 或缺套件時會走到
        return None
    return bool(avf.AVCaptureDevice.authorizationStatusForMediaType_(avf.AVMediaTypeVideo) == AUTHORIZED)


def list_devices() -> list[CameraDevice]:
    """列出系統上的攝影機,順序即 OpenCV 的 index。拿不到 AVFoundation 時回傳空清單。"""
    try:
        import AVFoundation as avf
    except ImportError:  # pragma: no cover - 只有非 macOS 或缺套件時會走到
        logger.warning("讀不到 AVFoundation,無法用名稱找攝影機,請改用 --camera-index。")
        return []

    devices = avf.AVCaptureDevice.devicesWithMediaType_(avf.AVMediaTypeVideo)
    return [
        CameraDevice(index=index, name=str(device.localizedName()), unique_id=str(device.uniqueID()))
        for index, device in enumerate(devices)
    ]


def find_device(name: str = DEFAULT_CAMERA_NAME, unique_id: str | None = None) -> CameraDevice:
    """指定 unique_id 就精準比對,否則用名稱做不分大小寫的部分比對。
    找不到就報錯並列出現在實際接了什麼。"""
    devices = list_devices()
    if not devices:
        raise RuntimeError("偵測不到任何攝影機。確認 Brio 100 已接上。")

    if unique_id is not None:
        for device in devices:
            if device.unique_id == unique_id:
                return device
        available = "、".join(f"{d.name}({d.unique_id})" for d in devices)
        raise RuntimeError(f"找不到 uniqueID 為 {unique_id} 的攝影機。目前接上的是:{available}")

    wanted = name.casefold()
    for device in devices:
        if wanted in device.name.casefold():
            return device

    available = "、".join(d.name for d in devices)
    raise RuntimeError(f"找不到名稱包含「{name}」的攝影機。目前接上的是:{available}")

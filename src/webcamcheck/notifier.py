"""macOS 系統通知與提示音。用 osascript 和 afplay,不額外加依賴。"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

SOUND_DIR = Path("/System/Library/Sounds")
DEFAULT_SOUND = "Sosumi"


def available_sounds() -> list[str]:
    if not SOUND_DIR.is_dir():
        return []
    return sorted(path.stem for path in SOUND_DIR.glob("*.aiff"))


def sound_path(name: str) -> Path:
    return SOUND_DIR / f"{name}.aiff"


def play_sound(name: str) -> None:
    """不等它播完就返回。afplay 播一次要兩秒多,擋在監控迴圈裡會拖慢偵測。"""
    path = sound_path(name)
    if not path.exists():
        logger.warning("找不到提示音「%s」,可用的有:%s", name, "、".join(available_sounds()))
        return
    try:
        subprocess.Popen(["afplay", str(path)])
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("提示音播放失敗: %s", exc)


def _escape_applescript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def notify(title: str, message: str, sound_name: str | None = DEFAULT_SOUND) -> None:
    """跳通知,並且出聲。

    聲音不是交給通知的 `sound name`,而是自己用 afplay 播:通知的聲音會被「通知設定」
    或專注模式吃掉,常常看得到卻聽不到,而提醒坐姿本來就需要你聽得見。
    """
    if sound_name:
        play_sound(sound_name)
    script = f'display notification "{_escape_applescript(message)}" with title "{_escape_applescript(title)}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.warning("系統通知發送失敗: %s", exc)

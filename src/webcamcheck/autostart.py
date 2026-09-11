"""登入時自動啟動選單列程式(macOS LaunchAgent)。

用 LaunchAgent 而不是 LaunchDaemon:選單列圖示必須跑在使用者的圖形介面 session 裡,
daemon 沒有 GUI session,圖示不會出現。
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

LABEL = "com.cnyang.webcamcheck"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_PATH = Path.home() / "Library" / "Logs" / "webcamcheck.log"

# bootout 之後等舊 job 消失、以及 bootstrap 失敗時的重試節奏
RETRY_INTERVAL_SECONDS = 0.5
UNLOAD_CHECKS = 20
BOOTSTRAP_RETRIES = 5


def executable_path() -> Path:
    """venv 裡的 webcamcheck 指令。console script 和 python 放在同一個 bin 目錄。

    這裡刻意不呼叫 resolve():.venv/bin/python 是指向 uv 所管理直譯器的符號連結,
    一旦解析就會跑到那個共用目錄去,而 webcamcheck 這個 console script 並不在那裡。
    """
    candidate = Path(sys.executable).with_name("webcamcheck")
    if candidate.exists():
        return candidate
    found = shutil.which("webcamcheck")
    if found is None:
        raise RuntimeError("找不到 webcamcheck 執行檔,無法設定開機自動啟動。")
    return Path(found)


def build_plist(program_args: list[str], log_path: Path = LOG_PATH) -> bytes:
    """產生 LaunchAgent 的 plist 內容。

    KeepAlive 設 False:從選單「結束」關掉之後不該又被 launchd 拉起來。
    """
    payload = {
        "Label": LABEL,
        "ProgramArguments": program_args,
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Interactive",
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
    }
    return plistlib.dumps(payload)


def _launchctl(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["launchctl", *args], capture_output=True, check=False)


def _service_target() -> str:
    return f"gui/{os.getuid()}/{LABEL}"


def is_loaded() -> bool:
    return _launchctl("print", _service_target()).returncode == 0


def install(
    program_args: list[str],
    plist_path: Path = PLIST_PATH,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Path:
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(build_plist(program_args))

    # 先 bootout 再 bootstrap,重複安裝才不會因為「已載入」而失敗。
    # bootout 是非同步的:舊 job 還沒收乾淨就 bootstrap,launchd 會回
    # 「Bootstrap failed: 5: Input/output error」,所以要等它真的消失,失敗再重試幾次。
    _launchctl("bootout", _service_target())
    for _ in range(UNLOAD_CHECKS):
        if not is_loaded():
            break
        sleep_fn(RETRY_INTERVAL_SECONDS)

    domain = f"gui/{os.getuid()}"
    result = _launchctl("bootstrap", domain, str(plist_path))
    for _ in range(BOOTSTRAP_RETRIES):
        if result.returncode == 0:
            return plist_path
        sleep_fn(RETRY_INTERVAL_SECONDS)
        result = _launchctl("bootstrap", domain, str(plist_path))
    if result.returncode != 0:
        raise RuntimeError(f"launchctl bootstrap 失敗:{result.stderr.decode().strip()}")
    return plist_path


def uninstall(plist_path: Path = PLIST_PATH) -> bool:
    """回傳有沒有真的移除掉(本來就沒安裝時回傳 False)。"""
    _launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
    if not plist_path.exists():
        return False
    plist_path.unlink()
    return True


def is_installed(plist_path: Path = PLIST_PATH) -> bool:
    return plist_path.exists()

"""校準結果與判斷標準落地存檔,下次執行不用重來。

分兩個檔:校準基準(動過鏡頭就要重做)和判斷標準(選單列隨時可調),
兩者生命週期不同,混在一起會讓「重新校準」不小心把調好的標準蓋掉。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from webcamcheck.posture import Baseline

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".webcamcheck"
CONFIG_PATH = CONFIG_DIR / "config.json"
TUNING_PATH = CONFIG_DIR / "tuning.json"


@dataclass(frozen=True)
class Tuning:
    """選單列可以調的判斷標準。"""

    neck_tolerance_deg: float
    sustain_seconds: float
    facing_ratio: float


def _write_atomically(path: Path, payload: dict[str, Any]) -> None:
    """先寫到暫存檔再 rename。直接覆寫的話,寫到一半當機或磁碟滿了就會留下半截的壞檔。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    os.replace(tmp_path, path)


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text())
        return data
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.warning("設定檔讀不出來(%s):%s", exc, path)
        return None


def save_baseline(baseline: Baseline) -> None:
    _write_atomically(CONFIG_PATH, asdict(baseline))


def load_baseline() -> Baseline | None:
    """檔案壞掉或格式對不上(例如舊版存的少了欄位)時回傳 None,當成「還沒校準」處理,
    讓使用者看到「請先執行 calibrate」而不是一串 traceback。"""
    data = _read(CONFIG_PATH)
    if data is None:
        return None
    try:
        return Baseline(**data)
    except TypeError as exc:
        logger.warning("校準格式不合(%s),請重新校準:%s", exc, CONFIG_PATH)
        return None


def save_tuning(tuning: Tuning) -> None:
    _write_atomically(TUNING_PATH, asdict(tuning))


def load_tuning() -> Tuning | None:
    """沒調過或檔案壞掉就回傳 None,呼叫端沿用啟動參數的預設值。"""
    data = _read(TUNING_PATH)
    if data is None:
        return None
    try:
        return Tuning(**data)
    except TypeError as exc:
        logger.warning("判斷標準格式不合(%s),改用預設值:%s", exc, TUNING_PATH)
        return None

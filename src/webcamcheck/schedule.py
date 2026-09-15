"""監控時段判斷:只在設定的時段內監控,其餘時間視同暫停,不開鏡頭。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime


@dataclass(frozen=True)
class ScheduleWindow:
    start: dtime
    end: dtime

    def contains(self, now: dtime) -> bool:
        return self.start <= now < self.end


# 使用者指定:早上 8 點到中午 12 點、下午 1 點半到 5 點監控,其餘時間不監控。
DEFAULT_WINDOWS: tuple[ScheduleWindow, ...] = (
    ScheduleWindow(dtime(8, 0), dtime(12, 0)),
    ScheduleWindow(dtime(13, 30), dtime(17, 0)),
)


def is_within_schedule(now: dtime, windows: tuple[ScheduleWindow, ...] = DEFAULT_WINDOWS) -> bool:
    return any(window.contains(now) for window in windows)


def describe(windows: tuple[ScheduleWindow, ...] = DEFAULT_WINDOWS) -> str:
    return "、".join(f"{w.start:%H:%M}–{w.end:%H:%M}" for w in windows)

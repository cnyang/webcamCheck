"""通知節流的狀態機:純邏輯,時間用注入的 now 參數,方便測試不必真的等待。"""

from __future__ import annotations

from webcamcheck.posture import PostureStatus


class PostureMonitorState:
    """追蹤「歪多久了」與「上次通知時間」,決定這一刻該不該跳通知。

    規則:
    - GOOD 或 UNKNOWN(離開座位、轉身)→ 計時歸零,不通知。
    - BAD → 記錄第一次變壞的時間;持續壞滿 sustain_seconds 才觸發通知(避免彎腰撿東西也跳通知)。
    - 觸發通知後,同一段壞姿勢期間要等滿 cooldown_seconds 才會再通知(避免洗版)。
      計時和 cooldown 都只在「連續壞姿勢」期間有效,一旦坐正或離開座位就整組重置,
      所以你改正之後再度駝背,會是全新一段、照樣會提醒。
    """

    def __init__(self) -> None:
        self._bad_since: float | None = None
        self._last_notified_at: float | None = None

    def update(
        self,
        status: PostureStatus,
        now: float,
        sustain_seconds: float,
        cooldown_seconds: float,
    ) -> bool:
        if status is not PostureStatus.BAD:
            self._bad_since = None
            self._last_notified_at = None
            return False

        if self._bad_since is None:
            self._bad_since = now

        sustained_long_enough = (now - self._bad_since) >= sustain_seconds
        if not sustained_long_enough:
            return False

        cooldown_elapsed = self._last_notified_at is None or (now - self._last_notified_at) >= cooldown_seconds
        if not cooldown_elapsed:
            return False

        self._last_notified_at = now
        return True

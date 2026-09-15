from datetime import time as dtime

from webcamcheck.schedule import DEFAULT_WINDOWS, describe, is_within_schedule


class TestIsWithinSchedule:
    def test_before_morning_window_is_off(self) -> None:
        assert is_within_schedule(dtime(7, 59)) is False

    def test_start_of_morning_window_is_on(self) -> None:
        assert is_within_schedule(dtime(8, 0)) is True

    def test_inside_morning_window_is_on(self) -> None:
        assert is_within_schedule(dtime(10, 0)) is True

    def test_end_of_morning_window_is_off(self) -> None:
        # 中午 12 點整不算,結束時刻不含在監控範圍內
        assert is_within_schedule(dtime(12, 0)) is False

    def test_lunch_gap_is_off(self) -> None:
        assert is_within_schedule(dtime(12, 30)) is False
        assert is_within_schedule(dtime(13, 29)) is False

    def test_start_of_afternoon_window_is_on(self) -> None:
        assert is_within_schedule(dtime(13, 30)) is True

    def test_inside_afternoon_window_is_on(self) -> None:
        assert is_within_schedule(dtime(15, 0)) is True

    def test_end_of_afternoon_window_is_off(self) -> None:
        assert is_within_schedule(dtime(17, 0)) is False

    def test_after_afternoon_window_is_off(self) -> None:
        assert is_within_schedule(dtime(20, 0)) is False

    def test_default_windows_match_user_schedule(self) -> None:
        assert describe(DEFAULT_WINDOWS) == "08:00–12:00、13:30–17:00"

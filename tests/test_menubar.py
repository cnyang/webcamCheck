from webcamcheck.controller import UiState
from webcamcheck.menubar import BUSY_ICON, ERROR_ICON, PAUSED_ICON, STATUS_ICONS, detail_for, title_for
from webcamcheck.posture import PostureStatus


class TestTitleFor:
    def test_shows_status_icon_when_running(self) -> None:
        for status in PostureStatus:
            assert title_for(UiState(status=status)) == STATUS_ICONS[status]

    def test_paused_beats_status(self) -> None:
        assert title_for(UiState(paused=True, status=PostureStatus.BAD)) == PAUSED_ICON

    def test_busy_beats_paused(self) -> None:
        assert title_for(UiState(busy=True, paused=True)) == BUSY_ICON

    def test_error_beats_everything(self) -> None:
        assert title_for(UiState(error="沒有攝影機", busy=True, paused=True, status=PostureStatus.GOOD)) == ERROR_ICON

    def test_before_first_detection(self) -> None:
        assert title_for(UiState()) == BUSY_ICON


class TestDetailFor:
    def test_error_text_is_surfaced(self) -> None:
        assert detail_for(UiState(error="找不到 Brio 100")) == "找不到 Brio 100"

    def test_paused(self) -> None:
        assert detail_for(UiState(paused=True)) == "已暫停監控"

    def test_busy(self) -> None:
        assert "校準" in detail_for(UiState(busy=True))

    def test_each_status_has_text(self) -> None:
        for status in PostureStatus:
            assert detail_for(UiState(status=status))

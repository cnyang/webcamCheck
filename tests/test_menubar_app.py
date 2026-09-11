"""rumps 外殼的測試。PostureApp 不需要跑起 runloop 就能建構,所以渲染和選單動作測得到。"""

from __future__ import annotations

from typing import Any

import pytest
import rumps

from webcamcheck.controller import MenuBarController, MenuBarSettings, UiState
from webcamcheck.menubar import (
    BUSY_ICON,
    ERROR_ICON,
    PAUSE_LABEL,
    PAUSED_ICON,
    RESUME_LABEL,
    STATUS_ICONS,
    PostureApp,
    view_command,
)
from webcamcheck.posture import PostureStatus

# 測試不跑 runloop,timer 不會觸發;間隔設大只是保險
SETTINGS = MenuBarSettings(interval_seconds=9999)


class _StubController:
    """只實作 PostureApp 會用到的部分,不去碰真的鏡頭。"""

    def __init__(self, ui: UiState | None = None) -> None:
        self.settings = MenuBarSettings(interval_seconds=SETTINGS.interval_seconds)
        self.ui = ui or UiState()
        self.ticks = 0
        self.pauses = 0
        self.closed = 0
        self.calibrations = 0
        self.notice: str | None = None
        self.applied: list[tuple[str, float]] = []

    def set_neck_tolerance(self, degrees: float) -> None:
        self.settings.neck_tolerance_deg = degrees
        self.applied.append(("neck", degrees))

    def set_sustain(self, seconds: float) -> None:
        self.settings.sustain_seconds = seconds
        self.applied.append(("sustain", seconds))

    def set_facing_ratio(self, ratio: float) -> None:
        self.settings.facing_ratio = ratio
        self.applied.append(("facing", ratio))

    def set_near_ratio(self, ratio: float) -> None:
        self.settings.near_ratio = ratio
        self.applied.append(("near", ratio))

    def tick(self) -> UiState:
        self.ticks += 1
        return self.ui

    def toggle_pause(self) -> None:
        self.pauses += 1
        self.ui.paused = not self.ui.paused

    def begin_calibration(self) -> bool:
        self.calibrations += 1
        return not self.ui.busy

    def run_calibration(self) -> None:
        self.ui.busy = False

    def take_pending_notice(self) -> str | None:
        notice, self.notice = self.notice, None
        return notice

    def close_camera(self) -> None:
        self.closed += 1


@pytest.fixture
def quiet_rumps(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """通知和離開都攔下來:測試不該真的跳通知,更不該把 process 關掉。"""
    sent: list[str] = []
    monkeypatch.setattr(rumps, "notification", lambda title, subtitle, message, **kw: sent.append(message))
    monkeypatch.setattr(rumps, "quit_application", lambda *args: None)
    return sent


def _app(controller: Any) -> PostureApp:
    return PostureApp(controller)


def _menu(app: PostureApp) -> Any:
    """rumps 的 App.menu 是個 Menu 對映,mypy 看不出型別,測試裡統一從這裡拿。"""
    return app.menu


class TestRendering:
    def test_shows_status_icon(self, quiet_rumps: list[str]) -> None:
        controller = _StubController(UiState(status=PostureStatus.BAD))
        app = _app(controller)
        app._render()
        assert app.title == STATUS_ICONS[PostureStatus.BAD]
        assert app._detail_item.title == "姿勢歪了"

    def test_starts_as_busy_icon(self, quiet_rumps: list[str]) -> None:
        assert _app(_StubController()).title == BUSY_ICON

    def test_error_state_is_rendered(self, quiet_rumps: list[str]) -> None:
        app = _app(_StubController(UiState(error="沒插上 Brio 100")))
        app._render()
        assert app.title == ERROR_ICON
        assert app._detail_item.title == "沒插上 Brio 100"


class TestMenuActions:
    def test_pause_label_toggles(self, quiet_rumps: list[str]) -> None:
        controller = _StubController()
        app = _app(controller)
        assert app._pause_item.title == PAUSE_LABEL

        app._toggle_pause(app._pause_item)
        assert controller.pauses == 1
        assert app._pause_item.title == RESUME_LABEL
        assert app.title == PAUSED_ICON

        app._toggle_pause(app._pause_item)
        assert app._pause_item.title == PAUSE_LABEL

    def test_calibration_runs_in_a_background_thread(self, quiet_rumps: list[str]) -> None:
        controller = _StubController()
        started: list[Any] = []

        class _FakeThread:
            def __init__(self, target: Any, daemon: bool = False) -> None:
                self.target = target

            def start(self) -> None:
                started.append(self.target)

        app = _app(controller)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("webcamcheck.menubar.threading.Thread", _FakeThread)
            app._start_calibration(app._pause_item)

        assert controller.calibrations == 1
        assert started == [controller.run_calibration], "校準會擋住,不能跑在主執行緒上"
        assert quiet_rumps, "應該提示使用者坐正"

    def test_calibration_click_is_ignored_while_busy(self, quiet_rumps: list[str]) -> None:
        controller = _StubController(UiState(busy=True))
        app = _app(controller)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("webcamcheck.menubar.threading.Thread", lambda **kw: pytest.fail("不該再開執行緒"))
            app._start_calibration(app._pause_item)

    def test_quit_releases_the_camera(self, quiet_rumps: list[str]) -> None:
        controller = _StubController()
        app = _app(controller)
        app._quit(app._pause_item)
        assert controller.closed == 1

    def test_open_view_spawns_a_separate_process(self, quiet_rumps: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
        controller = _StubController()
        app = _app(controller)
        spawned: list[list[str]] = []
        monkeypatch.setattr("webcamcheck.menubar.subprocess.Popen", lambda args: spawned.append(args))
        app._open_view(app._pause_item)
        assert spawned and spawned[0][1:3] == ["-m", "webcamcheck"]


class TestTick:
    def test_tick_drives_the_controller_and_repaints(self, quiet_rumps: list[str]) -> None:
        controller = _StubController(UiState(status=PostureStatus.GOOD))
        app = _app(controller)
        app._tick(None)
        assert controller.ticks == 1
        assert app.title == STATUS_ICONS[PostureStatus.GOOD]

    def test_pending_notice_is_shown_once(self, quiet_rumps: list[str]) -> None:
        controller = _StubController()
        controller.notice = "校準完成"
        app = _app(controller)
        app._tick(None)
        app._tick(None)
        assert quiet_rumps == ["校準完成"]


class TestViewCommand:
    def test_uses_the_camera_name(self) -> None:
        command = view_command(MenuBarSettings(camera_name="Brio 100"))
        assert "--camera-name" in command
        assert "Brio 100" in command

    def test_passes_explicit_id_when_set(self) -> None:
        assert "--camera-id" in view_command(MenuBarSettings(camera_id="0xabc"))

    def test_omits_id_when_using_the_name(self) -> None:
        assert "--camera-id" not in view_command(MenuBarSettings(camera_id=None))

    def test_view_command_carries_distance_settings(self) -> None:
        # 即時畫面要用和監控一樣的門檻,否則看到的判定和選單列不一致
        command = view_command(MenuBarSettings(near_ratio=1.2))
        assert command[command.index("--near-ratio") + 1] == "1.2"

    def test_view_command_carries_distance_opt_out(self) -> None:
        assert "--no-check-distance" in view_command(MenuBarSettings(check_distance=False))


def test_run_builds_a_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    from webcamcheck import menubar

    built: list[MenuBarController] = []
    monkeypatch.setattr(menubar, "PostureApp", lambda controller: _Recorder(controller, built))
    menubar.run(MenuBarSettings())
    assert isinstance(built[0], MenuBarController)


class _Recorder:
    def __init__(self, controller: MenuBarController, sink: list[MenuBarController]) -> None:
        sink.append(controller)

    def run(self) -> None:
        pass


class TestPresetMenus:
    def test_all_standards_are_adjustable(self, quiet_rumps: list[str]) -> None:
        app = _app(_StubController())
        titles = list(_menu(app).keys())
        assert "靈敏度" in titles
        assert "提醒前等待" in titles
        assert "轉身判定" in titles
        assert "距離判定" in titles

    def test_current_value_is_checked(self, quiet_rumps: list[str]) -> None:
        controller = _StubController()
        controller.settings.neck_tolerance_deg = 8.0
        app = _app(controller)
        neck = _menu(app)["靈敏度"]
        assert neck["標準(8°)"].state == 1
        assert neck["嚴格(5°)"].state == 0

    def test_clicking_applies_and_moves_the_check(self, quiet_rumps: list[str]) -> None:
        controller = _StubController()
        app = _app(controller)
        neck = _menu(app)["靈敏度"]
        item = neck["寬鬆(12°)"]
        item.callback(item)

        assert controller.applied == [("neck", 12.0)]
        assert neck["寬鬆(12°)"].state == 1
        assert neck["標準(8°)"].state == 0

    def test_other_presets_apply_too(self, quiet_rumps: list[str]) -> None:
        controller = _StubController()
        app = _app(controller)
        for menu_title, label, expected in (
            ("提醒前等待", "30 秒", ("sustain", 30.0)),
            ("轉身判定", "嚴格(80%)", ("facing", 0.8)),
            ("距離判定", "寬鬆(肩寬 120%)", ("near", 1.2)),
        ):
            item = _menu(app)[menu_title][label]
            item.callback(item)
            assert expected in controller.applied

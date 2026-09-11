"""macOS 選單列外殼(rumps)。

這裡只做兩件事:把 UiState 畫成圖示和選單、把點擊轉成 controller 的方法呼叫。
判斷邏輯全在 controller.py,那邊不 import rumps,才測得起來。

所有畫面更新都只在 rumps.Timer 的 callback 裡做,因為那是主執行緒;校準這種會擋住的工作
丟到背景執行緒,只回寫狀態,由下一次 tick 反映到選單上。
"""

from __future__ import annotations

import functools
import logging
import subprocess
import sys
import threading
from collections.abc import Callable

import rumps

from webcamcheck.controller import MenuBarController, MenuBarSettings, UiState
from webcamcheck.posture import PostureStatus

logger = logging.getLogger(__name__)

STATUS_ICONS = {
    PostureStatus.GOOD: "🟢",
    PostureStatus.BAD: "🔴",
    PostureStatus.UNKNOWN: "⚪",
}
PAUSED_ICON = "⏸"
ERROR_ICON = "⚠️"
BUSY_ICON = "⏳"

STATUS_TEXTS = {
    PostureStatus.GOOD: "坐姿良好",
    PostureStatus.BAD: "姿勢歪了",
    PostureStatus.UNKNOWN: "沒偵測到人(離開座位或轉身)",
}

PAUSE_LABEL = "暫停監控"
RESUME_LABEL = "繼續監控"

# 選單列沒有 slider,所以用預設檔位。數值是實測來的:正對鏡頭肩寬約 100%、轉身約 27%。
NECK_PRESETS = [("嚴格(5°)", 5.0), ("標準(8°)", 8.0), ("寬鬆(12°)", 12.0), ("很寬鬆(16°)", 16.0)]
SUSTAIN_PRESETS = [("3 秒", 3.0), ("5 秒", 5.0), ("8 秒", 8.0), ("15 秒", 15.0), ("30 秒", 30.0)]
FACING_PRESETS = [("嚴格(80%)", 0.8), ("標準(70%)", 0.7), ("寬鬆(55%)", 0.55)]
# 實測:正常坐著肩寬在基準的 99~107%,上身前傾是 109~117%。
NEAR_PRESETS = [("嚴格(肩寬 108%)", 1.08), ("標準(肩寬 112%)", 1.12), ("寬鬆(肩寬 120%)", 1.2)]


def title_for(state: UiState) -> str:
    if state.error:
        return ERROR_ICON
    if state.busy:
        return BUSY_ICON
    if state.paused:
        return PAUSED_ICON
    if state.status is None:
        return BUSY_ICON
    return STATUS_ICONS[state.status]


def detail_for(state: UiState) -> str:
    if state.error:
        return state.error
    if state.busy:
        return "校準中,請坐正…"
    if state.paused:
        return "已暫停監控"
    if state.status is None:
        return "啟動中…"
    return STATUS_TEXTS[state.status]


def view_command(settings: MenuBarSettings) -> list[str]:
    """開即時畫面用的另一個 process。cv2 的視窗要自己的主執行緒,塞進 rumps 的 runloop 會打架。"""
    command = [sys.executable, "-m", "webcamcheck", "view", "--camera-name", settings.camera_name]
    if settings.camera_id is not None:
        command += ["--camera-id", settings.camera_id]
    command += ["--facing-ratio", str(settings.facing_ratio), "--near-ratio", str(settings.near_ratio)]
    if not settings.check_distance:
        command.append("--no-check-distance")
    return command


class PostureApp(rumps.App):  # type: ignore[misc]  # rumps 沒有型別標註,strict 模式不准繼承 Any
    def __init__(self, controller: MenuBarController) -> None:
        super().__init__("webcamcheck", title=BUSY_ICON, quit_button=None)
        self._controller = controller
        self._preset_groups: list[tuple[rumps.MenuItem, list[tuple[str, float]], Callable[[], float]]] = []

        self._detail_item = rumps.MenuItem(detail_for(controller.ui))
        self._detail_item.set_callback(None)  # 只顯示,不能點
        self._pause_item = rumps.MenuItem(PAUSE_LABEL, callback=self._toggle_pause)

        self._neck_items = self._preset_menu(
            "靈敏度", NECK_PRESETS, lambda: controller.settings.neck_tolerance_deg, controller.set_neck_tolerance
        )
        self._sustain_items = self._preset_menu(
            "提醒前等待", SUSTAIN_PRESETS, lambda: controller.settings.sustain_seconds, controller.set_sustain
        )
        self._facing_items = self._preset_menu(
            "轉身判定", FACING_PRESETS, lambda: controller.settings.facing_ratio, controller.set_facing_ratio
        )

        self._near_items = self._preset_menu(
            "距離判定", NEAR_PRESETS, lambda: controller.settings.near_ratio, controller.set_near_ratio
        )

        self.menu = [
            self._detail_item,
            None,
            self._pause_item,
            rumps.MenuItem("重新校準", callback=self._start_calibration),
            rumps.MenuItem("開啟即時畫面", callback=self._open_view),
            None,
            self._neck_items,
            self._sustain_items,
            self._facing_items,
            self._near_items,
            None,
            rumps.MenuItem("結束", callback=self._quit),
        ]
        self._mark_current_presets()
        self._timer = rumps.Timer(self._tick, controller.settings.interval_seconds)
        self._timer.start()

    def _preset_menu(
        self,
        title: str,
        presets: list[tuple[str, float]],
        current: Callable[[], float],
        apply: Callable[[float], None],
    ) -> rumps.MenuItem:
        """一個子選單,每個檔位一列,選中的打勾。"""
        parent = rumps.MenuItem(title)
        for label, value in presets:
            item = rumps.MenuItem(label)
            item.set_callback(functools.partial(self._choose_preset, value, apply))
            parent.add(item)
        self._preset_groups.append((parent, presets, current))
        return parent

    def _choose_preset(self, value: float, apply: Callable[[float], None], _item: rumps.MenuItem) -> None:
        apply(value)
        self._mark_current_presets()
        self._render()

    def _mark_current_presets(self) -> None:
        for parent, presets, current in self._preset_groups:
            active = current()
            for label, value in presets:
                parent[label].state = 1 if value == active else 0

    def _toggle_pause(self, _item: rumps.MenuItem) -> None:
        self._controller.toggle_pause()
        self._pause_item.title = RESUME_LABEL if self._controller.ui.paused else PAUSE_LABEL
        self._render()

    def _start_calibration(self, _item: rumps.MenuItem) -> None:
        if not self._controller.begin_calibration():
            return
        self._render()
        rumps.notification("webcamcheck", "開始校準", f"坐正,維持 {self._controller.settings.calibrate_seconds:.0f} 秒")
        threading.Thread(target=self._controller.run_calibration, daemon=True).start()

    def _open_view(self, _item: rumps.MenuItem) -> None:
        subprocess.Popen(view_command(self._controller.settings))

    def _quit(self, _item: rumps.MenuItem) -> None:
        self._controller.close_camera()
        rumps.quit_application()

    def _tick(self, _timer: rumps.Timer) -> None:
        notice = self._controller.take_pending_notice()
        if notice:
            rumps.notification("webcamcheck", "", notice)
        self._controller.tick()
        self._render()

    def _render(self) -> None:
        state = self._controller.ui
        self.title = title_for(state)
        self._detail_item.title = detail_for(state)


def run(settings: MenuBarSettings) -> None:
    PostureApp(MenuBarController(settings)).run()

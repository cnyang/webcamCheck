"""選單列的大腦。刻意不 import rumps:所有判斷邏輯都能在沒有 AppKit 的情況下測。

menubar.py 只負責把 UiState 畫成圖示和選單,以及把點擊轉成這裡的方法呼叫。
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from webcamcheck import config
from webcamcheck.calibration import calibrate
from webcamcheck.camera import Camera
from webcamcheck.devices import DEFAULT_CAMERA_NAME
from webcamcheck.monitor import check_once
from webcamcheck.notifier import DEFAULT_SOUND, notify
from webcamcheck.ports import CameraHandle, PoseDetector
from webcamcheck.pose_estimator import PoseEstimator
from webcamcheck.posture import Baseline, PostureStatus
from webcamcheck.state import PostureMonitorState

logger = logging.getLogger(__name__)

NOT_CALIBRATED_MESSAGE = "尚未校準,請先點「重新校準」"

# 連續讀不到影格就重開攝影機。編號會隨 iPhone 接續互通攝影機插拔而變,重開時會重新用名稱查一次。
REOPEN_AFTER_FAILED_READS = 5


@dataclass
class MenuBarSettings:
    camera_name: str = DEFAULT_CAMERA_NAME
    camera_id: str | None = None
    neck_tolerance_deg: float = 8.0
    tilt_tolerance_deg: float = 15.0
    facing_ratio: float = 0.7
    check_tilt: bool = False
    near_ratio: float = config.DEFAULT_NEAR_RATIO
    check_distance: bool = True
    interval_seconds: float = 2.0
    sustain_seconds: float = 8.0
    cooldown_seconds: float = 120.0
    calibrate_seconds: float = 5.0
    sound_name: str | None = DEFAULT_SOUND


@dataclass
class UiState:
    """畫面要顯示什麼。純資料,和 rumps 無關。"""

    paused: bool = False
    busy: bool = False
    error: str | None = None
    status: PostureStatus | None = None
    pending_notice: str | None = None


def open_camera(settings: MenuBarSettings) -> Camera:
    return Camera(name=settings.camera_name, unique_id=settings.camera_id)


class MenuBarController:
    def __init__(
        self,
        settings: MenuBarSettings,
        open_camera: Callable[[MenuBarSettings], CameraHandle] = open_camera,
        make_estimator: Callable[[], PoseDetector] = PoseEstimator,
        load_baseline: Callable[[], Baseline | None] = config.load_baseline,
        save_baseline: Callable[[Baseline], None] = config.save_baseline,
        calibrate_fn: Callable[..., Baseline] = calibrate,
        now_fn: Callable[[], float] = time.monotonic,
        notify_fn: Callable[[str, str], None] | None = None,
        load_tuning: Callable[[], config.Tuning | None] = config.load_tuning,
        save_tuning: Callable[[config.Tuning], None] = config.save_tuning,
    ) -> None:
        self.settings = settings
        self.ui = UiState()
        self._open_camera = open_camera
        self._make_estimator = make_estimator
        self._load_baseline = load_baseline
        self._save_baseline = save_baseline
        self._calibrate = calibrate_fn
        self._now = now_fn
        self._notify = notify_fn or functools.partial(notify, sound_name=settings.sound_name)
        self._save_tuning = save_tuning

        # 從選單調過的標準要贏過啟動參數,否則每次登入都會被 plist 裡的舊值蓋回去。
        tuning = load_tuning()
        if tuning is not None:
            self.settings.neck_tolerance_deg = tuning.neck_tolerance_deg
            self.settings.sustain_seconds = tuning.sustain_seconds
            self.settings.facing_ratio = tuning.facing_ratio
            self.settings.near_ratio = tuning.near_ratio

        self._monitor_state = PostureMonitorState()
        self._camera: CameraHandle | None = None
        self._estimator: PoseDetector | None = None
        self._baseline = load_baseline()
        if self._baseline is None:
            self.ui.error = NOT_CALIBRATED_MESSAGE

    # --- 選單動作 -------------------------------------------------

    def toggle_pause(self) -> None:
        self.ui.paused = not self.ui.paused
        if self.ui.paused:
            # 暫停期間累積的秒數不算數,恢復後要重新累積才會通知
            self._monitor_state = PostureMonitorState()
            self.close_camera()

    def set_neck_tolerance(self, degrees: float) -> None:
        self.settings.neck_tolerance_deg = degrees
        self._tuning_changed()

    def set_sustain(self, seconds: float) -> None:
        self.settings.sustain_seconds = seconds
        self._tuning_changed()

    def set_facing_ratio(self, ratio: float) -> None:
        self.settings.facing_ratio = ratio
        self._tuning_changed()

    def set_near_ratio(self, ratio: float) -> None:
        self.settings.near_ratio = ratio
        self._tuning_changed()

    def _tuning_changed(self) -> None:
        """標準一改就把計時歸零:否則放寬門檻的瞬間,之前累積的秒數會立刻觸發一次通知。"""
        self._monitor_state = PostureMonitorState()
        self._save_tuning(
            config.Tuning(
                neck_tolerance_deg=self.settings.neck_tolerance_deg,
                sustain_seconds=self.settings.sustain_seconds,
                facing_ratio=self.settings.facing_ratio,
                near_ratio=self.settings.near_ratio,
            )
        )

    def begin_calibration(self) -> bool:
        """標記成校準中。回傳 False 代表正在忙,這次點擊要忽略。"""
        if self.ui.busy:
            return False
        self.ui.busy = True
        self.ui.error = None
        return True

    def run_calibration(self) -> None:
        """會擋住的部分,呼叫端應該丟到背景執行緒。只回寫狀態,不碰畫面。"""
        try:
            self.close_camera()
            camera = self._open_camera(self.settings)
            estimator = self._make_estimator()
            try:
                baseline = self._calibrate(camera, estimator, duration_seconds=self.settings.calibrate_seconds)
            finally:
                estimator.close()
                camera.close()
            self._save_baseline(baseline)
            self._baseline = baseline
            self._monitor_state = PostureMonitorState()
            self.ui.error = None
            self.ui.pending_notice = f"校準完成:neck {baseline.neck_angle_deg:.1f}°,肩寬 {baseline.shoulder_width:.3f}"
        except RuntimeError as exc:
            self.ui.error = str(exc)
            self.ui.pending_notice = f"校準失敗:{exc}"
        finally:
            self.ui.busy = False

    def take_pending_notice(self) -> str | None:
        notice, self.ui.pending_notice = self.ui.pending_notice, None
        return notice

    # --- 主迴圈 ---------------------------------------------------

    def tick(self) -> UiState:
        if self.ui.busy or self.ui.paused:
            return self.ui
        if self._baseline is None:
            self.ui.error = NOT_CALIBRATED_MESSAGE
            return self.ui
        if not self._ensure_camera():
            return self.ui

        camera, estimator = self._camera, self._estimator
        if camera is None or estimator is None:
            return self.ui

        verdict = check_once(
            camera=camera,
            estimator=estimator,
            baseline=self._baseline,
            state=self._monitor_state,
            neck_tolerance_deg=self.settings.neck_tolerance_deg,
            tilt_tolerance_deg=self.settings.tilt_tolerance_deg,
            sustain_seconds=self.settings.sustain_seconds,
            cooldown_seconds=self.settings.cooldown_seconds,
            now=self._now(),
            facing_ratio=self.settings.facing_ratio,
            check_tilt=self.settings.check_tilt,
            near_ratio=self.settings.near_ratio,
            check_distance=self.settings.check_distance,
            notify_fn=self._notify,
        )
        self.ui.status = verdict.status
        self.ui.error = None
        self._reopen_if_camera_is_gone()
        return self.ui

    def _reopen_if_camera_is_gone(self) -> None:
        """只看真正讀不到影格的次數。離開座位同樣是 UNKNOWN,但影格讀得到,不該重開鏡頭。"""
        if self._camera is not None and self._camera.consecutive_read_failures >= REOPEN_AFTER_FAILED_READS:
            logger.warning("連續 %s 次讀不到影格,重新開啟攝影機。", self._camera.consecutive_read_failures)
            self.close_camera()

    def _ensure_camera(self) -> bool:
        if self._camera is not None and self._estimator is not None:
            return True
        try:
            self._camera = self._open_camera(self.settings)
            self._estimator = self._make_estimator()
            return True
        except RuntimeError as exc:
            # 開機時 Brio 100 可能還沒插上,不要放棄,下次 tick 再試一次。
            self._camera = None
            self._estimator = None
            self.ui.error = str(exc)
            return False

    def close_camera(self) -> None:
        if self._estimator is not None:
            self._estimator.close()
            self._estimator = None
        if self._camera is not None:
            self._camera.close()
            self._camera = None

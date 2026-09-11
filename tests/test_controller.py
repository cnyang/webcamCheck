import numpy as np
import pytest

from webcamcheck import config
from webcamcheck.controller import (
    NOT_CALIBRATED_MESSAGE,
    REOPEN_AFTER_FAILED_READS,
    MenuBarController,
    MenuBarSettings,
)
from webcamcheck.ports import Frame
from webcamcheck.posture import Baseline, PostureSample, PostureStatus

BASELINE = Baseline(neck_angle_deg=10.0, shoulder_tilt_deg=2.0, shoulder_width=0.50)
GOOD = PostureSample(neck_angle_deg=10.0, shoulder_tilt_deg=2.0, shoulder_width=0.50)
SLOUCH = PostureSample(neck_angle_deg=30.0, shoulder_tilt_deg=2.0, shoulder_width=0.50)
TURNED = PostureSample(neck_angle_deg=60.0, shoulder_tilt_deg=2.0, shoulder_width=0.20)
FRAME = np.zeros((1, 1, 3), dtype=np.uint8)

SETTINGS = MenuBarSettings(sustain_seconds=5.0, cooldown_seconds=60.0, calibrate_seconds=1.0)


class _FakeCamera:
    def __init__(self, frames: list[Frame | None] | None = None) -> None:
        self.consecutive_read_failures = 0
        self.closed = False
        self._frames = frames
        self.reads = 0

    def read(self) -> Frame | None:
        self.reads += 1
        if self._frames is None:
            return FRAME
        frame = self._frames.pop(0) if self._frames else None
        if frame is None:
            self.consecutive_read_failures += 1
        else:
            self.consecutive_read_failures = 0
        return frame

    def close(self) -> None:
        self.closed = True


class _FakeEstimator:
    def __init__(self, sample: PostureSample | None) -> None:
        self.sample = sample
        self.closed = False

    def detect(self, frame: Frame) -> PostureSample | None:
        return self.sample

    def close(self) -> None:
        self.closed = True


class _Harness:
    """把假的鏡頭與估計器接到 controller 上,並記錄開了幾次鏡頭。"""

    def __init__(
        self,
        sample: PostureSample | None = GOOD,
        baseline: Baseline | None = BASELINE,
        open_error: str | None = None,
        settings: MenuBarSettings = SETTINGS,
    ) -> None:
        self.cameras: list[_FakeCamera] = []
        self.estimators: list[_FakeEstimator] = []
        self.saved: list[Baseline] = []
        self.notified: list[str] = []
        self.open_error = open_error
        self.sample = sample
        self.now = 0.0

        self.saved_tuning: list[config.Tuning] = []
        self.controller = MenuBarController(
            settings,
            open_camera=self._open_camera,
            make_estimator=self._make_estimator,
            load_baseline=lambda: baseline,
            save_baseline=self.saved.append,
            calibrate_fn=self._calibrate,
            now_fn=lambda: self.now,
            notify_fn=lambda _title, message: self.notified.append(message),
            # 一定要注入,否則測試會去讀使用者真正的 ~/.webcamcheck/tuning.json
            load_tuning=lambda: None,
            save_tuning=self.saved_tuning.append,
        )

    def _open_camera(self, settings: MenuBarSettings) -> _FakeCamera:
        if self.open_error:
            raise RuntimeError(self.open_error)
        camera = _FakeCamera()
        self.cameras.append(camera)
        return camera

    def _make_estimator(self) -> _FakeEstimator:
        estimator = _FakeEstimator(self.sample)
        self.estimators.append(estimator)
        return estimator

    def _calibrate(self, camera: object, estimator: object, duration_seconds: float) -> Baseline:
        if self.open_error:
            raise RuntimeError(self.open_error)
        return BASELINE

    def tick_at(self, now: float) -> PostureStatus | None:
        self.now = now
        return self.controller.tick().status


class TestTick:
    def test_good_posture_sets_status(self) -> None:
        h = _Harness(sample=GOOD)
        assert h.tick_at(0.0) is PostureStatus.GOOD
        assert h.controller.ui.error is None

    def test_slouch_sets_bad(self) -> None:
        h = _Harness(sample=SLOUCH)
        assert h.tick_at(0.0) is PostureStatus.BAD

    def test_sustained_slouch_notifies(self) -> None:
        h = _Harness(sample=SLOUCH)
        h.tick_at(0.0)
        assert h.notified == [], "才剛歪就通知的話,彎腰撿個東西都會被吵"
        h.tick_at(6.0)
        assert h.notified == ["頭往前垂了,調整一下吧"]

    def test_turning_away_never_notifies(self) -> None:
        # 轉去用另一台電腦,再久也不該提醒
        h = _Harness(sample=TURNED)
        for t in range(0, 120, 2):
            h.tick_at(float(t))
        assert h.notified == []

    def test_leaving_the_desk_never_notifies(self) -> None:
        h = _Harness(sample=None)
        for t in range(0, 120, 2):
            h.tick_at(float(t))
        assert h.notified == []

    def test_turning_away_is_unknown(self) -> None:
        h = _Harness(sample=TURNED)
        assert h.tick_at(0.0) is PostureStatus.UNKNOWN

    def test_no_person_is_unknown(self) -> None:
        h = _Harness(sample=None)
        assert h.tick_at(0.0) is PostureStatus.UNKNOWN

    def test_camera_is_opened_once_and_reused(self) -> None:
        h = _Harness()
        for t in (0.0, 2.0, 4.0):
            h.tick_at(t)
        assert len(h.cameras) == 1


class TestNotCalibrated:
    def test_starts_in_error_when_no_baseline(self) -> None:
        h = _Harness(baseline=None)
        assert h.controller.ui.error == NOT_CALIBRATED_MESSAGE

    def test_tick_does_not_open_camera_without_baseline(self) -> None:
        h = _Harness(baseline=None)
        h.tick_at(0.0)
        assert h.cameras == [], "還沒校準就不該去開鏡頭"


class TestCameraTrouble:
    def test_open_failure_surfaces_error_and_keeps_retrying(self) -> None:
        # 開機時 Brio 100 可能還沒插上,不能放棄
        h = _Harness(open_error="找不到名稱包含「Brio 100」的攝影機")
        h.tick_at(0.0)
        assert h.controller.ui.error is not None
        h.tick_at(2.0)
        assert h.controller.ui.error is not None

    def test_recovers_once_the_camera_comes_back(self) -> None:
        h = _Harness(open_error="沒插上")
        h.tick_at(0.0)
        h.open_error = None
        assert h.tick_at(2.0) is PostureStatus.GOOD
        assert h.controller.ui.error is None

    def test_reopens_after_repeated_read_failures(self) -> None:
        h = _Harness()
        h.tick_at(0.0)
        camera = h.cameras[0]
        camera.consecutive_read_failures = REOPEN_AFTER_FAILED_READS
        h.tick_at(2.0)
        assert camera.closed is True
        h.tick_at(4.0)
        assert len(h.cameras) == 2, "下一次 tick 要重新開一台"

    def test_does_not_reopen_just_because_nobody_is_there(self) -> None:
        # 離開座位同樣是 UNKNOWN,但影格讀得到。之前的寫法會在午餐時間每 10 秒重開一次鏡頭
        h = _Harness(sample=None)
        for t in range(0, 40, 2):
            h.tick_at(float(t))
        assert len(h.cameras) == 1


class TestPause:
    def test_pause_stops_ticking_and_releases_the_camera(self) -> None:
        h = _Harness()
        h.tick_at(0.0)
        h.controller.toggle_pause()
        assert h.cameras[0].closed is True
        assert h.estimators[0].closed is True

        h.tick_at(2.0)
        assert h.cameras[0].reads == 1, "暫停後不該再讀影格"

    def test_resume_reopens_and_resumes(self) -> None:
        h = _Harness()
        h.tick_at(0.0)
        h.controller.toggle_pause()
        h.controller.toggle_pause()
        assert h.controller.ui.paused is False
        assert h.tick_at(4.0) is PostureStatus.GOOD

    def test_pause_clears_the_bad_streak(self) -> None:
        # 暫停期間累積的秒數不算數,恢復後要重新累積滿 sustain 才會通知
        h = _Harness(sample=SLOUCH)
        h.tick_at(0.0)
        h.controller.toggle_pause()
        h.controller.toggle_pause()
        h.tick_at(100.0)
        h.tick_at(103.0)
        assert h.notified == [], "恢復後才 3 秒,還沒滿 sustain 就不該通知"
        h.tick_at(106.0)
        assert h.notified == ["頭往前垂了,調整一下吧"]

    def test_paused_never_notifies(self) -> None:
        h = _Harness(sample=SLOUCH)
        h.controller.toggle_pause()
        for t in range(0, 60, 2):
            h.tick_at(float(t))
        assert h.notified == []


class TestCalibration:
    def test_begin_calibration_marks_busy(self) -> None:
        h = _Harness()
        assert h.controller.begin_calibration() is True
        assert h.controller.ui.busy is True

    def test_second_click_while_busy_is_ignored(self) -> None:
        h = _Harness()
        h.controller.begin_calibration()
        assert h.controller.begin_calibration() is False

    def test_tick_is_skipped_while_calibrating(self) -> None:
        h = _Harness()
        h.controller.begin_calibration()
        h.tick_at(0.0)
        assert h.cameras == []

    def test_successful_calibration_saves_and_clears_busy(self) -> None:
        h = _Harness(baseline=None)
        h.controller.begin_calibration()
        h.controller.run_calibration()
        assert h.saved == [BASELINE]
        assert h.controller.ui.busy is False
        assert h.controller.ui.error is None
        assert "校準完成" in (h.controller.ui.pending_notice or "")

    def test_calibration_makes_monitoring_possible(self) -> None:
        h = _Harness(baseline=None)
        h.controller.begin_calibration()
        h.controller.run_calibration()
        assert h.tick_at(0.0) is PostureStatus.GOOD

    def test_failed_calibration_surfaces_the_error(self) -> None:
        h = _Harness(open_error="找不到攝影機")
        h.controller.begin_calibration()
        h.controller.run_calibration()
        assert h.controller.ui.busy is False
        assert h.controller.ui.error == "找不到攝影機"
        assert "校準失敗" in (h.controller.ui.pending_notice or "")

    def test_calibration_releases_the_camera_it_opened(self) -> None:
        h = _Harness()
        h.controller.begin_calibration()
        h.controller.run_calibration()
        assert all(camera.closed for camera in h.cameras)
        assert all(estimator.closed for estimator in h.estimators)


class TestPendingNotice:
    def test_notice_is_consumed_once(self) -> None:
        h = _Harness(baseline=None)
        h.controller.begin_calibration()
        h.controller.run_calibration()
        assert h.controller.take_pending_notice() is not None
        assert h.controller.take_pending_notice() is None

    def test_no_notice_by_default(self) -> None:
        assert _Harness().controller.take_pending_notice() is None


class TestShutdown:
    def test_close_camera_is_safe_when_nothing_is_open(self) -> None:
        _Harness().controller.close_camera()

    def test_close_camera_releases_resources(self) -> None:
        h = _Harness()
        h.tick_at(0.0)
        h.controller.close_camera()
        assert h.cameras[0].closed is True
        assert h.estimators[0].closed is True


def test_open_camera_passes_name_and_id(monkeypatch: pytest.MonkeyPatch) -> None:
    import webcamcheck.controller as controller_module

    seen: dict[str, object] = {}
    monkeypatch.setattr(controller_module, "Camera", lambda name, unique_id: seen.update(name=name, id=unique_id))
    controller_module.open_camera(MenuBarSettings(camera_name="Brio 100", camera_id="0xabc"))
    assert seen == {"name": "Brio 100", "id": "0xabc"}


class TestTuning:
    def _harness_with_tuning(self, tuning: config.Tuning | None) -> tuple[_Harness, list[config.Tuning]]:
        saved: list[config.Tuning] = []
        h = _Harness()
        h.controller = MenuBarController(
            MenuBarSettings(sustain_seconds=5.0, cooldown_seconds=60.0),
            open_camera=h._open_camera,
            make_estimator=h._make_estimator,
            load_baseline=lambda: BASELINE,
            save_baseline=h.saved.append,
            calibrate_fn=h._calibrate,
            now_fn=lambda: h.now,
            notify_fn=lambda _t, m: h.notified.append(m),
            load_tuning=lambda: tuning,
            save_tuning=saved.append,
        )
        return h, saved

    def test_saved_tuning_wins_over_startup_flags(self) -> None:
        # 否則每次登入都會被 plist 裡的舊值蓋回去
        tuning = config.Tuning(neck_tolerance_deg=12.0, sustain_seconds=30.0, facing_ratio=0.55)
        h, _ = self._harness_with_tuning(tuning)
        assert h.controller.settings.neck_tolerance_deg == 12.0
        assert h.controller.settings.sustain_seconds == 30.0
        assert h.controller.settings.facing_ratio == 0.55

    def test_without_saved_tuning_startup_flags_apply(self) -> None:
        h, _ = self._harness_with_tuning(None)
        assert h.controller.settings.sustain_seconds == 5.0

    def test_setters_persist(self) -> None:
        h, saved = self._harness_with_tuning(None)
        h.controller.set_neck_tolerance(16.0)
        assert saved[-1].neck_tolerance_deg == 16.0
        h.controller.set_sustain(3.0)
        assert saved[-1].sustain_seconds == 3.0
        h.controller.set_facing_ratio(0.8)
        assert saved[-1].facing_ratio == 0.8

    def test_new_tolerance_takes_effect_immediately(self) -> None:
        h, _ = self._harness_with_tuning(None)
        h.sample = SLOUCH  # 比基準高 20 度
        assert h.tick_at(0.0) is PostureStatus.BAD
        h.controller.set_neck_tolerance(25.0)
        assert h.tick_at(2.0) is PostureStatus.GOOD

    def test_changing_tuning_clears_the_streak(self) -> None:
        # 放寬門檻的瞬間不該因為之前累積的秒數立刻噴一次通知
        h, _ = self._harness_with_tuning(None)
        h.sample = SLOUCH
        h.tick_at(0.0)
        h.controller.set_sustain(3.0)
        h.tick_at(4.0)
        assert h.notified == [], "標準一改就重新計時"
        h.tick_at(8.0)
        assert h.notified == ["頭往前垂了,調整一下吧"]

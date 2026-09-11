from pathlib import Path

import pytest

import webcamcheck.config as config_module
from webcamcheck.posture import Baseline

BASELINE = Baseline(neck_angle_deg=12.3, shoulder_tilt_deg=4.5, shoulder_width=0.52)


def _redirect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_path = tmp_path / "cfgdir" / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_path.parent)
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    return config_path


def test_load_baseline_returns_none_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect(tmp_path, monkeypatch)
    assert config_module.load_baseline() is None


def test_save_then_load_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect(tmp_path, monkeypatch)
    config_module.save_baseline(BASELINE)
    assert config_module.load_baseline() == BASELINE


def test_corrupt_config_is_treated_as_not_calibrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 壞檔應該回傳 None 讓使用者看到「請先校準」,而不是噴 traceback
    config_path = _redirect(tmp_path, monkeypatch)
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"neck_angle_deg": 12.3, "shoulder')
    assert config_module.load_baseline() is None


def test_config_with_missing_fields_is_treated_as_not_calibrated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 舊版存的設定檔少了 shoulder_width 欄位,也要當成未校準而不是崩潰
    config_path = _redirect(tmp_path, monkeypatch)
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"neck_angle_deg": 12.3, "shoulder_tilt_deg": 4.5}')
    assert config_module.load_baseline() is None


def test_save_leaves_no_temp_file_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = _redirect(tmp_path, monkeypatch)
    config_module.save_baseline(BASELINE)
    leftovers = [p.name for p in config_path.parent.iterdir() if p.name != config_path.name]
    assert leftovers == []


TUNING = config_module.Tuning(neck_tolerance_deg=12.0, sustain_seconds=15.0, facing_ratio=0.55)


def _redirect_tuning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tuning_path = tmp_path / "cfgdir" / "tuning.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tuning_path.parent)
    monkeypatch.setattr(config_module, "TUNING_PATH", tuning_path)
    return tuning_path


def test_tuning_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_tuning(tmp_path, monkeypatch)
    config_module.save_tuning(TUNING)
    assert config_module.load_tuning() == TUNING


def test_no_tuning_file_means_use_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_tuning(tmp_path, monkeypatch)
    assert config_module.load_tuning() is None


def test_corrupt_tuning_falls_back_to_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tuning_path = _redirect_tuning(tmp_path, monkeypatch)
    tuning_path.parent.mkdir(parents=True)
    tuning_path.write_text("{oops")
    assert config_module.load_tuning() is None


def test_tuning_with_missing_fields_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tuning_path = _redirect_tuning(tmp_path, monkeypatch)
    tuning_path.parent.mkdir(parents=True)
    tuning_path.write_text('{"neck_tolerance_deg": 8.0}')
    assert config_module.load_tuning() is None


def test_tuning_and_baseline_are_separate_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 重新校準不該把調好的判斷標準蓋掉
    config_path = _redirect(tmp_path, monkeypatch)
    tuning_path = _redirect_tuning(tmp_path, monkeypatch)
    config_module.save_tuning(TUNING)
    config_module.save_baseline(BASELINE)
    assert config_path != tuning_path
    assert config_module.load_tuning() == TUNING
    assert config_module.load_baseline() == BASELINE

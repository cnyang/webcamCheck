import subprocess
from pathlib import Path
from typing import Any

import pytest

import webcamcheck.notifier as notifier_module
from webcamcheck import notifier


@pytest.fixture
def sound_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """用真的暫存檔當音效庫,避免去 patch pathlib.Path 這種全域行為。"""
    (tmp_path / "Sosumi.aiff").write_bytes(b"fake")
    monkeypatch.setattr(notifier_module, "SOUND_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """攔下 Popen(音效)和 run(通知),測試不該真的出聲或跳通知。"""
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd: calls.append(cmd))
    monkeypatch.setattr(subprocess, "run", lambda cmd, check, capture_output: calls.append(cmd))
    return calls


class TestPlaySound:
    def test_plays_with_afplay_without_blocking(self, spawned: list[list[str]], sound_dir: Path) -> None:
        # afplay 播一次要兩秒多,一定要 Popen 不能 run,否則監控迴圈會被拖住
        notifier.play_sound("Sosumi")
        assert spawned == [["afplay", str(sound_dir / "Sosumi.aiff")]]

    def test_unknown_sound_is_skipped_not_raised(self, spawned: list[list[str]], sound_dir: Path) -> None:
        notifier.play_sound("NoSuchSound")
        assert spawned == []

    def test_popen_failure_is_swallowed(self, sound_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(cmd: list[str]) -> None:
            raise OSError("no afplay")

        monkeypatch.setattr(subprocess, "Popen", boom)
        notifier.play_sound("Sosumi")  # 不能讓監控整個掛掉


class TestNotify:
    def test_plays_sound_then_shows_notification(self, spawned: list[list[str]], sound_dir: Path) -> None:
        notifier.notify("坐姿提醒", "頭往前垂了")
        assert spawned[0][0] == "afplay", "先出聲"
        assert spawned[1][0] == "osascript"

    def test_no_sound_when_disabled(self, spawned: list[list[str]]) -> None:
        notifier.notify("坐姿提醒", "頭往前垂了", sound_name=None)
        assert [cmd[0] for cmd in spawned] == ["osascript"]

    def test_notification_does_not_request_its_own_sound(self, spawned: list[list[str]]) -> None:
        # 通知自己的 sound name 會被通知設定或專注模式吃掉,聲音統一交給 afplay,免得重複播
        notifier.notify("坐姿提醒", "頭往前垂了", sound_name=None)
        assert "sound name" not in spawned[0][2]

    def test_escapes_quotes_in_message(self, spawned: list[list[str]]) -> None:
        notifier.notify("title", 'say "hi"', sound_name=None)
        assert '\\"hi\\"' in spawned[0][2]

    def test_missing_osascript_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*args: Any, **kwargs: Any) -> None:
            raise FileNotFoundError("no osascript")

        monkeypatch.setattr(subprocess, "run", boom)
        notifier.notify("title", "message", sound_name=None)


def test_available_sounds_are_real_files() -> None:
    sounds = notifier.available_sounds()
    assert "Sosumi" in sounds
    assert all(Path(f"/System/Library/Sounds/{name}.aiff").exists() for name in sounds)


def test_default_sound_exists() -> None:
    assert notifier.sound_path(notifier.DEFAULT_SOUND).exists()

import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import webcamcheck.autostart as autostart_module
from webcamcheck.autostart import LABEL, build_plist, executable_path, is_installed, uninstall

PROGRAM = ["/opt/venv/bin/webcamcheck", "menubar", "--camera-name", "Brio 100"]


@pytest.fixture
def no_launchctl(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試絕對不能真的去動使用者的 launchd。"""

    def fail(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("測試不該執行 launchctl")

    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(
        autostart_module,
        "_launchctl",
        lambda *args: subprocess.CompletedProcess(args=list(args), returncode=0, stdout=b"", stderr=b""),
    )


def _parsed(log_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = plistlib.loads(build_plist(PROGRAM, log_path=log_path))
    return payload


def test_plist_runs_the_menubar_command_at_login(tmp_path: Path) -> None:
    payload = _parsed(tmp_path / "webcamcheck.log")
    assert payload["Label"] == LABEL
    assert payload["ProgramArguments"] == PROGRAM
    assert payload["RunAtLoad"] is True


def test_keepalive_is_off_so_quitting_from_the_menu_sticks(tmp_path: Path) -> None:
    # KeepAlive 若為 True,從選單按「結束」會馬上被 launchd 重新拉起來
    assert _parsed(tmp_path / "webcamcheck.log")["KeepAlive"] is False


def test_plist_captures_logs(tmp_path: Path) -> None:
    log_path = tmp_path / "webcamcheck.log"
    payload = _parsed(log_path)
    assert payload["StandardOutPath"] == str(log_path)
    assert payload["StandardErrorPath"] == str(log_path)


def test_plist_is_valid_plist_xml(tmp_path: Path) -> None:
    assert build_plist(PROGRAM, log_path=tmp_path / "x.log").startswith(b"<?xml")


def test_executable_path_points_at_an_existing_file() -> None:
    # 曾經用 resolve() 導致路徑跑到 uv 共用的 python 目錄,那裡沒有 webcamcheck,開機必定啟動失敗
    assert executable_path().exists()


def test_executable_path_stays_in_the_venv_bin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "webcamcheck").write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "executable", str(venv_bin / "python"))
    assert executable_path() == venv_bin / "webcamcheck"


def test_is_installed_reflects_the_file(tmp_path: Path) -> None:
    plist_path = tmp_path / "agent.plist"
    assert is_installed(plist_path) is False
    plist_path.write_bytes(build_plist(PROGRAM, log_path=tmp_path / "x.log"))
    assert is_installed(plist_path) is True


class TestInstallRace:
    """bootout 是非同步的,舊 job 還沒收乾淨就 bootstrap,launchd 會回
    Bootstrap failed: 5: Input/output error。實際踩過,所以這裡釘住重試行為。"""

    def _install_with(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        results: list[int],
        loaded_until: int = 0,
    ) -> tuple[list[list[str]], list[float]]:
        calls: list[list[str]] = []
        slept: list[float] = []
        prints = {"n": 0}

        def fake_launchctl(*args: str) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(args))
            if args[0] == "print":
                prints["n"] += 1
                code = 0 if prints["n"] <= loaded_until else 1
                return subprocess.CompletedProcess(args=list(args), returncode=code, stdout=b"", stderr=b"")
            if args[0] == "bootstrap":
                code = results.pop(0) if results else 0
                return subprocess.CompletedProcess(args=list(args), returncode=code, stdout=b"", stderr=b"boom")
            return subprocess.CompletedProcess(args=list(args), returncode=0, stdout=b"", stderr=b"")

        monkeypatch.setattr(autostart_module, "_launchctl", fake_launchctl)
        monkeypatch.setattr(autostart_module, "LOG_PATH", tmp_path / "log" / "webcamcheck.log")
        autostart_module.install(PROGRAM, tmp_path / "agent.plist", sleep_fn=slept.append)
        return calls, slept

    def test_waits_for_the_old_job_to_disappear(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        calls, slept = self._install_with(monkeypatch, tmp_path, results=[0], loaded_until=3)
        verbs = [c[0] for c in calls]
        assert verbs[0] == "bootout"
        assert verbs.count("print") == 4, "要一直檢查到舊 job 真的不見了"
        assert verbs[-1] == "bootstrap", "確認消失之後才 bootstrap"
        assert slept, "檢查之間要等一下,不能忙碌輪詢"

    def test_retries_bootstrap_when_launchd_is_not_ready(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        calls, _ = self._install_with(monkeypatch, tmp_path, results=[1, 1, 0])
        assert [c[0] for c in calls].count("bootstrap") == 3

    def test_gives_up_with_a_clear_error(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="bootstrap 失敗"):
            self._install_with(monkeypatch, tmp_path, results=[1] * 20)


def test_uninstall_reports_when_nothing_was_installed(tmp_path: Path, no_launchctl: None) -> None:
    assert uninstall(tmp_path / "missing.plist") is False


def test_uninstall_removes_the_plist(tmp_path: Path, no_launchctl: None) -> None:
    plist_path = tmp_path / "agent.plist"
    plist_path.write_bytes(build_plist(PROGRAM, log_path=tmp_path / "x.log"))
    assert uninstall(plist_path) is True
    assert not plist_path.exists()

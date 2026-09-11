import pytest

import webcamcheck.devices as devices_module
from webcamcheck.devices import CameraDevice, find_device

BRIO = CameraDevice(index=0, name="Brio 100", unique_id="0x3123000046d094c")
IPHONE = CameraDevice(index=1, name="cnyangPhone16 Camera", unique_id="0EFC59B2")


def _fake_devices(monkeypatch: pytest.MonkeyPatch, found: list[CameraDevice]) -> None:
    monkeypatch.setattr(devices_module, "list_devices", lambda: found)


class TestFindByName:
    def test_finds_brio_alongside_the_iphone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_devices(monkeypatch, [BRIO, IPHONE])
        assert find_device("Brio 100") == BRIO

    def test_finds_brio_when_it_is_the_only_camera(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_devices(monkeypatch, [BRIO])
        assert find_device("Brio 100") == BRIO

    def test_match_is_case_insensitive_and_partial(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_devices(monkeypatch, [IPHONE, BRIO])
        assert find_device("brio") == BRIO

    def test_error_lists_what_is_connected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_devices(monkeypatch, [IPHONE])
        with pytest.raises(RuntimeError, match="cnyangPhone16 Camera"):
            find_device("Brio 100")


class TestFindByUniqueId:
    def test_exact_match_wins_over_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_devices(monkeypatch, [IPHONE, BRIO])
        assert find_device(name="cnyangPhone16", unique_id=BRIO.unique_id) == BRIO

    def test_unknown_id_reports_available_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_devices(monkeypatch, [BRIO])
        with pytest.raises(RuntimeError, match=BRIO.unique_id):
            find_device(unique_id="nope")


def test_no_cameras_at_all(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_devices(monkeypatch, [])
    with pytest.raises(RuntimeError, match="偵測不到任何攝影機"):
        find_device("Brio 100")


def test_real_enumeration_returns_unique_ids() -> None:
    # 實機:至少要能列出裝置且每台都有 uniqueID(擷取層就是靠它指定裝置)
    for device in devices_module.list_devices():
        assert device.unique_id
        assert device.name

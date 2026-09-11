from dataclasses import dataclass

import mediapipe as mp
import numpy as np
import pytest

from webcamcheck.ports import Frame
from webcamcheck.pose_estimator import PoseEstimator


@dataclass
class _FakeLandmark:
    x: float
    y: float
    visibility: float


@dataclass
class _FakeLandmarkList:
    landmark: list[_FakeLandmark]


@dataclass
class _FakeResult:
    pose_landmarks: _FakeLandmarkList | None


class _FakePose:
    def __init__(self, result: _FakeResult, calls: list[Frame]) -> None:
        self._result = result
        self._calls = calls
        self.closed = False

    def process(self, rgb_frame: Frame) -> _FakeResult:
        self._calls.append(rgb_frame)
        return self._result

    def close(self) -> None:
        self.closed = True


def _install_fake_pose(monkeypatch: pytest.MonkeyPatch, result: _FakeResult, calls: list[Frame]) -> _FakePose:
    fake_pose = _FakePose(result, calls)
    monkeypatch.setattr(mp.solutions.pose, "Pose", lambda **kwargs: fake_pose)
    return fake_pose


def _all_landmarks(overrides: dict[int, _FakeLandmark]) -> list[_FakeLandmark]:
    base = [_FakeLandmark(x=0.5, y=0.5, visibility=0.9) for _ in range(33)]
    for index, landmark in overrides.items():
        base[index] = landmark
    return base


def test_detect_returns_none_when_no_pose_found(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Frame] = []
    _install_fake_pose(monkeypatch, _FakeResult(pose_landmarks=None), calls)

    estimator = PoseEstimator()
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    assert estimator.detect(frame) is None
    assert len(calls) == 1


def _shoulders_and_ears() -> list[_FakeLandmark]:
    return _all_landmarks(
        {
            11: _FakeLandmark(x=0.4, y=0.6, visibility=0.9),  # left shoulder
            12: _FakeLandmark(x=0.6, y=0.6, visibility=0.9),  # right shoulder
            7: _FakeLandmark(x=0.5, y=0.3, visibility=0.9),  # left ear
            8: _FakeLandmark(x=0.5, y=0.3, visibility=0.9),  # right ear
        }
    )


def test_detect_converts_landmarks_to_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Frame] = []
    _install_fake_pose(
        monkeypatch, _FakeResult(pose_landmarks=_FakeLandmarkList(landmark=_shoulders_and_ears())), calls
    )

    estimator = PoseEstimator()
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    sample = estimator.detect(frame)

    assert sample is not None
    assert sample.neck_angle_deg == 0.0


def test_detect_passes_frame_aspect_ratio_through(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1920x1080 的畫面,水平距離要乘上 16/9 才是真實比例
    calls: list[Frame] = []
    _install_fake_pose(
        monkeypatch, _FakeResult(pose_landmarks=_FakeLandmarkList(landmark=_shoulders_and_ears())), calls
    )

    estimator = PoseEstimator()
    widescreen = estimator.detect(np.zeros((1080, 1920, 3), dtype=np.uint8))
    square = estimator.detect(np.zeros((100, 100, 3), dtype=np.uint8))

    assert widescreen is not None and square is not None
    assert widescreen.shoulder_width == pytest.approx(square.shoulder_width * 16 / 9)


def test_close_delegates_to_underlying_pose(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Frame] = []
    fake_pose = _install_fake_pose(monkeypatch, _FakeResult(pose_landmarks=None), calls)

    estimator = PoseEstimator()
    estimator.close()

    assert fake_pose.closed is True

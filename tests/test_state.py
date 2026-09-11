from webcamcheck.posture import PostureStatus
from webcamcheck.state import PostureMonitorState

SUSTAIN = 5.0
COOLDOWN = 60.0

GOOD = PostureStatus.GOOD
BAD = PostureStatus.BAD
UNKNOWN = PostureStatus.UNKNOWN


def _update(state: PostureMonitorState, status: PostureStatus, now: float) -> bool:
    return state.update(status=status, now=now, sustain_seconds=SUSTAIN, cooldown_seconds=COOLDOWN)


class TestPostureMonitorState:
    def test_good_posture_never_notifies(self) -> None:
        state = PostureMonitorState()
        for t in range(0, 100, 10):
            assert _update(state, GOOD, float(t)) is False

    def test_bad_posture_under_sustain_window_does_not_notify(self) -> None:
        state = PostureMonitorState()
        assert _update(state, BAD, 0.0) is False
        assert _update(state, BAD, 4.9) is False

    def test_bad_posture_past_sustain_window_notifies_once(self) -> None:
        state = PostureMonitorState()
        _update(state, BAD, 0.0)
        assert _update(state, BAD, 5.1) is True
        assert _update(state, BAD, 6.0) is False  # 同一段壞姿勢,cooldown 內不重複

    def test_notifies_again_after_cooldown_while_still_bad(self) -> None:
        state = PostureMonitorState()
        _update(state, BAD, 0.0)
        assert _update(state, BAD, 5.1) is True
        assert _update(state, BAD, 65.2) is True

    def test_good_posture_resets_the_bad_streak(self) -> None:
        state = PostureMonitorState()
        _update(state, BAD, 0.0)
        _update(state, BAD, 4.0)
        assert _update(state, GOOD, 4.5) is False
        _update(state, BAD, 4.6)
        assert _update(state, BAD, 9.0) is False
        assert _update(state, BAD, 9.7) is True

    def test_cooldown_does_not_leak_into_a_new_episode(self) -> None:
        # 被通知後你坐正了(episode 結束),之後再度駝背應該是全新一段,照樣要提醒
        state = PostureMonitorState()
        _update(state, BAD, 0.0)
        assert _update(state, BAD, 6.0) is True
        assert _update(state, GOOD, 10.0) is False
        _update(state, BAD, 20.0)
        assert _update(state, BAD, 30.0) is True

    def test_unknown_pauses_and_resets_the_streak(self) -> None:
        # 離開座位/轉身期間不判斷,而且回來後要重新累積 sustain,不能沿用離開前的計時
        state = PostureMonitorState()
        _update(state, BAD, 0.0)
        assert _update(state, UNKNOWN, 60.0) is False
        assert _update(state, UNKNOWN, 600.0) is False
        assert _update(state, BAD, 602.0) is False
        assert _update(state, BAD, 604.0) is False
        assert _update(state, BAD, 607.5) is True

    def test_unknown_also_clears_cooldown(self) -> None:
        state = PostureMonitorState()
        _update(state, BAD, 0.0)
        assert _update(state, BAD, 6.0) is True
        assert _update(state, UNKNOWN, 10.0) is False
        _update(state, BAD, 20.0)
        assert _update(state, BAD, 26.0) is True

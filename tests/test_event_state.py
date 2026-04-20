import time
from event_state import EventState


class TestEventState:
    def test_initial_state_is_absent(self):
        state = EventState(consecutive_hits_required=2)
        assert state.consecutive_hits == 0
        assert state.is_confirmed_present is False

    def test_update_above_threshold_increments_hits_without_firing(self):
        state = EventState(consecutive_hits_required=2)
        fired = state.update(above_threshold=True)
        assert state.consecutive_hits == 1
        assert state.is_confirmed_present is False
        assert fired is False

    def test_update_below_threshold_resets_hits_and_presence(self):
        state = EventState(consecutive_hits_required=2)
        state.consecutive_hits = 3
        state.is_confirmed_present = True
        state.update(above_threshold=False)
        assert state.consecutive_hits == 0
        assert state.is_confirmed_present is False

    def test_rising_edge_fires_when_hits_reach_required(self):
        state = EventState(consecutive_hits_required=2)
        state.update(above_threshold=True)           # hit 1 — not yet
        fired = state.update(above_threshold=True)   # hit 2 — fires
        assert fired is True
        assert state.is_confirmed_present is True

    def test_rising_edge_does_not_fire_again_while_icon_stays_present(self):
        state = EventState(consecutive_hits_required=2)
        state.update(above_threshold=True)
        state.update(above_threshold=True)           # fires once
        fired_again = state.update(above_threshold=True)
        assert fired_again is False

    def test_rising_edge_fires_again_after_icon_disappears_and_returns(self):
        state = EventState(consecutive_hits_required=2, cooldown_seconds=0)
        # First detection
        state.update(above_threshold=True)
        state.update(above_threshold=True)           # fires
        # Icon disappears
        state.update(above_threshold=False)
        assert state.is_confirmed_present is False
        assert state.consecutive_hits == 0
        # Icon returns
        state.update(above_threshold=True)
        fired = state.update(above_threshold=True)   # fires again
        assert fired is True

    def test_rising_edge_blocked_by_active_cooldown(self):
        state = EventState(consecutive_hits_required=2, cooldown_seconds=60)
        state.last_alert_time = time.monotonic()     # just alerted
        state.update(above_threshold=True)
        fired = state.update(above_threshold=True)
        assert fired is False

    def test_rising_edge_fires_after_cooldown_expires(self):
        state = EventState(consecutive_hits_required=2, cooldown_seconds=60)
        state.last_alert_time = time.monotonic() - 61   # cooldown elapsed
        state.update(above_threshold=True)
        fired = state.update(above_threshold=True)
        assert fired is True

    def test_single_hit_required_fires_immediately(self):
        state = EventState(consecutive_hits_required=1)
        fired = state.update(above_threshold=True)
        assert fired is True
        assert state.is_confirmed_present is True

    def test_consecutive_error_increment_and_clear(self):
        state = EventState()
        state.increment_error()
        state.increment_error()
        assert state.consecutive_errors == 2
        state.clear_errors()
        assert state.consecutive_errors == 0

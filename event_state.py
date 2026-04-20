import time


class EventState:
    """
    Per-event rising-edge state machine.

    Configuration (consecutive_hits_required, cooldown_seconds) is set at
    construction time from the event's config, then update() is called with
    just the current frame's detection result.

    Alert fires only on the transition from absent → present. A persistent icon
    will not re-alert after the first detection; the icon must disappear (any
    frame below threshold) and then reappear before a new alert can fire.

    Cooldown is a secondary anti-spam guard that suppresses re-alerting even
    after an icon disappears and reappears, until the cooldown elapses.

    Uses time.monotonic() so system clock changes do not affect timing.
    """

    def __init__(self, consecutive_hits_required: int = 2, cooldown_seconds: int = 60):
        self._required = consecutive_hits_required
        self._cooldown = cooldown_seconds
        self.consecutive_hits: int = 0
        self.is_confirmed_present: bool = False
        self.last_alert_time: float = 0.0
        self.consecutive_errors: int = 0

    def update(self, above_threshold: bool) -> bool:
        """
        Advance state for one poll. Returns True if an alert should fire.
        """
        if not above_threshold:
            self.consecutive_hits = 0
            self.is_confirmed_present = False
            return False

        self.consecutive_hits += 1

        if self.consecutive_hits < self._required:
            return False

        if self.is_confirmed_present:
            return False

        self.is_confirmed_present = True

        elapsed = time.monotonic() - self.last_alert_time
        if elapsed < self._cooldown:
            return False

        self.last_alert_time = time.monotonic()
        return True

    def increment_error(self) -> None:
        self.consecutive_errors += 1

    def clear_errors(self) -> None:
        self.consecutive_errors = 0

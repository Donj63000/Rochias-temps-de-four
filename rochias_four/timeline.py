"""Timeline helper to model alimentation ramp events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from .config import RAMP_DURATION_MIN


@dataclass
class FeedTimeline:
    """Piecewise-linear alimentation profile with ON/OFF ramping."""

    ramp_minutes: float = RAMP_DURATION_MIN
    alpha0: float = 0.0
    initial_time: float = 0.0
    events: List[Tuple[float, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.reset(self.initial_time, self.alpha0, 0)

    def reset(self, t_min: float = 0.0, alpha0: float = 0.0, target: int = 0) -> None:
        """Reset the timeline with a starting alpha and target."""
        self.alpha0 = self._clamp(alpha0)
        self.initial_time = float(t_min)
        self.events = [(self.initial_time, 1 if target else 0)]

    def set_target(self, target: int, t_min: float) -> None:
        """Append a new alimentation target (0 or 1) at time ``t_min``."""
        target = 1 if target else 0
        t = float(t_min)
        if self.events and t < self.events[-1][0]:
            # Ignore out-of-order events.
            return
        if not self.events:
            self.reset(t, self.alpha0, target)
            return
        if self.events[-1][1] != target:
            self.events.append((t, target))

    def alpha_at(self, t_min: float) -> float:
        """Return alpha(t) using the recorded ON/OFF ramps."""
        if not self.events:
            return self.alpha0
        t = float(t_min)
        first_time, first_target = self.events[0]
        if t <= first_time:
            return self.alpha0
        alpha = self.alpha0
        last_t = first_time
        last_target = first_target
        for ev_time, ev_target in self.events[1:]:
            if ev_time > t:
                break
            alpha = self._advance(alpha, last_target, ev_time - last_t)
            last_t = ev_time
            last_target = ev_target
        alpha = self._advance(alpha, last_target, t - last_t)
        return self._clamp(alpha)

    def _advance(self, alpha: float, target: int, delta_min: float) -> float:
        if delta_min <= 0.0:
            return alpha
        ramp = max(1e-6, float(self.ramp_minutes))
        if target:
            alpha += delta_min / ramp
        else:
            alpha -= delta_min / ramp
        return alpha

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))


__all__ = ["FeedTimeline"]

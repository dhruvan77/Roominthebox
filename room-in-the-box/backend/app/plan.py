"""Turn planning: how long the discussion runs and which phase each turn is in.

One turn = one AI message in the discussion (the Master's opening is not counted).

MANUAL (user picked N turns)      turns 1..N-2  free discussion (explore -> narrow -> converge)
                                  turn  N-1     WRAP-UP: any role starts the conclusion
                                  turn  N       the CONCLUDER closes the discussion
AUTO                              the Manager decides when the group is ready (after `min_turns` turns); that
                                  turn becomes the wrap-up and the next one is the Concluder. `cap` is a hard
                                  limit on total turns (wrap-up = cap-1, Concluder = cap at the latest).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurnPlan:
    mode: str            # "auto" | "manual"
    total: int | None    # manual: total turns including the Concluder
    min_turns: int       # auto: turns required before the Manager may wrap up
    cap: int             # auto: hard cap on total turns including the Concluder

    @classmethod
    def build(cls, mode: str, turns: int | None, min_queries: int, max_queries: int) -> "TurnPlan":
        if mode == "manual" and turns:
            return cls("manual", int(turns), min_queries, max_queries)
        return cls("auto", None, min_queries, max_queries)

    @property
    def wrapup_turn(self) -> int:
        """Turn that is the wrap-up (auto: the latest it can be; the Manager may call it earlier)."""
        return (self.total if self.mode == "manual" else self.cap) - 1

    @property
    def concluder_turn(self) -> int:
        return self.total if self.mode == "manual" else self.cap

    def phase(self, turn: int) -> str:
        if turn >= self.wrapup_turn:
            return "wrapup"
        if self.mode == "manual":
            ratio = (turn - 1) / max(1, self.total - 2)
            return "explore" if ratio < 0.34 else "narrow" if ratio < 0.67 else "converge"
        half = max(2, self.min_turns // 2)
        return "explore" if turn <= half else "narrow" if turn <= self.min_turns else "converge"

    def can_wrap_up(self, turns_done: int) -> bool:
        """AUTO only: may the Manager call the wrap-up now?"""
        return self.mode == "auto" and turns_done >= self.min_turns

    def label(self, turn: int) -> str:
        return f"Turn {turn} of {self.total}" if self.mode == "manual" else f"Turn {turn}"

    def schedule(self) -> str:
        """One paragraph telling the agents how the length works, so everyone paces themselves."""
        if self.mode == "manual":
            n = self.total
            parts = []
            if n > 2:
                parts.append(f"turns 1-{n - 2} are open discussion")
            parts.append(f"turn {n - 1} is the wrap-up (one role starts the conclusion)")
            parts.append(f"turn {n} is the Concluder, who closes with the final decision")
            return f"The user fixed this discussion at {n} turns: " + "; ".join(parts) + "."
        return (f"The length is AUTOMATIC: after at least {self.min_turns} turns the Manager calls the wrap-up as soon "
                f"as the group is ready; the Concluder then closes. Hard limit: {self.cap} turns in total.")

    def remaining(self, turn: int) -> str:
        if self.mode == "manual":
            left = self.total - turn
            return f"{left} turn(s) remain after this one, including the Concluder."
        return f"At most {max(0, self.cap - turn)} turn(s) remain after this one."

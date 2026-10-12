"""Shared conversation memory: the running transcript, visible to every agent.
Kept in memory while a discussion runs; the final text is saved to Supabase (sessions.conversation)."""
from __future__ import annotations


def _fmt(speaker: str, text: str) -> str:
    return f"{speaker}:\n{text}\n\n"


class Transcript:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str]] = []

    def append(self, speaker: str, text: str) -> None:
        self.entries.append((speaker, text.strip()))

    def full_text(self) -> str:
        return "".join(_fmt(s, t) for s, t in self.entries)

    def render(self, max_chars: int) -> str:
        """History handed to agents. If too long, keep the opening (user task + master) and the most
        recent messages, and drop the oldest middle part."""
        blocks = [_fmt(s, t) for s, t in self.entries]
        if sum(len(b) for b in blocks) <= max_chars:
            return "".join(blocks)

        head_limit = max_chars // 6
        head = [b if len(b) <= head_limit else b[:head_limit] + "\n[…truncated]\n\n" for b in blocks[:2]]
        remaining = max_chars - sum(len(b) for b in head) - 60
        tail: list[str] = []
        for b in reversed(blocks[2:]):
            if len(b) > remaining:
                break
            tail.append(b)
            remaining -= len(b)
        tail.reverse()
        return "".join(head) + "[… earlier discussion omitted for length …]\n\n" + "".join(tail)

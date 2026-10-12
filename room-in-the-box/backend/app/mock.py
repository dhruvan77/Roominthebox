"""Offline scripted 'model' so the whole pipeline can be tested without API keys (PROVIDER=mock)."""
from __future__ import annotations

import json
import re


def complete(purpose: str, system: str, user: str) -> str:
    if purpose == "master_initial":
        return ("I read this as: the user wants a strong, buildable answer.\n\n"
                "1. Idea A — safe and buildable\n2. Idea B — ambitious, high impact\n3. Idea C — niche but novel")
    if purpose == "master_final":
        return "FINAL (mock): A scoped-down version of Idea B, keeping the safe core of Idea A."
    if purpose == "manager":
        steps = int(re.search(r"STEPS_DONE:\s*(\d+)", user).group(1))
        ids = [i.strip() for i in re.search(r"AVAILABLE_ROLE_IDS:\s*(.+)", user).group(1).split(",")]
        # Tries to conclude too early at step 2 (backend must reject), then really concludes at 12.
        if "TOO EARLY" not in user and (steps == 2 or steps >= 12):
            return '["conclude"]'
        n = len(ids)
        pick = [ids[steps % n], ids[(steps + 1) % n]] if steps % 2 == 0 else [ids[steps % n]]
        return json.dumps([f"Mock step {steps + 1}: respond to the latest disagreement and propose a fix.", pick])
    name = re.search(r"You are (.+?) in a live", system)
    return f"[{name.group(1) if name else 'Agent'}] I partly agree with the last point, but the scope is still too big."

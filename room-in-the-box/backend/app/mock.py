"""Offline scripted 'model' so the whole pipeline can be tested without API keys (USE_MOCK=1)."""
from __future__ import annotations

import json
import re


def complete(purpose: str, system: str, user: str) -> str:
    if purpose == "master_initial":
        return ("I read this as: the user wants a strong, buildable answer.\n\n"
                "1. **Idea A** — safe and buildable\n2. **Idea B** — ambitious, high impact\n3. **Idea C** — niche but novel")
    if purpose == "concluder":
        return ("**Decision:** Build a scoped-down Idea B on top of the safe core of Idea A.\n\n"
                "**Why it won:**\n- Student showed it is buildable in time\n- Judge confirmed it can stand out\n\n"
                "**Trade-offs & dissent:** Scope was cut; Technical Expert's scaling worry is deferred.\n\n"
                "**Next steps:**\n- Prototype the core\n- Demo it")
    if purpose == "master_final":
        return "FINAL (mock): A scoped-down version of Idea B, keeping the safe core of Idea A.\n\n**Next:** prototype it."
    if purpose == "manager":
        steps = int(re.search(r"STEPS_DONE:\s*(\d+)", user).group(1))
        mode = re.search(r"TURN_MODE:\s*(\w+)", user).group(1)
        allowed = "CONCLUDE_ALLOWED: yes" in user
        ids = [i.strip() for i in re.search(r"AVAILABLE_ROLE_IDS:\s*(.+)", user).group(1).split(",")]
        if "REJECTED" not in user:
            # Tries to conclude too early (the backend must reject), and in auto mode concludes for real later.
            if (mode == "manual" and steps == 1) or (mode == "auto" and (steps == 2 or (allowed and steps >= 7))):
                return '["conclude"]'
        pick = ids[steps % len(ids)]
        return json.dumps([f"Mock turn {steps + 1}: respond to the latest point and propose a fix.", [pick]])
    name = re.search(r"You are (.+?) in a live", system)
    phase = (re.search(r"PHASE:\s*(\w+)", user) or [None, "explore"])[1]
    who = name.group(1) if name else "Agent"
    if phase == "wrapup":
        return f"[{who}] My proposed decision: go with the scoped-down Idea B. Main risk is scope; cut features to mitigate."
    if len(user) % 2:
        return f"[{who}] Agreed."
    return f"[{who}] I partly agree with the last point, but the scope is still too big. Cut it to one core feature."

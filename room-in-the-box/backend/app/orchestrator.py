"""The core discussion loop: Master -> (Manager -> role agents)* -> conclude -> final result."""
from __future__ import annotations

import asyncio
import logging

from . import agents
from .config import MAX_HISTORY_CHARS, MAX_QUERIES, MIN_QUERIES
from .llm import LLMError
from .roles import Role
from .routing import RoutingError, fallback_decision
from .sessions import Session

log = logging.getLogger("orchestrator")


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


async def run_discussion(session: Session) -> None:
    try:
        await _run(session)
    except asyncio.CancelledError:
        await session.emit("status", text="Discussion stopped.")
        await session.finish("cancelled")
        raise
    except (LLMError, RoutingError) as e:
        log.error("session %s failed: %s", session.id, e)
        await session.emit("error", message=str(e))
        await session.finish("error")
    except Exception:
        log.exception("session %s crashed", session.id)
        await session.emit("error", message="Internal error while running the discussion.")
        await session.finish("error")


async def _run(s: Session) -> None:
    tr = s.transcript
    role_slots = {r.id: f"ROLE{i + 1}" for i, r in enumerate(s.roles)}  # role -> its own API key slot
    by_id: dict[str, Role] = {r.id: r for r in s.roles}
    speak_counts = {r.id: 0 for r in s.roles}

    await s.emit("session", id=s.id, task=s.task, roles=[r.to_dict() for r in s.roles],
                 min_queries=MIN_QUERIES, max_queries=MAX_QUERIES)
    tr.append("USER", s.task)

    # 1. Master AI understands the request and seeds the discussion.
    await s.emit("status", text="Master AI is analysing your request…")
    first = await agents.master_initial("MASTER", s.task)
    tr.append("MASTER", first)
    await s.emit("message", speaker="MASTER AI", kind="master", text=first)

    # 2. Manager-driven loop.
    steps, rejections, note, failures = 0, 0, None, 0
    while steps < MAX_QUERIES:
        await s.emit("status", text="Manager is deciding what to discuss next…")
        history = tr.render(MAX_HISTORY_CHARS)
        try:
            decision = await agents.manager_decide("MANAGER", s.task, s.roles, history, steps, speak_counts, note)
        except RoutingError as e:
            log.warning("manager output unusable (%s); using fallback routing", e)
            decision = fallback_decision(s.roles, speak_counts, steps)
        note = None

        if decision.conclude:
            if steps >= MIN_QUERIES:
                break
            rejections += 1
            if rejections < 3:
                note = (f"TOO EARLY: you tried to conclude after only {steps} of the minimum {MIN_QUERIES} steps. "
                        "Find another unresolved weakness, disagreement or improvement and route it.")
                continue
            decision = fallback_decision(s.roles, speak_counts, steps)

        steps += 1
        rejections = 0
        names = _join([by_id[i].name for i in decision.roles])
        tr.append("MANAGER", f"Ask {names}: {decision.query}")
        await s.emit("message", speaker="MANAGER", kind="manager", text=f"→ Asking {names}",
                     query=decision.query, targets=decision.roles, step=steps)

        # Roles answer one after another, so the second speaker can react to the first.
        for rid in decision.roles:
            role = by_id[rid]
            await s.emit("typing", role_id=rid, speaker=role.name.upper())
            try:
                reply = await agents.role_speak(role_slots[rid], role, s.task,
                                                tr.render(MAX_HISTORY_CHARS), decision.query)
            except LLMError as e:
                failures += 1
                msg = f"{role.name} could not respond ({e})"
                tr.append("SYSTEM", msg)
                await s.emit("message", speaker="SYSTEM", kind="system", text=msg, role_id=rid)
                if failures >= 3:
                    raise LLMError("Too many consecutive agent failures; stopping the discussion.")
                continue
            failures = 0
            speak_counts[rid] += 1
            tr.append(role.name.upper(), reply)
            await s.emit("message", speaker=role.name.upper(), kind="role", role_id=rid, text=reply, step=steps)

    if steps >= MAX_QUERIES:
        await s.emit("status", text=f"Reached the safety limit of {MAX_QUERIES} steps; wrapping up.")

    # 3. Conclude: stop the loop, keep the transcript, produce the final result.
    await s.emit("status", text="Discussion concluded. Master AI is writing the final answer…")
    final = await agents.master_final("MASTER", s.task, tr.render(MAX_HISTORY_CHARS * 2))
    tr.append("FINAL ANSWER", final)
    s.final = final
    await s.emit("final", text=final, steps=steps)
    await s.finish("completed")

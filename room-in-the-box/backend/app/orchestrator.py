"""The discussion loop:  Master opens -> [Manager picks ONE speaker -> that role replies]* -> wrap-up -> Concluder
-> Master writes the final answer.  One turn = one AI message, so the turn count the user picks is exact."""
from __future__ import annotations

import asyncio
import logging

from . import agents
from .config import MAX_HISTORY_CHARS, MAX_QUERIES, MIN_QUERIES, role_slot
from .llm import LLMError
from .plan import TurnPlan
from .roles import Role
from .routing import RoutingError, fallback_decision, pick_speaker, WRAPUP_QUERY
from .sessions import Session

log = logging.getLogger("orchestrator")


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
    plan = TurnPlan.build(s.turn_mode, s.turns, MIN_QUERIES, MAX_QUERIES)
    slots = {r.id: role_slot(i) for i, r in enumerate(s.roles)}  # role -> API key slot
    by_id: dict[str, Role] = {r.id: r for r in s.roles}
    speak_counts = {r.id: 0 for r in s.roles}
    last_spoke = {r.id: 0 for r in s.roles}  # turn number of each role's latest message

    await s.emit("session", id=s.id, task=s.task, roles=[r.to_dict() for r in s.roles],
                 turn_mode=plan.mode, turns=plan.total, min_queries=MIN_QUERIES, max_queries=MAX_QUERIES)
    tr.append("USER", s.task)

    # 1. Master AI understands the request and seeds the discussion (not counted as a turn).
    await s.emit("status", text="Master AI is analysing your request…")
    first = await agents.master_initial("MASTER", s.task)
    tr.append("MASTER", first)
    await s.emit("message", speaker="MASTER AI", kind="master", text=first)

    # 2. Turn loop: each pass is exactly one AI message.
    steps, rejections, failures, note, last_speaker = 0, 0, 0, None, None
    while True:
        turn = steps + 1
        phase = plan.phase(turn)
        await s.emit("status", text=f"{plan.label(turn)} · Manager is choosing the next speaker…")
        try:
            decision = await agents.manager_decide("MANAGER", s.task, s.roles, tr.render(MAX_HISTORY_CHARS), plan,
                                                   turn, phase, speak_counts, last_speaker, note)
        except RoutingError as e:
            log.warning("manager output unusable (%s); using fallback routing", e)
            decision = fallback_decision(s.roles, last_spoke, steps, last_speaker, wrapup=phase == "wrapup")
        note = None

        if decision.conclude:
            if phase != "wrapup" and plan.can_wrap_up(steps):
                phase = "wrapup"  # AUTO: the Manager says the group is ready -> this turn is the wrap-up
                if not decision.roles:
                    decision.roles = [pick_speaker(s.roles, last_spoke, last_speaker)]
                decision.query = WRAPUP_QUERY
            elif phase == "wrapup":  # the schedule already makes this the wrap-up turn
                if not decision.roles:
                    decision.roles = [pick_speaker(s.roles, last_spoke, last_speaker)]
                decision.query = WRAPUP_QUERY
            else:
                rejections += 1
                why = ("the length is fixed by the user and the system ends the discussion on schedule"
                       if plan.mode == "manual" else
                       f"only {steps} of the {plan.min_turns} minimum turns have happened")
                if rejections < 3:
                    note = (f"REJECTED: you may not conclude now ({why}). Route the single most useful next speaker "
                            "instead; pick an unresolved weakness, disagreement or open question.")
                    continue
                decision = fallback_decision(s.roles, last_spoke, steps, last_speaker)
                phase = plan.phase(turn)
        rejections = 0

        rid = decision.roles[0]  # exactly one speaker per turn
        role = by_id[rid]
        steps = turn
        tr.append("MANAGER", f"Ask {role.name}: {decision.query}")
        await s.emit("message", speaker="MANAGER", kind="manager",
                     text=f"→ {'Opening the wrap-up with' if phase == 'wrapup' else 'Asking'} {role.name}",
                     query=decision.query, targets=[rid], step=turn, phase=phase)

        await s.emit("typing", role_id=rid, speaker=role.name.upper())
        try:
            reply = await agents.role_speak(slots[rid], role, s.task, tr.render(MAX_HISTORY_CHARS), decision.query,
                                            phase, plan.label(turn), plan.remaining(turn))
        except LLMError as e:
            failures += 1
            msg = f"{role.name} could not respond ({e})"
            tr.append("SYSTEM", msg)
            await s.emit("message", speaker="SYSTEM", kind="system", text=msg, role_id=rid, step=turn, phase=phase)
            if failures >= 3:
                raise LLMError("Too many consecutive agent failures; stopping the discussion.")
        else:
            failures = 0
            speak_counts[rid] += 1
            tr.append(role.name.upper(), reply)
            await s.emit("message", speaker=role.name.upper(), kind="role", role_id=rid, text=reply,
                         step=turn, phase=phase)
        last_spoke[rid] = turn
        last_speaker = rid

        if phase == "wrapup":
            break

    # 3. The Concluder appears only now, reads everything and closes the discussion.
    c_turn = steps + 1
    await s.emit("status", text="Concluder is reviewing the whole discussion…")
    verdict = await agents.concluder("CONCLUDER", s.task, s.roles, tr.render(MAX_HISTORY_CHARS * 2))
    tr.append("CONCLUDER", verdict)
    await s.emit("message", speaker="CONCLUDER", kind="concluder", text=verdict, step=c_turn, phase="concluder")

    # 4. Master turns the decision into the final answer for the user.
    await s.emit("status", text="Discussion concluded. Master AI is writing the final answer…")
    final = await agents.master_final("MASTER", s.task, tr.render(MAX_HISTORY_CHARS * 2), verdict)
    tr.append("FINAL ANSWER", final)
    s.final = final
    await s.emit("final", text=final, steps=c_turn)
    await s.finish("completed")

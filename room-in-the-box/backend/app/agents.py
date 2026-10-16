"""Prompts and calls for the Master, the Manager, the role agents and the Concluder."""
from __future__ import annotations

import re

from . import llm
from .plan import TurnPlan
from .roles import Role
from .routing import Decision, RoutingError, parse_decision

ROLE_WORD_LIMIT = 130

MASTER_INITIAL_SYSTEM = """You are the Master AI, the first voice in a multi-agent group discussion.
1. Work out what the user actually needs (not just what they literally typed) and state it in ONE sentence.
2. Seed the discussion with a compact opening: if the user wants ideas or options, give 3-5 distinct numbered options with one concrete sentence each; otherwise give a tight first draft.
A panel of specialists will critique and refine this next, so be concrete rather than cautious, and keep it short (under about 180 words). Plain text, light **bold** for key terms, no preamble."""

MASTER_FINAL_SYSTEM = """You are the Master AI. The group discussion is over and the Concluder has ruled. Write the FINAL response for the user, addressed to them directly.
- The Concluder's decision is binding: build on it, do not overturn it.
- State the final recommendation/answer clearly first, then why it won, the key trade-offs or risks that were raised and how they were resolved, and concrete next steps.
- Use the agents' fixes and scope changes; drop ideas that were convincingly rejected.
- Well organised, not padded, no turn-by-turn narration. Use **bold** for the key terms and short lists where they help."""

CONCLUDER_SYSTEM = """You are the Concluder. You appear exactly once, at the very end of a group discussion between AI specialists, after reading the whole transcript. You do not argue; you close the discussion and decide.

Write the group's conclusion in this shape (Markdown, use the bold labels exactly):
**Decision:** one clear sentence stating what the group decided.
**Why it won:** 2-4 short bullets drawn from what was actually argued; name who made each point.
**Trade-offs & dissent:** what was conceded, what is still disputed, and how you resolved it.
**Next steps:** 2-4 short bullets.

Rules:
- Base everything on the transcript; never invent points nobody made.
- If the specialists did not fully agree, choose the best-supported option and say plainly that it was a judgement call.
- Be decisive and compact: roughly 120-220 words."""

# What each phase asks of a role agent
PHASE_ROLE = {
    "explore": "EXPLORE: give your own distinct view and the biggest risk you see; react to a specific point from the previous speaker.",
    "narrow": "NARROW: the group is choosing. Respond to the live disagreement, pick between the options on the table, and say what would change your mind.",
    "converge": "CONVERGE: time to decide. Commit to the option you back, concede the points you lost, and name the one objection that still matters.",
    "wrapup": "WRAP-UP: you open the conclusion. State the decision you believe the group has reached (or the best-supported option), the 2-3 reasons it won, and the remaining risk with its mitigation. The Concluder speaks next, so be decisive.",
}
# What each phase asks of the Manager
PHASE_MANAGER = {
    "explore": "Get distinct views on the table and surface the real disagreements.",
    "narrow": "Pit the live options against each other; push roles to resolve the open disagreements.",
    "converge": "Push the group to commit: ask a role to choose, concede or defend one final point.",
    "wrapup": "This turn is the WRAP-UP. Pick the ONE role best placed to open the conclusion (state the decision, the reasons, the remaining risk). Do not output [\"conclude\"].",
}


def manager_system(plan: TurnPlan) -> str:
    if plan.mode == "manual":
        control = ("You can NOT conclude: the system ends the discussion on schedule, so never output [\"conclude\"]. "
                   "Pace the group so that it is ready to decide by the wrap-up turn.")
        options = '1. ["<message to the next speaker>", ["role_id"]]   -> exactly ONE role id: the single role who speaks next.'
    else:
        control = (f"You decide when the discussion is ready. Only when CONCLUDE_ALLOWED says yes may you output [\"conclude\"]. "
                   f"Conclude as soon as the key perspectives have been heard, the main disagreements are resolved and further "
                   f"talk would not improve the decision; do not stretch the discussion for its own sake.")
        options = ('1. ["<message to the next speaker>", ["role_id"]]   -> exactly ONE role id: the single role who speaks next.\n'
                   '2. ["conclude"] or ["conclude", "role_id"]   -> the group is ready: ends open discussion; the optional role_id opens the wrap-up.')
    return f"""You are the Manager (orchestrator) of a live group discussion between AI specialists. You never answer the user's task yourself. Your only job is to decide who speaks next and what they should address, so the group moves toward ONE clear decision.

OUTPUT FORMAT — respond with ONLY valid JSON, no prose, no code fences. Exactly one of:
{options}

LENGTH: {plan.schedule()}
{control}

ROUTING RULES
- Read the whole transcript. Base the next step on what was ACTUALLY said: unresolved disagreements, contradictions, unsupported claims, weaknesses nobody fixed, questions left unanswered.
- Route by relevance, not in a fixed rotation. Use only role ids from AVAILABLE_ROLES. Avoid sending the same role twice in a row.
- Keep the message to the speaker short and specific (1-2 sentences): reference the exact point and who said it, and say what you want (rebut, fix, compare, choose, concede).
- Encourage honest disagreement and let agents change their minds, but each turn must move the group closer to a decision: no repeating points, no new tangents once the group is converging.
- The goal is a real conversation that ends in a decision, not a list of monologues."""


def role_system(role: Role) -> str:
    return f"""You are {role.name} in a live group discussion between AI specialists who must reach a decision on the user's task.
Your perspective: {role.perspective}

How to behave:
- Talk like a real person in a group chat: first person, direct, conversational.
- Answer the person who spoke last or the question the Manager asked you, by name. Open with your reaction ("Good catch, Judge, but...", "I disagree with Student because...", "Agreed, and...") and then add something NEW.
- Match your length to the moment: a quick reaction, agreement or question can be one or two sentences; a real argument or proposal can run up to about {ROLE_WORD_LIMIT} words. Never pad and never recap the whole discussion.
- Be concrete: propose specific fixes, alternatives or scope changes. Change your position when someone makes a better argument, and say so. Don't agree just to be polite.
- No headings; at most a very short list. You may use **bold** for the one or two key points or the option you back.
- Do not prefix your message with your name; the interface adds it."""


def _role_lines(roles: list[Role]) -> str:
    return "\n".join(f"- {r.id}: {r.name} — {r.perspective}" for r in roles)


async def master_initial(slot: str, task: str) -> str:
    return await llm.complete(slot, "master_initial", MASTER_INITIAL_SYSTEM,
                              f"USER TASK:\n{task}\n\nWrite your response now.", max_tokens=2500)


async def master_final(slot: str, task: str, history: str, verdict: str) -> str:
    user = (f"USER TASK:\n{task}\n\nFULL DISCUSSION:\n{history}\n\nTHE CONCLUDER'S DECISION (binding):\n{verdict}\n\n"
            "Write the final response for the user.")
    return await llm.complete(slot, "master_final", MASTER_FINAL_SYSTEM, user, max_tokens=4000)


async def concluder(slot: str, task: str, roles: list[Role], history: str) -> str:
    user = (f"USER TASK:\n{task}\n\nPANEL: {', '.join(r.name for r in roles)}\n\n"
            f"FULL DISCUSSION:\n{history}\n\nWrite the conclusion now.")
    return await llm.complete(slot, "concluder", CONCLUDER_SYSTEM, user, max_tokens=2500)


async def manager_decide(slot: str, task: str, roles: list[Role], history: str, plan: TurnPlan, turn: int,
                         phase: str, speak_counts: dict[str, int], last_speaker: str | None,
                         note: str | None) -> Decision:
    counts = ", ".join(f"{r.id}={speak_counts.get(r.id, 0)}" for r in roles)
    can = plan.mode == "auto" and phase != "wrapup" and plan.can_wrap_up(turn - 1)
    user = (
        f"ORIGINAL USER TASK:\n{task}\n\n"
        f"AVAILABLE_ROLES:\n{_role_lines(roles)}\n"
        f"AVAILABLE_ROLE_IDS: {', '.join(r.id for r in roles)}\n"
        f"TURN_MODE: {plan.mode}\n"
        f"TURN: {turn} ({plan.label(turn)}). {plan.remaining(turn)}\n"
        f"STEPS_DONE: {turn - 1}\n"
        f"PHASE: {phase} — {PHASE_MANAGER[phase]}\n"
        f"CONCLUDE_ALLOWED: {'yes' if can else 'no'}\n"
        f"LAST_SPEAKER: {last_speaker or 'none'}\n"
        f"TIMES_SPOKEN: {counts}\n"
        + (f"\nNOTE FROM SYSTEM: {note}\n" if note else "")
        + f"\nDISCUSSION SO FAR:\n{history}\n"
        "Decide the next step. JSON only."
    )
    system, error = manager_system(plan), None
    for _ in range(3):
        prompt = user + (f"\n\nYour previous output was invalid ({error}). Output ONLY the JSON array." if error else "")
        raw = await llm.complete(slot, "manager", system, prompt, max_tokens=1500)
        try:
            return parse_decision(raw, roles)
        except RoutingError as e:
            error = str(e)
    raise RoutingError(error or "invalid manager output")


async def role_speak(slot: str, role: Role, task: str, history: str, query: str, phase: str,
                     turn_label: str, remaining: str) -> str:
    user = (
        f"USER TASK:\n{task}\n\nDISCUSSION SO FAR:\n{history}\n"
        f"{turn_label}. {remaining}\n"
        f"PHASE: {PHASE_ROLE[phase]}\n\n"
        f"THE MANAGER ASKS YOU: {query}\n\nReply now as {role.name}."
    )
    text = await llm.complete(slot, "role", role_system(role), user, max_tokens=1500)
    return re.sub(rf"^\W*{re.escape(role.name)}\W*[:\-–—]\s*", "", text.strip(), flags=re.I)

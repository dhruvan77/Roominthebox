"""Prompts and calls for Master, Manager and role agents."""
from __future__ import annotations

import re

from . import llm
from .config import MAX_QUERIES, MIN_QUERIES
from .roles import Role
from .routing import Decision, RoutingError, parse_decision

ROLE_WORD_LIMIT = 170

MASTER_INITIAL_SYSTEM = """You are the Master AI, the first voice in a multi-agent group discussion.
1. Work out what the user actually needs (not just what they literally typed).
2. Write 1-2 sentences stating your interpretation of the need.
3. Then give an initial response that will seed the discussion. If the user wants ideas or options, give 5-10 distinct, numbered options with a concrete 1-2 sentence description each. Otherwise give your best first-draft answer.
A panel of specialists will critique and refine this next, so be concrete and ambitious rather than cautious. Plain text, no preamble."""

MASTER_FINAL_SYSTEM = """You are the Master AI. The group discussion has concluded. Write the FINAL response for the user, addressed to them directly.
- Build on the refined outcome of the discussion, not on your first draft; the result should differ from and improve on it.
- State the final recommendation/answer clearly, then explain why it won, the key trade-offs or risks that were raised and how they were resolved, and concrete next steps.
- Use the agents' fixes and scope changes; drop ideas that were convincingly rejected.
- Be well organised but not padded. Do not narrate the transcript turn by turn."""


def manager_system() -> str:
    return f"""You are the Manager (orchestrator) of a live group discussion between AI specialists. You never answer the user's task yourself. Your only job is to decide what should be discussed next and who should discuss it.

OUTPUT FORMAT — respond with ONLY valid JSON, no prose, no code fences. Exactly one of:
1. ["<message to send next>", ["role_id", "role_id"]]  -> the instruction/question for the next speaker(s) and the role ids that receive it.
2. ["conclude"]  -> ends the discussion.

ROUTING RULES
- Read the whole transcript. Base the next step on what was ACTUALLY said: unresolved disagreements, contradictions, unsupported claims, weaknesses nobody fixed, ideas that need refinement, points that need a second opinion.
- Route by relevance, not in a fixed rotation: technical contradiction -> technical role; scientific claim -> science role; feasibility -> student/practical role; academic concern -> professor; competition/presentation -> judge. Use only role ids from AVAILABLE_ROLES.
- Do not send a role something it has nothing new to add to. Send to 1-3 roles per step.
- Make the message specific: reference the exact point and who said it, and say what you want (rebut, fix, compare, decide, defend, reconsider).
- Encourage genuine disagreement and let agents change their minds. Never force agreement or majority voting; the goal is iterative refinement toward a stronger answer.
- Only conclude when the important perspectives have been heard, major contradictions are resolved, the answer is refined enough, and more discussion would not help. The system requires at least {MIN_QUERIES} routing steps (max {MAX_QUERIES}); concluding earlier is rejected."""


def role_system(role: Role) -> str:
    return f"""You are {role.name} in a live group discussion between AI specialists helping a user with a task.
Your perspective: {role.perspective}

How to behave:
- Talk like a real person in a group chat: first person, direct, conversational. No headings; keep any list very short.
- React to what others actually said. Refer to them by name ("I disagree with Judge because..."). Agree, disagree, question, criticise, defend, or refine according to your honest judgement.
- Change your position when someone makes a better argument, and say so. Don't agree just to be polite. Don't repeat points already made.
- Be concrete: propose specific fixes, alternatives, or scope changes.
- Stay under {ROLE_WORD_LIMIT} words.
- Do not prefix your message with your name; the interface adds it."""


def _role_lines(roles: list[Role]) -> str:
    return "\n".join(f"- {r.id}: {r.name} — {r.perspective}" for r in roles)


async def master_initial(slot: str, task: str) -> str:
    return await llm.complete(slot, "master_initial", MASTER_INITIAL_SYSTEM,
                              f"USER TASK:\n{task}\n\nWrite your response now.", max_tokens=3500)


async def master_final(slot: str, task: str, history: str) -> str:
    user = f"USER TASK:\n{task}\n\nFULL DISCUSSION:\n{history}\n\nWrite the final response for the user."
    return await llm.complete(slot, "master_final", MASTER_FINAL_SYSTEM, user, max_tokens=4000)


async def manager_decide(slot: str, task: str, roles: list[Role], history: str,
                         steps_done: int, speak_counts: dict[str, int], note: str | None) -> Decision:
    counts = ", ".join(f"{r.id}={speak_counts.get(r.id, 0)}" for r in roles)
    user = (
        f"ORIGINAL USER TASK:\n{task}\n\n"
        f"AVAILABLE_ROLES:\n{_role_lines(roles)}\n"
        f"AVAILABLE_ROLE_IDS: {', '.join(r.id for r in roles)}\n"
        f"STEPS_DONE: {steps_done} (minimum {MIN_QUERIES}, maximum {MAX_QUERIES})\n"
        f"TIMES_SPOKEN: {counts}\n"
        + (f"\nNOTE FROM SYSTEM: {note}\n" if note else "")
        + f"\nDISCUSSION SO FAR:\n{history}\n"
        "Decide the next step. JSON only."
    )
    system, error = manager_system(), None
    for _ in range(3):
        prompt = user + (f"\n\nYour previous output was invalid ({error}). Output ONLY the JSON array." if error else "")
        raw = await llm.complete(slot, "manager", system, prompt, max_tokens=1500)
        try:
            return parse_decision(raw, roles)
        except RoutingError as e:
            error = str(e)
    raise RoutingError(error or "invalid manager output")


async def role_speak(slot: str, role: Role, task: str, history: str, query: str) -> str:
    user = (
        f"USER TASK:\n{task}\n\nDISCUSSION SO FAR:\n{history}\n"
        f"THE MANAGER ASKS YOU: {query}\n\nReply now as {role.name}."
    )
    text = await llm.complete(slot, "role", role_system(role), user, max_tokens=1500)
    return re.sub(rf"^\W*{re.escape(role.name)}\W*[:\-–—]\s*", "", text.strip(), flags=re.I)

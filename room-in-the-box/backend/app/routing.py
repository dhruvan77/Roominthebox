"""Parse and validate the Manager's machine-readable routing output."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .roles import Role, _norm


class RoutingError(ValueError):
    pass


@dataclass
class Decision:
    conclude: bool
    query: str = ""
    roles: list[str] = field(default_factory=list)


def _extract_json(raw: str):
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for m in re.finditer(r"\[", text):
        try:
            value, _ = dec.raw_decode(text[m.start():])
            if isinstance(value, list):
                return value
        except ValueError:
            continue
    raise RoutingError("output was not valid JSON")


def parse_decision(raw: str, roles: list[Role]) -> Decision:
    """Accepts ["conclude"], ["conclude", "<role_id>"] or ["<query>", ["role_id", ...]]
    (role ids or names, case-insensitive)."""
    value = _extract_json(raw)
    if not isinstance(value, list) or not value:
        raise RoutingError("output must be a non-empty JSON array")

    lookup = {}
    for r in roles:
        lookup[_norm(r.id)] = r.id
        lookup[_norm(r.name)] = r.id

    if isinstance(value[0], str) and value[0].strip().lower() == "conclude" and len(value) <= 2:
        opener = value[1] if len(value) == 2 else None
        if isinstance(opener, list) and opener:
            opener = opener[0]
        rid = lookup.get(_norm(opener)) if isinstance(opener, str) else None
        return Decision(conclude=True, roles=[rid] if rid else [])
    if len(value) != 2:
        raise RoutingError('expected ["conclude"] or ["<message>", ["role_id"]]')

    query, targets = value
    if not isinstance(query, str) or not query.strip():
        raise RoutingError("first element must be a non-empty message string")
    if isinstance(targets, str):
        targets = [targets]
    if not isinstance(targets, list):
        raise RoutingError("second element must be a list of role ids")

    resolved: list[str] = []
    for t in targets:
        rid = lookup.get(_norm(t)) if isinstance(t, str) else None
        if rid and rid not in resolved:
            resolved.append(rid)
    if not resolved:
        raise RoutingError("no valid role ids; valid ids are: " + ", ".join(r.id for r in roles))
    return Decision(conclude=False, query=query.strip(), roles=resolved)


_FALLBACK_QUERIES = [
    "Respond directly to the most recent points: name one weakness or disagreement you see and propose a concrete fix.",
    "Challenge the current leading idea. What is the biggest risk nobody has properly addressed yet?",
    "Build on what was said so far: how would you improve or narrow the current best option?",
]


WRAPUP_QUERY = ("Start the conclusion: state the decision you think the group has reached, the two or three "
                "reasons it won, and the one risk that still matters.")


def pick_speaker(roles: list[Role], last_spoke: dict[str, int], last_speaker: str | None = None) -> str:
    """The role that has been quiet the longest (never the one who just spoke, if there is a choice)."""
    pool = [r for r in roles if r.id != last_speaker] or roles
    return min(pool, key=lambda r: last_spoke.get(r.id, 0)).id


def fallback_decision(roles: list[Role], last_spoke: dict[str, int], step: int,
                      last_speaker: str | None = None, wrapup: bool = False) -> Decision:
    """Used only if the Manager keeps producing unusable output: pick the role quiet the longest."""
    rid = pick_speaker(roles, last_spoke, last_speaker)
    query = WRAPUP_QUERY if wrapup else _FALLBACK_QUERIES[step % len(_FALLBACK_QUERIES)]
    return Decision(False, query, [rid])

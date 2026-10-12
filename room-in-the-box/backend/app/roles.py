"""Configurable roles. Presets are only examples — users can pick presets or define their own."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from .config import MAX_ROLES


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    perspective: str

    def to_dict(self) -> dict:
        return asdict(self)


PRESETS: dict[str, Role] = {r.id: r for r in [
    Role("student", "Student",
         "Practicality, learning difficulty, student feasibility, implementation effort, and whether "
         "students could realistically build it in the time available."),
    Role("professor", "Professor",
         "Technical depth, academic value, correctness, overall quality, and whether the idea "
         "demonstrates meaningful engineering."),
    Role("scientist", "Scientist",
         "Scientific reasoning, innovation, technical possibilities, research potential, and whether "
         "the underlying concept is sound."),
    Role("judge", "Judge",
         "Originality, presentation potential, problem relevance, technical impact, and whether the "
         "idea can stand out in a competition."),
    Role("technical_expert", "Technical Expert",
         "Architecture, implementation problems, bugs, scalability, technical weaknesses, and ways to "
         "improve the implementation."),
    Role("product_manager", "Product Manager",
         "User value, market fit, scope control, prioritisation, and what a realistic MVP looks like."),
    Role("devils_advocate", "Devil's Advocate",
         "Finding hidden assumptions, failure modes and risks that everyone else is overlooking."),
]}


def _norm(value: str) -> str:
    return re.sub(r"[\s\-]+", "_", value.strip().lower())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", _norm(value))[:40]


def resolve_roles(items: list) -> list[Role]:
    """Accept preset ids/names (str) or custom definitions ({id?, name, perspective?}).

    Raises ValueError with a user-friendly message on invalid input.
    """
    if not isinstance(items, list) or not (2 <= len(items) <= MAX_ROLES):
        raise ValueError(f"Choose between 2 and {MAX_ROLES} roles.")

    by_norm = {_norm(r.id): r for r in PRESETS.values()} | {_norm(r.name): r for r in PRESETS.values()}
    roles: list[Role] = []
    used: set[str] = set()

    for item in items:
        if isinstance(item, str):
            preset = by_norm.get(_norm(item))
            if not preset:
                raise ValueError(f"Unknown role '{item[:40]}'. Use a preset id or provide a name and perspective.")
            role = preset
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()[:40]
            if not name:
                raise ValueError("Every custom role needs a name.")
            preset = by_norm.get(_norm(str(item.get("id") or name)))
            perspective = str(item.get("perspective") or "").strip()[:800]
            if not perspective:
                perspective = preset.perspective if preset else f"Give your honest expert perspective as a {name}."
            rid = _slug(str(item.get("id") or name)) or "role"
            role = Role(rid, name, perspective)
        else:
            raise ValueError("Invalid role entry.")

        base, n, rid = role.id, 2, role.id
        while rid in used:
            rid = f"{base}_{n}"
            n += 1
        used.add(rid)
        roles.append(Role(rid, role.name, role.perspective))
    return roles

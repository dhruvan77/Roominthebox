"""Environment-driven configuration. API keys are read here and never leave the backend."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _temperature() -> float | None:
    raw = os.getenv("TEMPERATURE", "0.8").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return 0.8


# One "turn" = one AI message in the discussion (the Master opening is not counted).
# AUTO mode : the Manager may call the wrap-up once MIN_QUERIES turns have happened; MAX_QUERIES is the hard
#             cap on total turns including the wrap-up and the Concluder.
# MANUAL    : the user picks N turns (2..MAX_QUERIES): turn N-1 is the wrap-up, turn N is the Concluder.
MIN_MANUAL_TURNS = 2
MIN_QUERIES = max(_int("MIN_QUERIES", 6), 1)
MAX_QUERIES = max(_int("MAX_QUERIES", 16), MIN_QUERIES + 3, MIN_MANUAL_TURNS)
MAX_ROLES = max(2, min(_int("MAX_ROLES", 8), 10))
MAX_HISTORY_CHARS = _int("MAX_HISTORY_CHARS", 24000)
MAX_TASK_CHARS = _int("MAX_TASK_CHARS", 4000)
MAX_CONCURRENT_SESSIONS = _int("MAX_CONCURRENT_SESSIONS", 5)
LLM_TIMEOUT = float(_env("LLM_TIMEOUT", "90") or 90)
LLM_RETRIES = _int("LLM_RETRIES", 3)
TEMPERATURE = _temperature()

# --- Supabase (database). Backend only: the service_role key must NEVER go in the frontend. ---
SUPABASE_URL = _env("SUPABASE_URL").rstrip("/")
SUPABASE_SERVICE_KEY = _env("SUPABASE_SERVICE_KEY")
CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if o.strip()]
ACCESS_TOKEN = _env("ACCESS_TOKEN")

# --- Groq / gpt-oss-120b is the only model. Six separate API keys, one per AI instance. ---
USE_MOCK = _env("USE_MOCK").lower() in ("1", "true", "yes")   # offline scripted replies for testing
GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
REASONING_EFFORT = _env("REASONING_EFFORT", "low")            # low | medium | high (gpt-oss)
LLM_CONCURRENCY = max(_int("LLM_CONCURRENCY", 2), 1)          # simultaneous calls per key

ROLE_SLOTS = [f"ROLE{i}" for i in range(1, 11)]
ALL_SLOTS = ["MASTER", "MANAGER", "CONCLUDER", *ROLE_SLOTS]


def get_key(slot: str) -> str:
    """GROQ_API_KEY_<SLOT>; falls back to the optional shared GROQ_API_KEY if that slot is empty.
    The Concluder has its own optional key and otherwise reuses the Master's key."""
    key = _env(f"GROQ_API_KEY_{slot}")
    if not key and slot == "CONCLUDER":
        key = _env("GROQ_API_KEY_MASTER")
    return key or _env("GROQ_API_KEY")


def role_slot(index: int) -> str:
    """Key slot for the index-th role. With more roles than keys, roles share keys round-robin."""
    configured = [s for s in ROLE_SLOTS if _env(f"GROQ_API_KEY_{s}")]
    pool = configured or ROLE_SLOTS
    return pool[index % len(pool)]


def missing_slots(n_roles: int = 5) -> list[str]:
    """Slot names (never key values) that have no key, for Master + Manager + the slots the roles will use."""
    if USE_MOCK:
        return []
    need = ["MASTER", "MANAGER", *[role_slot(i) for i in range(n_roles)]]
    return [s for s in dict.fromkeys(need) if not get_key(s)]

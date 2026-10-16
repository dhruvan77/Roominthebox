"""End-to-end test with the offline mock provider:  python tests/smoke_test.py"""
import json
import os
import sys
import tempfile

os.environ.update(USE_MOCK="1", DATA_DIR=tempfile.mkdtemp(), MIN_QUERIES="6", MAX_QUERIES="16")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.plan import TurnPlan  # noqa: E402
from app.routing import parse_decision  # noqa: E402
from app.roles import resolve_roles  # noqa: E402

ROLES = ["student", "professor", {"name": "Security Auditor", "perspective": "Threat models."},
         {"name": "Finance Lead", "perspective": "Costs."}, "judge"]
TASK = "I need a strong project idea for a hackathon next week."


def run(c, body):
    r = c.post("/api/discussions", json={"task": TASK, "roles": ROLES, **body})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    events, cur = [], {}
    with c.stream("GET", f"/api/discussions/{sid}/stream") as resp:
        for line in resp.iter_lines():
            if line.startswith("event:"):
                cur["type"] = line[6:].strip()
            elif line.startswith("data:"):
                cur["data"] = json.loads(line[5:])
                events.append(cur)
                cur = {}
    return sid, r.json(), events


def check_common(events):
    types = [e["type"] for e in events]
    assert types[0] == "session" and types[-1] == "done"
    assert events[-1]["data"]["status"] == "completed"
    msgs = [e["data"] for e in events if e["type"] == "message"]
    conc = [m for m in msgs if m["kind"] == "concluder"]
    assert len(conc) == 1 and conc[0]["step"] > 0, "exactly one Concluder message"
    assert msgs[-1]["kind"] == "concluder", "Concluder speaks last in the chat"
    assert types.index("final") > max(i for i, e in enumerate(events) if e["data"].get("kind") == "concluder")
    speakers = [m for m in msgs if m["kind"] in ("role", "system")]
    wrap = [m for m in speakers if m.get("phase") == "wrapup"]
    assert len(wrap) == 1, "exactly one wrap-up turn"
    assert wrap[0]["step"] == conc[0]["step"] - 1, "wrap-up is the turn right before the Concluder"
    assert not any("API_KEY" in json.dumps(e) for e in events)
    return msgs, speakers, conc[0]


# pure logic
p = TurnPlan.build("manual", 5, 6, 16)
assert [p.phase(t) for t in range(1, 5)] == ["explore", "explore", "narrow", "wrapup"], [p.phase(t) for t in range(1, 5)]
assert p.wrapup_turn == 4 and p.concluder_turn == 5
assert TurnPlan.build("manual", 2, 6, 16).phase(1) == "wrapup"
assert TurnPlan.build("auto", None, 6, 16).wrapup_turn == 15
roles = resolve_roles(ROLES)
assert parse_decision('["conclude"]', roles).conclude
d = parse_decision('["conclude", "student"]', roles)
assert d.conclude and d.roles == ["student"]
assert parse_decision('["Go on", ["judge", "student"]]', roles).roles == ["judge", "student"]

with TestClient(app) as c:
    assert c.get("/api/health").json() == {"ok": True}
    info = c.get("/api/roles").json()
    assert len(info["presets"]) >= 5 and info["max_roles"] >= 5 and info["max_turns"] == 16

    # validation
    assert c.post("/api/discussions", json={"task": "x y z", "roles": ["student"]}).status_code == 422
    assert c.post("/api/discussions", json={"task": "x y z", "roles": ["student", "nope"]}).status_code == 422
    assert c.post("/api/discussions", json={"task": "x y z", "roles": ["student", "judge"],
                                            "turn_mode": "manual"}).status_code == 422
    assert c.post("/api/discussions", json={"task": "x y z", "roles": ["student", "judge"],
                                            "turn_mode": "sometimes"}).status_code == 422

    # MANUAL, 5 turns: turns 1-3 discuss, turn 4 wrap-up (any role), turn 5 Concluder
    sid, started, events = run(c, {"turn_mode": "manual", "turns": 5})
    assert started["turn_mode"] == "manual" and started["turns"] == 5 and len(started["roles"]) == 5
    msgs, speakers, conc = check_common(events)
    assert [m["step"] for m in speakers] == [1, 2, 3, 4], "one AI message per turn"
    assert conc["step"] == 5
    assert [e for e in events if e["type"] == "final"][0]["data"]["steps"] == 5
    assert events[0]["data"]["turn_mode"] == "manual" and events[0]["data"]["turns"] == 5
    summary = c.get(f"/api/discussions/{sid}").json()
    assert summary["turn_mode"] == "manual" and summary["turns"] == 5 and summary["status"] == "completed"
    print("manual(5) OK")

    # MANUAL, out-of-range values are clamped (max 16)
    _, started, events = run(c, {"turn_mode": "manual", "turns": 999})
    assert started["turns"] == 16
    _, speakers, conc = check_common(events)
    assert conc["step"] == 16 and len(speakers) == 15
    print("manual(clamped) OK")

    # AUTO: Manager decides; early conclude attempts are rejected, then wrap-up + Concluder
    sid, started, events = run(c, {})
    assert started["turn_mode"] == "auto" and started["turns"] is None
    msgs, speakers, conc = check_common(events)
    assert 6 <= len(speakers) - 1 and conc["step"] <= 16, (len(speakers), conc["step"])
    print(f"auto OK: {len(speakers)} speaker turns + Concluder")

    convo = c.get(f"/api/discussions/{sid}/conversation").text
    assert convo.startswith("USER:") and "MASTER:" in convo and "MANAGER:" in convo
    assert "CONCLUDER:" in convo and "FINAL ANSWER:" in convo
    assert c.get("/api/discussions/" + "0" * 32).status_code == 404
    assert c.get("/api/discussions/../../etc/passwd").status_code in (404, 422)
    print("SMOKE TEST PASSED")
    print(convo[:600])

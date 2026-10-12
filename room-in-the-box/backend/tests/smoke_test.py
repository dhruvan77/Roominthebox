"""End-to-end test with the offline mock provider:  python tests/smoke_test.py"""
import json
import os
import sys
import tempfile

os.environ.update(USE_MOCK="1", DATA_DIR=tempfile.mkdtemp(), MIN_QUERIES="10", MAX_QUERIES="24")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.get("/api/health").json() == {"ok": True}
    assert len(c.get("/api/roles").json()["presets"]) >= 5

    # validation
    assert c.post("/api/discussions", json={"task": "x y z", "roles": ["student"]}).status_code == 422
    assert c.post("/api/discussions", json={"task": "x y z", "roles": ["student", "nope"]}).status_code == 422

    r = c.post("/api/discussions", json={
        "task": "I need a strong project idea for a hackathon next week.",
        "roles": ["student", "professor", {"name": "Security Auditor", "perspective": "Threat models."}, "judge"]})
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

    types = [e["type"] for e in events]
    routed = [e for e in events if e["type"] == "message" and e["data"]["kind"] == "manager"]
    final = [e for e in events if e["type"] == "final"]
    print(f"events={len(events)} manager_steps={len(routed)}")
    assert types[0] == "session" and types[-1] == "done"
    assert events[-1]["data"]["status"] == "completed"
    assert len(routed) >= 10, "manager must not conclude before the minimum"
    assert len(final) == 1
    assert not any("API_KEY" in json.dumps(e) for e in events)

    convo = c.get(f"/api/discussions/{sid}/conversation").text
    assert convo.startswith("USER:") and "MASTER:" in convo and "MANAGER:" in convo and "FINAL ANSWER:" in convo
    assert c.get(f"/api/discussions/{sid}").json()["status"] == "completed"
    assert c.get("/api/discussions/" + "0" * 32).status_code == 404
    assert c.get("/api/discussions/../../etc/passwd").status_code in (404, 422)
    print("SMOKE TEST PASSED")
    print(convo[:700])

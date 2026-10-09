from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web"


def test_static_console_is_present_and_calls_deterministic_api_surface():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    javascript = (WEB / "app.js").read_text(encoding="utf-8")
    stylesheet = (WEB / "styles.css").read_text(encoding="utf-8")
    for path in ("/v1/datasets", "/v1/agent-builds", "/v1/evaluation-runs", "/comparisons/"):
        assert path in javascript
    assert "/ci-verdict" in javascript
    assert "MISSING" in javascript
    assert "TIMEOUT" in javascript
    assert "INVALID_RESULT" in javascript
    assert "FAIL-CLOSED" in javascript
    assert "No arbitrary execution" in html
    assert "agent" not in javascript.lower() or "agent-build" in javascript.lower()
    assert "terminalStatuses" in javascript
    assert ".pill.fail" in stylesheet


def test_static_console_does_not_expose_arbitrary_agent_execution():
    javascript = (WEB / "app.js").read_text(encoding="utf-8").lower()
    html = (WEB / "index.html").read_text(encoding="utf-8").lower()
    forbidden = ("/execute", "/run-agent", "arbitrary agent", "eval(")
    assert not any(marker in javascript or marker in html for marker in forbidden)

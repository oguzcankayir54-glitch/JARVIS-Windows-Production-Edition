import json
from pathlib import Path

from jarvis.core.observability import RequestTraceLog
from jarvis.security.audit import AuditEntry, AuditLog


def test_trace_hides_raw_user_text_by_default(tmp_path: Path):
    log = RequestTraceLog(tmp_path / "requests.jsonl")
    trace, started = log.start(
        request_id="req1", user_text="Benim parolam CokGizli123",
        intent="CHAT", confidence=0.99, model="qwen",
    )
    log.finish(trace, started, status="ok")
    raw = (tmp_path / "requests.jsonl").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["user_message"] == "[privacy-redacted]"
    assert "CokGizli123" not in raw
    assert len(data["user_message_sha256"]) == 64


def test_trace_records_reasoning_without_private_reasoning_text(tmp_path: Path):
    log = RequestTraceLog(tmp_path / "requests.jsonl")
    trace, started = log.start(
        request_id="req-level", user_text="Jarvis", intent="CHAT",
        confidence=0.99, model="qwen", reasoning_level=0,
        thinking_enabled=False,
    )
    log.finish(trace, started, status="ok")
    data = json.loads((tmp_path / "requests.jsonl").read_text(encoding="utf-8"))
    assert data["reasoning_level"] == 0
    assert data["thinking_enabled"] is False
    assert "chain" not in data and "reasoning_trace" not in data


def test_trace_can_record_tool_outcome_metadata_without_tool_payload(tmp_path: Path):
    log = RequestTraceLog(tmp_path / "requests.jsonl")
    trace, started = log.start(
        request_id="req-tool", user_text="sistem nasıl", intent="SYSTEM_MONITOR",
        confidence=0.9, model="qwen",
    )
    trace.tool_results.append({"tool": "get_system_info", "success": False,
                               "verified": False, "duration_ms": 3.2,
                               "error_type": "TOOL_FAILURE"})
    log.finish(trace, started, status="error")
    data = json.loads((tmp_path / "requests.jsonl").read_text(encoding="utf-8"))
    assert data["tool_results"][0]["success"] is False
    assert "payload" not in data["tool_results"][0]


def test_trace_redacts_secrets_even_when_text_logging_enabled(tmp_path: Path):
    log = RequestTraceLog(tmp_path / "requests.jsonl", include_user_text=True)
    trace, started = log.start(
        request_id="req2", user_text="api_key=sk-abcdefghijklmnop",
        intent="CHAT", confidence=1.0, model="qwen",
    )
    log.finish(trace, started, status="error", error="Bearer abcdefghijklmnop")
    raw = (tmp_path / "requests.jsonl").read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnop" not in raw
    assert "abcdefghijklmnop" not in raw
    assert "[SECRET]" in raw


def test_audit_file_redacts_secret_arguments(tmp_path: Path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record(AuditEntry(
        tool="example", risk="HIGH", decision="denied",
        args={"api_key": "sk-abcdefghijklmnop", "url": "https://u:pass@example.com/x"},
        detail="token=abcdefghijklmnop",
    ))
    raw = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnop" not in raw
    assert "u:pass@" not in raw
    assert "abcdefghijklmnop" not in raw
    assert "[SECRET]" in raw

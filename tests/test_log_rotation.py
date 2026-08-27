from jarvis.core.observability import RequestTrace, RequestTraceLog
from jarvis.security.audit import AuditEntry, AuditLog


def test_audit_log_rotates_before_crossing_limit(tmp_path):
    path = tmp_path / "audit.log.jsonl"
    log = AuditLog(path, max_bytes=180, backup_count=2)
    for number in range(8):
        log.record(AuditEntry("test", "LOW", "allowed", detail="x" * 60,
                              ts=float(number)))
    assert path.is_file() and path.with_name("audit.log.jsonl.1").is_file()
    assert not path.with_name("audit.log.jsonl.3").exists()


def test_request_trace_log_uses_same_retention_policy(tmp_path):
    path = tmp_path / "requests.log.jsonl"
    log = RequestTraceLog(path, max_bytes=220, backup_count=1)
    for number in range(4):
        log.record(RequestTrace(str(number), float(number), "[privacy-redacted]",
                                "hash", "chat", 1.0))
    assert path.is_file() and path.with_name("requests.log.jsonl.1").is_file()
    assert not path.with_name("requests.log.jsonl.2").exists()


def test_zero_limit_disables_rotation(tmp_path):
    path = tmp_path / "audit.log.jsonl"
    log = AuditLog(path, max_bytes=0, backup_count=2)
    for _ in range(5):
        log.record(AuditEntry("test", "LOW", "allowed", detail="x" * 100))
    assert path.is_file() and not path.with_name("audit.log.jsonl.1").exists()

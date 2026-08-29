"""Threshold-based proactive monitoring without notification spam."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..core.events import Event, EventBus


@dataclass(frozen=True)
class MonitorConfig:
    enabled: bool = False
    expect_tts: bool = False
    expect_stt: bool = False
    interval: float = 15.0
    health_interval: float = 60.0
    cooldown: float = 300.0
    recovery_samples: int = 2
    ram_warning: float = 85.0
    ram_critical: float = 95.0
    disk_warning: float = 90.0
    disk_critical: float = 97.0
    gpu_temp_warning: float = 80.0
    gpu_temp_critical: float = 90.0
    vram_warning: float = 85.0
    vram_critical: float = 95.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "interval", max(4.0, float(self.interval)))
        object.__setattr__(self, "health_interval", max(15.0, float(self.health_interval)))
        object.__setattr__(self, "cooldown", max(1.0, float(self.cooldown)))
        object.__setattr__(self, "recovery_samples", max(1, int(self.recovery_samples)))
        for warning_name, critical_name, ceiling in (
            ("ram_warning", "ram_critical", 100.0),
            ("disk_warning", "disk_critical", 100.0),
            ("vram_warning", "vram_critical", 100.0),
            ("gpu_temp_warning", "gpu_temp_critical", 150.0),
        ):
            warning = min(ceiling, max(0.0, float(getattr(self, warning_name))))
            critical = min(ceiling, max(warning, float(getattr(self, critical_name))))
            object.__setattr__(self, warning_name, warning)
            object.__setattr__(self, critical_name, critical)


@dataclass
class _Issue:
    severity: str
    last_emit: float
    clear_samples: int = 0


class ProactiveMonitor:
    """Evaluate measured snapshots and emit changes, not a stream of noise."""

    def __init__(self, events: EventBus, config: MonitorConfig,
                 *, clock: Callable[[], float] = time.monotonic) -> None:
        self.events = events
        self.config = config
        self._clock = clock
        self._issues: dict[str, _Issue] = {}
        self._lock = threading.RLock()
        self._unsubscribers = [
            events.subscribe("jarvis.error", self._on_error),
            events.subscribe("llm.error", self._on_error),
            events.subscribe("tool.error", self._on_error),
            events.subscribe("voice.error", self._on_error),
            events.subscribe("vision.error", self._on_error),
            events.subscribe("llm.finished", self._on_success),
            events.subscribe("voice.finished", self._on_success),
            events.subscribe("tool.finished", self._on_success),
            events.subscribe("vision.finished", self._on_success),
        ] if config.enabled else []

    def close(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    def _emit(self, key: str, severity: str, message: str,
              details: dict[str, Any]) -> None:
        now = self._clock()
        with self._lock:
            issue = self._issues.get(key)
            should_emit = (issue is None or issue.severity != severity
                           or now - issue.last_emit >= self.config.cooldown)
            self._issues[key] = _Issue(
                severity=severity,
                last_emit=now if should_emit else issue.last_emit,
            )
        if should_emit:
            self.events.publish(
                "system.alert" if severity == "critical" else "system.warning",
                {"key": key, "severity": severity, "message": message, **details},
                source="proactive-monitor",
            )

    def _clear(self, key: str, *, measured: bool = True) -> None:
        if not measured:
            return
        with self._lock:
            issue = self._issues.get(key)
            if issue is None:
                return
            issue.clear_samples += 1
            if issue.clear_samples < max(1, self.config.recovery_samples):
                return
            self._issues.pop(key, None)
        self.events.publish(
            "system.recovered", {"key": key, "message": f"{key} normale döndü"},
            source="proactive-monitor",
        )

    def _threshold(self, key: str, value: float | None, warning: float,
                   critical: float, unit: str, label: str) -> None:
        if value is None:
            return  # unknown is not healthy and not actionable
        value = float(value)
        if value >= critical:
            self._emit(key, "critical", f"{label} kritik seviyede",
                       {"value": value, "threshold": critical, "unit": unit})
        elif value >= warning:
            self._emit(key, "warning", f"{label} yüksek",
                       {"value": value, "threshold": warning, "unit": unit})
        else:
            self._clear(key)

    def evaluate_telemetry(self, telemetry: dict[str, Any]) -> None:
        if not self.config.enabled:
            return
        ram = telemetry.get("ram", {})
        disk = telemetry.get("disk", {})
        gpu = telemetry.get("gpu", {})
        self._threshold("ram.high", ram.get("percent"), self.config.ram_warning,
                        self.config.ram_critical, "%", "RAM kullanımı")
        self._threshold("disk.high", disk.get("used_percent"), self.config.disk_warning,
                        self.config.disk_critical, "%", "Disk kullanımı")
        if gpu.get("available"):
            self._threshold("gpu.temperature", gpu.get("temp_c"),
                            self.config.gpu_temp_warning, self.config.gpu_temp_critical,
                            "°C", "GPU sıcaklığı")
            total, used = gpu.get("vram_total_mb"), gpu.get("vram_used_mb")
            percent = (float(used) / float(total) * 100
                       if total and used is not None else None)
            self._threshold("vram.high", percent, self.config.vram_warning,
                            self.config.vram_critical, "%", "VRAM kullanımı")

    def evaluate_health(self, report: dict[str, Any]) -> None:
        if not self.config.enabled:
            return
        checks = {item.get("key"): item for item in report.get("checks", [])}
        for key, label in (("ollama", "Ollama"), ("model", "Model"),
                           ("tts", "TTS"), ("microphone", "Mikrofon")):
            check = checks.get(key)
            if not check or check.get("status") == "unknown":
                continue
            if key == "tts" and not self.config.expect_tts:
                continue
            if key == "microphone" and not self.config.expect_stt:
                continue
            issue_key = f"health.{key}"
            status = check.get("status")
            if status in {"critical", "unavailable"}:
                self._emit(issue_key, "critical", f"{label} kullanılamıyor",
                           {"component": key, "status": status})
            elif status == "warning":
                self._emit(issue_key, "warning", f"{label} hazır değil",
                           {"component": key, "status": status})
            else:
                self._clear(issue_key)

    def report_error(self, key: str, message: str, *, severity: str = "warning",
                     error_type: str = "UNKNOWN") -> None:
        """Route monitor/service probe failures through the same cooldown."""
        if self.config.enabled:
            self._emit(key, severity, message, {"error_type": error_type})

    def report_success(self, key: str) -> None:
        if self.config.enabled:
            self._clear(key)

    def _on_error(self, event: Event) -> None:
        domain = event.name.split(".", 1)[0]
        suffix = str(event.payload.get("tool") or event.payload.get("stage") or "")
        key = f"service.{domain}" + (f".{suffix}" if suffix else "")
        severity = "critical" if domain in {"jarvis", "llm"} else "warning"
        self._emit(key, severity, f"{domain.upper()} arka plan hatası",
                   {"event": event.name,
                    "error_type": event.payload.get("error_type", "UNKNOWN")})

    def _on_success(self, event: Event) -> None:
        domain = event.name.split(".", 1)[0]
        suffix = str(event.payload.get("tool") or event.payload.get("stage") or "")
        self._clear(f"service.{domain}" + (f".{suffix}" if suffix else ""))

    def active_issues(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._issues))

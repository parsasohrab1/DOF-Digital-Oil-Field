"""
Zero Trust + SIEM + threat detection helpers.
"""
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Tuple
import ipaddress
import json
import os

from .logging_config import setup_logging

logger = setup_logging("threat-detection")

MAX_SIEM_EVENTS = 500


class SIEMEventLogger:
    """Emit structured security events for SIEM ingestion."""

    def __init__(self, output_file: Optional[str] = None):
        self.output_file = output_file or os.getenv("SIEM_OUTPUT_FILE")
        self._events: Deque[Dict[str, Any]] = deque(maxlen=MAX_SIEM_EVENTS)

    def emit(self, event_type: str, severity: str, payload: Dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "severity": severity,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": payload,
        }
        self._events.appendleft(event)
        logger.warning("SIEM_EVENT %s", json.dumps(event, ensure_ascii=True))
        if self.output_file:
            try:
                with open(self.output_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=True) + "\n")
            except Exception as exc:
                logger.error("Failed to write SIEM event file: %s", exc)

    def recent_events(
        self, limit: int = 50, severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        events = list(self._events)
        if severity:
            events = [e for e in events if e.get("severity") == severity]
        return events[:limit]

    def summary(self) -> Dict[str, Any]:
        counts: Dict[str, int] = defaultdict(int)
        for event in self._events:
            counts[event.get("severity", "unknown")] += 1
        return {
            "total_buffered": len(self._events),
            "by_severity": dict(counts),
            "zero_trust_enforced": os.getenv("ZERO_TRUST_ENFORCED", "false").lower()
            == "true",
            "threat_block_threshold": int(os.getenv("THREAT_BLOCK_THRESHOLD", "70")),
        }


class ThreatDetector:
    """Simple behavior-based detector for suspicious request patterns."""

    def __init__(self):
        self._ip_hits: Dict[str, List[datetime]] = defaultdict(list)
        self._user_hits: Dict[str, List[datetime]] = defaultdict(list)
        self.window = timedelta(minutes=5)
        self.max_ip_hits = 120
        self.max_user_hits = 80

    def evaluate(
        self,
        *,
        ip: str,
        user: Optional[str],
        path: str,
        method: str,
        status_code: int,
        user_agent: str = "",
    ) -> Tuple[int, List[str]]:
        now = datetime.utcnow()
        reasons: List[str] = []
        risk = 0

        self._ip_hits[ip] = [t for t in self._ip_hits[ip] if now - t < self.window]
        self._ip_hits[ip].append(now)
        if len(self._ip_hits[ip]) > self.max_ip_hits:
            risk += 45
            reasons.append("high_request_rate_ip")

        if user:
            self._user_hits[user] = [
                t for t in self._user_hits[user] if now - t < self.window
            ]
            self._user_hits[user].append(now)
            if len(self._user_hits[user]) > self.max_user_hits:
                risk += 35
                reasons.append("high_request_rate_user")

        if status_code in (401, 403):
            risk += 20
            reasons.append("authz_failure")

        if method in ("PUT", "PATCH", "DELETE") and "/health" in path:
            risk += 30
            reasons.append("suspicious_method_for_health")

        if "sqlmap" in user_agent.lower() or "' or 1=1" in path.lower():
            risk += 60
            reasons.append("known_attack_pattern")

        return min(100, risk), reasons


def is_private_or_loopback(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


siem_logger = SIEMEventLogger()
threat_detector = ThreatDetector()

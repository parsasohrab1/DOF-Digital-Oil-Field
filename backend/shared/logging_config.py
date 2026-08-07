"""
Structured logging configuration
"""
import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict

from .config import settings


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": self.service_name,
            "environment": settings.ENVIRONMENT,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context fields if present
        for key in ("correlation_id", "user_id", "request_id"):
            value = getattr(record, key, None)
            if value is not None:
                log_data[key] = value

        # Include exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(service_name: str):
    """Setup structured logging for a service."""

    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_FORMAT == "json":
        formatter = JSONFormatter(service_name)
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter to add contextual data to logs."""

    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {}).copy()
        extra.update(self.extra or {})
        kwargs["extra"] = extra
        return msg, kwargs

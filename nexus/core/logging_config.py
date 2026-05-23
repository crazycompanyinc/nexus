from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Any

# Context variable for correlation ID — automatically propagates across async boundaries
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get the current correlation ID, generating one if not set.

    Returns:
        The current correlation ID string.
    """
    cid = _correlation_id.get("")
    if not cid:
        cid = str(uuid.uuid4())[:12]
        _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Set the current correlation ID.

    Args:
        cid: The correlation ID to set.
    """
    _correlation_id.set(cid)


class CorrelationFilter(logging.Filter):
    """Logging filter that injects correlation_id and component into every log record.

    Usage:
        >>> handler = logging.StreamHandler()
        >>> handler.addFilter(CorrelationFilter(component="nexus.api"))
    """

    def __init__(self, component: str = "nexus") -> None:
        """Initialize the correlation filter with a component name.

        Args:
            component: Name to inject into log records (e.g. 'nexus.api').
        """
        super().__init__()
        self.component = component

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject correlation_id and component into the log record.

        Args:
            record: The log record to enrich.

        Returns:
            True (always allows the record through).
        """
        record.correlation_id = get_correlation_id()  # type: ignore[attr-defined]
        record.component = self.component  # type: ignore[attr-defined]
        return True


class StructuredFormatter(logging.Formatter):
    """Structured log formatter with correlation ID and component.

    Format: [correlation_id] LEVEL component: message
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as [correlation_id] LEVEL component: message.

        Args:
            record: The log record to format.

        Returns:
            Formatted log line string.
        """
        cid = getattr(record, "correlation_id", "-")
        component = getattr(record, "component", "nexus")
        record.msg = f"[{cid}] {record.levelname} {component}: {record.msg}"
        return super().format(record)


def configure_logging(level: int = logging.INFO, component: str = "nexus") -> None:
    """Configure structured logging for Nexus.

    Args:
        level: Logging level (default: INFO).
        component: Component name for log records.
    """
    handler = logging.StreamHandler()
    handler.addFilter(CorrelationFilter(component=component))
    handler.setFormatter(StructuredFormatter("%(message)s"))

    root = logging.getLogger("nexus")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

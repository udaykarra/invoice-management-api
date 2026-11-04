"""Contract and interface definitions for the invoice_concurrency task."""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass(frozen=True)
class ConcurrencyResult:
    """Result of an invoice creation attempt under concurrent load."""
    status_code: int
    data: Dict[str, Any]
    headers: Dict[str, str]


class ConcurrentInvoiceHandler(Protocol):
    """Protocol that candidate solutions must satisfy."""

    def process_request(
        self,
        engine: Any,
        payload: Dict[str, Any],
        idempotency_key: Optional[str],
    ) -> ConcurrencyResult:
        """Process an invoice creation request against a SQLAlchemy engine."""
        ...

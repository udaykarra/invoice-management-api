"""Flawed candidate that crashes with unhandled 500 / IntegrityError on concurrent collisions."""

import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.orm import sessionmaker

from tasks.invoice_concurrency.contract import ConcurrencyResult
from tasks.invoice_concurrency.reference import TaskIdempotency, TaskInvoice


class RaceConditionHandler:
    """Deliberately flawed candidate omitting collision recovery and concurrency locks."""

    def process_request(
        self,
        engine: Any,
        payload: Dict[str, Any],
        idempotency_key: Optional[str],
    ) -> ConcurrencyResult:
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = Session()
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()

        # Defect: Fast check without handling concurrent integrity collision
        if idempotency_key:
            clean_key = idempotency_key.strip()
            existing = session.query(TaskIdempotency).filter(TaskIdempotency.key == clean_key).first()
            if existing:
                session.close()
                return ConcurrencyResult(status_code=200, data=json.loads(existing.response_body), headers={})

        try:
            inv_id = f"inv_{uuid.uuid4().hex[:10]}"
            total = Decimal(str(payload.get("total_amount", "100.00")))
            inv = TaskInvoice(id=inv_id, customer_name=payload.get("customer_name", "Acme"), total_amount=total)
            session.add(inv)
            session.flush()

            data = {"id": inv_id, "customer_name": inv.customer_name, "total_amount": str(total)}
            if idempotency_key:
                clean_key = idempotency_key.strip()
                idem = TaskIdempotency(
                    key=clean_key,
                    request_hash=payload_hash,
                    response_code=201,
                    response_body=json.dumps(data),
                )
                session.add(idem)

            session.commit()
            session.close()
            return ConcurrencyResult(status_code=201, data=data, headers={})
        except Exception:
            # Defect: Does not retry or poll for winner; crashes with 500
            session.rollback()
            session.close()
            return ConcurrencyResult(status_code=500, data={"error": "Database collision error"}, headers={})


handler = RaceConditionHandler()

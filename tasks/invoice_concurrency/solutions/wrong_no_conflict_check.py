"""Flawed candidate that fails to detect payload mismatches on idempotency key reuse."""

import json
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from tasks.invoice_concurrency.contract import ConcurrencyResult
from tasks.invoice_concurrency.reference import TaskIdempotency, TaskInvoice


class NoConflictCheckHandler:
    """Deliberately flawed candidate that blinds itself to payload hash mismatches."""

    def process_request(
        self,
        engine: Any,
        payload: Dict[str, Any],
        idempotency_key: Optional[str],
    ) -> ConcurrencyResult:
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = Session()

        if idempotency_key:
            clean_key = idempotency_key.strip()
            existing = session.query(TaskIdempotency).filter(TaskIdempotency.key == clean_key).first()
            if existing:
                session.close()
                # Defect: Always returns 200 without checking if payload matches (never returns 409!)
                return ConcurrencyResult(
                    status_code=200,
                    data=json.loads(existing.response_body),
                    headers={"X-Idempotent-Replay": "true"},
                )

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
                    request_hash="dummy_hash",
                    response_code=201,
                    response_body=json.dumps(data),
                )
                session.add(idem)

            session.commit()
            session.close()
            return ConcurrencyResult(status_code=201, data=data, headers={})
        except (IntegrityError, OperationalError):
            session.rollback()
            if idempotency_key:
                clean_key = idempotency_key.strip()
                for _ in range(15):
                    time.sleep(0.02)
                    winner = session.query(TaskIdempotency).filter(TaskIdempotency.key == clean_key).first()
                    if winner:
                        session.close()
                        # Defect: Always returns 200 without checking if payload matches
                        return ConcurrencyResult(status_code=200, data=json.loads(winner.response_body), headers={})
            session.close()
            return ConcurrencyResult(status_code=500, data={"error": "Collision"}, headers={})


handler = NoConflictCheckHandler()

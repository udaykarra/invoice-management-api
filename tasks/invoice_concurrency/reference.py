"""Reference implementation for concurrent idempotent invoice creation."""

import hashlib
import json
import random
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import Column, Integer, Numeric, String, Text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from tasks.invoice_concurrency.contract import ConcurrencyResult

Base = declarative_base()


class TaskInvoice(Base):
    __tablename__ = "task_invoices"
    id = Column(String(36), primary_key=True)
    customer_name = Column(String(255), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)


class TaskIdempotency(Base):
    __tablename__ = "task_idempotency"
    key = Column(String(128), primary_key=True)
    request_hash = Column(String(64), nullable=False)
    response_code = Column(Integer, nullable=False)
    response_body = Column(Text, nullable=False)


def compute_hash(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ReferenceConcurrentHandler:
    """Robust reference implementation with atomic transactions and backoff retry."""

    def process_request(
        self,
        engine: Any,
        payload: Dict[str, Any],
        idempotency_key: Optional[str],
    ) -> ConcurrencyResult:
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = Session()
        payload_hash = compute_hash(payload)

        # 1. Fast read check
        if idempotency_key:
            clean_key = idempotency_key.strip()
            existing = session.query(TaskIdempotency).filter(TaskIdempotency.key == clean_key).first()
            if existing:
                if existing.request_hash == payload_hash:
                    session.close()
                    return ConcurrencyResult(
                        status_code=200,
                        data=json.loads(existing.response_body),
                        headers={"X-Idempotent-Replay": "true"},
                    )
                else:
                    session.close()
                    return ConcurrencyResult(
                        status_code=409,
                        data={"error": "IDEMPOTENCY_CONFLICT", "message": "Key used with different payload"},
                        headers={},
                    )

        # 2. Transaction insertion with retry for concurrent collisions
        try:
            inv_id = f"inv_{uuid.uuid4().hex[:10]}"
            total = Decimal(str(payload.get("total_amount", "100.00")))
            inv = TaskInvoice(
                id=inv_id,
                customer_name=payload.get("customer_name", "Acme"),
                total_amount=total,
            )
            session.add(inv)
            session.flush()

            response_data = {"id": inv_id, "customer_name": inv.customer_name, "total_amount": str(total)}

            if idempotency_key:
                clean_key = idempotency_key.strip()
                idem = TaskIdempotency(
                    key=clean_key,
                    request_hash=payload_hash,
                    response_code=201,
                    response_body=json.dumps(response_data),
                )
                session.add(idem)

            session.commit()
            session.close()
            return ConcurrencyResult(
                status_code=201,
                data=response_data,
                headers={},
            )

        except (IntegrityError, OperationalError):
            session.rollback()

            if idempotency_key:
                clean_key = idempotency_key.strip()
                for attempt in range(15):
                    time.sleep(min(0.2, 0.01 * (1.5 ** attempt)) + random.uniform(0.001, 0.01))
                    try:
                        winner = session.query(TaskIdempotency).filter(TaskIdempotency.key == clean_key).first()
                        if winner:
                            session.close()
                            if winner.request_hash == payload_hash:
                                return ConcurrencyResult(
                                    status_code=200,
                                    data=json.loads(winner.response_body),
                                    headers={"X-Idempotent-Replay": "true"},
                                )
                            else:
                                return ConcurrencyResult(
                                    status_code=409,
                                    data={"error": "IDEMPOTENCY_CONFLICT", "message": "Key conflict"},
                                    headers={},
                                )
                    except OperationalError:
                        continue

            session.close()
            return ConcurrencyResult(
                status_code=500,
                data={"error": "INTERNAL_ERROR"},
                headers={},
            )
        except Exception as e:
            session.rollback()
            session.close()
            return ConcurrencyResult(status_code=500, data={"error": str(e)}, headers={})

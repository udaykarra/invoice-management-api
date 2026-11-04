"""Alternative valid candidate using mutex synchronization for transaction coordination."""

import hashlib
import json
import threading
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.orm import sessionmaker

from tasks.invoice_concurrency.contract import ConcurrencyResult
from tasks.invoice_concurrency.reference import TaskIdempotency, TaskInvoice

_lock = threading.Lock()


class LockSynchronizedHandler:
    """Alternative valid solution utilizing coordination locks to synchronize write serialization."""

    def process_request(
        self,
        engine: Any,
        payload: Dict[str, Any],
        idempotency_key: Optional[str],
    ) -> ConcurrencyResult:
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()

        with _lock:
            session = Session()
            try:
                if idempotency_key:
                    clean_key = idempotency_key.strip()
                    existing = session.query(TaskIdempotency).filter(TaskIdempotency.key == clean_key).first()
                    if existing:
                        if existing.request_hash == payload_hash:
                            return ConcurrencyResult(
                                status_code=200,
                                data=json.loads(existing.response_body),
                                headers={"X-Idempotent-Replay": "true"},
                            )
                        else:
                            return ConcurrencyResult(
                                status_code=409,
                                data={"error": "IDEMPOTENCY_CONFLICT"},
                                headers={},
                            )

                inv_id = f"inv_{uuid.uuid4().hex[:10]}"
                total = Decimal(str(payload.get("total_amount", "100.00")))
                inv = TaskInvoice(
                    id=inv_id,
                    customer_name=payload.get("customer_name", "Acme"),
                    total_amount=total,
                )
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
                return ConcurrencyResult(status_code=201, data=data, headers={})
            except Exception as e:
                session.rollback()
                return ConcurrencyResult(status_code=500, data={"error": str(e)}, headers={})
            finally:
                session.close()


handler = LockSynchronizedHandler()

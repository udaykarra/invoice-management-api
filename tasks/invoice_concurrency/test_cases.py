"""Deterministic concurrency test harness for candidate solutions."""

import concurrent.futures
import os
import tempfile
import threading
from typing import Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tasks.invoice_concurrency.contract import ConcurrentInvoiceHandler
from tasks.invoice_concurrency.reference import Base, TaskIdempotency, TaskInvoice


def init_test_db():
    """Create dedicated test database with WAL mode and busy timeout."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        conn.exec_driver_sql("PRAGMA busy_timeout=30000;")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, db_path


def cleanup_db(engine, db_path):
    engine.dispose()
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except OSError:
        pass


def test_concurrent_identical_batch(handler: ConcurrentInvoiceHandler, num_workers: int = 10) -> Tuple[bool, str]:
    """Test N simultaneous identical requests using the same idempotency key."""
    engine, db_path = init_test_db()
    try:
        key = "test_concurrent_identical_key"
        payload = {"customer_name": "Acme Corp", "total_amount": "250.00"}
        barrier = threading.Barrier(num_workers)

        def worker():
            barrier.wait()
            return handler.process_request(engine, payload, key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker) for _ in range(num_workers)]
            results = [f.result() for f in futures]

        codes = [r.status_code for r in results]
        if codes.count(201) != 1:
            return False, f"Expected exactly 1 x 201 Created, got {codes.count(201)} (all codes: {codes})"
        if codes.count(200) != num_workers - 1:
            return False, f"Expected {num_workers - 1} x 200 Replays, got {codes.count(200)} (all codes: {codes})"

        ids = {r.data.get("id") for r in results}
        if len(ids) != 1:
            return False, f"Expected identical invoice ID for all responses, got: {ids}"

        Session = sessionmaker(bind=engine)
        s = Session()
        inv_count = s.query(TaskInvoice).count()
        idem_count = s.query(TaskIdempotency).count()
        s.close()

        if inv_count != 1:
            return False, f"Database has {inv_count} invoices; expected exactly 1"
        if idem_count != 1:
            return False, f"Database has {idem_count} idempotency records; expected exactly 1"

        return True, "Passed identical concurrent batch"
    finally:
        cleanup_db(engine, db_path)


def test_concurrent_conflicting_batch(handler: ConcurrentInvoiceHandler, num_workers: int = 10) -> Tuple[bool, str]:
    """Test N simultaneous conflicting requests using the same idempotency key."""
    engine, db_path = init_test_db()
    try:
        key = "test_concurrent_conflict_key"
        barrier = threading.Barrier(num_workers)

        def worker(idx):
            payload = {"customer_name": f"Customer {idx}", "total_amount": f"{100 + idx:.2f}"}
            barrier.wait()
            return handler.process_request(engine, payload, key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker, i) for i in range(num_workers)]
            results = [f.result() for f in futures]

        codes = [r.status_code for r in results]
        if codes.count(201) != 1:
            return False, f"Expected exactly 1 x 201 Winner, got {codes.count(201)} (all codes: {codes})"
        if codes.count(409) != num_workers - 1:
            return False, f"Expected {num_workers - 1} x 409 Conflicts, got {codes.count(409)} (all codes: {codes})"

        Session = sessionmaker(bind=engine)
        s = Session()
        inv_count = s.query(TaskInvoice).count()
        idem_count = s.query(TaskIdempotency).count()
        s.close()

        if inv_count != 1:
            return False, f"Database has {inv_count} invoices; expected exactly 1"
        if idem_count != 1:
            return False, f"Database has {idem_count} idempotency records; expected exactly 1"

        return True, "Passed conflicting concurrent batch"
    finally:
        cleanup_db(engine, db_path)

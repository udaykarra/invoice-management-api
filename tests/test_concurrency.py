"""Comprehensive concurrent idempotency test suite.

Validates:
- 2, 5, 10, and 20 simultaneous identical requests with synchronization barriers.
- 2, 5, 10, and 20 simultaneous conflicting requests with synchronization barriers.
- Exactly one invoice creation for identical requests (1 x 201, (N-1) x 200).
- Exactly one winner and (N-1) x 409 Conflict for conflicting requests.
- Repeated executions to verify absence of intermittent concurrency bugs.
- Original response snapshot preservation across lifecycle state mutations.
- Zero orphan records and complete database integrity.
"""

import concurrent.futures
import threading

import pytest

from app.models import IdempotencyRecord, Invoice


def run_concurrent_requests(client, num_workers, payload_generator, headers_generator):
    """Execute simultaneous requests using ThreadPoolExecutor and threading.Barrier."""
    barrier = threading.Barrier(num_workers)

    def worker(worker_id):
        payload = payload_generator(worker_id)
        headers = headers_generator(worker_id)
        barrier.wait()  # Synchronize all threads to fire at the exact same instant
        return client.post("/invoices/", json=payload, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker, i) for i in range(num_workers)]
        responses = [f.result() for f in futures]

    return responses


@pytest.mark.parametrize("worker_count", [2, 5, 10, 20])
def test_concurrent_identical_requests(client, db_session, worker_count):
    """Verify that N simultaneous identical requests create exactly 1 invoice and 1 idempotency record.

    One worker receives HTTP 201 Created; all others receive HTTP 200 OK with X-Idempotent-Replay: true.
    """
    key = f"concurrent_identical_key_{worker_count}_workers"
    payload = {
        "customer_name": f"Acme Concurrency {worker_count}",
        "customer_email": f"concurrency{worker_count}@acme.com",
        "currency": "USD",
        "tax_rate": "0.0825",
        "items": [
            {"description": "Compute Units", "quantity": 4, "unit_price": "25.00"},
            {"description": "Network Bandwidth", "quantity": 10, "unit_price": "1.50"},
        ],
    }

    responses = run_concurrent_requests(
        client=client,
        num_workers=worker_count,
        payload_generator=lambda idx: payload,
        headers_generator=lambda idx: {"Idempotency-Key": key},
    )

    status_codes = [r.status_code for r in responses]
    assert 201 in status_codes, f"Expected at least one 201 Created among {status_codes}"
    assert status_codes.count(201) == 1, f"Expected exactly one 201 Created, got: {status_codes.count(201)}"

    # All non-201 responses must be 200 OK with the replay header
    replay_responses = [r for r in responses if r.status_code != 201]
    for r in replay_responses:
        assert r.status_code == 200, f"Expected 200 replay, got {r.status_code}: {r.json()}"
        assert r.headers.get("X-Idempotent-Replay") == "true"

    # All responses must return the identical invoice ID and totals
    invoice_ids = {r.json()["id"] for r in responses}
    assert len(invoice_ids) == 1, f"Expected identical invoice ID, got multiple: {invoice_ids}"

    total_amounts = {r.json()["total_amount"] for r in responses}
    assert len(total_amounts) == 1

    # Verify database state: exactly 1 invoice, matching items, exactly 1 idempotency record
    assert db_session.query(Invoice).count() == 1
    assert db_session.query(IdempotencyRecord).filter(IdempotencyRecord.key == key).count() == 1

    invoice = db_session.query(Invoice).first()
    assert invoice is not None
    assert len(invoice.items) == 2


@pytest.mark.parametrize("worker_count", [2, 5, 10, 20])
def test_concurrent_conflicting_requests(client, db_session, worker_count):
    """Verify that N simultaneous conflicting requests using the same key result in exactly 1 winner (201)
    and (N-1) rejections with HTTP 409 Conflict.
    """
    key = f"concurrent_conflict_key_{worker_count}_workers"

    def payload_for(idx):
        return {
            "customer_name": f"Conflicting Customer {idx}",
            "customer_email": f"cust{idx}@example.com",
            "currency": "USD",
            "tax_rate": "0.0500",
            "items": [
                {"description": f"Unique Line Item {idx}", "quantity": idx + 1, "unit_price": f"{10.00 + idx:.2f}"}
            ],
        }

    responses = run_concurrent_requests(
        client=client,
        num_workers=worker_count,
        payload_generator=payload_for,
        headers_generator=lambda idx: {"Idempotency-Key": key},
    )

    status_codes = [r.status_code for r in responses]
    assert status_codes.count(201) == 1, f"Expected exactly one 201 winner, got: {status_codes}"
    assert status_codes.count(409) == worker_count - 1, (
        f"Expected {worker_count - 1} x 409 Conflict, got: {status_codes}"
    )

    for r in responses:
        if r.status_code == 409:
            assert r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
            assert key in r.json()["error"]["message"]

    # Verify database consistency: exactly 1 invoice persisted, matching the single winner
    assert db_session.query(Invoice).count() == 1
    assert db_session.query(IdempotencyRecord).filter(IdempotencyRecord.key == key).count() == 1


def test_concurrency_repeated_execution_detects_no_intermittent_failures(client, db_session):
    """Execute repeated batches of concurrent requests to detect intermittent race conditions or deadlocks."""
    for iteration in range(5):
        key = f"repeated_concurrency_key_iter_{iteration}"
        payload = {
            "customer_name": f"Repeat Corp {iteration}",
            "customer_email": f"repeat{iteration}@corp.com",
            "items": [{"description": "Service", "quantity": 2, "unit_price": "50.00"}],
        }

        responses = run_concurrent_requests(
            client=client,
            num_workers=8,
            payload_generator=lambda idx: payload,
            headers_generator=lambda idx: {"Idempotency-Key": key},
        )

        codes = [r.status_code for r in responses]
        assert codes.count(201) == 1, f"Iteration {iteration}: expected 1 x 201, got {codes}"
        assert codes.count(200) == 7, f"Iteration {iteration}: expected 7 x 200, got {codes}"


def test_idempotency_original_response_snapshot_replay(client, db_session):
    """Verify that replaying an idempotency key returns the exact original response snapshot
    even if the underlying entity status has subsequently changed (e.g. from ISSUED to PAID).
    """
    key = "snapshot_replay_verification_key_001"
    payload = {
        "customer_name": "Snapshot Corp",
        "customer_email": "billing@snapshot.com",
        "currency": "USD",
        "tax_rate": "0.1000",
        "items": [{"description": "Subscription", "quantity": 1, "unit_price": "100.00"}],
    }

    # 1. Create invoice (HTTP 201) -> Initial status is ISSUED
    res1 = client.post("/invoices/", json=payload, headers={"Idempotency-Key": key})
    assert res1.status_code == 201
    inv_data = res1.json()
    inv_id = inv_data["id"]
    assert inv_data["status"] == "ISSUED"

    # 2. Transition invoice to PAID in the database
    pay_res = client.post(f"/invoices/{inv_id}/pay")
    assert pay_res.status_code == 200
    assert pay_res.json()["status"] == "PAID"

    # Verify that querying GET /invoices/{id} reflects the live PAID state
    get_res = client.get(f"/invoices/{inv_id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "PAID"

    # 3. Replay the creation request with the identical key
    # Invariant: Must return the immutable original response snapshot (HTTP 200, status=ISSUED)
    res_replay = client.post("/invoices/", json=payload, headers={"Idempotency-Key": key})
    assert res_replay.status_code == 200
    assert res_replay.headers.get("X-Idempotent-Replay") == "true"
    replay_data = res_replay.json()
    assert replay_data["id"] == inv_id
    assert replay_data["status"] == "ISSUED", (
        "Replayed response must match original creation response snapshot (status ISSUED)"
    )

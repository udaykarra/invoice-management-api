# Task: `invoice_concurrency` (AI Candidate Solution Evaluation Benchmark)

## Overview
This task evaluates AI coding agents and backend engineers on implementing robust concurrent idempotency, race condition mitigation, and transactional safety under high thread contention.

---

## Problem Statement
Implement a concurrent invoice processor that handles simultaneous requests arriving with identical or conflicting payloads using the same `Idempotency-Key`:

1. **Identical Concurrent Payloads**:
   - $N$ simultaneous requests must produce exactly 1 persisted invoice record.
   - Exactly 1 request receives HTTP 201 Created (winner).
   - The remaining $(N-1)$ requests receive HTTP 200 OK (replayed original response).
   - All $N$ responses must return the identical invoice identifier and totals.

2. **Conflicting Concurrent Payloads**:
   - $N$ simultaneous requests with differing payloads sharing the same idempotency key.
   - Exactly 1 request wins and receives HTTP 201 Created.
   - All rival requests receive HTTP 409 Conflict.
   - The database persists only the winner's invoice and idempotency record.

3. **Collision & Deadlock Recovery**:
   - Implement bounded exponential backoff with randomized jitter to handle unique constraint collisions and database write locks without raising unhandled 500 errors.

---

## Precise Acceptance Criteria

| Requirement | Contract Rule |
|---|---|
| **Zero Duplication** | Under high concurrency ($N \ge 10$ threads), at most one invoice record may be created. |
| **Replay Fidelity** | Identical requests must return the original creation response with `X-Idempotent-Replay: true`. |
| **Conflict Detection** | Reusing a key with a mismatched payload hash must return HTTP 409 Conflict. |
| **Crash Prevention** | Database collisions must be cleanly caught and recovered rather than raising unhandled 500 errors. |

---

## Running Verification
```bash
python tasks/invoice_concurrency/verifier.py
```


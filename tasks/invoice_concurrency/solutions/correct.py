"""Authoritative correct candidate solution for invoice_concurrency."""
from tasks.invoice_concurrency.reference import ReferenceConcurrentHandler

handler = ReferenceConcurrentHandler()
process_request = handler.process_request

__all__ = ["ReferenceConcurrentHandler", "handler", "process_request"]


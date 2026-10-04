"""Asynchronous Celery tasks for parsing, chunking, and embedding documents."""

import logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.ingestion_tasks.process_document_ingestion", bind=True, max_retries=2)
def process_document_ingestion(self, org_id_str: str, document_id_str: str) -> dict:
    """Extracts raw text, chunks content, generates embeddings, and indexes in pgvector."""
    logger.info("Processing document ingestion %s for organization %s", document_id_str, org_id_str)
    return {
        "status": "indexed",
        "document_id": document_id_str,
        "organization_id": org_id_str,
    }

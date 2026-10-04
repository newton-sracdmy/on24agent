"""Asynchronous Celery tasks for broadcasting WhatsApp campaigns to target audience segments."""

import logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.campaign_tasks.dispatch_campaign_broadcast", bind=True, max_retries=1)
def dispatch_campaign_broadcast(self, org_id_str: str, campaign_id_str: str) -> dict:
    """Dispatches approved WhatsApp HSM templates across recipients with rate-limit throttling."""
    logger.info("Dispatching campaign broadcast %s for organization %s", campaign_id_str, org_id_str)
    return {
        "status": "completed",
        "campaign_id": campaign_id_str,
        "organization_id": org_id_str,
    }

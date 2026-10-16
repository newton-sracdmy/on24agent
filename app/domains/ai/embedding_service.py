"""Google Gemini text embeddings for pgvector semantic retrieval."""

import asyncio
import logging
import math
from typing import List, Optional

import httpx

from app.config import settings

logger = logging.getLogger("embedding_service")

EMBEDDING_MODEL = "gemini-embedding-001"
# Matches the Vector(1536) column on document_chunks
EMBEDDING_DIMENSIONS = 1536
_BATCH_SIZE = 100
# Model input limit is 2048 tokens; longer text is truncated rather than failing the whole batch
_MAX_INPUT_CHARS = 8000


def _normalize(vector: List[float]) -> List[float]:
    # Gemini only returns unit vectors at full 3072 dims; truncated outputs must be re-normalized
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


_MAX_ATTEMPTS = 3
_MAX_RETRY_DELAY_SECONDS = 20.0


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    """Honor Google's RetryInfo delay when present, else exponential backoff."""
    try:
        for detail in resp.json().get("error", {}).get("details", []):
            delay = detail.get("retryDelay")
            if delay:
                return min(float(delay.rstrip("s")), _MAX_RETRY_DELAY_SECONDS)
    except ValueError:
        pass
    return float(2 ** attempt)


async def _post_with_retry(client: httpx.AsyncClient, url: str, payload: dict) -> httpx.Response:
    for attempt in range(_MAX_ATTEMPTS):
        resp = await client.post(url, json=payload)
        if resp.status_code != 429 and resp.status_code < 500:
            return resp
        if attempt < _MAX_ATTEMPTS - 1:
            delay = _retry_delay(resp, attempt)
            logger.info(f"Gemini embedding HTTP {resp.status_code}; retrying in {delay:.1f}s")
            await asyncio.sleep(delay)
    return resp


async def embed_texts(texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT") -> Optional[List[List[float]]]:
    """Embed texts in order. Returns None if the provider is unavailable so callers can degrade."""
    api_key = settings.GOOGLE_API_KEY
    if not api_key:
        logger.warning("GOOGLE_API_KEY is not configured; skipping embeddings.")
        return None
    if not texts:
        return []

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:batchEmbedContents"
    vectors: List[List[float]] = []
    try:
        async with httpx.AsyncClient(timeout=30.0, headers={"x-goog-api-key": api_key}) as client:
            for start in range(0, len(texts), _BATCH_SIZE):
                batch = texts[start:start + _BATCH_SIZE]
                payload = {
                    "requests": [
                        {
                            "model": f"models/{EMBEDDING_MODEL}",
                            "content": {"parts": [{"text": t[:_MAX_INPUT_CHARS]}]},
                            "taskType": task_type,
                            "outputDimensionality": EMBEDDING_DIMENSIONS,
                        }
                        for t in batch
                    ]
                }
                resp = await _post_with_retry(client, url, payload)
                if resp.status_code != 200:
                    logger.warning(f"Gemini embedding returned HTTP {resp.status_code}: {resp.text[:300]}")
                    return None
                embeddings = resp.json().get("embeddings", [])
                if len(embeddings) != len(batch):
                    logger.warning("Gemini embedding returned an unexpected number of vectors.")
                    return None
                vectors.extend(_normalize(e["values"]) for e in embeddings)
    except Exception as e:
        logger.warning(f"Gemini embedding request failed: {e}")
        return None
    return vectors


async def embed_query(text: str) -> Optional[List[float]]:
    result = await embed_texts([text], task_type="RETRIEVAL_QUERY")
    return result[0] if result else None

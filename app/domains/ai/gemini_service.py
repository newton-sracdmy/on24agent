"""Google Gemini LLM Service for Generative Conversational AI with RAG Grounding."""

import logging
import re
from typing import List, Optional, Tuple
import httpx
from app.config import settings

logger = logging.getLogger("gemini_service")
GEMINI_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash"]


async def generate_gemini_response(
    user_query: str,
    system_prompt: str,
    kb_context: str = "",
    chat_history: Optional[List[dict]] = None,
) -> Optional[str]:
    """Generate intelligent conversational response via Google Gemini with RAG grounding and multi-model fallback."""
    api_key = settings.GOOGLE_API_KEY
    if not api_key:
        logger.warning("GOOGLE_API_KEY is not configured in settings.")
        return None

    # Construct system instruction with RAG grounding
    grounded_instruction = (
        f"{system_prompt}\n\n"
        f"KNOWLEDGE BASE CONTEXT (Always ground your answers in these official facts):\n"
        f"{kb_context if kb_context else 'No relevant knowledge base documents were found for this message.'}\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Be friendly, concise, and helpful.\n"
        f"2. Respond in the same language the user uses (Bengali or English).\n"
        f"3. Strictly follow the prices, policies and facts given in the knowledge context. Never invent prices, "
        f"policies, dates or contact details that are not in it.\n"
        f"4. Keep the response formatted neatly for mobile messaging (WhatsApp/Messenger)."
    )

    contents = []

    # Include recent conversation turns if provided
    if chat_history:
        for turn in chat_history[-4:]:
            role = "user" if turn.get("sender_type") == "contact" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": turn.get("text_content", "")}]
            })

    # Current user query
    contents.append({
        "role": "user",
        "parts": [{"text": user_query}]
    })

    payload = {
        "system_instruction": {
            "parts": [{"text": grounded_instruction}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.6,
            "maxOutputTokens": 600,
        }
    }

    async with httpx.AsyncClient(timeout=12.0, headers={"x-goog-api-key": api_key}) as client:
        for model in GEMINI_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            reply_text = parts[0].get("text", "").strip()
                            logger.info(f"Gemini ({model}) successfully generated response ({len(reply_text)} chars)")
                            return reply_text
                else:
                    logger.warning(f"Google Gemini model {model} returned HTTP {resp.status_code}, trying next model fallback...")
            except Exception as e:
                logger.warning(f"Exception calling Gemini model {model}: {e}, trying next fallback...")

    logger.error("All candidate Gemini models failed to generate a response.")
    return None


NO_KB_ANSWER_MARKER = "[[NO_KB_ANSWER]]"
_NO_KB_ANSWER_RE = re.compile(r"\[\[\s*NO_KB_ANSWER\s*\]\]", re.IGNORECASE)


async def generate_grounded_reply(
    user_query: str,
    system_prompt: str,
    kb_context: str = "",
    chat_history: Optional[List[dict]] = None,
) -> Tuple[Optional[str], Optional[bool]]:
    """Generate a customer reply and report whether the knowledge base covered the question.

    Returns (reply, kb_covered). kb_covered is None when the model is unavailable.
    """
    gap_instruction = (
        f"{system_prompt}\n\n"
        f"KNOWLEDGE GAP REPORTING: If the customer asks something about the business that the knowledge base "
        f"context does not answer, reply helpfully without inventing facts and end your reply with the exact token "
        f"{NO_KB_ANSWER_MARKER}. Do not add the token for greetings, thanks, or small talk."
    )
    reply = await generate_gemini_response(user_query, gap_instruction, kb_context, chat_history)
    if not reply:
        return None, None
    kb_covered = not _NO_KB_ANSWER_RE.search(reply)
    cleaned = _NO_KB_ANSWER_RE.sub("", reply).strip()
    return (cleaned or None), kb_covered

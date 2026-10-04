"""Unit tests for models, UUIDv7 generation, and schema representations."""

from app.common.models import generate_uuid7
from app.constants import ConversationStatus, MessageSenderType
from app.domains.conversations.schemas import MessageCreate


def test_uuid7_generation():
    u1 = generate_uuid7()
    u2 = generate_uuid7()
    assert u1 != u2
    assert u1.version == 7
    assert u2.version == 7


def test_message_create_schema():
    payload = MessageCreate(
        text_content="Hello customer! How can we assist you today?",
    )
    assert payload.text_content == "Hello customer! How can we assist you today?"
    assert payload.content_type == "text"

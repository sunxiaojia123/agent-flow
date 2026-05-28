"""Request/Response Pydantic schemas."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class SaveConversationRequest(BaseModel):
    messages: list[dict] = []
    events: list[dict] = []
    title: str = "新会话"

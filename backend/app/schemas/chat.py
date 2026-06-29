from pydantic import BaseModel
from datetime import datetime


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    tool_calls: list[dict] | None = None


class ConversationOut(BaseModel):
    id: str
    title: str | None
    created_at: datetime
    messages: list[MessageOut] = []

    model_config = {"from_attributes": True}

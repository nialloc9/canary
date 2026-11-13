from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse, ConversationOut, ConversationUpdate
from app.services.chat_service import ChatService
from app.models.conversation import Conversation

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    service = ChatService(db, account_id)
    return await service.chat(request.message, account_id, request.conversation_id, request.stack_id)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.account_id == account_id)
        .order_by(Conversation.created_at.desc())
        .limit(50)
        .options(selectinload(Conversation.messages))
    )
    return result.scalars().all()


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.account_id == account_id,
        )
        .options(selectinload(Conversation.messages))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.account_id == account_id)
        .options(selectinload(Conversation.messages))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title cannot be empty")
    conv.title = title[:255]
    await db.commit()
    return conv


@router.post("/conversations/{conversation_id}/generate-title", response_model=ConversationOut)
async def generate_conversation_title(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    service = ChatService(db, account_id)
    conv = await service.generate_title(conversation_id, account_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.commit()
    return conv

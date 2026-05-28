"""API routes: chat streaming + skill listing."""

import uuid
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.api.schemas import ChatRequest
from app.api.sse import sse_event_generator

router = APIRouter(prefix="/api/v1")


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, req: Request):
    conv_id = request.conversation_id or str(uuid.uuid4())
    graph = req.app.state.graph

    input_state = {
        "messages": [HumanMessage(content=request.message)],
        "conversation_id": conv_id,
        "plan": None,
        "supervisor_decision": None,
        "coordinator_reply": None,
        "final_action": "",
        "popup_message": "",
        "popup_fields": [],
        "card_type": "",
        "card_data": {},
    }

    config = {"configurable": {"thread_id": conv_id}}

    return StreamingResponse(
        sse_event_generator(graph, input_state, config),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conv_id,
        },
    )


@router.get("/skills")
async def list_skills(req: Request):
    registry = req.app.state.skill_registry
    skills = []
    for skill in registry.list_all():
        skills.append({
            "name": skill.name,
            "display_name": skill.display_name,
            "description": skill.description,
            "category": skill.category,
            "api_count": len(skill.apis),
            "apis": [a.name for a in skill.apis],
        })
    return {"skills": skills}


@router.post("/skills/reload")
async def reload_skills(req: Request):
    registry = req.app.state.skill_registry
    registry.reload()
    return {"status": "ok", "count": len(registry.list_all())}

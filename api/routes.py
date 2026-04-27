import uuid
import asyncio
from fastapi import APIRouter, Request
from langchain_core.messages import HumanMessage, ToolMessage

from api.schemas import ChatRequest, ChatResponse, NewSessionResponse

router = APIRouter()

_sessions: dict[str, list] = {}

RESPONSE_TIMEOUT = 75   # per attempt
MAX_RETRIES = 2
MAX_HISTORY = 6
TOOL_RESULT_MAX_CHARS = 300


def _trim(messages: list) -> list:
    recent = messages[-MAX_HISTORY:] if len(messages) > MAX_HISTORY else messages
    result = []
    for m in recent:
        if isinstance(m, ToolMessage):
            content = m.content
            # MCP tools return list[{'type': 'text', 'text': '...'}]; direct tools return str
            if isinstance(content, list):
                text = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            else:
                text = str(content)
            if len(text) > TOOL_RESULT_MAX_CHARS:
                m = m.model_copy(update={"content": text[:TOOL_RESULT_MAX_CHARS] + "…"})
        result.append(m)
    return result


@router.post("/session/new", response_model=NewSessionResponse)
async def new_session():
    session_id = str(uuid.uuid4())
    _sessions[session_id] = []
    return NewSessionResponse(session_id=session_id)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    graph = request.app.state.graph

    if req.session_id not in _sessions:
        _sessions[req.session_id] = []

    _sessions[req.session_id].append(HumanMessage(content=req.message))

    result = None
    reply = None
    for attempt in range(MAX_RETRIES):
        try:
            result = await asyncio.wait_for(
                graph.ainvoke(
                    {"messages": _trim(_sessions[req.session_id])},
                    config={"recursion_limit": 12},
                ),
                timeout=RESPONSE_TIMEOUT,
            )
            break

        except asyncio.TimeoutError:
            reply = "Request timed out. The model may be under load — please try again."
            break

        except Exception as e:
            err = str(e)
            if ("429" in err or "rate_limit" in err.lower()) and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(70)
                continue
            elif "recursion" in err.lower():
                reply = "Agent exceeded maximum steps. Please rephrase your question."
            else:
                reply = f"Something went wrong: {err[:200]}"
            break

    if result is not None:
        _sessions[req.session_id] = result["messages"]
        last = result["messages"][-1]
        reply = last.content if hasattr(last, "content") else str(last)
    elif reply is None:
        reply = "Rate limit reached. Retried but still unavailable — please wait a minute."

    turn = sum(1 for m in _sessions[req.session_id] if isinstance(m, HumanMessage))
    return ChatResponse(session_id=req.session_id, response=reply, turn=turn)


@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"status": "cleared"}


@router.get("/health")
async def health():
    return {"status": "ok"}

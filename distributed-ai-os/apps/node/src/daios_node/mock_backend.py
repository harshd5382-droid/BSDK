"""Mock inference backend for testing without llama.cpp binaries."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/v1", tags=["mock-inference"])


def _mock_models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": "daios-mock-7b",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "daios",
            }
        ],
    }


def _mock_completion(body: dict[str, Any]) -> dict[str, Any]:
    prompt = ""
    messages = body.get("messages", [])
    if messages:
        prompt = messages[-1].get("content", "")
    elif "prompt" in body:
        prompt = body["prompt"]

    text = (
        f"[DAIOS mock inference on distributed cluster] "
        f"Received: {prompt[:200]}"
    )
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "daios-mock-7b"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": max(1, len(prompt.split())),
            "completion_tokens": max(1, len(text.split())),
            "total_tokens": max(2, len(prompt.split()) + len(text.split())),
        },
    }


@router.get("/models")
async def list_models() -> dict[str, Any]:
    return _mock_models()


@router.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    if body.get("stream"):
        async def stream():
            chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": body.get("model", "daios-mock-7b"),
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "[DAIOS mock stream] "},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return JSONResponse(_mock_completion(body))


@router.post("/completions")
async def completions(request: Request) -> JSONResponse:
    body = await request.json()
    result = _mock_completion(body)
    result["object"] = "text_completion"
    result["choices"] = [
        {
            "index": 0,
            "text": result["choices"][0]["message"]["content"],
            "finish_reason": "stop",
        }
    ]
    return JSONResponse(result)

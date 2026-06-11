"""
provider_router_routes.py
=========================
FastAPI routes for the multi-provider LLM router.
Exposes endpoints to:
  - List available external providers
  - Get provider health/status
  - Trigger a GitHub Actions research job
  - Receive research results callback from GitHub Actions
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

# In-memory store for research results (keyed by session_id)
_research_results: Dict[str, Any] = {}


def setup_provider_router_routes():
    router = APIRouter(prefix="/api/providers", tags=["providers"])

    # ──────────────────────────────────────────────────────────────────────────
    # GET /api/providers/status
    # ──────────────────────────────────────────────────────────────────────────
    @router.get("/status")
    def get_provider_status():
        """Return status of all configured external LLM providers."""
        try:
            from src.multi_provider_llm import get_provider_status, get_available_providers
            return {
                "providers": get_provider_status(),
                "available": get_available_providers(),
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"Error getting provider status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ──────────────────────────────────────────────────────────────────────────
    # POST /api/providers/chat
    # ──────────────────────────────────────────────────────────────────────────
    @router.post("/chat")
    async def provider_chat(request: Request):
        """
        Route a chat completion request to the best available free provider.
        Body: { messages: [...], model: str, temperature: float, max_tokens: int }
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        messages = body.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="messages field is required")

        model = body.get("model")
        temperature = float(body.get("temperature", 0.7))
        max_tokens = int(body.get("max_tokens", 4096))
        preferred = body.get("provider")

        try:
            from src.multi_provider_llm import auto_call
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: auto_call(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                    preferred_provider=preferred,
                ),
            )
            return JSONResponse(content=result)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            logger.error(f"Provider chat error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ──────────────────────────────────────────────────────────────────────────
    # POST /api/providers/research/dispatch
    # ──────────────────────────────────────────────────────────────────────────
    @router.post("/research/dispatch")
    async def dispatch_research(request: Request):
        """
        Dispatch a deep-research job to GitHub Actions.
        Body: { query: str, session_id: str }
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        query = body.get("query", "").strip()
        session_id = body.get("session_id", f"hf_{int(time.time())}")

        if not query:
            raise HTTPException(status_code=400, detail="query is required")

        github_token = os.getenv("GITHUB_TOKEN", "")
        github_repo = os.getenv("GITHUB_REPO", "")  # e.g. "absullh997-rgb/odysseus-original-repo"

        if not github_token or not github_repo:
            raise HTTPException(
                status_code=503,
                detail="GITHUB_TOKEN and GITHUB_REPO must be set to dispatch research jobs",
            )

        # Build callback URL (this HF Space's own endpoint)
        space_host = os.getenv("SPACE_HOST", "")
        callback_url = f"https://{space_host}/api/providers/research/callback" if space_host else ""

        # Dispatch via GitHub repository_dispatch
        import httpx
        try:
            r = httpx.post(
                f"https://api.github.com/repos/{github_repo}/dispatches",
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json={
                    "event_type": "run_deep_research",
                    "client_payload": {
                        "query": query,
                        "session_id": session_id,
                        "callback_url": callback_url,
                    },
                },
                timeout=15,
            )
            if r.status_code == 204:
                _research_results[session_id] = {
                    "status": "dispatched",
                    "query": query,
                    "dispatched_at": time.time(),
                }
                return {"status": "dispatched", "session_id": session_id}
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"GitHub dispatch failed: {r.status_code} {r.text[:200]}",
                )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"GitHub API error: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # POST /api/providers/research/callback
    # ──────────────────────────────────────────────────────────────────────────
    @router.post("/research/callback")
    async def research_callback(request: Request):
        """
        Receive research results posted back from GitHub Actions.
        """
        try:
            result = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        session_id = result.get("session_id", "unknown")
        _research_results[session_id] = {
            "status": "completed",
            "result": result,
            "received_at": time.time(),
        }
        logger.info(f"Research callback received for session: {session_id}")
        return {"status": "received", "session_id": session_id}

    # ──────────────────────────────────────────────────────────────────────────
    # GET /api/providers/research/{session_id}
    # ──────────────────────────────────────────────────────────────────────────
    @router.get("/research/{session_id}")
    def get_research_result(session_id: str):
        """Poll for research results by session_id."""
        result = _research_results.get(session_id)
        if not result:
            raise HTTPException(status_code=404, detail="Research session not found")
        return result

    return router

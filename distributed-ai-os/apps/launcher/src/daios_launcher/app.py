"""FastAPI launcher application — control API + dashboard static files."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from daios_launcher.config_gen import StartRequest, build_node_config, write_runtime_config
from daios_launcher.process_manager import LauncherState, ProcessManager, _sanitize_log_text
from daios_launcher.system_info import gather_system_info
from daios_launcher.validation import validate_start_request, wait_for_peer
from daios_protocol.config import NodeRole, PeerConfig

logger = logging.getLogger(__name__)


def _sanitize_start_error(error: str | None) -> str | None:
    if not error:
        return None
    text = _sanitize_log_text(error).strip()
    if "address already in use" in text:
        return "Port already in use — stop the old node and try again."
    if "Failed to connect" in text or "Connection refused" in text:
        return text
    return text or None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str | None = None
    messages: list[ChatMessage] | None = None
    max_tokens: int | None = None
    stream: bool = False


class LauncherApp:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.venv_bin = self.project_root / ".venv" / "bin"
        self.runtime_dir = self.project_root / ".daios-runtime"
        self.dashboard_dist = self.project_root / "apps" / "dashboard" / "dist"
        self.process_manager = ProcessManager(
            project_root=self.project_root,
            venv_bin=self.venv_bin,
            runtime_dir=self.runtime_dir,
        )
        self._http: httpx.AsyncClient | None = None

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        self._http = httpx.AsyncClient(timeout=120.0)
        yield
        self.process_manager.stop_node()
        if self._http:
            await self._http.aclose()

    def create_app(self) -> FastAPI:
        app = FastAPI(
            title="DAIOS Launcher",
            version="0.1.0",
            description="One-click node control for Distributed AI OS",
            lifespan=self.lifespan,
        )

        @app.get("/api/launcher/system")
        async def system():
            return gather_system_info(self.project_root).model_dump()

        @app.get("/api/launcher/status")
        async def status():
            node = self.process_manager.node
            if node:
                node.refresh()
            last_error = _sanitize_start_error(node.last_error) if node else None
            return {
                "launcher": "ok",
                "node_state": node.state.value if node else LauncherState.STOPPED.value,
                "role": node.role if node else None,
                "node_id": node.node_id if node else None,
                "api_port": node.api_port if node else None,
                "uptime_seconds": node.uptime_seconds() if node else 0,
                "last_error": last_error,
            }

        @app.post("/api/launcher/start")
        async def start(req: StartRequest):
            if self.process_manager.node and self.process_manager.node.state == LauncherState.RUNNING:
                raise HTTPException(status_code=409, detail="Node already running")

            validation_error = validate_start_request(req)
            if validation_error:
                raise HTTPException(status_code=400, detail=validation_error)

            peer_config: PeerConfig | None = None
            if req.role in (NodeRole.COORDINATOR, NodeRole.HYBRID) and req.peer_host and req.backend != "mock":
                peer_config = PeerConfig(
                    id="preflight",
                    host=req.peer_host.strip(),
                    rpc_port=req.peer_rpc_port,
                    api_port=req.peer_api_port,
                )
                peer_status = await wait_for_peer(peer_config, timeout=20.0)
                if not peer_status.reachable or peer_status.error:
                    detail = (
                        f"Worker not reachable at {req.peer_host}:{req.peer_rpc_port}. "
                        "On the other PC, open this dashboard → Help another PC → Start Worker, "
                        "then try again."
                    )
                    if peer_status.error:
                        detail += f" ({peer_status.error})"
                    raise HTTPException(status_code=503, detail=detail)

            config = build_node_config(req, project_root=self.project_root)
            config_path = write_runtime_config(config, self.runtime_dir)
            node = self.process_manager.start_node(
                config_path=config_path,
                role=config.role.value,
                node_id=config.node_id,
                api_port=config.network.api_port,
                rpc_port=config.network.rpc_port if config.runs_rpc_server else None,
            )
            if node.state == LauncherState.FAILED:
                raise HTTPException(
                    status_code=500,
                    detail=_sanitize_start_error(node.last_error) or "Start failed",
                )

            if self._http and config.inference.backend != "mock":
                await asyncio.sleep(2.0)
                try:
                    resp = await self._http.get(
                        f"http://127.0.0.1:{node.api_port}/health",
                        timeout=10.0,
                    )
                    health = resp.json()
                    llama_state = health.get("inference", {}).get("llama_server")
                    if config.runs_coordinator and llama_state in ("failed", "stopped"):
                        self.process_manager.stop_node()
                        raise HTTPException(
                            status_code=500,
                            detail=(
                                "llama-server did not start. Ensure the worker PC is running "
                                "and port 50052 is open in its firewall."
                            ),
                        )
                except httpx.HTTPError:
                    pass

            return {
                "status": node.state.value,
                "node_id": node.node_id,
                "role": node.role,
                "config_path": str(config_path),
            }

        @app.post("/api/launcher/stop")
        async def stop():
            self.process_manager.stop_node()
            return {"status": LauncherState.STOPPED.value}

        @app.get("/api/launcher/cluster")
        async def cluster():
            if not self._http:
                raise HTTPException(status_code=503, detail="Launcher not ready")
            api_port = await self._active_api_port()
            try:
                resp = await self._http.get(
                    f"http://127.0.0.1:{api_port}/api/v1/cluster",
                    timeout=5.0,
                )
                return resp.json()
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

        @app.get("/api/launcher/health")
        async def node_health():
            if not self._http:
                raise HTTPException(status_code=503, detail="Launcher not ready")
            api_port = await self._active_api_port()
            try:
                resp = await self._http.get(
                    f"http://127.0.0.1:{api_port}/health",
                    timeout=5.0,
                )
                return resp.json()
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

        @app.get("/api/launcher/logs")
        async def logs_stream():
            node = self.process_manager.node

            async def event_generator():
                last_size = 0
                while True:
                    if node and node._log_path and node._log_path.exists():
                        data = node._log_path.read_bytes()
                        if len(data) > last_size:
                            chunk = data[last_size:].decode("utf-8", errors="replace")
                            for line in chunk.splitlines():
                                if line.strip():
                                    yield f"data: {json.dumps({'line': line})}\n\n"
                            last_size = len(data)
                    await asyncio.sleep(0.5)

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        @app.post("/api/launcher/chat")
        async def chat(req: ChatRequest):
            if not self._http:
                raise HTTPException(status_code=503, detail="Launcher not ready")
            api_port = await self._active_api_port()

            if req.messages:
                messages = [m.model_dump() for m in req.messages]
            elif req.message:
                messages = [{"role": "user", "content": req.message}]
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Provide either message or messages",
                )

            body: dict[str, object] = {
                "model": "daios",
                "messages": messages,
                "stream": req.stream,
            }
            if req.max_tokens is not None:
                body["max_tokens"] = req.max_tokens
            url = f"http://127.0.0.1:{api_port}/v1/chat/completions"

            if req.stream:
                async def stream_proxy():
                    async with self._http.stream("POST", url, json=body) as resp:
                        async for chunk in resp.aiter_bytes():
                            yield chunk

                return StreamingResponse(stream_proxy(), media_type="text/event-stream")

            try:
                resp = await self._http.post(url, json=body)
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

            if resp.headers.get("content-type", "").startswith("application/json"):
                try:
                    content = resp.json()
                except ValueError:
                    content = {"error": resp.text or "Upstream returned invalid JSON"}
            else:
                detail = resp.text.strip() or f"Inference request failed (HTTP {resp.status_code})"
                content = {"error": {"message": detail, "type": "inference_error"}}

            return JSONResponse(content=content, status_code=resp.status_code)

        self._mount_dashboard(app)
        return app

    async def _active_api_port(self) -> int:
        node = self.process_manager.node
        if not node:
            raise HTTPException(status_code=503, detail="Node not running")
        node.refresh()
        if node.state == LauncherState.RUNNING:
            return node.api_port
        if self._http:
            try:
                resp = await self._http.get(
                    f"http://127.0.0.1:{node.api_port}/health",
                    timeout=2.0,
                )
                if resp.status_code == 200:
                    return node.api_port
            except httpx.HTTPError:
                pass
        detail = _sanitize_start_error(node.last_error) or "Node not running"
        raise HTTPException(status_code=503, detail=detail)

    def _mount_dashboard(self, app: FastAPI) -> None:
        dist = self.dashboard_dist
        if not dist.is_dir():
            logger.warning("Dashboard dist not found at %s — API-only mode", dist)
            return

        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            index = dist / "index.html"
            if index.is_file():
                return FileResponse(index)
            raise HTTPException(status_code=404, detail="Dashboard not built")

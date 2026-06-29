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
from daios_launcher.process_manager import LauncherState, ProcessManager
from daios_launcher.system_info import gather_system_info

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    max_tokens: int = 64
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
            return {
                "launcher": "ok",
                "node_state": node.state.value if node else LauncherState.STOPPED.value,
                "role": node.role if node else None,
                "node_id": node.node_id if node else None,
                "api_port": node.api_port if node else None,
                "uptime_seconds": node.uptime_seconds() if node else 0,
                "last_error": node.last_error if node else None,
            }

        @app.post("/api/launcher/start")
        async def start(req: StartRequest):
            if self.process_manager.node and self.process_manager.node.state == LauncherState.RUNNING:
                raise HTTPException(status_code=409, detail="Node already running")

            config = build_node_config(req, project_root=self.project_root)
            config_path = write_runtime_config(config, self.runtime_dir)
            node = self.process_manager.start_node(
                config_path=config_path,
                role=config.role.value,
                node_id=config.node_id,
                api_port=config.network.api_port,
            )
            if node.state == LauncherState.FAILED:
                raise HTTPException(status_code=500, detail=node.last_error or "Start failed")
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
            node = self.process_manager.node
            if not node or node.state != LauncherState.RUNNING:
                raise HTTPException(status_code=503, detail="Node not running")
            if not self._http:
                raise HTTPException(status_code=503, detail="Launcher not ready")
            try:
                resp = await self._http.get(
                    f"http://127.0.0.1:{node.api_port}/api/v1/cluster",
                    timeout=5.0,
                )
                return resp.json()
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

        @app.get("/api/launcher/health")
        async def node_health():
            node = self.process_manager.node
            if not node or node.state != LauncherState.RUNNING:
                raise HTTPException(status_code=503, detail="Node not running")
            if not self._http:
                raise HTTPException(status_code=503, detail="Launcher not ready")
            try:
                resp = await self._http.get(
                    f"http://127.0.0.1:{node.api_port}/health",
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
            node = self.process_manager.node
            if not node or node.state != LauncherState.RUNNING:
                raise HTTPException(status_code=503, detail="Node not running")
            if not self._http:
                raise HTTPException(status_code=503, detail="Launcher not ready")

            body = {
                "model": "daios",
                "messages": [{"role": "user", "content": req.message}],
                "max_tokens": req.max_tokens,
                "stream": req.stream,
            }
            url = f"http://127.0.0.1:{node.api_port}/v1/chat/completions"

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

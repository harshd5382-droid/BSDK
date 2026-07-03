"""FastAPI launcher application — control API + dashboard static files."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from daios_launcher import exe_update, paths
from daios_launcher.artifacts import ArtifactError
from daios_launcher.autostart_windows import install_task, task_installed, uninstall_task
from daios_launcher.config_gen import (
    DEFAULT_CHAT_MAX_TOKENS,
    StartRequest,
    build_node_config,
    write_runtime_config,
)
from daios_launcher.models_manager import (
    delete_model,
    download_model,
    download_state,
    list_models,
)
from daios_launcher.process_manager import LauncherState, ProcessManager, default_venv_bin
from daios_launcher.security import LauncherTokenMiddleware
from daios_launcher.settings import LauncherSettings
from daios_launcher.system_info import gather_system_info
from daios_launcher.update import get_version, pull_latest, reinstall_deps, reexec_launcher
from daios_launcher.validation import validate_start_request, wait_for_peer
from daios_launcher.worker_proxy import (
    forward_worker_launcher,
    get_worker_status as proxy_worker_status,
    start_worker as proxy_start_worker,
    stop_worker as proxy_stop_worker,
    update_worker as proxy_update_worker,
)
from daios_protocol.config import NodeRole, PeerConfig

logger = logging.getLogger(__name__)

# How long chat should wait for the model to finish loading before giving up,
# and how often to re-probe. Distributed model load over the RPC pool can take
# minutes on CPU, so we default to a generous wait instead of failing fast.
_INFERENCE_READY_WAIT_S = float(os.environ.get("DAIOS_INFERENCE_READY_WAIT", "180"))
_INFERENCE_READY_POLL_S = float(os.environ.get("DAIOS_INFERENCE_READY_POLL", "1.0"))


def _sanitize_start_error(error: str | None) -> str | None:
    if not error:
        return None
    from daios_launcher.process_manager import _sanitize_log_text

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


class ModelDownloadRequest(BaseModel):
    url: str | None = None
    hf_repo: str | None = None
    filename: str | None = None


class ModelSelectRequest(BaseModel):
    name: str


class UpdateRequest(BaseModel):
    branch: str | None = None
    reexec: bool = True
    # Exe-based update (frozen worker installs): the coordinator announces the
    # SHA-256 of the exe it serves at /api/launcher/worker-exe. Host defaults to
    # the requesting client (the coordinator that pushed the update).
    exe_sha256: str | None = None
    exe_source_host: str | None = None
    exe_source_port: int | None = None


class AutostartInstallRequest(BaseModel):
    exe_path: str | None = None


class WorkerPauseRequest(BaseModel):
    host: str


class LauncherApp:
    def __init__(
        self,
        project_root: Path,
        *,
        role: Literal["coordinator", "worker"] = "coordinator",
        cluster_token: str | None = None,
        autostart: bool = False,
    ) -> None:
        self.project_root = project_root.resolve()
        self.role = role
        self.cluster_token = cluster_token
        self.autostart = autostart
        self.venv_bin = default_venv_bin(self.project_root)
        self.runtime_dir = self.project_root / ".daios-runtime"
        self.dashboard_dist = self.project_root / "apps" / "dashboard" / "dist"
        self.settings = LauncherSettings.load()
        self.process_manager = ProcessManager(
            project_root=self.project_root,
            venv_bin=self.venv_bin,
            runtime_dir=self.runtime_dir,
        )
        self._http: httpx.AsyncClient | None = None
        self._last_start: StartRequest | None = None

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        self._http = httpx.AsyncClient(timeout=120.0)
        if self.autostart and self.role == "worker":
            await self._autostart_worker()
        yield
        self.process_manager.stop_node()
        if self._http:
            await self._http.aclose()

    async def _autostart_worker(self) -> None:
        from daios_launcher import paths
        from daios_launcher.config_gen import _runtime_binary

        rpc_bin = _runtime_binary(self.project_root, "ggml-rpc-server")
        if not Path(rpc_bin).is_file():
            if paths.is_frozen() or os.environ.get("DAIOS_REQUIRE_REAL_BACKEND") == "1":
                # Production: never silently mock. The installer is responsible for
                # materializing a verified ggml-rpc-server.exe before the service runs.
                logger.error(
                    "Real worker binary missing at %s — refusing to start. The mock "
                    "backend is not a substitute. Re-run the installer to download and "
                    "verify ggml-rpc-server.exe.",
                    rpc_bin,
                )
                return
            logger.warning(
                "ggml-rpc-server not found at %s; starting MOCK worker (dev only — "
                "this is NOT a real worker).",
                rpc_bin,
            )
            backend = "mock"
        else:
            backend = "llama.cpp"
        req = StartRequest(
            role=NodeRole.WORKER,
            backend=backend,
            api_port=8001,
            rpc_port=50052,
            discovery_enabled=True,
        )
        validation_error = validate_start_request(req)
        if validation_error:
            logger.error("Autostart worker validation failed: %s", validation_error)
            return
        config = build_node_config(req, project_root=self.project_root)
        config_path = write_runtime_config(config, self.runtime_dir)
        self._last_start = req
        self.process_manager.start_node(
            config_path=config_path,
            role=config.role.value,
            node_id=config.node_id,
            api_port=config.network.api_port,
            rpc_port=config.network.rpc_port if config.runs_rpc_server else None,
        )

    def create_app(self) -> FastAPI:
        app = FastAPI(
            title="DAIOS Launcher",
            version="0.2.0",
            description="One-click node control for Distributed AI OS",
            lifespan=self.lifespan,
        )

        if self.cluster_token:
            app.add_middleware(LauncherTokenMiddleware, token=self.cluster_token)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/api/launcher/system")
        async def system():
            info = gather_system_info(self.project_root).model_dump()
            info["role"] = self.role
            info["cluster_token"] = self.cluster_token
            info["version"] = get_version(self.project_root).to_dict()
            info["autostart_task"] = task_installed()
            return info

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
                "launcher_role": self.role,
            }

        @app.get("/api/launcher/version")
        async def version():
            info = get_version(self.project_root).to_dict()
            if paths.is_frozen():
                info["exe_sha256"] = await asyncio.to_thread(exe_update.current_exe_sha256)
            return info

        @app.post("/api/launcher/start")
        async def start(req: StartRequest):
            if self.process_manager.node and self.process_manager.node.state == LauncherState.RUNNING:
                raise HTTPException(status_code=409, detail="Node already running")

            validation_error = validate_start_request(req)
            if validation_error:
                raise HTTPException(status_code=400, detail=validation_error)

            # Preflight: probe every manually-entered worker IP (Gen 1). With
            # Auto Discovery we skip this — workers appear via mDNS at runtime.
            if (
                req.role in (NodeRole.COORDINATOR, NodeRole.HYBRID)
                and not req.discovery_enabled
                and req.backend != "mock"
            ):
                for idx, host in enumerate(req.effective_peer_hosts()):
                    peer_config = PeerConfig(
                        id=f"preflight-{idx + 1}",
                        host=host,
                        rpc_port=req.peer_rpc_port,
                        api_port=req.peer_api_port,
                    )
                    peer_status = await wait_for_peer(peer_config, timeout=20.0)
                    if not peer_status.reachable or peer_status.error:
                        detail = (
                            f"Worker not reachable at {host}:{req.peer_rpc_port}. "
                            "On the other PC, open this dashboard → Help another PC → Start Worker, "
                            "then try again."
                        )
                        if peer_status.error:
                            detail += f" ({peer_status.error})"
                        raise HTTPException(status_code=503, detail=detail)

            config = await asyncio.to_thread(
                build_node_config, req, project_root=self.project_root
            )
            config_path = write_runtime_config(config, self.runtime_dir)
            self._last_start = req
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
                # A discovery+distribution coordinator intentionally defers
                # llama-server start until workers are pooled (up to
                # wait_for_workers_seconds). Poll instead of bailing at 2s, so
                # we don't kill a node that is correctly waiting for workers.
                # Only a real "failed" state aborts the start.
                deadline = asyncio.get_event_loop().time() + 35.0
                started_ok = False
                while asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(2.0)
                    try:
                        resp = await self._http.get(
                            f"http://127.0.0.1:{node.api_port}/health",
                            timeout=10.0,
                        )
                        health = resp.json()
                    except httpx.HTTPError:
                        continue
                    inf = health.get("inference", {})
                    llama_state = inf.get("llama_server")
                    pending = inf.get("llama_server_pending", False)
                    if not config.runs_coordinator:
                        started_ok = True
                        break
                    if llama_state == "running":
                        started_ok = True
                        break
                    if llama_state == "failed":
                        self.process_manager.stop_node()
                        raise HTTPException(
                            status_code=500,
                            detail="llama-server failed to start.",
                        )
                    # stopped while pending == still waiting for workers; keep polling.
                    if llama_state == "stopped" and not pending:
                        self.process_manager.stop_node()
                        raise HTTPException(
                            status_code=500,
                            detail=(
                                "llama-server did not start. Ensure the worker PC is running "
                                "and port 50052 is open in its firewall."
                            ),
                        )
                if not started_ok and config.runs_coordinator:
                    # Timed out waiting; the node stays up — the recovery loop
                    # will (re)start llama-server once a worker is discovered.
                    logger.warning(
                        "llama-server not running 35s after start; leaving node up so "
                        "discovery can complete"
                    )

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

        @app.post("/api/launcher/update")
        async def update(req: UpdateRequest, request: Request):
            if paths.is_frozen():
                # Self-contained exe install: no git repo/venv to update. Pull the
                # new exe from the coordinator and relaunch via the installer.
                return await self._exe_self_update(req, request)
            self.process_manager.stop_node()
            pull = pull_latest(self.project_root, branch=req.branch)
            if not pull.ok:
                raise HTTPException(status_code=500, detail="; ".join(pull.messages))
            reinstall = reinstall_deps(self.project_root)
            messages = pull.messages + reinstall.messages
            if not reinstall.ok:
                raise HTTPException(status_code=500, detail="; ".join(messages))
            result = {
                "ok": True,
                "messages": messages,
                "version": pull.version.to_dict() if pull.version else None,
            }
            if req.reexec:
                threading.Timer(
                    1.0,
                    lambda: reexec_launcher(
                        self.project_root,
                        [
                            "--root",
                            str(self.project_root),
                            "--role",
                            self.role,
                            "--token",
                            self.cluster_token or "",
                            "--autostart",
                            "--no-window",
                        ],
                    ),
                ).start()
                result["restarting"] = True
            return result

        @app.post("/api/launcher/autostart/install")
        async def autostart_install(req: AutostartInstallRequest):
            exe = Path(req.exe_path) if req.exe_path else Path(__file__).resolve()
            ok, message = install_task(exe)
            if not ok:
                raise HTTPException(status_code=500, detail=message)
            return {"ok": True, "message": message}

        @app.post("/api/launcher/autostart/uninstall")
        async def autostart_uninstall():
            ok, message = uninstall_task()
            if not ok:
                raise HTTPException(status_code=500, detail=message)
            return {"ok": True, "message": message}

        @app.get("/api/launcher/autostart/status")
        async def autostart_status():
            return {"installed": task_installed()}

        @app.get("/api/launcher/models")
        async def models_list():
            active = self.settings.active_model
            return {"models": list_models(self.project_root / "models", active=active)}

        @app.get("/api/launcher/models/download/status")
        async def models_download_status():
            return download_state.snapshot()

        @app.post("/api/launcher/models/download")
        async def models_download(req: ModelDownloadRequest):
            if not req.url and not req.hf_repo:
                raise HTTPException(status_code=400, detail="Provide url or hf_repo")
            thread = threading.Thread(
                target=download_model,
                kwargs={
                    "project_root": self.project_root,
                    "url": req.url,
                    "hf_repo": req.hf_repo,
                    "filename": req.filename,
                },
                daemon=True,
            )
            thread.start()
            return {"status": "started"}

        @app.post("/api/launcher/models/select")
        async def models_select(req: ModelSelectRequest):
            models_dir = self.project_root / "models"
            path = models_dir / req.name
            if not path.is_file():
                raise HTTPException(status_code=404, detail="Model not found")

            self.settings.active_model = req.name
            self.settings.save()

            if self.process_manager.node and self.process_manager.node.state == LauncherState.RUNNING:
                if self._last_start and self._last_start.role == NodeRole.COORDINATOR:
                    self.process_manager.stop_node()
                    updated = self._last_start.model_copy(update={"model_path": req.name, "backend": "llama.cpp"})
                    config = await asyncio.to_thread(
                        build_node_config, updated, project_root=self.project_root
                    )
                    config_path = write_runtime_config(config, self.runtime_dir)
                    self._last_start = updated
                    self.process_manager.start_node(
                        config_path=config_path,
                        role=config.role.value,
                        node_id=config.node_id,
                        api_port=config.network.api_port,
                        rpc_port=config.network.rpc_port if config.runs_rpc_server else None,
                    )
            return {"active": req.name}

        @app.delete("/api/launcher/models/{name}")
        async def models_delete(name: str):
            try:
                delete_model(self.project_root / "models", name)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            if self.settings.active_model == name:
                self.settings.active_model = None
                self.settings.save()
            return {"deleted": name}

        if self.role == "coordinator":

            @app.get("/api/launcher/workers/{host}/status")
            async def worker_status(host: str, api_port: int = 8001):
                if not self._http:
                    raise HTTPException(status_code=503, detail="Launcher not ready")
                return await proxy_worker_status(
                    self._http, host, self.cluster_token, api_port
                )

            @app.post("/api/launcher/workers/{host}/start")
            async def worker_start(host: str, req: StartRequest):
                if not self._http:
                    raise HTTPException(status_code=503, detail="Launcher not ready")
                return await proxy_start_worker(
                    self._http, host, self.cluster_token, req
                )

            @app.post("/api/launcher/workers/{host}/stop")
            async def worker_stop(host: str):
                if not self._http:
                    raise HTTPException(status_code=503, detail="Launcher not ready")
                return await proxy_stop_worker(self._http, host, self.cluster_token)

            @app.post("/api/launcher/workers/{host}/update")
            async def worker_update(host: str):
                if not self._http:
                    raise HTTPException(status_code=503, detail="Launcher not ready")
                # Announce our exe build (if any) so frozen workers can pull it;
                # git-based workers ignore these fields.
                extra: dict = {}
                exe = exe_update.serveable_worker_exe(self.project_root)
                if exe:
                    info = await asyncio.to_thread(exe_update.exe_info, exe)
                    extra = {
                        "exe_sha256": info["sha256"],
                        "exe_source_port": self.settings.launcher_port,
                    }
                return await proxy_update_worker(
                    self._http, host, self.cluster_token, extra=extra
                )

            @app.get("/api/launcher/workers/{host}/version")
            async def worker_version(host: str):
                if not self._http:
                    raise HTTPException(status_code=503, detail="Launcher not ready")
                return await forward_worker_launcher(
                    self._http, host, self.cluster_token, "GET", "/version"
                )

            @app.get("/api/launcher/worker-exe/info")
            async def worker_exe_info():
                exe = exe_update.serveable_worker_exe(self.project_root)
                if not exe:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            "No worker exe build found (dist/daios-worker.exe). "
                            "Build it with scripts\\windows\\build-exe.ps1."
                        ),
                    )
                info = dict(await asyncio.to_thread(exe_update.exe_info, exe))
                info["path"] = str(exe)
                return info

            @app.get("/api/launcher/worker-exe")
            async def worker_exe_download():
                exe = exe_update.serveable_worker_exe(self.project_root)
                if not exe:
                    raise HTTPException(status_code=404, detail="No worker exe build found")
                return FileResponse(
                    exe,
                    media_type="application/octet-stream",
                    filename="daios-worker.exe",
                )

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

        @app.post("/api/launcher/cluster/workers/pause")
        async def cluster_pause_worker(req: WorkerPauseRequest):
            return await self._forward_node_pause("pause", req.host)

        @app.post("/api/launcher/cluster/workers/resume")
        async def cluster_resume_worker(req: WorkerPauseRequest):
            return await self._forward_node_pause("resume", req.host)

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
            await self._ensure_inference_ready(api_port)

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
                "max_tokens": req.max_tokens if req.max_tokens is not None else DEFAULT_CHAT_MAX_TOKENS,
            }
            url = f"http://127.0.0.1:{api_port}/v1/chat/completions"
            # Distributed model load + first token can take several minutes on CPU.
            chat_timeout = httpx.Timeout(600.0, connect=15.0)

            if req.stream:

                async def stream_proxy():
                    async with self._http.stream(
                        "POST", url, json=body, timeout=chat_timeout
                    ) as resp:
                        if resp.status_code >= 400:
                            detail = (await resp.aread()).decode("utf-8", errors="replace")
                            msg = json.dumps(
                                {
                                    "error": {
                                        "message": detail or f"HTTP {resp.status_code}",
                                        "type": "inference_error",
                                    }
                                }
                            )
                            yield f"data: {msg}\n\n".encode()
                            return
                        async for chunk in resp.aiter_bytes():
                            yield chunk

                return StreamingResponse(stream_proxy(), media_type="text/event-stream")

            try:
                resp = await self._http.post(url, json=body, timeout=chat_timeout)
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

    async def _forward_node_pause(self, action: str, host: str) -> dict:
        """Forward a worker pause/resume to the local coordinator node."""
        if not self._http:
            raise HTTPException(status_code=503, detail="Launcher not ready")
        api_port = await self._active_api_port()
        try:
            resp = await self._http.post(
                f"http://127.0.0.1:{api_port}/api/v1/workers/{action}",
                json={"host": host},
                timeout=60.0,  # resume/pause restarts llama-server (model reload)
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise HTTPException(status_code=resp.status_code, detail=detail)
        return resp.json()

    async def _exe_self_update(self, req: UpdateRequest, request: Request) -> dict:
        """Frozen-install update: pull the new exe from the coordinator and relaunch."""
        if not req.exe_sha256:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This worker is a self-contained exe install; the coordinator has "
                    "no worker exe build to push. On the main PC, build it with "
                    "scripts\\windows\\build-exe.ps1 and try again."
                ),
            )
        current = await asyncio.to_thread(exe_update.current_exe_sha256)
        if current and current.lower() == req.exe_sha256.lower():
            return {"ok": True, "up_to_date": True, "exe_sha256": current}

        source_host = req.exe_source_host or (request.client.host if request.client else None)
        if not source_host:
            raise HTTPException(status_code=400, detail="Cannot determine update source host")
        source_port = req.exe_source_port or 8090

        try:
            staged = await asyncio.to_thread(
                exe_update.download_worker_exe,
                source_host,
                source_port,
                req.exe_sha256,
                self.cluster_token,
            )
        except ArtifactError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        # Respond first, then hand off to the staged installer (which stops this
        # process, swaps the exe atomically, and restarts the service).
        threading.Timer(1.0, lambda: exe_update.spawn_staged_installer(staged)).start()
        return {"ok": True, "restarting": True, "exe_sha256": req.exe_sha256}

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

    async def _ensure_inference_ready(self, api_port: int) -> None:
        """Wait for llama-server to actually serve, not just for the process to be alive.

        The node reports ``llama_server: running`` as soon as the process is
        spawned, but llama-server returns 503 on ``/v1/*`` while the model is
        still loading into memory (which can take minutes over the RPC pool).
        Failing fast here surfaces "loading model" to the chat UI and never
        recovers. Instead we poll the node health and probe llama-server's
        ``/v1/models`` (200 when ready, 503 while loading) up to a bounded
        timeout, so a prompt sent during load just waits and then streams.
        """
        if not self._http:
            raise HTTPException(status_code=503, detail="Launcher not ready")

        deadline = asyncio.get_event_loop().time() + _INFERENCE_READY_WAIT_S
        last_detail: str | None = None
        while True:
            try:
                resp = await self._http.get(
                    f"http://127.0.0.1:{api_port}/health",
                    timeout=5.0,
                )
                health = resp.json()
            except httpx.HTTPError as exc:
                last_detail = f"Node health check failed: {exc}"
                if asyncio.get_event_loop().time() >= deadline:
                    raise HTTPException(status_code=503, detail=last_detail) from exc
                await asyncio.sleep(_INFERENCE_READY_POLL_S)
                continue

            inf = health.get("inference", {})
            state = inf.get("llama_server")
            pending = inf.get("llama_server_pending", False)

            if state == "failed":
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "llama-server failed to load the model. Click Restart on "
                        "the coordinator and check that worker PCs are running."
                    ),
                )

            # Probe llama-server itself: the process can be "running" while the
            # model is still loading. /v1/models returns 200 only when ready.
            ready, probe_detail = await self._probe_llama_ready(api_port)
            if ready and state == "running" and not pending:
                return

            if not ready:
                last_detail = probe_detail or last_detail
            elif pending:
                last_detail = (
                    "Model is still loading across workers (waiting for RPC pool)."
                )

            if asyncio.get_event_loop().time() >= deadline:
                break
            await asyncio.sleep(_INFERENCE_READY_POLL_S)

        raise HTTPException(
            status_code=503,
            detail=(
                last_detail
                or "Model is still loading. Wait a few seconds and try again."
            ),
            headers={"Retry-After": "5"},
        )

    async def _probe_llama_ready(self, api_port: int) -> tuple[bool, str | None]:
        """GET /v1/models through the node proxy. 200 => ready, 503 => loading."""
        if not self._http:
            return False, "Launcher not ready"
        try:
            resp = await self._http.get(
                f"http://127.0.0.1:{api_port}/v1/models",
                timeout=5.0,
            )
        except httpx.HTTPError as exc:
            return False, f"llama-server unreachable: {exc}"
        if resp.status_code == 200:
            return True, None
        if resp.status_code == 503:
            detail = "Model is still loading across workers (waiting for RPC pool)."
            try:
                body = resp.json()
                msg = body.get("error", {}).get("message") if isinstance(body, dict) else None
                if isinstance(msg, str) and msg:
                    detail = f"Model is still loading: {msg}"
            except ValueError:
                pass
            return False, detail
        return False, f"llama-server returned HTTP {resp.status_code}"

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

"""FastAPI application for the DAIOS node daemon."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import psutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from daios_protocol.config import NodeConfig
from daios_protocol.health import ClusterStatus, NodeHealth, ProcessState, ResourceUsage

from daios_node.inference import InferenceManager
from daios_node.mock_backend import router as mock_router
from daios_node.peers import check_all_peers

logger = logging.getLogger(__name__)


def gather_resources() -> ResourceUsage:
    """Snapshot live CPU / RAM usage for this machine.

    ``cpu_percent(interval=None)`` is non-blocking and reports utilization since
    the previous call, so values become meaningful once the dashboard polls
    repeatedly (every couple of seconds).
    """
    mem = psutil.virtual_memory()
    return ResourceUsage(
        cpu_percent=round(psutil.cpu_percent(interval=None), 1),
        cpu_count=psutil.cpu_count(logical=True),
        ram_used_gb=round((mem.total - mem.available) / (1024**3), 2),
        ram_total_gb=round(mem.total / (1024**3), 2),
        ram_percent=mem.percent,
    )


class NodeApp:
    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self.inference = InferenceManager(config)
        self._http_client: httpx.AsyncClient | None = None

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        self.inference.start()
        self._http_client = httpx.AsyncClient(timeout=120.0)
        logger.info(
            "Node %s started (role=%s, backend=%s)",
            self.config.node_id,
            self.config.role.value,
            self.config.inference.backend,
        )
        yield
        if self._http_client:
            await self._http_client.aclose()
        self.inference.stop()
        logger.info("Node %s stopped", self.config.node_id)

    def create_app(self) -> FastAPI:
        app = FastAPI(
            title="Distributed AI OS Node",
            version="0.1.0",
            description="Generation 1 peer node with llama.cpp / GGML RPC integration",
            lifespan=self.lifespan,
        )

        @app.get("/health")
        async def health() -> NodeHealth:
            return NodeHealth(
                node_id=self.config.node_id,
                role=self.config.role.value,
                inference=self.inference.status(),
                uptime_seconds=self.inference.uptime_seconds(),
                resources=gather_resources(),
            )

        @app.get("/metrics")
        async def metrics() -> dict:
            status = self.inference.status()
            peers = await check_all_peers(self.config)
            return {
                "node_id": self.config.node_id,
                "role": self.config.role.value,
                "uptime_seconds": self.inference.uptime_seconds(),
                "inference": status.model_dump(),
                "peers_online": sum(1 for p in peers if p.reachable),
                "peers_total": len(peers),
                "generation": 1,
            }

        @app.get("/api/v1/cluster")
        async def cluster() -> ClusterStatus:
            peers = await check_all_peers(self.config)
            return ClusterStatus(
                coordinator_node_id=self.config.node_id
                if self.config.runs_coordinator
                else "remote",
                peers=peers,
                rpc_endpoints=self.config.rpc_endpoints(),
                local_resources=gather_resources(),
            )

        if self.config.inference.backend == "mock":
            app.include_router(mock_router)
        elif self.config.runs_coordinator:
            self._mount_openai_proxy(app)

        return app

    def _mount_openai_proxy(self, app: FastAPI) -> None:
        base = f"http://127.0.0.1:{self.config.inference.llama_server_port}"

        @app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
        async def proxy_openai(path: str, request: Request):
            if not self._http_client:
                raise HTTPException(status_code=503, detail="Node not ready")

            llama_state = self.inference.status().llama_server
            if llama_state == ProcessState.FAILED:
                err = self.inference.llama_server.last_error if self.inference.llama_server else None
                raise HTTPException(
                    status_code=503,
                    detail=err or "llama-server failed to start",
                )

            url = f"{base}/v1/{path}"
            body = await request.body()
            headers = {
                k: v
                for k, v in request.headers.items()
                if k.lower() not in {"host", "content-length"}
            }

            if self._wants_stream(request, body):
                return await self._proxy_stream(url, headers, body)

            try:
                response = await self._http_client.request(
                    request.method,
                    url,
                    headers=headers,
                    content=body,
                )
            except httpx.ConnectError as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"llama-server unavailable on port {self.config.inference.llama_server_port}: {exc}",
                ) from exc

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type"),
            )

    @staticmethod
    def _wants_stream(request: Request, body: bytes) -> bool:
        if request.headers.get("accept") == "text/event-stream":
            return True
        if not body:
            return False
        try:
            return bool(json.loads(body).get("stream"))
        except (json.JSONDecodeError, AttributeError):
            return False

    async def _proxy_stream(self, url: str, headers: dict, body: bytes) -> StreamingResponse:
        if not self._http_client:
            raise HTTPException(status_code=503, detail="Node not ready")

        llama_state = self.inference.status().llama_server
        if llama_state == ProcessState.FAILED:
            err = self.inference.llama_server.last_error if self.inference.llama_server else None
            raise HTTPException(
                status_code=503,
                detail=err or "llama-server failed to start",
            )

        request = self._http_client.build_request("POST", url, headers=headers, content=body)

        async def event_stream():
            try:
                async with self._http_client.stream(
                    request.method,
                    request.url,
                    headers=request.headers,
                    content=body,
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
            except httpx.ConnectError as exc:
                msg = json.dumps(
                    {"error": {"message": f"llama-server unavailable: {exc}", "type": "inference_error"}}
                )
                yield f"data: {msg}\n\n".encode()

        return StreamingResponse(event_stream(), media_type="text/event-stream")

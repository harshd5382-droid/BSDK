"""FastAPI application for the DAIOS node daemon."""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import psutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from daios_protocol.config import NodeConfig
from daios_protocol.health import ClusterStatus, ModelUsage, NodeHealth, ProcessState, ResourceUsage

from daios_node.inference import InferenceManager
from daios_node.inference_tracker import InferenceTracker
from daios_node.mock_backend import router as mock_router
from daios_node.model_usage import gather_model_usage
from daios_node.peers import check_all_peers, count_inbound_rpc_clients

logger = logging.getLogger(__name__)

_COORDINATOR_PING_TTL = 30.0  # seconds — how long a health ping keeps "connected" alive


def _is_loopback(ip: str) -> bool:
    return ip.startswith("127.") or ip in ("::1", "localhost", "0.0.0.0")


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
        self.inference_tracker = InferenceTracker()
        self._http_client: httpx.AsyncClient | None = None
        self._last_coordinator_ping: float = 0.0
        self._coordinator_ip: str | None = None

    def _local_model_usage(self) -> ModelUsage:
        inbound = (
            count_inbound_rpc_clients(self.config.network.rpc_port)
            if self.config.runs_rpc_server
            else 0
        )
        return gather_model_usage(
            self.config,
            self.inference.status(),
            self.inference_tracker.active,
            inbound,
        )

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
        app.state.inference_tracker = self.inference_tracker

        @app.get("/health")
        async def health(request: Request) -> NodeHealth:
            if self.config.runs_rpc_server:
                client_ip = request.client.host if request.client else None
                if client_ip and not _is_loopback(client_ip):
                    self._last_coordinator_ping = time.monotonic()
                    self._coordinator_ip = client_ip
            return NodeHealth(
                node_id=self.config.node_id,
                role=self.config.role.value,
                inference=self.inference.status(),
                uptime_seconds=self.inference.uptime_seconds(),
                resources=gather_resources(),
                model_usage=self._local_model_usage(),
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
            inbound = (
                count_inbound_rpc_clients(self.config.network.rpc_port)
                if self.config.runs_rpc_server
                else 0
            )
            # If no active RPC connection exists yet, fall back to the health-ping
            # tracker: the coordinator probes our /health endpoint every few seconds
            # while running, so a recent ping means a coordinator is attached.
            coordinator_ip: str | None = None
            if self.config.runs_rpc_server:
                ping_age = time.monotonic() - self._last_coordinator_ping
                if ping_age < _COORDINATOR_PING_TTL:
                    coordinator_ip = self._coordinator_ip
                    inbound = max(inbound, 1)
            return ClusterStatus(
                coordinator_node_id=self.config.node_id
                if self.config.runs_coordinator
                else "remote",
                peers=peers,
                rpc_endpoints=self.config.rpc_endpoints(),
                inbound_rpc_clients=inbound,
                local_resources=gather_resources(),
                local_model_usage=self._local_model_usage(),
                coordinator_ip=coordinator_ip,
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

            self.inference_tracker.begin()
            try:
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
            finally:
                if not self._wants_stream(request, body):
                    self.inference_tracker.end()

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
            finally:
                self.inference_tracker.end()

        return StreamingResponse(event_stream(), media_type="text/event-stream")

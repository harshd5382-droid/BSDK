"""FastAPI application for the DAIOS node daemon."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from daios_protocol.config import NodeConfig
from daios_protocol.health import ClusterStatus, ModelUsage, NodeHealth, ProcessState
from daios_protocol.messages import HeartbeatMessage, LeaveMessage

from daios_node.coordinator import CoordinatorRegistry
from daios_node.discovery import DiscoveryService
from daios_node.inference import InferenceManager
from daios_node.inference_tracker import InferenceTracker
from daios_node.membership import MembershipService
from daios_node.mock_backend import router as mock_router
from daios_node.model_usage import gather_model_usage
from daios_node.peers import check_all_peers, count_inbound_rpc_clients
from daios_node.resources import gather_resources
from daios_node.security import ApiTokenMiddleware, ensure_dev_certs

logger = logging.getLogger(__name__)

_COORDINATOR_PING_TTL = 30.0


def _is_loopback(ip: str) -> bool:
    return ip.startswith("127.") or ip in ("::1", "localhost", "0.0.0.0")


class WorkerPauseRequest(BaseModel):
    host: str


class NodeApp:
    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self.inference = InferenceManager(config)
        self.inference_tracker = InferenceTracker()
        self.discovery = DiscoveryService(config)
        self.coordinator_registry = CoordinatorRegistry(config)
        self.membership = MembershipService(
            config,
            self.discovery,
            self.coordinator_registry,
            model_usage_fn=self._local_model_usage,
        )
        self._http_client: httpx.AsyncClient | None = None
        self._last_coordinator_ping: float = 0.0
        self._coordinator_ip: str | None = None
        self._bg_tasks: list[asyncio.Task] = []
        # Worker hosts temporarily excluded from the RPC pool ("disconnected" in
        # the dashboard). In-memory: a node restart reconnects everyone.
        self._paused_hosts: set[str] = set()

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

    def _sync_inference_peers(self) -> None:
        if not self.config.discovery_enabled:
            return
        hosts = self.membership.get_alive_worker_hosts()
        if hosts:
            self.inference.set_peer_hosts(hosts)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        ensure_dev_certs(self.config)
        self.inference.start()
        self._http_client = httpx.AsyncClient(timeout=120.0)

        if self.config.discovery_enabled:
            discovery_task = asyncio.create_task(self.discovery.run_loop())
            membership_task = asyncio.create_task(self.membership.run())
            self._bg_tasks = [discovery_task, membership_task]

        logger.info(
            "Node %s started (role=%s, backend=%s, discovery=%s)",
            self.config.node_id,
            self.config.role.value,
            self.config.inference.backend,
            self.config.discovery_enabled,
        )
        yield

        self.membership.stop()
        for task in self._bg_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.discovery.stop()
        if self._http_client:
            await self._http_client.aclose()
        self.inference.stop()
        logger.info("Node %s stopped", self.config.node_id)

    def create_app(self) -> FastAPI:
        app = FastAPI(
            title="Distributed AI OS Node",
            version="0.2.0",
            description="DAIOS peer node with llama.cpp / GGML RPC and Generation 2 discovery",
            lifespan=self.lifespan,
        )
        if self.config.security.api_token:
            app.add_middleware(ApiTokenMiddleware, token=self.config.security.api_token)
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
            gen = 2 if self.config.discovery_enabled else 1
            if self.config.discovery_enabled:
                view = self.membership.get_membership_view()
                peers_online = sum(1 for m in view.members if m.node_id != self.config.node_id)
                peers_total = len(view.members) - 1
            else:
                peers = await check_all_peers(self.config)
                peers_online = sum(1 for p in peers if p.reachable)
                peers_total = len(peers)
            return {
                "node_id": self.config.node_id,
                "role": self.config.role.value,
                "uptime_seconds": self.inference.uptime_seconds(),
                "inference": status.model_dump(),
                "peers_online": peers_online,
                "peers_total": peers_total,
                "generation": gen,
                "active_coordinator_leases": len(self.coordinator_registry.active_leases()),
            }

        @app.get("/api/v1/workers/paused")
        async def paused_workers():
            if not self.config.runs_coordinator:
                raise HTTPException(status_code=404, detail="Not a coordinator")
            return {"paused": sorted(self._paused_hosts)}

        @app.post("/api/v1/workers/pause")
        async def pause_worker(req: WorkerPauseRequest):
            if not self.config.runs_coordinator:
                raise HTTPException(status_code=404, detail="Not a coordinator")
            host = req.host.strip().split(":")[0]
            if not host:
                raise HTTPException(status_code=400, detail="host is required")
            self._paused_hosts.add(host)
            self.inference.set_excluded_hosts(self._paused_hosts)
            return {"paused": sorted(self._paused_hosts)}

        @app.post("/api/v1/workers/resume")
        async def resume_worker(req: WorkerPauseRequest):
            if not self.config.runs_coordinator:
                raise HTTPException(status_code=404, detail="Not a coordinator")
            host = req.host.strip().split(":")[0]
            self._paused_hosts.discard(host)
            self.inference.set_excluded_hosts(self._paused_hosts)
            return {"paused": sorted(self._paused_hosts)}

        @app.get("/api/v1/membership")
        async def membership_view():
            if not self.config.discovery_enabled:
                raise HTTPException(status_code=404, detail="Discovery not enabled")
            return self.membership.get_membership_view()

        @app.post("/api/v1/internal/heartbeat")
        async def internal_heartbeat(msg: HeartbeatMessage) -> dict:
            if not self.config.discovery_enabled:
                raise HTTPException(status_code=404, detail="Discovery not enabled")
            resp = await self.membership.handle_heartbeat(msg)
            return resp.model_dump(mode="json")

        @app.post("/api/v1/internal/leave")
        async def internal_leave(msg: LeaveMessage) -> dict:
            if not self.config.discovery_enabled:
                raise HTTPException(status_code=404, detail="Discovery not enabled")
            await self.membership.handle_leave(msg)
            return {"status": "ok"}

        @app.get("/api/v1/cluster")
        async def cluster() -> ClusterStatus:
            inbound = (
                count_inbound_rpc_clients(self.config.network.rpc_port)
                if self.config.runs_rpc_server
                else 0
            )
            coordinator_ip: str | None = None
            if self.config.runs_rpc_server:
                ping_age = time.monotonic() - self._last_coordinator_ping
                if ping_age < _COORDINATOR_PING_TTL:
                    coordinator_ip = self._coordinator_ip
                    inbound = max(inbound, 1)

            if self.config.discovery_enabled:
                self._sync_inference_peers()
                view = self.membership.get_membership_view()
                peers = [
                    {
                        "id": m.node_id,
                        "host": m.host,
                        "rpc_port": m.rpc_port,
                        "reachable": m.status.value in ("alive", "suspect"),
                        "latency_ms": (
                            m.advertisement.rtt_ms.get(self.config.node_id)
                            if m.advertisement
                            else None
                        ),
                        "error": None if m.status.value != "dead" else "unreachable",
                        "resources": m.resources.model_dump() if m.resources else None,
                        "model_usage": m.model_usage.model_dump() if m.model_usage else None,
                    }
                    for m in view.members
                    if m.node_id != self.config.node_id
                ]
                from daios_protocol.health import PeerStatus

                peer_statuses = [PeerStatus.model_validate(p) for p in peers]
                worker_hosts = self.membership.get_alive_worker_hosts()
                rpc_eps = [
                    ep
                    for ep in self.config.rpc_endpoints(worker_hosts or None)
                    if ep.rsplit(":", 1)[0] not in self._paused_hosts
                ]
                return ClusterStatus(
                    coordinator_node_id=self.config.node_id
                    if self.config.runs_coordinator
                    else None,
                    peers=peer_statuses,
                    rpc_endpoints=rpc_eps,
                    inbound_rpc_clients=inbound,
                    generation=2,
                    local_resources=gather_resources(),
                    local_model_usage=self._local_model_usage(),
                    coordinator_ip=coordinator_ip,
                    membership=view,
                    paused_workers=sorted(self._paused_hosts),
                )

            peers = await check_all_peers(self.config)
            return ClusterStatus(
                coordinator_node_id=self.config.node_id
                if self.config.runs_coordinator
                else "remote",
                peers=peers,
                rpc_endpoints=[
                    ep
                    for ep in self.config.rpc_endpoints()
                    if ep.rsplit(":", 1)[0] not in self._paused_hosts
                ],
                inbound_rpc_clients=inbound,
                generation=1,
                local_resources=gather_resources(),
                local_model_usage=self._local_model_usage(),
                coordinator_ip=coordinator_ip,
                paused_workers=sorted(self._paused_hosts),
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

            request_id: str | None = None
            if self.config.discovery_enabled and path == "chat/completions":
                self._sync_inference_peers()
                view = self.membership.get_membership_view()
                # Paused workers stay members but never get placement.
                eligible = [m for m in view.members if m.host not in self._paused_hosts]
                lease = self.coordinator_registry.create_lease(eligible)
                request_id = lease.request_id
                if lease.worker_endpoints:
                    hosts = [ep.rsplit(":", 1)[0] for ep in lease.worker_endpoints]
                    self.inference.set_peer_hosts(hosts)

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
                    return await self._proxy_stream(url, headers, body, request_id)

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
                    if request_id:
                        self.coordinator_registry.complete_lease(request_id)

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

    async def _proxy_stream(
        self, url: str, headers: dict, body: bytes, request_id: str | None = None
    ) -> StreamingResponse:
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
                if request_id:
                    self.coordinator_registry.complete_lease(request_id)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

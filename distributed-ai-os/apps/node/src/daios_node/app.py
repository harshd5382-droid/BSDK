"""FastAPI application for the DAIOS node daemon."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from daios_protocol.config import NodeConfig
from daios_protocol.health import (
    ClusterStatus,
    DistributionDiagnostics,
    ModelUsage,
    NodeCapabilities,
    NodeHealth,
    ProcessState,
)
from daios_protocol.messages import HeartbeatMessage, LeaveMessage

from daios_node.coordinator import CoordinatorRegistry
from daios_node.discovery import DiscoveryService
from daios_node.inference import InferenceManager
from daios_node.inference_tracker import InferenceTracker
from daios_node.membership import MembershipService
from daios_node.mock_backend import router as mock_router
from daios_node.model_usage import gather_model_usage
from daios_node.peers import check_all_peers, count_inbound_rpc_clients
from daios_node.resilience import forward_with_retry
from daios_node.resources import gather_capabilities, gather_resources
from daios_node.security import ApiTokenMiddleware, ensure_dev_certs

logger = logging.getLogger(__name__)

_COORDINATOR_PING_TTL = 30.0
# Bounded retry for transient forward failures while a dropped worker is being
# evicted and llama-server restarts with the remaining topology.
_PROXY_RETRIES = int(os.environ.get("DAIOS_PROXY_RETRIES", "1"))
_PROXY_RETRY_BACKOFF_S = float(os.environ.get("DAIOS_PROXY_RETRY_BACKOFF", "0.5"))


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
            queue_depth_fn=lambda: 0,
            capabilities_fn=self._local_capabilities,
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

    def _local_capabilities(self) -> NodeCapabilities:
        rpc_ready: bool | None = None
        if self.config.runs_rpc_server:
            rpc_ready = self.inference.status().rpc_server == ProcessState.RUNNING
        return gather_capabilities(
            self.config,
            rpc_ready=rpc_ready,
            rpc_devices=self.inference.rpc_server_devices(),
        )

    def _sync_inference_peers(self) -> None:
        if not self.config.discovery_enabled:
            return
        hosts = self.membership.get_alive_worker_hosts()
        if hosts:
            self.inference.set_peer_hosts(hosts)
        view = self.membership.get_membership_view()
        caps: dict[str, NodeCapabilities] = {}
        rtt_by_host: dict[str, float] = {}
        rtt_by_node = self.membership.get_rtt_ms()
        for m in view.members:
            if m.node_id == self.config.node_id:
                continue
            if m.advertisement and m.advertisement.capabilities:
                caps[m.host] = m.advertisement.capabilities
            if m.node_id in rtt_by_node:
                rtt_by_host[m.host] = rtt_by_node[m.node_id]
        if caps:
            self.inference.set_worker_capabilities(caps)
        if rtt_by_host:
            self.inference.set_worker_rtt(rtt_by_host)

    def _distribution_summary(self) -> DistributionDiagnostics | None:
        """Compact distribution view embedded in /api/v1/cluster (dashboard)."""
        if not self.config.runs_coordinator or self.config.inference.backend == "mock":
            return None
        return self.inference.distribution_diagnostics(
            active_requests=self.inference_tracker.active
        )

    def _sync_gen1_peer_capabilities(self, peers: list) -> None:
        caps: dict[str, NodeCapabilities] = {}
        rtt_by_host: dict[str, float] = {}
        for p in peers:
            if getattr(p, "capabilities", None):
                caps[p.host] = p.capabilities
            if getattr(p, "latency_ms", None) is not None:
                rtt_by_host[p.host] = p.latency_ms
        if caps:
            self.inference.set_worker_capabilities(caps)
        if rtt_by_host:
            self.inference.set_worker_rtt(rtt_by_host)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        ensure_dev_certs(self.config)
        self.inference.start()
        self._http_client = httpx.AsyncClient(timeout=120.0)

        if self.config.discovery_enabled:
            discovery_task = asyncio.create_task(self.discovery.run_loop())
            membership_task = asyncio.create_task(self.membership.run())
            self._bg_tasks = [discovery_task, membership_task]
        if self.config.inference.backend != "mock":
            # Handles auto-restart of failed processes and safe, debounced
            # llama-server reloads when the RPC topology changes.
            self._bg_tasks.append(asyncio.create_task(self._inference_recovery_loop()))

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
                capabilities=self._local_capabilities(),
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
                "requests": self.inference_tracker.snapshot(),
            }

        @app.get("/api/v1/distribution")
        async def distribution() -> DistributionDiagnostics:
            """Where model tensors and computation are placed, and why.

            Available on every node: workers report their capabilities and
            RPC readiness; coordinators additionally report the allocation
            plan, effective launch flags, and topology/restart state.
            """
            if self.config.discovery_enabled:
                self._sync_inference_peers()
            return self.inference.distribution_diagnostics(
                active_requests=self.inference_tracker.active,
                local_capabilities=self._local_capabilities(),
            )

        @app.post("/api/v1/inference/reload")
        async def reload_inference():
            """Controlled model reload with the current RPC topology.

            llama.cpp cannot attach RPC devices to an already-loaded model, so
            a worker that joins late requires this (or the automatic stale-
            topology reload). Waits for active requests to drain first.
            """
            if not self.config.runs_coordinator:
                raise HTTPException(status_code=404, detail="Not a coordinator")
            if self.config.inference.backend == "mock":
                return {"restart_state": "idle", "detail": "mock backend has no llama-server"}
            state = self.inference.request_reload()
            return {"restart_state": state}

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

        @app.get("/metrics/prometheus")
        async def metrics_prometheus() -> Response:
            snap = self.inference_tracker.snapshot()
            nid = self.config.node_id
            gen = 2 if self.config.discovery_enabled else 1
            labels = f'{{node="{nid}",role="{self.config.role.value}"}}'

            def metric(name: str, help_: str, kind: str, value: float) -> list[str]:
                return [
                    f"# HELP {name} {help_}",
                    f"# TYPE {name} {kind}",
                    f"{name}{labels} {value}",
                ]

            lines: list[str] = []
            lines += metric("daios_active_requests", "In-flight inference requests",
                            "gauge", snap["active_requests"])
            lines += metric("daios_requests_total", "Completed inference requests",
                            "counter", snap["total_requests"])
            lines += metric("daios_requests_failed_total", "Failed inference requests",
                            "counter", snap["failed_requests"])
            lines += metric("daios_request_latency_ms_avg", "Average request latency (ms)",
                            "gauge", snap["avg_latency_ms"])
            lines += metric("daios_tokens_total", "Total generated tokens",
                            "counter", snap["total_tokens"])
            lines += metric("daios_tokens_per_second", "Generation throughput (tokens/s)",
                            "gauge", snap["tokens_per_second"])
            lines += metric("daios_uptime_seconds", "Node uptime (s)",
                            "gauge", round(self.inference.uptime_seconds(), 1))
            lines += metric("daios_generation", "Active platform generation",
                            "gauge", gen)
            return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

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
                    distribution=self._distribution_summary(),
                )

            peers = await check_all_peers(self.config)
            self._sync_gen1_peer_capabilities(peers)
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
                distribution=self._distribution_summary(),
            )

        if self.config.inference.backend == "mock":
            app.include_router(mock_router)
        elif self.config.runs_coordinator:
            self._mount_openai_proxy(app)

        return app

    async def _inference_recovery_loop(self) -> None:
        while True:
            try:
                if self.config.discovery_enabled:
                    self._sync_inference_peers()
                # Both calls may block (restart backoff, RPC readiness waits);
                # run them off the event loop.
                if self.config.inference.auto_restart:
                    await asyncio.to_thread(self.inference.ensure_running)
                active = max(
                    self.inference_tracker.active,
                    len(self.coordinator_registry.active_leases()),
                )
                await asyncio.to_thread(self.inference.maybe_apply_topology, active)
            except Exception:  # pragma: no cover - safety guard for background task
                logger.exception("Inference recovery loop failed")
            await asyncio.sleep(5.0)

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

            start = self.inference_tracker.begin()
            if self._wants_stream(request, body):
                return await self._proxy_stream(url, headers, body, request_id, start)

            tokens = 0
            failed = False
            try:
                async def _send():
                    return await self._request_with_recovery(
                        request.method, url, headers=headers, content=body
                    )

                async def _on_retry(attempt: int) -> None:
                    logger.warning(
                        "Transient inference failure; retry %d/%d (resyncing peers)",
                        attempt,
                        _PROXY_RETRIES,
                    )
                    if self.config.discovery_enabled:
                        self._sync_inference_peers()

                try:
                    response = await forward_with_retry(
                        _send,
                        retries=_PROXY_RETRIES,
                        is_transient=self._is_transient_failure,
                        on_retry=_on_retry,
                        backoff=_PROXY_RETRY_BACKOFF_S,
                    )
                except httpx.ConnectError as exc:
                    failed = True
                    raise HTTPException(
                        status_code=503,
                        detail=f"llama-server unavailable on port {self.config.inference.llama_server_port}: {exc}",
                        headers={"Retry-After": "2"},
                    ) from exc

                if response.status_code >= 500:
                    failed = True
                else:
                    tokens = self._extract_tokens(response.content)

                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.headers.get("content-type"),
                )
            finally:
                self.inference_tracker.end(start, tokens=tokens, failed=failed)
                if request_id:
                    self.coordinator_registry.complete_lease(request_id)

    @staticmethod
    def _is_transient_failure(result: object) -> bool:
        """True for retryable forward outcomes (connect errors or 5xx responses)."""
        if isinstance(result, httpx.ConnectError):
            return True
        if isinstance(result, Exception):
            return False  # other errors are not retried
        status = getattr(result, "status_code", None)
        return isinstance(status, int) and status >= 500

    @staticmethod
    def _extract_tokens(content: bytes) -> int:
        """Best-effort completion-token count from an OpenAI-style response body."""
        try:
            data = json.loads(content)
            return int((data.get("usage") or {}).get("completion_tokens", 0) or 0)
        except (json.JSONDecodeError, ValueError, AttributeError, TypeError):
            return 0

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
        self,
        url: str,
        headers: dict,
        body: bytes,
        request_id: str | None = None,
        start: float | None = None,
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
            got_first_chunk = False
            failed = False
            try:
                for attempt in range(3):
                    try:
                        async with self._http_client.stream(
                            request.method,
                            request.url,
                            headers=request.headers,
                            content=body,
                        ) as response:
                            async for chunk in response.aiter_bytes():
                                got_first_chunk = True
                                yield chunk
                            return
                    except httpx.ConnectError:
                        if got_first_chunk or attempt >= 2:
                            raise
                        self.inference.ensure_running()
                        await asyncio.sleep(0.25 if attempt == 0 else 0.75)
            except httpx.ConnectError as exc:
                failed = True
                msg = json.dumps(
                    {"error": {"message": f"llama-server unavailable: {exc}", "type": "inference_error"}}
                )
                yield f"data: {msg}\n\n".encode()
            finally:
                self.inference_tracker.end(start, failed=failed)
                if request_id:
                    self.coordinator_registry.complete_lease(request_id)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    async def _request_with_recovery(
        self, method: str, url: str, headers: dict[str, str], content: bytes
    ) -> httpx.Response:
        if not self._http_client:
            raise RuntimeError("Node HTTP client is not initialized")
        last_exc: httpx.ConnectError | None = None
        for attempt in range(3):
            try:
                return await self._http_client.request(method, url, headers=headers, content=content)
            except httpx.ConnectError as exc:
                last_exc = exc
                if attempt >= 2:
                    break
                self.inference.ensure_running()
                await asyncio.sleep(0.25 if attempt == 0 else 0.75)
        assert last_exc is not None
        raise last_exc

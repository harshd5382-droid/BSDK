"""Proxy remote worker control from the coordinator launcher."""

from __future__ import annotations

import httpx
from fastapi import HTTPException

from daios_launcher.config_gen import StartRequest

WORKER_LAUNCHER_PORT = 8090


def _normalize_host(host: str) -> str:
    return host.strip().split(":")[0]


def _launcher_headers(token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-DAIOS-Token"] = token
    return headers


async def fetch_worker_launcher_status(
    http: httpx.AsyncClient,
    host: str,
    token: str | None,
) -> dict | None:
    normalized = _normalize_host(host)
    url = f"http://{normalized}:{WORKER_LAUNCHER_PORT}/api/launcher/status"
    try:
        resp = await http.get(url, headers=_launcher_headers(token), timeout=5.0)
    except (httpx.HTTPError, OSError):
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    data["remote_control"] = "launcher"
    return data


async def fetch_worker_node_status(
    http: httpx.AsyncClient,
    host: str,
    api_port: int,
) -> dict:
    normalized = _normalize_host(host)
    url = f"http://{normalized}:{api_port}/health"
    try:
        resp = await http.get(url, timeout=5.0)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Worker unreachable at {normalized} "
                f"(launcher :{WORKER_LAUNCHER_PORT} down, node :{api_port} — {exc})"
            ),
        ) from exc
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Worker node at {normalized}:{api_port} returned HTTP {resp.status_code}",
        )
    health = resp.json()
    return {
        "launcher": "unavailable",
        "node_state": "running",
        "role": health.get("role"),
        "node_id": health.get("node_id"),
        "api_port": api_port,
        "uptime_seconds": health.get("uptime_seconds", 0),
        "last_error": None,
        "remote_control": "node_only",
    }


async def get_worker_status(
    http: httpx.AsyncClient,
    host: str,
    token: str | None,
    api_port: int = 8001,
) -> dict:
    launcher_status = await fetch_worker_launcher_status(http, host, token)
    if launcher_status is not None:
        return launcher_status
    return await fetch_worker_node_status(http, host, api_port)


async def forward_worker_launcher(
    http: httpx.AsyncClient,
    host: str,
    token: str | None,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    timeout: float = 120.0,
) -> dict:
    normalized = _normalize_host(host)
    url = f"http://{normalized}:{WORKER_LAUNCHER_PORT}/api/launcher{path}"
    try:
        resp = await http.request(
            method,
            url,
            headers=_launcher_headers(token),
            json=json_body,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Worker launcher not reachable at {normalized}:{WORKER_LAUNCHER_PORT}. "
                "On the worker PC, run make dashboard, choose Help another PC → Start Worker, "
                "and keep the dashboard running."
            ),
        ) from exc
    if resp.status_code >= 400:
        try:
            payload = resp.json()
            detail = payload.get("detail", resp.text)
        except ValueError:
            detail = resp.text or resp.reason_phrase
        raise HTTPException(status_code=resp.status_code, detail=detail)
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {"status": "ok"}


async def start_worker(
    http: httpx.AsyncClient,
    host: str,
    token: str | None,
    req: StartRequest,
) -> dict:
    return await forward_worker_launcher(
        http, host, token, "POST", "/start", json_body=req.model_dump(mode="json")
    )


async def stop_worker(http: httpx.AsyncClient, host: str, token: str | None) -> dict:
    return await forward_worker_launcher(http, host, token, "POST", "/stop")


async def update_worker(
    http: httpx.AsyncClient,
    host: str,
    token: str | None,
    extra: dict | None = None,
) -> dict:
    return await forward_worker_launcher(
        http,
        host,
        token,
        "POST",
        "/update",
        json_body={"reexec": True, **(extra or {})},
        timeout=300.0,
    )

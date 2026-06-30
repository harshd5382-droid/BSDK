"""Wire protocol message types for Generation 2 peer communication."""

from __future__ import annotations

from pydantic import BaseModel, Field

from daios_protocol.health import CoordinatorLease, MemberInfo, ResourceAdvertisement


class HeartbeatMessage(BaseModel):
    """Periodic heartbeat from one member to another."""

    sender: MemberInfo
    membership_version: int = 0
    advertisement: ResourceAdvertisement | None = None
    active_leases: list[CoordinatorLease] = Field(default_factory=list)


class LeaveMessage(BaseModel):
    """Graceful leave notification."""

    node_id: str
    membership_version: int = 0


class HeartbeatResponse(BaseModel):
    """Response to a heartbeat."""

    sender: MemberInfo
    membership_version: int = 0
    members: list[MemberInfo] = Field(default_factory=list)

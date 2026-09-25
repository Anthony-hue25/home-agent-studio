"""Explicit physical capability placement for Adaptive Stay.

This supplements PropertyTwin without changing the accepted Gate C domain model.
It answers the question Gate H needs: exactly where is a usable capability located?
"""
from dataclasses import dataclass
from .audit import digest
from .stay import PropertyTwin

PLACEMENT_SCOPES = ("ROOM", "ZONE", "SHARED_SPACE", "PROPERTY")


def _bounded(value, label, maximum=160):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"bounded {label} required")
    return value.strip()


@dataclass(frozen=True)
class CapabilityPlacement:
    placement_id: str
    device_id: str
    capability_ref: str
    scope: str
    subject_id: str
    available: bool = True

    def __post_init__(self):
        object.__setattr__(self, "placement_id", _bounded(self.placement_id, "placement_id"))
        object.__setattr__(self, "device_id", _bounded(self.device_id, "device_id"))
        object.__setattr__(self, "capability_ref", _bounded(self.capability_ref, "capability_ref"))
        if self.scope not in PLACEMENT_SCOPES:
            raise ValueError("unsupported capability placement scope")
        object.__setattr__(self, "subject_id", _bounded(self.subject_id, "subject_id"))
        if type(self.available) is not bool:
            raise ValueError("capability availability must be boolean")


@dataclass(frozen=True)
class PropertyCapabilityMap:
    property_id: str
    version: int
    placements: tuple

    def __post_init__(self):
        object.__setattr__(self, "property_id", _bounded(self.property_id, "property_id"))
        if type(self.version) is not int or self.version < 1:
            raise ValueError("positive capability map version required")
        if type(self.placements) is not tuple or any(type(p) is not CapabilityPlacement for p in self.placements):
            raise ValueError("typed capability placements required")
        ids = tuple(p.placement_id for p in self.placements)
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate capability placement identity")

    @property
    def binding(self):
        return digest((self.property_id, self.version, self.placements))

    def validate_against(self, twin):
        if type(twin) is not PropertyTwin:
            raise ValueError("typed PropertyTwin required")
        if twin.property_id != self.property_id:
            raise ValueError("capability map/property mismatch")
        rooms = set(twin.room_ids)
        zones = set(twin.zone_ids)
        devices = set(twin.device_ids)
        capabilities = set(twin.capability_refs)
        for p in self.placements:
            if p.device_id not in devices:
                raise ValueError("capability placement references unknown device")
            if p.capability_ref not in capabilities:
                raise ValueError("capability placement references unknown capability")
            if p.scope == "ROOM" and p.subject_id not in rooms:
                raise ValueError("ROOM capability placement references unknown room")
            if p.scope == "ZONE" and p.subject_id not in zones:
                raise ValueError("ZONE capability placement references unknown zone")
            if p.scope == "PROPERTY" and p.subject_id != twin.property_id:
                raise ValueError("PROPERTY capability placement requires property_id")
        return self

    def available(self, capability_ref, scope, subject_id):
        return tuple(
            p for p in self.placements
            if p.available
            and p.capability_ref == capability_ref
            and p.scope == scope
            and p.subject_id == subject_id
        )

    def has(self, capability_ref, scope, subject_id):
        return bool(self.available(capability_ref, scope, subject_id))

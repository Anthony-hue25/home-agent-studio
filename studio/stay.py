"""Deterministic Adaptive Stay domain foundation.

Gate C deliberately models property/stay state without AI interpretation or device
orchestration. Persistent property data survives checkout; guest/stay state does not.
"""
from dataclasses import dataclass, replace
from datetime import date
from .audit import digest

PREFERENCE_SCOPES = ("PERSON", "ROOM", "ZONE", "SHARED_SPACE", "PROPERTY", "STAY")
STAY_STATES = ("BOOKED", "ACTIVE")


def _bounded_id(value, label, maximum=120):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"bounded {label} required")
    return value.strip()


def _unique_tuple(values, label):
    if type(values) is not tuple or any(type(v) is not str or not v.strip() for v in values):
        raise ValueError(f"{label} must be a tuple of ids")
    cleaned = tuple(v.strip() for v in values)
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"duplicate {label}")
    return cleaned


@dataclass(frozen=True)
class PropertyProfile:
    property_id: str
    name: str
    shared_space_ids: tuple = ()
    policy_refs: tuple = ()
    owner_preference_refs: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "property_id", _bounded_id(self.property_id, "property_id"))
        object.__setattr__(self, "name", _bounded_id(self.name, "property name", 200))
        object.__setattr__(self, "shared_space_ids", _unique_tuple(self.shared_space_ids, "shared_space_ids"))
        object.__setattr__(self, "policy_refs", _unique_tuple(self.policy_refs, "policy_refs"))
        object.__setattr__(self, "owner_preference_refs", _unique_tuple(self.owner_preference_refs, "owner_preference_refs"))


@dataclass(frozen=True)
class PropertyTwin:
    property_id: str
    room_ids: tuple
    zone_ids: tuple
    room_zone_map: tuple
    device_ids: tuple = ()
    capability_refs: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "property_id", _bounded_id(self.property_id, "property_id"))
        rooms = _unique_tuple(self.room_ids, "room_ids")
        zones = _unique_tuple(self.zone_ids, "zone_ids")
        devices = _unique_tuple(self.device_ids, "device_ids")
        caps = _unique_tuple(self.capability_refs, "capability_refs")
        if type(self.room_zone_map) is not tuple:
            raise ValueError("room_zone_map must be tuple")
        mappings = []
        seen_rooms = set()
        for item in self.room_zone_map:
            if type(item) is not tuple or len(item) != 2:
                raise ValueError("room_zone_map entries must be (room_id, zone_id)")
            room, zone = item
            if room not in rooms or zone not in zones or room in seen_rooms:
                raise ValueError("invalid room/zone topology")
            seen_rooms.add(room)
            mappings.append((room, zone))
        if seen_rooms != set(rooms):
            raise ValueError("every room must map to exactly one zone")
        object.__setattr__(self, "room_ids", rooms)
        object.__setattr__(self, "zone_ids", zones)
        object.__setattr__(self, "room_zone_map", tuple(mappings))
        object.__setattr__(self, "device_ids", devices)
        object.__setattr__(self, "capability_refs", caps)

    def zone_for_room(self, room_id):
        return next((zone for room, zone in self.room_zone_map if room == room_id), None)


@dataclass(frozen=True)
class Guest:
    guest_id: str
    display_name: str
    group_id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "guest_id", _bounded_id(self.guest_id, "guest_id"))
        object.__setattr__(self, "display_name", _bounded_id(self.display_name, "guest display_name", 200))
        if type(self.group_id) is not str or len(self.group_id) > 120:
            raise ValueError("invalid guest group_id")
        object.__setattr__(self, "group_id", self.group_id.strip())


@dataclass(frozen=True)
class RoomAssignment:
    guest_id: str
    room_id: str

    def __post_init__(self):
        object.__setattr__(self, "guest_id", _bounded_id(self.guest_id, "guest_id"))
        object.__setattr__(self, "room_id", _bounded_id(self.room_id, "room_id"))


@dataclass(frozen=True)
class ScopedPreference:
    preference_id: str
    scope: str
    subject_id: str
    preference_ref: str
    value_ref: str
    source: str = "GUEST"

    def __post_init__(self):
        object.__setattr__(self, "preference_id", _bounded_id(self.preference_id, "preference_id"))
        if self.scope not in PREFERENCE_SCOPES:
            raise ValueError("unsupported preference scope")
        object.__setattr__(self, "subject_id", _bounded_id(self.subject_id, "preference subject"))
        object.__setattr__(self, "preference_ref", _bounded_id(self.preference_ref, "preference_ref", 200))
        object.__setattr__(self, "value_ref", _bounded_id(self.value_ref, "value_ref", 200))
        if self.source not in ("GUEST", "HOST", "PROPERTY"):
            raise ValueError("unsupported preference source")


@dataclass(frozen=True)
class StayProfile:
    stay_id: str
    property_id: str
    arrival: str
    departure: str
    guests: tuple
    assignments: tuple
    preferences: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "stay_id", _bounded_id(self.stay_id, "stay_id"))
        object.__setattr__(self, "property_id", _bounded_id(self.property_id, "property_id"))
        try:
            arrival = date.fromisoformat(self.arrival)
            departure = date.fromisoformat(self.departure)
        except (TypeError, ValueError):
            raise ValueError("arrival/departure must be ISO dates") from None
        if arrival >= departure:
            raise ValueError("departure must be after arrival")
        if type(self.guests) is not tuple or not self.guests or any(type(g) is not Guest for g in self.guests):
            raise ValueError("at least one typed Guest required")
        guest_ids = [g.guest_id for g in self.guests]
        if len(guest_ids) != len(set(guest_ids)):
            raise ValueError("duplicate guest identity")
        if type(self.assignments) is not tuple or any(type(a) is not RoomAssignment for a in self.assignments):
            raise ValueError("typed RoomAssignment tuple required")
        assigned = [a.guest_id for a in self.assignments]
        if set(assigned) != set(guest_ids) or len(assigned) != len(set(assigned)):
            raise ValueError("each guest requires exactly one room assignment")
        if type(self.preferences) is not tuple or any(type(p) is not ScopedPreference for p in self.preferences):
            raise ValueError("typed ScopedPreference tuple required")
        pref_ids = [p.preference_id for p in self.preferences]
        if len(pref_ids) != len(set(pref_ids)):
            raise ValueError("duplicate preference identity")


@dataclass(frozen=True)
class StayVersion:
    version: int
    state: str
    profile: StayProfile
    parent_version: object = None

    def __post_init__(self):
        if type(self.version) is not int or self.version < 1:
            raise ValueError("positive stay version required")
        if self.state not in STAY_STATES:
            raise ValueError("unsupported live stay state")
        if type(self.profile) is not StayProfile:
            raise ValueError("typed StayProfile required")
        if self.parent_version is not None and (type(self.parent_version) is not int or self.parent_version < 1):
            raise ValueError("invalid parent stay version")

    @property
    def binding(self):
        return digest((self.version, self.state, self.profile, self.parent_version))


@dataclass(frozen=True)
class CompletedStayReceipt:
    stay_id: str
    property_id: str
    terminal_binding: str
    version_count: int
    guest_count: int
    preference_count: int


class StayStore:
    """Owns persistent property context and at most one temporary live stay."""

    def __init__(self, profile, twin):
        if type(profile) is not PropertyProfile or type(twin) is not PropertyTwin:
            raise ValueError("typed property profile and twin required")
        if profile.property_id != twin.property_id:
            raise ValueError("property profile/twin mismatch")
        self.property_profile = profile
        self.property_twin = twin
        self.current = None
        self._versions = ()
        self.receipts = ()

    def _validate_profile(self, profile):
        if type(profile) is not StayProfile:
            raise ValueError("typed StayProfile required")
        if profile.property_id != self.property_profile.property_id:
            raise ValueError("stay belongs to another property")
        guests = {g.guest_id for g in profile.guests}
        rooms = set(self.property_twin.room_ids)
        zones = set(self.property_twin.zone_ids)
        shared = set(self.property_profile.shared_space_ids)
        for assignment in profile.assignments:
            if assignment.guest_id not in guests or assignment.room_id not in rooms:
                raise ValueError("invalid room assignment for property")
        for pref in profile.preferences:
            if pref.scope == "PERSON" and pref.subject_id not in guests:
                raise ValueError("PERSON preference requires current guest")
            if pref.scope == "ROOM" and pref.subject_id not in rooms:
                raise ValueError("ROOM preference requires property room")
            if pref.scope == "ZONE" and pref.subject_id not in zones:
                raise ValueError("ZONE preference requires property zone")
            if pref.scope == "SHARED_SPACE" and pref.subject_id not in shared:
                raise ValueError("SHARED_SPACE preference requires property shared space")
            if pref.scope == "PROPERTY" and pref.subject_id != self.property_profile.property_id:
                raise ValueError("PROPERTY preference requires this property")
            if pref.scope == "STAY" and pref.subject_id != profile.stay_id:
                raise ValueError("STAY preference requires this stay")
        return profile

    def create(self, profile):
        if self.current is not None:
            raise ValueError("checkout current stay before creating another")
        profile = self._validate_profile(profile)
        self.current = StayVersion(1, "BOOKED", profile)
        self._versions = (self.current,)
        return self.current

    def activate(self):
        if self.current is None or self.current.state != "BOOKED":
            raise ValueError("BOOKED stay required")
        previous = self.current
        self.current = StayVersion(previous.version + 1, "ACTIVE", previous.profile, previous.version)
        self._versions = self._versions + (self.current,)
        return self.current

    def amend(self, *, assignments=None, preferences=None):
        if self.current is None:
            raise ValueError("current stay required")
        profile = self.current.profile
        if assignments is not None:
            if type(assignments) is not tuple:
                raise ValueError("assignments must be tuple")
            profile = replace(profile, assignments=assignments)
        if preferences is not None:
            if type(preferences) is not tuple:
                raise ValueError("preferences must be tuple")
            profile = replace(profile, preferences=preferences)
        profile = self._validate_profile(profile)
        previous = self.current
        self.current = StayVersion(previous.version + 1, previous.state, profile, previous.version)
        self._versions = self._versions + (self.current,)
        return self.current

    @property
    def versions(self):
        return self._versions

    def checkout(self):
        if self.current is None:
            raise ValueError("current stay required")
        terminal = self.current
        profile = terminal.profile
        receipt = CompletedStayReceipt(
            stay_id=profile.stay_id,
            property_id=profile.property_id,
            terminal_binding=terminal.binding,
            version_count=len(self._versions),
            guest_count=len(profile.guests),
            preference_count=len(profile.preferences),
        )
        self.receipts = self.receipts + (receipt,)
        self.current = None
        self._versions = ()
        return receipt

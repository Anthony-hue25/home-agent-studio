"""Deterministic shared-resource model for Adaptive Stay Gate G.

Gate G answers one narrow question: can individually valid stay preferences or
resource requests coexist in the same physical property state?

It does not choose winners, negotiate, schedule, call a model, mutate the stay,
or commit device actions. Those decisions belong to later Dream/orchestration
gates.
"""
from dataclasses import dataclass
from .audit import digest
from .stay import PropertyTwin, StayProfile

THERMAL_PREFERENCE_REF = "pref.thermal.feel"
THERMAL_VALUES = ("thermal.cooler", "thermal.neutral", "thermal.warmer")
HOT_WATER_LEVELS = ("LOW", "MEDIUM", "HIGH")
ASSESSMENT_STATES = ("FEASIBLE", "CONFLICT")

_HOT_WATER_CAPACITY = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_CAPACITY_LEVEL = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}


def _bounded_id(value, label, maximum=160):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"bounded {label} required")
    return value.strip()


def _typed_tuple(values, item_type, label):
    if type(values) is not tuple or any(type(v) is not item_type for v in values):
        raise ValueError(f"typed {label} tuple required")
    return values


@dataclass(frozen=True)
class ClimateDemand:
    preference_id: str
    scope: str
    subject_id: str
    zone_id: str
    value_ref: str

    def __post_init__(self):
        object.__setattr__(self, "preference_id", _bounded_id(self.preference_id, "preference_id"))
        object.__setattr__(self, "scope", _bounded_id(self.scope, "scope", 40))
        object.__setattr__(self, "subject_id", _bounded_id(self.subject_id, "subject_id"))
        object.__setattr__(self, "zone_id", _bounded_id(self.zone_id, "zone_id"))
        if self.value_ref not in THERMAL_VALUES:
            raise ValueError("unsupported thermal value")


@dataclass(frozen=True)
class SharedResourceConflict:
    code: str
    resource_type: str
    resource_id: str
    participants: tuple
    requested_values: tuple

    def __post_init__(self):
        object.__setattr__(self, "code", _bounded_id(self.code, "conflict code"))
        object.__setattr__(self, "resource_type", _bounded_id(self.resource_type, "resource_type"))
        object.__setattr__(self, "resource_id", _bounded_id(self.resource_id, "resource_id"))
        if type(self.participants) is not tuple or len(self.participants) < 2:
            raise ValueError("shared-resource conflict requires at least two participants")
        if any(type(v) is not str or not v.strip() for v in self.participants):
            raise ValueError("bounded conflict participants required")
        if len(self.participants) != len(set(self.participants)):
            raise ValueError("duplicate conflict participants")
        if type(self.requested_values) is not tuple or not self.requested_values:
            raise ValueError("requested_values tuple required")
        if any(type(v) is not str or not v.strip() for v in self.requested_values):
            raise ValueError("bounded requested_values required")


@dataclass(frozen=True)
class HotWaterState:
    level: str

    def __post_init__(self):
        if self.level not in HOT_WATER_LEVELS:
            raise ValueError("hot-water level must be LOW, MEDIUM or HIGH")

    @property
    def available_draws(self):
        return _HOT_WATER_CAPACITY[self.level]


@dataclass(frozen=True)
class HotWaterRequest:
    request_id: str
    subject_id: str

    def __post_init__(self):
        object.__setattr__(self, "request_id", _bounded_id(self.request_id, "hot-water request_id"))
        object.__setattr__(self, "subject_id", _bounded_id(self.subject_id, "hot-water subject_id"))


@dataclass(frozen=True)
class HotWaterAssessment:
    status: str
    available_draws: int
    requested_draws: int
    projected_state: HotWaterState
    conflicts: tuple = ()

    def __post_init__(self):
        if self.status not in ASSESSMENT_STATES:
            raise ValueError("unsupported hot-water assessment state")
        if type(self.available_draws) is not int or self.available_draws < 0:
            raise ValueError("invalid available_draws")
        if type(self.requested_draws) is not int or self.requested_draws < 0:
            raise ValueError("invalid requested_draws")
        if type(self.projected_state) is not HotWaterState:
            raise ValueError("typed projected hot-water state required")
        _typed_tuple(self.conflicts, SharedResourceConflict, "hot-water conflicts")
        if (self.status == "FEASIBLE") != (not self.conflicts):
            raise ValueError("hot-water status/conflict mismatch")


@dataclass(frozen=True)
class SharedResourceAssessment:
    status: str
    climate_demands: tuple
    conflicts: tuple
    hot_water: object = None

    def __post_init__(self):
        if self.status not in ASSESSMENT_STATES:
            raise ValueError("unsupported shared-resource assessment state")
        _typed_tuple(self.climate_demands, ClimateDemand, "climate demands")
        _typed_tuple(self.conflicts, SharedResourceConflict, "shared-resource conflicts")
        if self.hot_water is not None and type(self.hot_water) is not HotWaterAssessment:
            raise ValueError("typed hot-water assessment required")
        if (self.status == "FEASIBLE") != (not self.conflicts):
            raise ValueError("assessment status/conflict mismatch")

    @property
    def binding(self):
        return digest((self.status, self.climate_demands, self.conflicts, self.hot_water))


def _assignment_map(profile):
    return {item.guest_id: item.room_id for item in profile.assignments}


def climate_demands(twin, profile):
    """Translate thermal preferences onto the physical climate zones they consume."""
    if type(twin) is not PropertyTwin or type(profile) is not StayProfile:
        raise ValueError("typed property twin and stay profile required")
    if twin.property_id != profile.property_id:
        raise ValueError("property/stay mismatch")

    assignments = _assignment_map(profile)
    rooms = set(twin.room_ids)
    zones = set(twin.zone_ids)
    if any(room not in rooms for room in assignments.values()):
        raise ValueError("stay assignment references unknown property room")

    demands = []
    for pref in profile.preferences:
        if pref.preference_ref != THERMAL_PREFERENCE_REF:
            continue
        if "climate" not in twin.capability_refs:
            raise ValueError("thermal preference requires climate capability")
        if pref.value_ref not in THERMAL_VALUES:
            raise ValueError("unsupported thermal value")

        if pref.scope == "PERSON":
            room = assignments.get(pref.subject_id)
            if room is None:
                raise ValueError("PERSON thermal preference requires assigned current guest")
            zone_ids = (twin.zone_for_room(room),)
        elif pref.scope == "ROOM":
            if pref.subject_id not in rooms:
                raise ValueError("ROOM thermal preference requires property room")
            zone_ids = (twin.zone_for_room(pref.subject_id),)
        elif pref.scope == "ZONE":
            if pref.subject_id not in zones:
                raise ValueError("ZONE thermal preference requires property zone")
            zone_ids = (pref.subject_id,)
        elif pref.scope == "STAY":
            if pref.subject_id != profile.stay_id:
                raise ValueError("STAY thermal preference requires current stay")
            zone_ids = tuple(sorted(zones))
        else:
            raise ValueError("thermal preference has unsupported shared-resource scope")

        if any(zone is None or zone not in zones for zone in zone_ids):
            raise ValueError("thermal preference cannot resolve physical climate zone")

        for zone_id in zone_ids:
            demands.append(
                ClimateDemand(
                    pref.preference_id,
                    pref.scope,
                    pref.subject_id,
                    zone_id,
                    pref.value_ref,
                )
            )

    return tuple(sorted(
        demands,
        key=lambda d: (d.zone_id, d.preference_id, d.scope, d.subject_id, d.value_ref),
    ))


def assess_climate(twin, profile):
    demands = climate_demands(twin, profile)
    conflicts = []
    for zone_id in sorted(set(d.zone_id for d in demands)):
        zone_demands = tuple(d for d in demands if d.zone_id == zone_id)
        values = tuple(sorted(set(d.value_ref for d in zone_demands)))
        if len(values) <= 1:
            continue
        participants = tuple(sorted(d.preference_id for d in zone_demands))
        conflicts.append(
            SharedResourceConflict(
                "SHARED_CLIMATE_ZONE_CONFLICT",
                "CLIMATE_ZONE",
                zone_id,
                participants,
                values,
            )
        )
    return demands, tuple(conflicts)


def assess_hot_water(state, requests):
    """Assess a simultaneous shower batch without mutating the supplied state."""
    if type(state) is not HotWaterState:
        raise ValueError("typed hot-water state required")
    _typed_tuple(requests, HotWaterRequest, "hot-water requests")
    ids = tuple(r.request_id for r in requests)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate hot-water request identity")

    available = state.available_draws
    requested = len(requests)
    if requested <= available:
        remaining = available - requested
        return HotWaterAssessment(
            "FEASIBLE",
            available,
            requested,
            HotWaterState(_CAPACITY_LEVEL[remaining]),
            (),
        )

    participants = tuple(sorted(r.request_id for r in requests))
    conflict = SharedResourceConflict(
        "SHARED_HOT_WATER_CAPACITY",
        "HOT_WATER",
        "hot-water",
        participants,
        (f"available:{available}", f"requested:{requested}"),
    )
    return HotWaterAssessment(
        "CONFLICT",
        available,
        requested,
        state,
        (conflict,),
    )


def recover_hot_water(state, ticks=1):
    """Pure deterministic recovery: each tick restores one discrete level."""
    if type(state) is not HotWaterState:
        raise ValueError("typed hot-water state required")
    if type(ticks) is not int or ticks < 0:
        raise ValueError("non-negative integer recovery ticks required")
    capacity = min(2, state.available_draws + ticks)
    return HotWaterState(_CAPACITY_LEVEL[capacity])


def assess_shared_resources(
    twin,
    profile,
    *,
    hot_water_state=None,
    hot_water_requests=(),
):
    """Return joint feasibility only; never arbitrate or mutate."""
    demands, conflicts = assess_climate(twin, profile)
    hot_water = None

    if hot_water_state is not None or hot_water_requests:
        if hot_water_state is None:
            raise ValueError("hot-water requests require current hot-water state")
        hot_water = assess_hot_water(hot_water_state, hot_water_requests)
        conflicts = conflicts + hot_water.conflicts

    return SharedResourceAssessment(
        "FEASIBLE" if not conflicts else "CONFLICT",
        demands,
        conflicts,
        hot_water,
    )

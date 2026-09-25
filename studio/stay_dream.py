"""Bounded strategy catalog and deterministic Dream evaluator for Adaptive Stay Gate H.

AI is allowed to select only catalog option references. Dream expands those references
and independently evaluates physical feasibility. No model output can grade itself,
grant authority, mutate live state, or commit a device action.
"""
from dataclasses import dataclass
from itertools import combinations, product
from .audit import digest
from .capability_topology import PropertyCapabilityMap
from .shared_resources import SharedResourceAssessment
from .stay import PropertyTwin, StayVersion

THERMAL_VALUES = ("thermal.cooler", "thermal.neutral", "thermal.warmer")
AIRFLOW_HIGH = "airflow.high"
MAX_OPTIONS = 12


def _bounded(value, label, maximum=180):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"bounded {label} required")
    return value.strip()


@dataclass(frozen=True)
class StrategyPrimitive:
    primitive_ref: str
    kind: str
    target_id: str
    value_ref: str

    def __post_init__(self):
        object.__setattr__(self, "primitive_ref", _bounded(self.primitive_ref, "primitive_ref"))
        if self.kind not in ("ZONE_THERMAL", "ROOM_AIRFLOW", "DEFER_HOT_WATER"):
            raise ValueError("unsupported strategy primitive")
        object.__setattr__(self, "target_id", _bounded(self.target_id, "target_id"))
        object.__setattr__(self, "value_ref", _bounded(self.value_ref, "value_ref"))


@dataclass(frozen=True)
class StrategyOption:
    option_ref: str
    primitive_refs: tuple

    def __post_init__(self):
        object.__setattr__(self, "option_ref", _bounded(self.option_ref, "option_ref"))
        if type(self.primitive_refs) is not tuple:
            raise ValueError("primitive_refs tuple required")
        if any(type(v) is not str or not v for v in self.primitive_refs):
            raise ValueError("bounded primitive refs required")
        if len(self.primitive_refs) != len(set(self.primitive_refs)):
            raise ValueError("duplicate primitive reference")


@dataclass(frozen=True)
class StrategyCatalog:
    primitives: tuple
    options: tuple
    coverage_mode: str = "SYSTEMATIC"
    truncated: bool = False

    def __post_init__(self):
        if type(self.primitives) is not tuple or any(type(v) is not StrategyPrimitive for v in self.primitives):
            raise ValueError("typed strategy primitives required")
        if type(self.options) is not tuple or any(type(v) is not StrategyOption for v in self.options):
            raise ValueError("typed strategy options required")
        if self.coverage_mode != "SYSTEMATIC":
            raise ValueError("Gate H supports SYSTEMATIC bounded strategy coverage")
        if type(self.truncated) is not bool:
            raise ValueError("truncated must be boolean")
        pids = tuple(v.primitive_ref for v in self.primitives)
        oids = tuple(v.option_ref for v in self.options)
        if len(pids) != len(set(pids)) or len(oids) != len(set(oids)):
            raise ValueError("duplicate strategy identity")
        known = set(pids)
        if any(ref not in known for option in self.options for ref in option.primitive_refs):
            raise ValueError("strategy option references unknown primitive")
        if len(self.options) > MAX_OPTIONS:
            raise ValueError("strategy catalog exceeds bounded option limit")

    @property
    def catalog_hash(self):
        return digest(self)

    def primitive(self, ref):
        return next((p for p in self.primitives if p.primitive_ref == ref), None)

    def option(self, ref):
        return next((o for o in self.options if o.option_ref == ref), None)

    def public_view(self):
        return {
            "catalog_hash": self.catalog_hash,
            "coverage_mode": self.coverage_mode,
            "truncated": self.truncated,
            "options": tuple({
                "option_ref": option.option_ref,
                "primitives": tuple({
                    "kind": self.primitive(ref).kind,
                    "target_id": self.primitive(ref).target_id,
                    "value_ref": self.primitive(ref).value_ref,
                } for ref in option.primitive_refs),
            } for option in self.options),
        }


@dataclass(frozen=True)
class DreamEvaluation:
    status: str
    option_ref: str
    context_hash: str
    evidence: tuple
    unresolved: tuple

    def __post_init__(self):
        if self.status not in ("PASS", "FAIL"):
            raise ValueError("Dream status must be PASS or FAIL")
        object.__setattr__(self, "option_ref", _bounded(self.option_ref, "option_ref"))
        object.__setattr__(self, "context_hash", _bounded(self.context_hash, "context_hash"))
        if type(self.evidence) is not tuple or any(type(v) is not str for v in self.evidence):
            raise ValueError("Dream evidence tuple required")
        if type(self.unresolved) is not tuple or any(type(v) is not str for v in self.unresolved):
            raise ValueError("Dream unresolved tuple required")
        if (self.status == "PASS") != (not self.unresolved):
            raise ValueError("Dream status/unresolved mismatch")

    @property
    def binding(self):
        return digest(self)


def _room_for_subject(stay, scope, subject_id):
    assignments = {a.guest_id: a.room_id for a in stay.profile.assignments}
    if scope == "PERSON":
        return assignments.get(subject_id)
    if scope == "ROOM":
        return subject_id
    return None


def _add_primitive(primitives, index, kind, target_id, value_ref):
    key = (kind, target_id, value_ref)
    if key in index:
        return index[key]
    ref = f"P{len(primitives)+1:03d}"
    primitive = StrategyPrimitive(ref, kind, target_id, value_ref)
    primitives.append(primitive)
    index[key] = ref
    return ref


def build_strategy_catalog(twin, topology, stay, assessment, max_options=MAX_OPTIONS):
    """Build a bounded whole-stay strategy catalog.

    Conflict-free demand is planned explicitly as well as conflict resolution. This
    keeps Dream meaningful for ordinary stays and avoids making the product depend on
    a contrived conflict before a Stay Blueprint can exist.
    """
    if type(twin) is not PropertyTwin or type(topology) is not PropertyCapabilityMap:
        raise ValueError("typed physical context required")
    if type(stay) is not StayVersion or type(assessment) is not SharedResourceAssessment:
        raise ValueError("typed stay version and shared-resource assessment required")
    if stay.profile.property_id != twin.property_id:
        raise ValueError("stay/property mismatch")
    topology.validate_against(twin)
    if type(max_options) is not int or not 1 <= max_options <= MAX_OPTIONS:
        raise ValueError("bounded max_options required")

    primitives = []
    index = {}
    components = []

    climate_conflict_zones = {
        c.resource_id
        for c in assessment.conflicts
        if c.code == "SHARED_CLIMATE_ZONE_CONFLICT"
    }

    demands_by_zone = {}
    for demand in assessment.climate_demands:
        demands_by_zone.setdefault(demand.zone_id, []).append(demand)

    for zone_id in sorted(demands_by_zone):
        zone_demands = tuple(demands_by_zone[zone_id])
        if not topology.has("climate", "ZONE", zone_id):
            raise ValueError("thermal demand has no available zone climate control")

        requested_values = tuple(sorted({d.value_ref for d in zone_demands}))
        local_cooler = []
        for demand in zone_demands:
            if demand.value_ref != "thermal.cooler":
                continue
            room_id = _room_for_subject(stay, demand.scope, demand.subject_id)
            if room_id and topology.has("fan", "ROOM", room_id):
                local_cooler.append(
                    _add_primitive(primitives, index, "ROOM_AIRFLOW", room_id, AIRFLOW_HIGH)
                )

        if zone_id not in climate_conflict_zones and len(requested_values) == 1:
            direct = _add_primitive(
                primitives, index, "ZONE_THERMAL", zone_id, requested_values[0]
            )
            components.append(((direct,),))
            continue

        if zone_id not in climate_conflict_zones:
            raise ValueError("inconsistent climate assessment")

        zone_refs = tuple(
            _add_primitive(primitives, index, "ZONE_THERMAL", zone_id, value)
            for value in THERMAL_VALUES
        )
        component = [(ref,) for ref in zone_refs]
        warmer_ref = next(
            ref for ref in zone_refs
            if next(p for p in primitives if p.primitive_ref == ref).value_ref == "thermal.warmer"
        )
        neutral_ref = next(
            ref for ref in zone_refs
            if next(p for p in primitives if p.primitive_ref == ref).value_ref == "thermal.neutral"
        )
        if local_cooler:
            component.append(tuple(dict.fromkeys((warmer_ref, *local_cooler))))
            component.append(tuple(dict.fromkeys((neutral_ref, *local_cooler))))
        components.append(tuple(component))

    if assessment.hot_water is not None and assessment.hot_water.status == "CONFLICT":
        requests = tuple(sorted(
            r for c in assessment.hot_water.conflicts for r in c.participants
        ))
        required_deferrals = max(
            1,
            assessment.hot_water.requested_draws - assessment.hot_water.available_draws,
        )
        refs = {
            request_id: _add_primitive(
                primitives, index, "DEFER_HOT_WATER", request_id, "defer"
            )
            for request_id in requests
        }
        component = tuple(
            tuple(refs[r] for r in group)
            for group in combinations(requests, min(required_deferrals, len(requests)))
        )
        if not component:
            raise ValueError("hot-water conflict produced no bounded strategy")
        components.append(component)

    if not components:
        option_sets = [()]
    else:
        option_sets = []
        for combo in product(*components):
            merged = tuple(dict.fromkeys(ref for part in combo for ref in part))
            option_sets.append(merged)

    option_sets = sorted(set(option_sets))
    truncated = len(option_sets) > max_options
    option_sets = option_sets[:max_options]
    options = tuple(
        StrategyOption(f"O{i+1:03d}", refs)
        for i, refs in enumerate(option_sets)
    )
    return StrategyCatalog(tuple(primitives), options, "SYSTEMATIC", truncated)


def _context_hash(twin, topology, stay, assessment, catalog):
    return digest((
        twin,
        topology.binding,
        stay.binding,
        assessment.binding,
        catalog.catalog_hash,
    ))


def evaluate_option(twin, topology, stay, assessment, catalog, option_ref):
    if type(catalog) is not StrategyCatalog:
        raise ValueError("typed StrategyCatalog required")
    option = catalog.option(option_ref)
    if option is None:
        raise ValueError("unknown strategy option reference")
    topology.validate_against(twin)

    zone_settings = {}
    airflow_high_rooms = set()
    deferred = set()
    evidence = []
    unresolved = []

    for ref in option.primitive_refs:
        primitive = catalog.primitive(ref)
        if primitive.kind == "ZONE_THERMAL":
            if not topology.has("climate", "ZONE", primitive.target_id):
                unresolved.append(f"CAPABILITY_UNAVAILABLE:{ref}")
                continue
            prior = zone_settings.get(primitive.target_id)
            if prior is not None and prior != primitive.value_ref:
                unresolved.append(f"CONFLICTING_ZONE_PRIMITIVES:{primitive.target_id}")
            zone_settings[primitive.target_id] = primitive.value_ref
        elif primitive.kind == "ROOM_AIRFLOW":
            if not topology.has("fan", "ROOM", primitive.target_id):
                unresolved.append(f"CAPABILITY_UNAVAILABLE:{ref}")
                continue
            if primitive.value_ref == AIRFLOW_HIGH:
                airflow_high_rooms.add(primitive.target_id)
        elif primitive.kind == "DEFER_HOT_WATER":
            deferred.add(primitive.target_id)

    for demand in assessment.climate_demands:
        zone_value = zone_settings.get(demand.zone_id)
        room_id = _room_for_subject(stay, demand.scope, demand.subject_id)
        satisfied = zone_value == demand.value_ref
        if not satisfied and demand.value_ref == "thermal.cooler" and room_id in airflow_high_rooms:
            satisfied = True
        if satisfied:
            evidence.append(f"THERMAL_SATISFIED:{demand.preference_id}")
        else:
            unresolved.append(f"THERMAL_UNRESOLVED:{demand.preference_id}")

    if assessment.hot_water is not None:
        active_draws = assessment.hot_water.requested_draws - len(deferred)
        if active_draws <= assessment.hot_water.available_draws:
            evidence.append("HOT_WATER_CAPACITY_RESOLVED")
        else:
            unresolved.append("HOT_WATER_CAPACITY_UNRESOLVED")

    unresolved = tuple(sorted(set(unresolved)))
    evidence = tuple(sorted(set(evidence)))
    status = "PASS" if not unresolved else "FAIL"
    return DreamEvaluation(
        status,
        option.option_ref,
        _context_hash(twin, topology, stay, assessment, catalog),
        evidence,
        unresolved,
    )

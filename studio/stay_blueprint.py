"""Immutable Stay Blueprint and asynchronous Dream job seam for Gate H."""
from dataclasses import dataclass, replace
from .audit import digest
from .capability_topology import PropertyCapabilityMap
from .shared_resources import SharedResourceAssessment
from .stay import PropertyTwin, StayVersion
from .stay_dream import DreamEvaluation, StrategyCatalog, StrategyOption

JOB_STATES = ("REQUESTED", "RUNNING", "READY", "FAILED")


def _bounded(value, label, maximum=200):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"bounded {label} required")
    return value.strip()


@dataclass(frozen=True)
class StayBlueprint:
    blueprint_id: str
    property_id: str
    stay_id: str
    stay_version: int
    property_twin_hash: str
    capability_map_hash: str
    resource_snapshot_hash: str
    strategy_catalog_hash: str
    option_ref: str
    option_hash: str
    dream_binding: str
    evidence: tuple
    status: str = "PROPOSED"

    def __post_init__(self):
        for field, label in (
            (self.blueprint_id, "blueprint_id"),
            (self.property_id, "property_id"),
            (self.stay_id, "stay_id"),
            (self.property_twin_hash, "property_twin_hash"),
            (self.capability_map_hash, "capability_map_hash"),
            (self.resource_snapshot_hash, "resource_snapshot_hash"),
            (self.strategy_catalog_hash, "strategy_catalog_hash"),
            (self.option_ref, "option_ref"),
            (self.option_hash, "option_hash"),
            (self.dream_binding, "dream_binding"),
        ):
            _bounded(field, label)
        if type(self.stay_version) is not int or self.stay_version < 1:
            raise ValueError("positive stay_version required")
        if self.status != "PROPOSED":
            raise ValueError("Gate H creates PROPOSED blueprints only")
        if type(self.evidence) is not tuple or any(type(v) is not str for v in self.evidence):
            raise ValueError("blueprint evidence tuple required")

    @property
    def binding(self):
        return digest(self)


def create_blueprint(blueprint_id, twin, topology, stay, assessment, catalog, option, dream):
    if type(twin) is not PropertyTwin or type(topology) is not PropertyCapabilityMap:
        raise ValueError("typed physical context required")
    if type(stay) is not StayVersion or type(assessment) is not SharedResourceAssessment:
        raise ValueError("typed stay/resource context required")
    if type(catalog) is not StrategyCatalog or type(option) is not StrategyOption:
        raise ValueError("typed strategy context required")
    if type(dream) is not DreamEvaluation:
        raise ValueError("typed Dream evaluation required")
    if dream.status != "PASS" or dream.option_ref != option.option_ref:
        raise ValueError("only independently Dream-PASS option may become a blueprint")
    if catalog.option(option.option_ref) != option:
        raise ValueError("option does not belong to supplied strategy catalog")

    return StayBlueprint(
        _bounded(blueprint_id, "blueprint_id"),
        twin.property_id,
        stay.profile.stay_id,
        stay.version,
        digest(twin),
        topology.binding,
        assessment.binding,
        catalog.catalog_hash,
        option.option_ref,
        digest(option),
        dream.binding,
        dream.evidence,
    )


def is_blueprint_current(blueprint, twin, topology, stay, assessment, catalog):
    if type(blueprint) is not StayBlueprint:
        raise ValueError("typed StayBlueprint required")
    if type(stay) is not StayVersion:
        raise ValueError("typed StayVersion required")
    return (
        blueprint.property_id == twin.property_id
        and blueprint.stay_id == stay.profile.stay_id
        and blueprint.stay_version == stay.version
        and blueprint.property_twin_hash == digest(twin)
        and blueprint.capability_map_hash == topology.binding
        and blueprint.resource_snapshot_hash == assessment.binding
        and blueprint.strategy_catalog_hash == catalog.catalog_hash
    )


@dataclass(frozen=True)
class DreamJob:
    job_id: str
    context_hash: str
    status: str = "REQUESTED"
    blueprint_binding: str = ""
    error_code: str = ""

    def __post_init__(self):
        object.__setattr__(self, "job_id", _bounded(self.job_id, "job_id"))
        object.__setattr__(self, "context_hash", _bounded(self.context_hash, "context_hash"))
        if self.status not in JOB_STATES:
            raise ValueError("unsupported Dream job state")
        if type(self.blueprint_binding) is not str or type(self.error_code) is not str:
            raise ValueError("invalid Dream job metadata")
        if self.status == "READY" and not self.blueprint_binding:
            raise ValueError("READY Dream job requires blueprint binding")
        if self.status == "FAILED" and not self.error_code:
            raise ValueError("FAILED Dream job requires error code")


class DreamJobStore:
    """In-memory Gate H state machine; persistence/worker deployment belongs to Gate J."""

    def __init__(self):
        self._jobs = {}

    def request(self, job_id, context_hash):
        if job_id in self._jobs:
            raise ValueError("duplicate Dream job identity")
        job = DreamJob(job_id, context_hash)
        self._jobs[job_id] = job
        return job

    def get(self, job_id):
        return self._jobs.get(job_id)

    def start(self, job_id):
        job = self._require(job_id, "REQUESTED")
        job = replace(job, status="RUNNING")
        self._jobs[job_id] = job
        return job

    def complete(self, job_id, blueprint):
        job = self._require(job_id, "RUNNING")
        if type(blueprint) is not StayBlueprint:
            raise ValueError("typed StayBlueprint required")
        job = replace(job, status="READY", blueprint_binding=blueprint.binding)
        self._jobs[job_id] = job
        return job

    def fail(self, job_id, error_code):
        job = self._require(job_id, "RUNNING")
        job = replace(job, status="FAILED", error_code=_bounded(error_code, "error_code"))
        self._jobs[job_id] = job
        return job

    def _require(self, job_id, state):
        job = self._jobs.get(job_id)
        if job is None:
            raise ValueError("unknown Dream job")
        if job.status != state:
            raise ValueError("invalid Dream job transition")
        return job

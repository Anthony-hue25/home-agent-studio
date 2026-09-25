"""Gate J2 -- minimal deterministic simulated Home State Gateway.

This is the execution/readback boundary for Stay Blueprint activation. It
never trusts its own write: `apply_and_verify()` commits an authorized
configuration into an isolated simulated physical-state store, then
performs a completely separate read of that same store and deterministically
compares it, primitive by primitive, against the exact configuration that
was meant to be applied. Only an exact match returns VERIFIED_ACTIVE;
anything else fails closed (READBACK_MISMATCH) rather than reporting
success. Re-applying the same configuration is last-value-wins per target,
so repeated activation of the same Blueprint produces no duplicate physical
effect and still verifies.

This module knows nothing about Strands, Bedrock, MCP, or guest data --
it only ever sees the small (kind, target_id, value_ref) primitives a
Blueprint's authorized strategy option already carries.
"""
from dataclasses import dataclass


def _bounded(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(f"bounded {label} required")
    return value


@dataclass(frozen=True)
class GatewayPrimitive:
    kind: str
    target_id: str
    value_ref: str

    def __post_init__(self):
        object.__setattr__(self, "kind", _bounded(self.kind, "kind"))
        object.__setattr__(self, "target_id", _bounded(self.target_id, "target_id"))
        object.__setattr__(self, "value_ref", _bounded(self.value_ref, "value_ref"))

    @property
    def key(self):
        return (self.kind, self.target_id)


class SimulatedHomeStateGateway:
    """One isolated simulated physical-state boundary per property/session.

    `apply_and_verify` is the whole contract: give it the blueprint's
    binding (used only as an idempotency/audit key, never trusted as proof
    of anything by itself) and the exact authorized primitives, and it
    returns a (status, detail) pair. status is either "VERIFIED_ACTIVE"
    (readback matched exactly) or "READBACK_MISMATCH" (it did not --
    callers must treat this as activation having failed, never as success).
    """

    def __init__(self):
        self._physical_state = {}
        self._applied_blueprint_bindings = {}

    def _write_physical_state(self, primitives):
        for primitive in primitives:
            self._physical_state[primitive.key] = primitive.value_ref

    def _read_physical_state(self, keys):
        # Deliberately a fresh dict-comprehension lookup against the store,
        # never a reuse of anything the caller already holds in memory, so
        # this is a real independent read rather than an echo of the write.
        return {key: self._physical_state.get(key) for key in keys}

    def apply_and_verify(self, blueprint_binding, primitives):
        blueprint_binding = _bounded(blueprint_binding, "blueprint_binding")
        primitives = tuple(primitives)
        # An option with zero primitives (a smooth stay needing no device
        # change) is a legitimate authorized configuration: applying and
        # reading back "no changes" is trivially an exact match, and it
        # still records a real (vacuous) verification rather than being
        # rejected outright.
        if any(type(p) is not GatewayPrimitive for p in primitives):
            raise ValueError("typed GatewayPrimitive required")
        if len({p.key for p in primitives}) != len(primitives):
            raise ValueError("duplicate gateway primitive target in one activation")

        expected = {p.key: p.value_ref for p in primitives}
        self._write_physical_state(primitives)
        actual = self._read_physical_state(expected.keys())

        match = actual == expected
        detail = {
            "primitive_count": len(primitives),
            "readback_match": match,
        }

        if not match:
            return "READBACK_MISMATCH", detail

        self._applied_blueprint_bindings[blueprint_binding] = expected
        return "VERIFIED_ACTIVE", detail

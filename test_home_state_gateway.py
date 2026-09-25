#!/usr/bin/env python3
"""
Gate J2 -- Home State Gateway apply/readback/verify tests.

Pure logic, no server/AWS/Strands needed. Run directly with:
    python3 test_home_state_gateway.py
"""
import sys
import os


from studio.home_state_gateway import GatewayPrimitive, SimulatedHomeStateGateway

ok = True


def check(label, cond, extra=""):
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"[{status}] {label} {extra}")


PRIMITIVES = (
    GatewayPrimitive("ZONE_THERMAL", "zone-a", "thermal.cooler"),
    GatewayPrimitive("ROOM_AIRFLOW", "bedroom-1", "airflow.high"),
)

# --- 1. Normal apply/readback match -> VERIFIED_ACTIVE ----------------------
gw = SimulatedHomeStateGateway()
status, detail = gw.apply_and_verify("bp-binding-1", PRIMITIVES)
check("normal apply/readback match -> VERIFIED_ACTIVE", status == "VERIFIED_ACTIVE", str((status, detail)))
check("readback_match flag true", detail.get("readback_match") is True)
check("primitive_count recorded", detail.get("primitive_count") == 2, str(detail))
check("physical state actually holds the applied values",
      gw._physical_state[("ZONE_THERMAL", "zone-a")] == "thermal.cooler"
      and gw._physical_state[("ROOM_AIRFLOW", "bedroom-1")] == "airflow.high")


# --- 2. Deliberately incorrect gateway state -> readback mismatch -> not ACTIVE
class _FaultyWriteGateway(SimulatedHomeStateGateway):
    """Simulates a real actuation bug: the physical device fleet silently
    applies a *different* value than what was authorized (e.g. a stuck
    actuator, a unit-conversion bug, a race with another writer). The
    contract under test is that verify() must catch this via its
    independent read, not that this specific fault can occur today.
    """
    def _write_physical_state(self, primitives):
        for primitive in primitives:
            # Deliberately write the wrong value for one target.
            if primitive.key == ("ZONE_THERMAL", "zone-a"):
                self._physical_state[primitive.key] = "thermal.warmer"  # wrong!
            else:
                self._physical_state[primitive.key] = primitive.value_ref


faulty_gw = _FaultyWriteGateway()
status2, detail2 = faulty_gw.apply_and_verify("bp-binding-2", PRIMITIVES)
check("deliberately incorrect gateway state -> READBACK_MISMATCH (not VERIFIED_ACTIVE)",
      status2 == "READBACK_MISMATCH", str((status2, detail2)))
check("readback_match flag false on mismatch", detail2.get("readback_match") is False)
check("mismatch result is not the ACTIVE status string used elsewhere",
      status2 != "VERIFIED_ACTIVE" and status2 != "ACTIVE")


class _FaultyReadGateway(SimulatedHomeStateGateway):
    """Simulates the write succeeding but the independent readback path
    itself being broken (e.g. reading from a stale cache) -- also must
    fail closed, not just a bad write.
    """
    def _read_physical_state(self, keys):
        real = super()._read_physical_state(keys)
        # Corrupt exactly one value on the way back out.
        corrupted = dict(real)
        for key in corrupted:
            corrupted[key] = "STALE_CACHED_VALUE"
            break
        return corrupted


faulty_read_gw = _FaultyReadGateway()
status3, detail3 = faulty_read_gw.apply_and_verify("bp-binding-3", PRIMITIVES)
check("broken independent readback path -> READBACK_MISMATCH (fails closed)",
      status3 == "READBACK_MISMATCH", str((status3, detail3)))


# --- 3. Duplicate activation -> no duplicate physical effect ----------------
gw2 = SimulatedHomeStateGateway()
status_a, detail_a = gw2.apply_and_verify("bp-binding-4", PRIMITIVES)
state_after_first = dict(gw2._physical_state)
bindings_after_first = dict(gw2._applied_blueprint_bindings)

status_b, detail_b = gw2.apply_and_verify("bp-binding-4", PRIMITIVES)
state_after_second = dict(gw2._physical_state)
bindings_after_second = dict(gw2._applied_blueprint_bindings)

check("duplicate activation of same Blueprint still verifies", status_b == "VERIFIED_ACTIVE", str(status_b))
check("duplicate activation produces identical physical state (no duplicate effect)",
      state_after_first == state_after_second, str((state_after_first, state_after_second)))
check("duplicate activation does not grow the applied-bindings ledger",
      len(bindings_after_first) == len(bindings_after_second) == 1,
      str((bindings_after_first, bindings_after_second)))
check("physical state key count unchanged by repetition (no accumulation)",
      len(state_after_first) == len(state_after_second) == 2)

# A second, *different* blueprint activating afterwards must not disturb the
# first blueprint's already-verified physical effect for untouched targets.
other_primitives = (GatewayPrimitive("DEFER_HOT_WATER", "req-1", "defer"),)
status_c, detail_c = gw2.apply_and_verify("bp-binding-5", other_primitives)
check("a second, disjoint Blueprint activation also verifies independently",
      status_c == "VERIFIED_ACTIVE", str(status_c))
check("original Blueprint's physical effect is untouched by the second activation",
      gw2._physical_state[("ZONE_THERMAL", "zone-a")] == "thermal.cooler"
      and gw2._physical_state[("ROOM_AIRFLOW", "bedroom-1")] == "airflow.high")

# --- 4. Guardrails ------------------------------------------------------------
gw3 = SimulatedHomeStateGateway()
status_empty, detail_empty = gw3.apply_and_verify("bp-empty", ())
check("zero-primitive (smooth stay, no device change) activation vacuously VERIFIED_ACTIVE",
      status_empty == "VERIFIED_ACTIVE" and detail_empty.get("primitive_count") == 0,
      str((status_empty, detail_empty)))

try:
    gw3.apply_and_verify("bp-dup", (
        GatewayPrimitive("ZONE_THERMAL", "zone-a", "thermal.cooler"),
        GatewayPrimitive("ZONE_THERMAL", "zone-a", "thermal.warmer"),
    ))
    check("duplicate target within one activation rejected", False)
except ValueError:
    check("duplicate target within one activation rejected", True)

print()
print("OVERALL:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

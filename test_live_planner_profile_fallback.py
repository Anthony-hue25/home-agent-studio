#!/usr/bin/env python3
"""
Gate J2 -- LiveStayPlanner AWS-profile-fallback test.

Proves that when the runtime has no local named CLI profile (the normal
case for an ECS task, which authenticates via its task role through the
default credential chain rather than a profile file), LiveStayPlanner
falls back to the default credential chain instead of hard-failing with
ProfileNotFound -- while the identity gate (is_authorized_runtime_identity)
still runs, unchanged, against whatever identity that resolves to.

Everything AWS/Strands/Bedrock is mocked; no network or real credentials
are used. Run directly with:
    python3 test_live_planner_profile_fallback.py
"""
import sys
import types
from unittest import mock


ok = True


def check(label, cond, extra=""):
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"[{status}] {label} {extra}")


from studio.stay_dream import StrategyCatalog, StrategyOption, StrategyPrimitive

CATALOG = StrategyCatalog(
    (StrategyPrimitive("P001", "ZONE_THERMAL", "zone-a", "thermal.cooler"),),
    (StrategyOption("O001", ("P001",)),),
)


class _FakeConflictAssessment:
    conflicts = ()


def _make_fake_boto3(identity_arn, profile_name_should_fail):
    """A fake boto3 module whose Session(profile_name=...) raises
    ProfileNotFound only when profile_name is set (simulating "no such
    named profile in this runtime"), and otherwise returns a session whose
    sts client reports `identity_arn`.
    """
    from botocore.exceptions import ProfileNotFound as RealProfileNotFound

    calls = []

    class FakeSTSClient:
        def get_caller_identity(self):
            return {"Arn": identity_arn}

    class FakeSession:
        def __init__(self, profile_name=None, region_name=None):
            calls.append({"profile_name": profile_name, "region_name": region_name})
            if profile_name_should_fail and profile_name is not None:
                raise RealProfileNotFound(profile=profile_name)
            self.profile_name = profile_name
            self.region_name = region_name

        def client(self, service, config=None):
            assert service == "sts"
            return FakeSTSClient()

    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.Session = FakeSession
    return fake_boto3, calls


def _make_fake_strands():
    """Strands module stubs sufficient for plan() to run its tool-use loop
    without ever touching a real model. The tool is invoked once, structured
    output is returned immediately.
    """
    fake_strands = types.ModuleType("strands")
    fake_models = types.ModuleType("strands.models")

    def tool(fn):
        return fn

    class FakeAgent:
        def __init__(self, model, tools, system_prompt, structured_output_model,
                     callback_handler, load_tools_from_directory, retry_strategy):
            self.model = model
            self.tools = tools
            self.structured_output_model = structured_output_model

        def __call__(self, payload):
            # Simulate the tool-use loop: call the (single) grounding tool,
            # then produce grounded structured output, exactly like a real
            # Strands agent would after its tool call.
            for t in self.tools:
                t()
            structured = self.structured_output_model.model_validate({"option_refs": ["O001"]})

            class Result:
                pass
            result = Result()
            result.structured_output = structured
            return result

    class FakeBedrockModel:
        def __init__(self, boto_session, boto_client_config, model_id, temperature,
                     max_tokens, streaming):
            self.boto_session = boto_session

            class FakeClient:
                class meta:
                    class events:
                        @staticmethod
                        def register(name, fn):
                            # Immediately fire the registered after-call hook
                            # with a synthetic successful Bedrock response,
                            # exactly like the real boto3 event system would
                            # after a real Converse call.
                            fn({"ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req-fake-123"}})
            self.client = FakeClient()

    fake_strands.Agent = FakeAgent
    fake_strands.tool = tool
    fake_models.BedrockModel = FakeBedrockModel
    fake_strands.models = fake_models
    return fake_strands, fake_models


# --- Test 1: ECS-shaped identity, no local profile available -> fallback works
fake_boto3, calls = _make_fake_boto3(
    identity_arn="arn:aws:sts::861276109104:assumed-role/adaptive-stay-task-role/ecs-task-abc123",
    profile_name_should_fail=True,
)
fake_strands, fake_models = _make_fake_strands()

with mock.patch.dict(sys.modules, {
    "boto3": fake_boto3,
    "strands": fake_strands,
    "strands.models": fake_models,
}):
    from studio.stay_planner import LiveStayPlanner
    planner = LiveStayPlanner()  # default profile_name="agent-factory"
    result = planner.plan(CATALOG, _FakeConflictAssessment())

check("plan() succeeds despite ProfileNotFound on the named profile (ECS fallback)",
      result is not None and result.provenance.get("success") is True)
check("first Session() attempt used the configured profile_name",
      calls[0]["profile_name"] == "agent-factory", str(calls))
check("fallback Session() attempt used no profile_name (default credential chain)",
      calls[1]["profile_name"] is None, str(calls))
check("resulting provenance reflects the real (ECS task role) identity's Bedrock call",
      result.provenance.get("bedrock_calls") == [{"http_status": 200, "request_id": "req-fake-123"}],
      str(result.provenance.get("bedrock_calls")))


# --- Test 2: fallback identity is STILL subject to the identity gate --------
fake_boto3_bad, calls_bad = _make_fake_boto3(
    identity_arn="arn:aws:sts::999999999999:assumed-role/some-other-role/ecs-task-xyz",
    profile_name_should_fail=True,
)
fake_strands2, fake_models2 = _make_fake_strands()

with mock.patch.dict(sys.modules, {
    "boto3": fake_boto3_bad,
    "strands": fake_strands2,
    "strands.models": fake_models2,
}):
    import importlib
    import studio.stay_planner as stay_planner_mod
    importlib.reload(stay_planner_mod)
    from studio.stay_planner import LiveStayPlanner as LiveStayPlanner2, LivePlannerFailure

    planner2 = LiveStayPlanner2()
    try:
        planner2.plan(CATALOG, _FakeConflictAssessment())
        check("unauthorized fallback identity is still rejected by the identity gate", False)
    except LivePlannerFailure as exc:
        check("unauthorized fallback identity is still rejected by the identity gate",
              exc.diagnostic.get("failure_stage") == "aws_identity"
              and exc.diagnostic.get("error_type") == "UnexpectedDevelopmentIdentity",
              str(exc.diagnostic))

# reload back to the real (unmocked) module state for any subsequent test in
# the same process
import importlib
import studio.stay_planner as stay_planner_mod
importlib.reload(stay_planner_mod)

print()
print("OVERALL:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

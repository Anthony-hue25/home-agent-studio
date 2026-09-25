#!/usr/bin/env python3
"""
Gate J2 -- identity gate unit tests for LiveStayPlanner.is_authorized_runtime_identity.

Pure logic test: no AWS credentials, network, Strands, or boto3 needed. Run
directly with:  python3 test_identity_gate.py
Exits non-zero if any assertion fails.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio.stay_planner import is_authorized_runtime_identity

ACCOUNT = "861276109104"
ROLE = "adaptive-stay-task-role"

CASES = [
    # (label, arn, expected)
    ("intended dev IAM user accepted",
     f"arn:aws:iam::{ACCOUNT}:user/agent-factory-dev", True),

    ("intended ECS task role (assumed-role, real session name) accepted",
     f"arn:aws:sts::{ACCOUNT}:assumed-role/{ROLE}/i-0abc123def456-worker", True),

    ("intended ECS task role accepted with a different session-name shape",
     f"arn:aws:sts::{ACCOUNT}:assumed-role/{ROLE}/ecs-task-9f8e7d6c", True),

    ("wrong account (dev user shape, foreign account) rejected",
     "arn:aws:iam::999999999999:user/agent-factory-dev", False),

    ("wrong account (ECS role shape, foreign account) rejected",
     f"arn:aws:sts::999999999999:assumed-role/{ROLE}/i-0abc123", False),

    ("wrong role name (right account, not the pinned task role) rejected",
     f"arn:aws:sts::{ACCOUNT}:assumed-role/some-other-role/i-0abc123", False),

    ("wrong role name (looks similar, substring/prefix trick) rejected",
     f"arn:aws:sts::{ACCOUNT}:assumed-role/adaptive-stay-task-role-extra/i-0abc123", False),

    ("root user rejected",
     f"arn:aws:iam::{ACCOUNT}:root", False),

    ("unrelated IAM user in the right account rejected",
     f"arn:aws:iam::{ACCOUNT}:user/some-other-developer", False),

    ("unrelated IAM role (not assumed-role, not the pinned name) rejected",
     f"arn:aws:iam::{ACCOUNT}:role/{ROLE}", False),

    ("empty/malformed ARN rejected",
     "", False),

    ("None rejected",
     None, False),

    ("garbage string rejected",
     "not-an-arn-at-all", False),

    ("assumed-role with no session-name segment rejected",
     f"arn:aws:sts::{ACCOUNT}:assumed-role/{ROLE}", False),

    ("assumed-role with an extra path segment rejected",
     f"arn:aws:sts::{ACCOUNT}:assumed-role/{ROLE}/session/extra", False),
]

ok = True
for label, arn, expected in CASES:
    actual = is_authorized_runtime_identity(arn)
    status = "PASS" if actual == expected else "FAIL"
    if actual != expected:
        ok = False
    print(f"[{status}] {label} -- arn={arn!r} expected={expected} actual={actual}")

print()
print("OVERALL:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

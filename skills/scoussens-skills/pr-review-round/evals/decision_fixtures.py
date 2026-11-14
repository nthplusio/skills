"""Synthetic regressions based on the audit, not fresh PR assessments."""
from review_config import resolve

HEAD = "a" * 40
BASE = "b" * 40
TARGET = {"ref": "main", "sha": BASE}
REVISION = "2026-11-11T20:00:00Z"


def assessment(number=17, kind="ready", owner="Reviewer", **changes):
    return {"number": number, "head": HEAD, "base": BASE, "assessed_at": REVISION,
            "evidence_inputs": {"forge": REVISION, "issues": "issue-revision-1", "policy": resolve(".")["revision"], "target": TARGET},
            "decisions": [{"id": "criterion-1", "kind": kind, "axis": "Spec", "severity": "blocking",
                           "criterion": "Demonstrate the live workflow", "summary": "Live workflow acceptance",
                           "owner": owner, "unblock": "Run the live workflow and attach its result" if kind != "ready" else "Check mutable forge gates",
                           "effort": "one workflow", "proposed_action": "comment" if kind != "ready" else "approve",
                           "evidence": {"source": "https://example.test/evidence", "at": REVISION,
                                        "observation": "Synthetic observed result"}}], **changes}


def bundle(item=None):
    return {"repository": "owner/repo", "assessments": [item or assessment()]}


def authority(**changes):
    return {"repository": "owner/repo", "prs": [17], "instruction": "Test-only explicit authority for #17",
            "actions": ["enqueue", "enable-auto-merge", "approve", "dismiss", "comment", "request-changes"],
            "possible_landing": True, **changes}

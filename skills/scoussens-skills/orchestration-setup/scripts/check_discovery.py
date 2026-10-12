#!/usr/bin/env python3
"""Validate saved observations without invoking harness operations."""

import argparse
from datetime import datetime
import json
from pathlib import Path


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")


def texts(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of text")
    for item in value:
        text(item, label)


def check(discovery):
    if discovery["schema_version"] != 1:
        raise ValueError("unsupported discovery schema_version; run orchestration-discovery")
    repository = discovery["repository"]
    for field in ("guidance", "ticket_sources", "notes"):
        texts(repository[field], f"repository.{field}")
    if repository["ticket_template"] is not None:
        text(repository["ticket_template"], "repository.ticket_template")
    if not isinstance(discovery["harnesses"], dict) or not discovery["harnesses"]:
        raise ValueError("harnesses must contain a discovered harness name")
    for name, facts in discovery["harnesses"].items():
        text(name, "harness name")
        for field in ("context", "owner_term", "helper_term"):
            text(facts[field], f"{name}.{field}")
        observed = datetime.fromisoformat(facts["observed_at"].replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError("observed_at needs a timezone")
        texts(facts["sources"], f"{name}.sources")
        if not facts["sources"]:
            raise ValueError("sources must identify the inspected tools or documentation")
        for section, fields in {
            "owners": ("launch", "inspect", "message", "collect", "close", "resume"),
            "helpers": ("invoke", "collect"),
            "monitoring": ("notifications", "wait", "wake"),
            "skills": ("load",),
            "evidence": ("transfer", "retain_before_close"),
        }.items():
            for field in fields:
                if facts[section][field] is not None:
                    text(facts[section][field], f"{name}.{section}.{field}")
        if facts["owners"]["workspace_model"] not in ("shared", "isolated", "selectable", "unknown"):
            raise ValueError("owners.workspace_model must describe workspace sharing")
        for field in ("blocks_caller", "follow_up"):
            if facts["helpers"][field] is not None and type(facts["helpers"][field]) is not bool:
                raise ValueError(f"helpers.{field} must be boolean or null")
        text(facts["skills"]["brief"], "skills.brief")
        texts(facts["limitations"], "limitations")
        if not isinstance(facts["artifacts"], list):
            raise ValueError("artifacts must be a list")
        seen = set()
        for artifact in facts["artifacts"]:
            for field in ("id", "label", "present", "update", "audience"):
                text(artifact[field], f"artifact.{field}")
            if artifact["id"] in seen:
                raise ValueError("artifact IDs must be unique per harness")
            seen.add(artifact["id"])
            for field in ("interaction", "auto_refresh"):
                if artifact.get(field) is not None:
                    text(artifact[field], f"artifact.{field}")
    if "REPLACE_WITH_" in json.dumps(discovery):
        raise ValueError("replace every template placeholder with a discovered value")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("discovery", type=Path)
    args = parser.parse_args()
    try:
        check(json.loads(args.discovery.read_text()))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"FAIL: {error}\n")
    print(f"PASS: discovery for {args.discovery}")


if __name__ == "__main__":
    main()

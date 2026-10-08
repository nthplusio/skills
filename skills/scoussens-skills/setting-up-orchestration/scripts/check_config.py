#!/usr/bin/env python3
"""Check the stored harness configuration, without invoking any operation."""

import argparse
import json
import re
from pathlib import Path, PureWindowsPath


def check(config):
    if config["schema_version"] != 1:
        raise ValueError("unsupported schema_version; run setting-up-orchestration")
    for field in ("id", "name", "context", "owner_term", "helper_term"):
        if not isinstance(config["harness"][field], str) or not config["harness"][field].strip():
            raise ValueError(f"harness.{field} must be nonempty text")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", config["harness"]["id"]):
        raise ValueError("harness.id must be a lowercase slug")
    for section, fields in {
        "owners": ("launch", "inspect", "message", "collect", "close", "resume"),
        "helpers": ("invoke", "collect"),
        "skills": ("load",),
        "evidence": ("transfer", "retain_before_close"),
    }.items():
        for field in fields:
            value = config[section][field]
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{section}.{field} must be an operation description or null")
    if config["owners"]["workspace_model"] not in ("shared", "isolated", "selectable", "unknown"):
        raise ValueError("owners.workspace_model must describe workspace sharing")
    for field in ("blocks_caller", "follow_up"):
        if config["helpers"][field] is not None and type(config["helpers"][field]) is not bool:
            raise ValueError(f"helpers.{field} must be boolean or null")
    if not isinstance(config["skills"]["brief"], str) or not config["skills"]["brief"].strip():
        raise ValueError("skills.brief must describe instruction propagation")
    for values in (config["skills"]["shared"], config["limitations"]):
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError("shared skills and limitations must be lists of text")
    if {"setting-up-orchestration", "running-orchestration"} & set(config["skills"]["shared"]):
        raise ValueError("orchestration skills belong to the coordinator, not shared workers")
    if not isinstance(config["artifacts"], list):
        raise ValueError("artifacts must be a list")
    seen = set()
    for artifact in config["artifacts"]:
        for field in ("id", "label", "present", "update", "audience"):
            if not isinstance(artifact[field], str) or not artifact[field].strip():
                raise ValueError(f"artifact.{field} must be nonempty text")
        if artifact["id"] in seen:
            raise ValueError("artifact IDs must be unique")
        seen.add(artifact["id"])
    root = config["run_root"]
    if not isinstance(root, str) or not (Path(root).is_absolute() or PureWindowsPath(root).is_absolute()):
        raise ValueError("run_root must be an absolute local path")
    if "REPLACE_WITH_" in json.dumps(config):
        raise ValueError("replace every template placeholder with a discovered value")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    try:
        check(json.loads(args.config.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"FAIL: {error}\n")
    print(f"PASS: configuration for {args.config}")


if __name__ == "__main__":
    main()

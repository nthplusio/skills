#!/usr/bin/env python3
"""Validate setup and resolve one harness profile without invoking its tools."""

import argparse
from copy import deepcopy
import json
from pathlib import Path, PureWindowsPath
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "orchestration-discovery" / "scripts"))
from check_discovery import check as check_discovery, text, texts


ORCHESTRATION_SKILLS = {"orchestration-discovery", "orchestration-setup", "orchestration-run"}


def check(config, discovery):
    if config["schema_version"] != 2:
        raise ValueError("unsupported setup schema_version; run orchestration-setup")
    check_discovery(discovery)
    text(config["discovery_file"], "discovery_file")
    policy = config["project"]["ticket_policy"]
    for field in ("source", "location", "definition", "template", "id_convention", "confirmed_from"):
        text(policy[field], f"ticket_policy.{field}")
    if type(policy["criteria_limit"]) is not int or policy["criteria_limit"] < 1:
        raise ValueError("ticket_policy.criteria_limit must be a positive integer")

    def shared(values):
        texts(values, "shared_skills")
        if ORCHESTRATION_SKILLS & set(values):
            raise ValueError("orchestration skills belong to the coordinator, not shared workers")

    shared(config["project"]["shared_skills"])
    if not isinstance(config["harnesses"], dict) or not config["harnesses"]:
        raise ValueError("harnesses must contain a confirmed setup profile")
    for name, profile in config["harnesses"].items():
        if name not in discovery["harnesses"]:
            raise ValueError(f"{name}: no saved discovery; run orchestration-discovery")
        text(profile["run_root"], "run_root")
        shared(profile["shared_skills"])
        text(profile["confirmed_from"], "confirmed_from")
        defaults = profile["defaults"]
        text(defaults["finish_line"], "defaults.finish_line")
        if type(defaults["interval_seconds"]) is not int or defaults["interval_seconds"] < 1:
            raise ValueError("defaults.interval_seconds must be a positive integer")
        destination = defaults["destination"]
        if destination is not None and destination not in {item["id"] for item in discovery["harnesses"][name]["artifacts"]}:
            raise ValueError(f"{name}: default destination must be a discovered artifact ID or null")
    if "REPLACE_WITH_" in json.dumps(config):
        raise ValueError("replace every template placeholder with a confirmed value")


def resolve(config_path, harness_name=None):
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text())
    discovery = json.loads((config_path.parent / config["discovery_file"]).read_text())
    check(config, discovery)
    if harness_name is None:
        return None
    if harness_name not in config["harnesses"]:
        raise ValueError(f"{harness_name}: no setup profile; run orchestration-setup for this harness")
    profile = config["harnesses"][harness_name]
    facts = deepcopy(discovery["harnesses"][harness_name])
    root = Path(profile["run_root"]).expanduser()
    if PureWindowsPath(profile["run_root"]).is_absolute() and not root.is_absolute():
        raise ValueError("run_root is for another operating system; repair this harness profile with orchestration-setup")
    facts.update(harness={"name": harness_name, "context": facts["context"],
                          "owner_term": facts["owner_term"], "helper_term": facts["helper_term"]},
                 config_path=str(config_path), run_root=str((config_path.parent / root).resolve()),
                 ticket_policy=deepcopy(config["project"]["ticket_policy"]), defaults=deepcopy(profile["defaults"]))
    facts["skills"]["shared"] = list(dict.fromkeys(config["project"]["shared_skills"] + profile["shared_skills"]))
    return facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--harness", help="discovered harness name, exactly as saved")
    args = parser.parse_args()
    try:
        selected = resolve(args.config, args.harness)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"FAIL: {error}\n")
    print(json.dumps(selected, indent=2) if selected is not None else f"PASS: configuration for {args.config}")


if __name__ == "__main__":
    main()

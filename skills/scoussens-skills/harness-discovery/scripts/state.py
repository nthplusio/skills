#!/usr/bin/env python3
"""Check and resolve the saved state in <repository>/.nthplusio-skills/.

  state.py check [discovery|orchestration] [--root DIR]
  state.py resolve --harness NAME [--orchestration] [--root DIR]

check    Validates discovery.json and orchestration.json, or only the one named.
resolve  Prints one harness's discovery entry. NAME is its saved key or that
         key's slug. --orchestration adds the harness's orchestration.json
         profile, which orchestration-run consumes.

No command invokes harness tools. --root defaults to the Git repository that
holds the working directory.
"""

import argparse
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path, PureWindowsPath
import re
import subprocess


STATE_DIR = ".nthplusio-skills"
FILES = {"discovery": "discovery.json", "orchestration": "orchestration.json"}
CURRENT = {"discovery": 1, "orchestration": 3}
OWNERS = {"discovery": "harness-discovery", "orchestration": "orchestration-setup"}
COORDINATOR_SKILLS = {"harness-discovery", "orchestration-setup", "orchestration-run"}
# Business stage keys from orchestration-run's dashboard data contract.
STAGES = ("defined", "researched", "pr_readiness", "code_publication", "review", "verification",
          "deployment", "business_acceptance")


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")


def texts(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of text")
    for item in value:
        text(item, label)


def slug(name):
    """`Claude Code` -> `claude-code`: the name callers use for files and flags."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def check_version(document, kind):
    found = document["schema_version"]
    if found == CURRENT[kind]:
        return
    if type(found) is int and found < CURRENT[kind]:
        raise ValueError(f"{kind} schema_version {found} is older than {CURRENT[kind]}; run {OWNERS[kind]}")
    raise ValueError(f"unsupported {kind} schema_version {found!r}; update these skills")


def check_discovery(discovery):
    check_version(discovery, "discovery")
    repository = discovery["repository"]
    for field in ("guidance", "ticket_sources", "notes"):
        texts(repository[field], f"repository.{field}")
    if repository["ticket_template"] is not None:
        text(repository["ticket_template"], "repository.ticket_template")
    if not isinstance(discovery["harnesses"], dict) or not discovery["harnesses"]:
        raise ValueError("harnesses must contain a discovered harness name")
    slugs = {}
    for name, facts in discovery["harnesses"].items():
        text(name, "harness name")
        key = slug(name)
        if not key:
            raise ValueError(f"{name}: a harness name needs letters or digits")
        if key in slugs:
            raise ValueError(f"{slugs[key]} and {name} share the slug {key}; harness names must differ in letters or digits")
        slugs[key] = name
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


def check_orchestration(config, discovery):
    check_version(config, "orchestration")
    check_discovery(discovery)
    policy = config["project"]["ticket_policy"]
    for field in ("source", "location", "definition", "template", "id_convention", "confirmed_from"):
        text(policy[field], f"ticket_policy.{field}")
    if type(policy["criteria_limit"]) is not int or policy["criteria_limit"] < 1:
        raise ValueError("ticket_policy.criteria_limit must be a positive integer")

    def shared(values):
        texts(values, "shared_skills")
        if COORDINATOR_SKILLS & set(values):
            raise ValueError("harness-discovery, orchestration-setup and orchestration-run belong to the coordinator, not shared workers")

    shared(config["project"]["shared_skills"])
    stage_skills = config["project"].get("stage_skills", {})
    if not isinstance(stage_skills, dict) or set(stage_skills) - set(STAGES):
        raise ValueError(f"project.stage_skills keys must be business stages: {', '.join(STAGES)}")
    for values in stage_skills.values():
        shared(values)
    if not isinstance(config["harnesses"], dict) or not config["harnesses"]:
        raise ValueError("harnesses must contain a confirmed setup profile")
    for name, profile in config["harnesses"].items():
        if name not in discovery["harnesses"]:
            raise ValueError(f"{name}: no saved discovery; run harness-discovery")
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


def repository_root(given):
    if given:
        return Path(given).expanduser().resolve()
    found = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if found.returncode:
        raise ValueError("not inside a Git repository; pass --root")
    return Path(found.stdout.strip()).resolve()


def state_path(root, kind):
    return root / STATE_DIR / FILES[kind]


def saved(root, kind):
    """The current file and its document, or an error naming what to run."""
    path = state_path(root, kind)
    if not path.is_file():
        raise ValueError(f"no {FILES[kind]} in {path.parent}; run {OWNERS[kind]}")
    return path, json.loads(path.read_text())


def check(root, scope=None):
    kinds = [scope] if scope else [kind for kind in FILES if state_path(root, kind).is_file()] or ["discovery"]
    discovery_path, discovery = saved(root, "discovery")
    check_discovery(discovery)
    lines = [f"PASS: discovery {discovery_path}"] if "discovery" in kinds else []
    if "orchestration" in kinds:
        config_path, config = saved(root, "orchestration")
        check_orchestration(config, discovery)
        lines.append(f"PASS: orchestration {config_path}")
    return lines


def match(harnesses, name):
    if name in harnesses:
        return name
    found = [key for key in harnesses if slug(key) == slug(name)]
    if len(found) != 1:
        raise ValueError(f"{name}: no saved discovery for this harness; run harness-discovery in it")
    return found[0]


def resolve(root, name, orchestration=False):
    _, discovery = saved(root, "discovery")
    check_discovery(discovery)
    key = match(discovery["harnesses"], name)
    facts = deepcopy(discovery["harnesses"][key])
    facts["harness"] = {"name": key, "slug": slug(key), "context": facts["context"],
                        "owner_term": facts["owner_term"], "helper_term": facts["helper_term"]}
    if not orchestration:
        return facts
    config_path, config = saved(root, "orchestration")
    check_orchestration(config, discovery)
    if key not in config["harnesses"]:
        raise ValueError(f"{key}: no setup profile; run orchestration-setup for this harness")
    profile = config["harnesses"][key]
    run_root = Path(profile["run_root"]).expanduser()
    if PureWindowsPath(profile["run_root"]).is_absolute() and not run_root.is_absolute():
        raise ValueError("run_root is for another operating system; repair this harness profile with orchestration-setup")
    facts.update(config_path=str(config_path), run_root=str((config_path.parent / run_root).resolve()),
                 ticket_policy=deepcopy(config["project"]["ticket_policy"]), defaults=deepcopy(profile["defaults"]))
    facts["skills"]["shared"] = list(dict.fromkeys(config["project"]["shared_skills"] + profile["shared_skills"]))
    facts["skills"]["stages"] = deepcopy(config["project"].get("stage_skills", {}))
    return facts


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="repository holding .nthplusio-skills/; defaults to the working directory's Git repository")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    checking = commands.add_parser("check", parents=[common], help="validate saved state")
    checking.add_argument("scope", nargs="?", choices=tuple(FILES))
    resolving = commands.add_parser("resolve", parents=[common], help="print one harness's saved facts")
    resolving.add_argument("--harness", required=True, help="saved harness key, or its slug")
    resolving.add_argument("--orchestration", action="store_true", help="add the harness's orchestration profile")
    args = parser.parse_args()
    try:
        root = repository_root(args.root)
        if args.command == "check":
            print("\n".join(check(root, args.scope)))
        else:
            print(json.dumps(resolve(root, args.harness, args.orchestration), indent=2))
    except KeyError as error:
        parser.exit(1, f"FAIL: missing field {error}\n")
    except (OSError, ValueError, TypeError, AttributeError) as error:
        parser.exit(1, f"FAIL: {error}\n")


if __name__ == "__main__":
    main()

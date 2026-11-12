#!/usr/bin/env python3
"""Resolve repository review policy and bundled references without executing it."""
import argparse
import hashlib
import json
from pathlib import Path


DEFAULTS = ("conventions", "data-layer", "integration", "security", "verification")


def fields(value, allowed, location):
    if not isinstance(value, dict) or value.keys() - set(allowed):
        raise ValueError(f"{location}: expected an object with only {', '.join(allowed)}")


def files(root, value, location):
    if not isinstance(value, list) or any(not isinstance(p, str) or not p for p in value):
        raise ValueError(f"{location}: expected a list of repository-relative file paths")
    resolved = []
    for name in value:
        path = (root / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"{location}: missing or outside-repository file: {name}")
        resolved.append(str(path))
    return list(dict.fromkeys(resolved))


def resolve(root, config=None):
    root = Path(root).resolve()
    name = config if config is not None else ".nthplusio-skills/review.json"
    profile = root / name
    if not root.is_dir():
        raise ValueError(f"repository root does not exist: {root}")
    data = {}
    if profile.exists() or profile.is_symlink() or config is not None:
        profile = Path(files(root, [name], "profile")[0])
        data = json.loads(profile.read_text())
        fields(data, ("schema_version", "guidance", "tracker", "execution", "references"), "profile")
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ValueError("profile: schema_version must be 1")
    tracker = data.get("tracker", {})
    fields(tracker, ("policy",), "tracker")
    execution = data.get("execution", {})
    fields(execution, ("reviewers", "policy"), "execution")
    reviewers = execution.get("reviewers", "auto")
    if reviewers not in ("auto", "serial", "parallel"):
        raise ValueError("execution.reviewers: expected auto, serial or parallel")
    overrides = data.get("references", {})
    if not isinstance(overrides, dict) or any(not name.strip() for name in overrides):
        raise ValueError("references: expected an object keyed by category name")
    references = {}
    disabled = []
    for name in dict.fromkeys((*DEFAULTS, *overrides)):
        override = overrides.get(name, {})
        fields(override, ("mode", "files"), f"references.{name}")
        mode = override.get("mode", "extend")
        if mode not in ("extend", "replace", "disable"):
            raise ValueError(f"references.{name}: expected extend, replace or disable")
        selected = files(root, override.get("files", []), f"references.{name}.files")
        if mode == "disable":
            if selected:
                raise ValueError(f"references.{name}: disable accepts no files")
            disabled.append(name)
            continue
        if (mode == "replace" or name not in DEFAULTS) and not selected:
            raise ValueError(f"references.{name}: supply at least one file")
        if mode == "extend" and name in DEFAULTS:
            default = Path(__file__).resolve().parents[1] / "references" / "defaults" / f"{name}.md"
            if not default.is_file():
                raise ValueError(f"bundled reference missing: {default}; repair this skill installation")
            selected.insert(0, str(default))
        references[name] = selected
    result = {
        "profile": str(profile) if data else None,
        "guidance": files(root, data.get("guidance", []), "guidance"),
        "tracker": {"policy": files(root, tracker.get("policy", []), "tracker.policy")},
        "execution": {"reviewers": reviewers, "policy": files(root, execution.get("policy", []), "execution.policy")},
        "references": references,
        "disabled": disabled,
    }
    # Hash contents and logical paths, not installation-specific absolute paths.
    # Consumers use this revision to invalidate reused reviews after policy edits.
    inputs = {"profile": data}
    paths = [*result["guidance"], *result["tracker"]["policy"], *result["execution"]["policy"],
             *(path for selected in references.values() for path in selected)]
    defaults = Path(__file__).resolve().parents[1] / "references" / "defaults"
    for value in paths:
        path = Path(value)
        key = f"builtin/{path.name}" if path.is_relative_to(defaults) else f"repository/{path.relative_to(root)}"
        inputs[key] = path.read_text()
    result["revision"] = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", help="Repository-relative alternate profile path")
    args = parser.parse_args()
    try:
        result = resolve(args.root, args.config)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Review configuration error: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

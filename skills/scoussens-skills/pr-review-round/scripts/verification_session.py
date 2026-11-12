#!/usr/bin/env python3
"""Run a command against pinned, clean tracked source and retain a result manifest.

Use a detached verification worktree, not the checkout used to merge or rebase.
Shell pipelines must use bash -o pipefail; the runner preserves command exits,
but cannot recover a failure that the supplied shell command hides.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess


def source(base):
    def git(*args):
        return subprocess.check_output(["git", *args], text=True).strip()
    return {"head": git("rev-parse", "HEAD"), "base": git("rev-parse", base),
            "tracked_changes": git("status", "--porcelain", "--untracked-files=no")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--state", action="append", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not all(re.fullmatch(r"[0-9a-f]{40}", value) for value in (args.head, args.base)):
        parser.error("--head and --base must be pinned full SHAs, not moving refs")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("supply a command after --")
    initial = source(args.base)
    if initial["head"] != args.head or initial["tracked_changes"]:
        parser.error("use a clean worktree at --head; do not verify mutable source")
    record = {**initial, "command": command, "states": args.state, "expected": args.expected,
              "exclusions": args.exclude, "started_at": datetime.now(timezone.utc).isoformat()}
    child = subprocess.Popen(command, start_new_session=True)
    changed = False
    while child.poll() is None:
        if source(args.base) != initial:
            changed = True
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # The command may finish while the source check runs.
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            break
        try:
            child.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            pass
    changed = changed or source(args.base) != initial
    code = 1 if changed else child.returncode
    record.update(exit_code=code, observed="Source changed; evidence invalid" if changed else f"Command exited {code}; inspect retained output against expected outcome",
                  ended_at=datetime.now(timezone.utc).isoformat())
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(record, indent=2) + "\n")
    print(record["observed"])
    return code if code >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

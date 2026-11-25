#!/usr/bin/env python3
"""authority.py -- the round's write permissions, settled once at its start.

    authority.py questions [--root <repository>] [--answers <answers.json>]
    authority.py init --repo <owner/repo> --scope <scope.json> --answers <answers.json> [--root <repository>] --out <authority.json>
    authority.py show <authority.json>
    authority.py grant <authority.json> --pr N --action <action> --instruction "<the user's words>"

`questions` prints only what the review profile and the answers leave open, each with
its recommended answer. `answers.json` holds the user's answers:

    {"level": "review", "approvals": true, "policies": {"dismiss-bot-review": "auto"}, "instruction": "<their exact words>"}

Every key is optional. A missing answer falls back to the profile's `round` block, then
to the registry default (level assess, no approvals, each kind's default mode). `init`
writes an authority file for exactly the PRs in the scope file `queue.py --save-scope`
wrote, records where each value came from, and derives `actions` and `possible_landing`,
which the write helpers recompute and compare. `grant` adds one explicit write for one PR
when the user says yes mid-round; it never raises the level or overrides a `never` policy.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ledger import GOVERNED, LEVELS, SEPARATE, check_authority, possible_landing, standing_actions
from review_config import KINDS, MODES, resolve, supports


def profile_round(root):
    resolved = resolve(root)
    return resolved["round"], resolved["profile"]


def validate_answers(answers):
    if not isinstance(answers, dict) or answers.keys() - {"level", "approvals", "policies", "instruction"}:
        raise ValueError("answers: expected an object with only level, approvals, policies and instruction")
    if "level" in answers and answers["level"] not in LEVELS:
        raise ValueError("answers.level: expected " + ", ".join(LEVELS))
    if "approvals" in answers and type(answers["approvals"]) is not bool:
        raise ValueError("answers.approvals: expected true or false")
    policies = answers.get("policies", {})
    if not isinstance(policies, dict) or policies.keys() - set(KINDS):
        raise ValueError("answers.policies: expected an object keyed by " + ", ".join(KINDS))
    if any(mode not in MODES for mode in policies.values()):
        raise ValueError("answers.policies: expected " + ", ".join(MODES))
    if answers and not answers.get("instruction"):
        raise ValueError("answers.instruction: record the user's exact words")


def build(repo, prs, answers, round_, profile=None):
    """The authority record: each value from the answer, then the profile, then the default."""
    validate_answers(answers)
    sources = {"policies": {}}
    if "level" in answers:
        level, sources["level"] = answers["level"], "answer"
    elif round_.get("level"):
        level, sources["level"] = round_["level"], "profile"
    else:
        level, sources["level"] = "assess", "default"
    if "approvals" in answers:
        approvals, sources["approvals"] = answers["approvals"], "answer"
    elif round_.get("level") and level != "assess":
        approvals, sources["approvals"] = round_.get("approvals", False), "profile"
    else:
        approvals, sources["approvals"] = False, "default"
    if approvals and level == "assess":
        raise ValueError("approvals need level review, moderate or major; assess makes no writes")
    policies = {}
    for kind, entry in KINDS.items():
        if kind in answers.get("policies", {}):
            mode, source = answers["policies"][kind], "answer"
            if mode == "auto" and not supports(kind, level, approvals):
                raise ValueError(f"{kind}: auto needs level review or above"
                                 + (" with approvals" if entry["with_approvals"] else "") + f"; the level is {level}"
                                 + (" with approvals" if approvals else " without approvals"))
        elif kind in round_.get("policies", {}):
            mode, source = round_["policies"][kind], "profile"
        else:
            mode, source = entry["default"], "default"
        # A profile or default `auto` the chosen level cannot use asks instead.
        policies[kind] = "ask" if mode == "auto" and not supports(kind, level, approvals) else mode
        sources["policies"][kind] = source
    actions = standing_actions(level, approvals, policies)
    return {"version": 2, "repository": repo, "prs": prs, "level": level, "approvals": approvals,
            "policies": policies, "sources": sources,
            "instruction": answers.get("instruction") or f"review profile {profile or '(none)'}: round defaults",
            "profile": profile, "actions": actions, "possible_landing": possible_landing(actions, []), "grants": []}


def grant(record, pr, action, instruction, at=None):
    if action not in SEPARATE:
        raise ValueError(f"grant covers {', '.join(SEPARATE)}; {action} comes from the level, so raise it with init")
    if pr not in record["prs"]:
        raise ValueError(f"#{pr} is not in this round's scope")
    kind = GOVERNED.get(action)
    if kind and record["policies"].get(kind) == "never":
        raise ValueError(f"the {kind} policy is never; change it with init before granting {action}")
    if not instruction:
        raise ValueError("record the user's exact words with --instruction")
    grants = [g for g in record["grants"] if (g["pr"], g["action"]) != (pr, action)]
    grants.append({"pr": pr, "action": action, "instruction": instruction,
                   "at": at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    updated = {**record, "grants": grants, "possible_landing": possible_landing(record["actions"], grants)}
    check_authority(updated, record["repository"], pr, action)
    return updated


SOURCE = {"answer": "your answer", "profile": "the review profile", "default": "the default"}
MODE = {"auto": "yes, without asking", "ask": "ask me for each PR", "never": "never"}


def describe(record):
    origin = lambda source: SOURCE[source] + (f" ({record['profile']})" if source == "profile" and record["profile"] else "")
    lines = [f"Repository {record['repository']}, PRs " + ", ".join(f"#{n}" for n in record["prs"]) + ".",
             f"Work level: {record['level']} (from {origin(record['sources']['level'])}).",
             f"Approvals: {'yes' if record['approvals'] else 'no'} (from {origin(record['sources']['approvals'])})."]
    for kind, mode in record["policies"].items():
        lines.append(f"{kind}: {MODE[mode]} (from {origin(record['sources']['policies'][kind])}). "
                     f"{KINDS[kind]['question']}")
    lines.append("Writes allowed on every PR: " + (", ".join(record["actions"]) or "none") + ".")
    lines.append(f"Can a write make a PR merge: {'yes' if record['possible_landing'] else 'no'}.")
    lines += [f"Granted: {g['action']} on #{g['pr']} (\"{g['instruction']}\")." for g in record["grants"]]
    lines.append(f"Instruction: {record['instruction']}")
    return lines


def open_questions(round_, answers):
    """The questions neither the profile nor the answers settle, each with its recommended answer."""
    validate_answers(answers)
    questions = []
    level = answers.get("level") or round_.get("level")
    approvals = answers.get("approvals", round_.get("approvals", False) if round_.get("level") else None)
    if not level:
        questions.append(("level", "How far should the round go: assess, review, moderate or major?", "review"))
    if approvals is None and level != "assess":
        questions.append(("approvals", "May the round approve PRs that pass review?", "no"))
    for kind, entry in KINDS.items():
        if kind in answers.get("policies", {}) or kind in round_.get("policies", {}):
            continue
        if level and approvals is not None and not supports(kind, level, approvals):
            continue  # this level cannot use auto, so the answer is moot: the write is asked for
        questions.append((kind, entry["question"], entry["default"]))
    return questions


def read(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("questions")
    ask.add_argument("--root", default=".")
    ask.add_argument("--answers", type=Path)
    init = sub.add_parser("init")
    init.add_argument("--repo", required=True)
    init.add_argument("--scope", type=Path, required=True)
    init.add_argument("--answers", type=Path, required=True)
    init.add_argument("--root", default=".")
    init.add_argument("--out", type=Path, required=True)
    show = sub.add_parser("show")
    show.add_argument("authority", type=Path)
    add = sub.add_parser("grant")
    add.add_argument("authority", type=Path)
    add.add_argument("--pr", type=int, required=True)
    add.add_argument("--action", required=True, choices=SEPARATE)
    add.add_argument("--instruction", required=True)
    args = parser.parse_args()
    try:
        if args.command == "questions":
            round_, profile = profile_round(args.root)
            questions = open_questions(round_, read(args.answers) if args.answers else {})
            for key, question, recommended in questions:
                print(f"{key}: {question} Recommended: {recommended}.")
            settled = ([f"level {round_['level']}", f"approvals {'yes' if round_['approvals'] else 'no'}"]
                       if round_["level"] else []) + [f"{kind} {mode}" for kind, mode in round_["policies"].items()]
            if settled:
                print(f"From the review profile {profile}: " + "; ".join(settled) + ". Name any to change it.")
            if not questions:
                print("No open questions.")
        elif args.command == "init":
            if args.out.exists():
                raise ValueError(f"{args.out} exists; add one-PR writes with grant, or write a new file")
            prs = read(args.scope)
            if not isinstance(prs, list) or not prs or any(type(n) is not int or n <= 0 for n in prs):
                raise ValueError(f"{args.scope}: expected the JSON list of PR numbers queue.py --save-scope writes")
            round_, profile = profile_round(args.root)
            record = build(args.repo, prs, read(args.answers), round_, profile)
            args.out.write_text(json.dumps(record, indent=2) + "\n")
            print("\n".join(describe(record)))
        elif args.command == "show":
            print("\n".join(describe(read(args.authority))))
        else:
            record = grant(read(args.authority), args.pr, args.action, args.instruction)
            args.authority.write_text(json.dumps(record, indent=2) + "\n")
            print(f"Granted {args.action} on #{args.pr}.")
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"authority: {error}\n")


if __name__ == "__main__":
    main()

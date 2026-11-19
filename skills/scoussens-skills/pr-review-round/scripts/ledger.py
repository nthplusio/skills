#!/usr/bin/env python3
"""ledger.py -- what one round remembers for the next one.

Run a round:

    python3 ledger.py start <base>                          # open a round; prints its id
    python3 ledger.py record <round-id> <assessments.json>  # save every assessment, clean ones too
    python3 ledger.py end <round-id> --scope <scope.json> --report <round.json>

`record` refuses a round id that `start` did not print. `end` closes the round
only when every scoped PR is in the report with complete request coverage and
no unhandled request; otherwise it prints each blocker and exits 1.

Read a round's history:

    python3 ledger.py open               # findings still open, per PR
    python3 ledger.py heads              # head SHA each PR carried at its last review
    python3 ledger.py precision          # how often my findings were overstated
    python3 ledger.py rounds             # round history, newest first

Every field here exists because it changes what the *next* round does. A field
that does not name the step whose behaviour it changes does not belong in the
ledger, and per-author or per-week aggregates deliberately are not recorded.

    head/base -> matching source permits reuse of code checks, not the verdict:
                 refresh discussion, issue evidence and accepted decisions.
    status    -> `open` findings are what step 3 verifies first, instead of
                 re-deriving them from the review body. `fixed` drafts the
                 dismissal evidence.
    overstated-> the only field that audits the reviewer. After a few rounds it
                 gives a per-tier precision rate; a tier that runs consistently
                 overstated has the wrong depth in the risk table.
    unblock   -> the smallest change that makes the finding false, carried
                 forward so a blocked PR's next round opens with the path off it.
    writes    -> what review_write.py posted and land.py requested. The report
                 uses it to tell the round's own reviews from ones posted from
                 the same account some other way, which step 7 must not claim.

State lives outside the repository, so git worktrees share one ledger and
nothing is ever committed:

    ~/.local/state/pr-review-round/<owner>__<repo>/{findings,assessments,rounds,writes}.jsonl
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from review_config import resolve as review_config

STATUSES = ("open", "fixed", "overstated", "pre-existing", "withdrawn")
DECISIONS = {
    "code": "Needs code changes", "evidence": "Needs evidence",
    "decision": "Needs owner decision", "reviewer-incomplete": "Review incomplete",
    "ready": "Source review complete",
}


def validate_assessment(assessment):
    """Validate saved decisions at the boundary, including clean assessments."""
    for field in ("number", "head", "base", "assessed_at", "evidence_inputs", "decisions"):
        if field not in assessment:
            raise ValueError(f"assessment requires {field}")
    if type(assessment["number"]) is not int or assessment["number"] <= 0:
        raise ValueError("assessment requires a positive PR number")
    for field in ("head", "base"):
        if not re.fullmatch(r"[0-9a-f]{40}", assessment[field]):
            raise ValueError(f"assessment {field} must be a full SHA")
    if not all(assessment["evidence_inputs"].get(field) for field in ("forge", "issues", "policy")):
        raise ValueError("assessment requires forge updatedAt, refreshed issue evidence and review policy revisions")
    if not assessment["decisions"]:
        raise ValueError("include a ready decision for a clean assessment")
    for decision in assessment["decisions"]:
        if decision.get("kind") not in DECISIONS:
            raise ValueError("use code, evidence, decision, reviewer-incomplete, or ready; not hold")
        for field in ("id", "axis", "criterion", "severity", "owner", "summary", "unblock", "effort", "proposed_action"):
            if not decision.get(field):
                raise ValueError(f"decision requires {field}")
        if decision["severity"] not in ("blocking", "should-fix", "non-blocking"):
            raise ValueError("severity must be blocking, should-fix or non-blocking")
        evidence = decision.get("evidence") or {}
        if not all(evidence.get(field) for field in ("source", "at", "observation")):
            raise ValueError("decision evidence requires source, at and observation")
        posted = decision.get("posted_action")
        if posted and not all(posted.get(field) for field in ("action", "url", "at")):
            raise ValueError("posted action requires actual action, URL and time")
        waiver = decision.get("waiver")
        if waiver and (not all(waiver.get(field) for field in ("actor", "source", "at", "scope"))
                       or waiver.get("criterion") != decision["criterion"]):
            raise ValueError("waiver must name actor, source, time, scope and this exact criterion")
        if waiver and decision["kind"] not in ("evidence", "decision"):
            raise ValueError("a waiver cannot substitute for code verification or unfinished review")
    gate = assessment.get("approval_gate")
    if gate and not all(gate.get(k) for k in ("owner", "source", "reason")):
        raise ValueError("approval gate requires owner, source and reason from repository setup/policy")
    from review_requests import DISPOSITIONS
    request_keys = []
    for request in assessment.get("request_events", []):
        if not all(request.get(k) for k in ("event_id", "target", "at", "disposition")):
            raise ValueError("request event requires event_id, target, at and disposition")
        if request["disposition"] not in DISPOSITIONS or not request["target"].startswith(("user:", "team:")):
            raise ValueError("use a local request disposition and a user/team target; forge responses come from readback")
        request_keys.append((str(request["event_id"]), request["target"]))
    if len(request_keys) != len(set(request_keys)):
        raise ValueError("duplicate handled request event")
    ids = [d["id"] for d in assessment["decisions"]]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate decision IDs")
    if any(d["kind"] == "ready" for d in assessment["decisions"]) and len(ids) != 1:
        raise ValueError("ready cannot mask another decision")


def unresolved(assessment):
    validate_assessment(assessment)
    return [d for d in assessment["decisions"] if d["kind"] != "ready" and not d.get("waiver")
            and (d["severity"] == "blocking" or d["kind"] == "reviewer-incomplete")]


def target_state(repo, ref):
    """Read the actual target ref, independently of a PR's baseRefOid."""
    from urllib.parse import quote
    target = {"ref": ref, "sha": None}
    if not repo or not ref:
        return target
    result = subprocess.run(["gh", "api", f"repos/{repo}/git/ref/heads/{quote(ref, safe='')}"],
                            capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        if (result.returncode == 0 and data["ref"] == "refs/heads/" + ref
                and data["object"]["type"] == "commit"
                and re.fullmatch(r"[0-9a-f]{40}", data["object"]["sha"])):
            target["sha"] = data["object"]["sha"]
    except (ValueError, KeyError, TypeError):
        pass
    return target


def target_matches(inputs, target):
    return bool(target and target.get("ref") and re.fullmatch(r"[0-9a-f]{40}", target.get("sha") or "")
                and inputs.get("target") == target)


def assessment_current(assessment, head, base, evidence_inputs):
    validate_assessment(assessment)
    return (assessment["head"] == head and assessment["base"] == base
            and target_matches(assessment["evidence_inputs"], evidence_inputs.get("target"))
            and assessment["evidence_inputs"] == evidence_inputs)


def marker_current(assessment, head):
    """A request disposition holds for its request event at the assessed head.

    Deliberately narrower than assessment_current. Discussion, requirement, policy
    and target-branch movement make the recommendation stale, not the handoff.
    """
    return bool(assessment and head) and assessment.get("head") == head


def record_assessment(rid, assessment, repo=None):
    validate_assessment(assessment)
    _append("assessments", {**assessment, "round": rid, "recorded_at": _now()}, repo)


def assessment_history(repo=None):
    return _read("assessments", repo)


def assessments(repo=None):
    return {a["number"]: a for a in assessment_history(repo)}


def handled_requests(repo=None):
    """Last handled event per PR/target, retaining its original evidence identity."""
    latest = {}
    for assessment in assessment_history(repo):
        for marker in assessment.get("request_events", []):
            latest[(assessment["number"], marker["target"])] = {
                **marker, **{k: assessment[k] for k in ("number", "head", "base", "evidence_inputs", "assessed_at")}}
    return list(latest.values())


def check_authority(authority, repo, number, action, possible_landing=False):
    if (authority.get("repository") != repo or number not in authority.get("prs", [])
            or action not in authority.get("actions", []) or not authority.get("instruction")
            or (possible_landing and authority.get("possible_landing") is not True)):
        raise ValueError("out-of-scope authority: record instruction, repository, exact PRs, action and possible landing")


def check_clearance(bundle, repo, number, head, base, forge_revision, target):
    if bundle.get("repository") != repo:
        raise ValueError("assessment belongs to a different repository")
    matches = [a for a in bundle.get("assessments", []) if a.get("number") == number]
    if len(matches) != 1:
        raise ValueError("one current assessment required for this PR")
    assessment = matches[0]
    validate_assessment(assessment)
    if assessment["evidence_inputs"]["policy"] != review_config(".", bundle.get("review_config"))["revision"]:
        raise ValueError("review policy changed; resolve configuration and review affected checks again")
    if (assessment["head"] != head or assessment["base"] != base
            or assessment["evidence_inputs"]["forge"] != forge_revision):
        raise ValueError("assessment source or discussion changed; refresh evidence and review again")
    if not target_matches(assessment["evidence_inputs"], target):
        raise ValueError("actual target ref changed or unavailable; refresh integration evidence")
    blockers = unresolved(assessment)
    if blockers:
        raise ValueError("unresolved decisions: " + "; ".join(f'{d["owner"]}: {d["unblock"]}' for d in blockers))
    return assessment


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_slug():
    r = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner",
                        "-q", ".nameWithOwner"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def state_dir(repo=None):
    repo = repo or repo_slug()
    if not repo:
        raise SystemExit("could not determine the repo (is `gh` authenticated?)")
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    d = os.path.join(base, "pr-review-round", repo.replace("/", "__"))
    os.makedirs(d, exist_ok=True)
    return d


def _path(name, repo=None):
    return os.path.join(state_dir(repo), f"{name}.jsonl")


def _read(name, repo=None):
    p = _path(name, repo)
    if not os.path.exists(p):
        return []
    out = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn line must not take down the round
    return out


def _append(name, rec, repo=None):
    with open(_path(name, repo), "a") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------- writes

def record_write(repo, number, action, head, url=None):
    """One accepted write by a helper. Never a proposed action or a failed request."""
    _append("writes", {"number": number, "action": action, "head": head, "url": url, "at": _now()}, repo)


def writes(repo=None):
    return _read("writes", repo)


# ---------------------------------------------------------------- rounds

def round_start(base, repo=None):
    """Stamp the start of a round and return its id. The id is what findings
    are tagged with, so `--since` can be the round itself rather than a
    guessed clock window."""
    rid = _now()
    _append("rounds", {"round": rid, "base": base, "started_at": rid,
                       "ended_at": None, "prs": []}, repo)
    return rid


def round_known(rid, repo=None):
    return any(r.get("round") == rid for r in _read("rounds", repo))


def open_round(base=None, repo=None):
    """The most recent round that was started and never closed."""
    pending = [r for r in _read("rounds", repo)
               if not r.get("ended_at") and (base is None or r.get("base") == base)]
    return sorted(pending, key=lambda r: r.get("started_at") or "")[-1] if pending else None


def round_blockers(reconciliation):
    """Every reason the collected records cannot close a round, one line per PR and cause."""
    blockers = []
    for row in reconciliation:
        state = row.get("handoffs", {})
        if state.get("coverage") != "complete":
            blockers.append(f'PR #{row["number"]}: request coverage unknown '
                            f'({", ".join(state.get("gaps") or ["not collected"])})')
        if state.get("unhandled") != 0:
            waiting = [f'{r["event_id"]} -> {r["target"]}' for r in state.get("requests", [])
                       if r.get("disposition") == "unhandled"]
            blockers.append(f'PR #{row["number"]}: {state.get("unhandled", "unknown")} unhandled request(s)'
                            + (f' ({"; ".join(waiting)})' if waiting else ""))
    return blockers


def round_end(rid, prs, repo=None, *, reconciliation):
    """Close only a fully accounted round; incomplete reviews stay explicit."""
    if len(reconciliation) != len(prs) or {r["number"] for r in reconciliation} != set(prs):
        raise ValueError("reconcile every scoped PR before closing the round")
    blockers = round_blockers(reconciliation)
    if blockers:
        raise ValueError(blockers[0] + "; round remains unfinished")
    rounds = _read("rounds", repo)
    for r in rounds:
        if r.get("round") == rid:
            r["ended_at"] = _now()
            r["prs"] = prs
    with open(_path("rounds", repo), "w") as f:
        for r in rounds:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


def last_round(base=None, repo=None):
    """The most recent completed round. Its `ended_at` is the honest lower
    bound for "what merged during this round" -- a fixed clock window catches
    PRs that landed before the round opened."""
    done = [r for r in _read("rounds", repo)
            if r.get("ended_at") and (base is None or r.get("base") == base)]
    return sorted(done, key=lambda r: r["ended_at"])[-1] if done else None


# -------------------------------------------------------------- findings

def record(rid, findings, repo=None):
    """findings: list of dicts with at least {pr, head, summary, status}.
    Optional: file, line, tier, severity, unblock."""
    n = 0
    for f in findings:
        if f.get("status") not in STATUSES:
            raise SystemExit(f"bad status {f.get('status')!r}; use one of {STATUSES}")
        rec = {"round": rid, "recorded_at": _now()}
        rec.update(f)
        _append("findings", rec, repo)
        n += 1
    return n


def open_findings(repo=None):
    """Latest status per (pr, file, line, summary), keeping only `open`.
    This is what step 3 checks at head first."""
    latest = {}
    for f in _read("findings", repo):
        key = (f.get("pr"), f.get("file"), f.get("line"), f.get("summary"))
        latest[key] = f
    out = {}
    for f in latest.values():
        if f.get("status") == "open":
            out.setdefault(f["pr"], []).append(f)
    return out


def heads(repo=None):
    """Head SHA each PR carried the last time it was reviewed."""
    out = {}
    for f in _read("findings", repo):
        if f.get("pr") and f.get("head"):
            out[f["pr"]] = f["head"]
    for number, assessment in assessments(repo).items():
        out[number] = assessment["head"]
    return out


def precision(repo=None):
    """Per-tier counts of resolved findings. A tier with a high overstated rate
    is being reviewed at the wrong depth -- that is the risk table's problem,
    not the author's."""
    agg = {}
    for f in _read("findings", repo):
        st = f.get("status")
        if st in ("open", "withdrawn"):
            continue
        t = agg.setdefault(f.get("tier") or "?", {s: 0 for s in STATUSES})
        t[st] += 1
    return agg


# ------------------------------------------------------------------ cli

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]

    if cmd == "start":
        if len(sys.argv) != 3:
            sys.exit("usage: ledger.py start <base>")
        pending = open_round(sys.argv[2])
        if pending:
            print(f'note: round {pending["round"]} on {sys.argv[2]} was started and never closed', file=sys.stderr)
        print(round_start(sys.argv[2]))
        return

    if cmd == "record":
        if len(sys.argv) != 4:
            sys.exit("usage: ledger.py record <round-id> <assessments.json>")
        rid, repo = sys.argv[2], repo_slug()
        if not repo:
            sys.exit("could not determine the repo (is `gh` authenticated?)")
        try:
            with open(sys.argv[3]) as f:
                bundle = json.load(f)
        except (OSError, ValueError) as error:
            sys.exit(f"could not read the assessments: {error}")
        if (not isinstance(bundle, dict) or bundle.get("repository") != repo
                or not isinstance(bundle.get("assessments"), list)):
            sys.exit(f'expected {{"repository": "{repo}", "assessments": [...]}}; nothing recorded')
        if not round_known(rid, repo):
            sys.exit(f"unknown round {rid!r}; run `ledger.py start <base>` and pass the id it prints. Nothing recorded")
        # Validate every assessment before writing any, so a bad one records nothing.
        for item in bundle["assessments"]:
            try:
                validate_assessment(item)
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                number = item.get("number") if isinstance(item, dict) else "?"
                sys.exit(f"PR #{number}: {error}; nothing recorded")
        for item in bundle["assessments"]:
            record_assessment(rid, item, repo)
        print(f'recorded {len(bundle["assessments"])} assessment(s) in round {rid}')
        return

    if cmd == "end":
        rid, rest = (sys.argv[2] if len(sys.argv) > 2 else None), sys.argv[3:]
        options = dict(zip(rest[::2], rest[1::2]))
        if not rid or len(rest) != 4 or set(options) != {"--scope", "--report"}:
            sys.exit("usage: ledger.py end <round-id> --scope <scope.json> --report <round.json>")
        repo = repo_slug()
        if not repo:
            sys.exit("could not determine the repo (is `gh` authenticated?)")
        try:
            with open(options["--scope"]) as f:
                scope = json.load(f)
            with open(options["--report"]) as f:
                report = json.load(f)
        except (OSError, ValueError) as error:
            sys.exit(f"could not read the scope or report: {error}")
        if (not isinstance(scope, list) or any(type(n) is not int for n in scope) or not isinstance(report, list)
                or any(not isinstance(r, dict) or r.get("repository") != repo for r in report)):
            sys.exit(f"expected a JSON list of PR numbers and round_report.py output for {repo}; round remains unfinished")
        if not round_known(rid, repo):
            sys.exit(f"unknown round {rid!r}; run `ledger.py rounds` for the ids on file")
        rows = {r.get("number"): r for r in report}
        blockers = [f"PR #{n}: not in the report; run round_report.py again with --scope" for n in scope if n not in rows]
        blockers += round_blockers([rows[n] for n in scope if n in rows])
        if not blockers:
            try:
                round_end(rid, scope, repo, reconciliation=[rows[n] for n in scope])
            except ValueError as error:
                blockers.append(str(error))
        if blockers:
            print(f"round {rid} remains unfinished: {len(blockers)} blocker(s)")
            for blocker in blockers:
                print("  " + blocker)
            sys.exit(1)
        print(f"round {rid} closed with {len(scope)} PR(s)")
        return

    if cmd == "open":
        o = open_findings()
        if not o:
            print("no open findings carried forward -- this is a first round, or "
                  "every prior finding was resolved")
            return
        print("Open findings from previous rounds. Verify each at the CURRENT head")
        print("before re-stating it; a finding is not live because it is recorded.\n")
        for pr in sorted(o):
            print(f"#{pr}")
            for f in o[pr]:
                loc = f.get("file") or ""
                if loc and f.get("line"):
                    loc += f":{f['line']}"
                print(f"   [{f.get('tier','?')}/{f.get('severity','?')}] {f.get('summary','')}")
                if loc:
                    print(f"      at {loc} (as of {f.get('head','?')[:9]})")
                if f.get("unblock"):
                    print(f"      unblock: {f['unblock']}")
        return

    if cmd == "heads":
        h = heads()
        if not h:
            print("no recorded heads yet")
            return
        print("Head SHA per PR at its last review. Matching head/base permits code reuse;")
        print("refresh discussion, issue evidence and accepted decisions before reusing a verdict.\n")
        for pr in sorted(h):
            print(f"  #{pr:<7} {h[pr]}")
        return

    if cmd == "precision":
        agg = precision()
        if not agg:
            print("no resolved findings yet -- precision needs a few rounds of "
                  "outcomes before it means anything")
            return
        print(f'{"TIER":<8}{"FIXED":<8}{"OVERSTATED":<12}{"PRE-EXIST":<11}RATE')
        for t in sorted(agg):
            c = agg[t]
            tot = sum(c.values())
            rate = f"{100 * c['overstated'] / tot:.0f}% overstated" if tot else "-"
            print(f'{t:<8}{c["fixed"]:<8}{c["overstated"]:<12}'
                  f'{c["pre-existing"]:<11}{rate}')
        print("\nA tier running consistently overstated is being reviewed at the")
        print("wrong depth. Adjust the risk table, not the authors.")
        return

    if cmd == "rounds":
        rs = sorted(_read("rounds"), key=lambda r: r.get("started_at") or "", reverse=True)
        if not rs:
            print("no rounds recorded yet")
            return
        for r in rs[:20]:
            end = r.get("ended_at") or "(unfinished)"
            print(f'  {r.get("started_at")}  ->  {end:<22} base={r.get("base")} '
                  f'prs={len(r.get("prs") or [])}')
        return

    if cmd == "where":
        print(state_dir())
        return

    sys.exit(f"unknown command {cmd!r}\n\n{__doc__}")


if __name__ == "__main__":
    main()

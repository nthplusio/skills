#!/usr/bin/env python3
"""ledger.py -- what one round remembers for the next one.

Run a round:

    python3 ledger.py start <base>                          # open a round; prints its id
    python3 ledger.py record <round-id> <assessments.json>  # save every assessment, clean ones too
    python3 ledger.py end <round-id> --scope <scope.json> --report <round.json>

`record` refuses a round id that `start` did not print. `end` closes the round
only when every scoped PR is in the report with complete request coverage and
no unhandled request, and every related pair in `<scope>.related.json` has a
relation on an assessment from this round; otherwise it prints each blocker
and exits 1.

Settle owner decisions in one batch:

    python3 ledger.py waiting [--assessments <f>]  # open owner/evidence decisions across PRs, one line each
    python3 ledger.py decide <key> --answer accept|waive|rescope|reject --instruction "<owner's words>"
                             [--scope "<what it covers>"] [--actor <who>] [--assessments <f>]

`decide` appends a new assessment for every PR whose latest saved assessment carries
the decision `<key>` (its `subject`, or `<pr>/<decision id>`), and prints each PR as
clear or still blocked by the gates it names.

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
                 The freshness check uses it so the round's own posts do not
                 count as new discussion. `accepted` names a moved base or
                 discussion the write judged benign.

State lives outside the repository, so git worktrees share one ledger and
nothing is ever committed:

    ~/.local/state/pr-review-round/<owner>__<repo>/{findings,assessments,rounds,writes}.jsonl
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from review_config import KINDS, MODES, resolve as review_config, supports

STATUSES = ("open", "fixed", "overstated", "pre-existing", "withdrawn")
DECISIONS = {
    "code": "Needs code changes", "evidence": "Needs evidence",
    "decision": "Needs owner decision", "reviewer-incomplete": "Review incomplete",
    "ready": "Source review complete",
}
# The decisions an owner's answer can settle, and the answers. Code and unfinished review need a new head or a review.
OWNED = ("evidence", "decision")
ANSWERS = ("accept", "waive", "rescope", "reject")
# How a PR stands against another one. Superseded and duplicate PRs are never ready.
RELATIONS = {
    "supersedes": "Supersedes", "superseded-by": "Superseded by", "duplicates": "Duplicates",
    "conflicts": "Conflicts with", "depends-on": "Depends on", "independent": "Overlaps, independent of",
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
        if waiver and decision["kind"] not in OWNED:
            raise ValueError("a waiver cannot substitute for code verification or unfinished review")
        rejected = decision.get("rejected")
        if rejected and (not all(rejected.get(field) for field in ("actor", "source", "at"))
                         or waiver or decision["kind"] not in OWNED):
            raise ValueError("a rejection names actor, source and time, on an unwaived evidence or owner decision")
        subject = decision.get("subject")
        if subject is not None and (not isinstance(subject, str) or not re.fullmatch(r"[a-z][a-z0-9-]*:\S+", subject)):
            raise ValueError('subject is a shared key such as "adr:183", the same on every PR the decision gates')
        if decision.get("recommend") not in (None, *ANSWERS):
            raise ValueError("recommend is one of " + ", ".join(ANSWERS))
    carried = assessment.get("carried")
    if carried is not None and (
            not isinstance(carried, dict) or carried.get("head") != assessment["head"]
            or not re.fullmatch(r"[0-9a-f]{40}", carried.get("from_head") or "") or not carried.get("check")
            or not carried.get("at") or not isinstance(carried.get("commits"), list)
            or not (carried["commits"] or carried["from_head"] == carried["head"]) or not assessment.get("provenance")):
        raise ValueError("carried requires from_head, this head, the check, its commits (none only when the head is "
                         "unchanged) and time, plus a provenance")
    for finding in assessment.get("verified_findings", []):
        if (type(finding.get("comment")) is not int or finding.get("status") not in ("fixed", "overstated")
                or not finding.get("file") or type(finding.get("line")) is not int or not finding.get("observation")):
            raise ValueError("verified finding requires the inline comment id, status fixed or overstated, "
                             "the file and line checked at the head, and the observation")
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
    for relation in assessment.get("relations", []):
        if (type(relation.get("pr")) is not int or relation["pr"] == assessment["number"]
                or relation.get("kind") not in RELATIONS or not relation.get("evidence")):
            raise ValueError("relation requires another PR number, a kind from "
                             + ", ".join(RELATIONS) + " and the evidence that decided it")
        if relation["kind"] in ("superseded-by", "duplicates") and not any(
                d["kind"] != "ready" and d["severity"] == "blocking" and not d.get("waiver")
                for d in assessment["decisions"]):
            raise ValueError(f'a PR {relation["kind"]} #{relation["pr"]} cannot be ready; record a blocking '
                             "decision naming who closes or keeps which PR")


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


def assessment_current(assessment, head, base, evidence_inputs):
    """Exact match of saved and collected inputs, for offline rendering of records nobody classified."""
    validate_assessment(assessment)
    target = evidence_inputs.get("target") or {}
    return (assessment["head"] == head and assessment["base"] == base
            and bool(re.fullmatch(r"[0-9a-f]{40}", target.get("sha") or ""))
            and assessment["evidence_inputs"] == evidence_inputs)


def marker_current(assessment, head):
    """A request disposition holds for its request event at the assessed head.

    Deliberately narrower than the assessment's freshness. Discussion, requirement,
    policy and target-branch movement can make the recommendation stale, not the handoff.
    """
    return bool(assessment and head) and assessment.get("head") == head


def record_assessment(rid, assessment, repo=None):
    validate_assessment(assessment)
    _append("assessments", {**assessment, "round": rid, "recorded_at": _now()}, repo)


def assessment_history(repo=None):
    return _read("assessments", repo)


def assessments(repo=None):
    return {a["number"]: a for a in assessment_history(repo)}


def decision_key(number, decision):
    """What an owner's answer names: a `subject` shared across PRs (one ADR gating three PRs),
    otherwise this PR's own decision id."""
    return decision.get("subject") or f'{number}/{decision["id"]}'


def waiting(items):
    """Open owner and evidence decisions across PRs, one entry per key, in the order first seen.
    A rejected decision still blocks but was answered, so it is not asked again."""
    groups = {}
    for item in items:
        for decision in unresolved(item):
            if decision["kind"] not in OWNED or decision.get("rejected"):
                continue
            key = decision_key(item["number"], decision)
            group = groups.setdefault(key, {"key": key, "prs": [], "kind": decision["kind"], "owner": decision["owner"],
                                            "question": decision["summary"], "criterion": decision["criterion"],
                                            "recommend": decision.get("recommend"), "unblock": decision["unblock"]})
            if item["number"] not in group["prs"]:
                group["prs"].append(item["number"])
    return list(groups.values())


def waiting_lines(groups):
    """The batch to ask in one message: one line per decision, then its answer forms."""
    lines = []
    for g in groups:
        prs = ", ".join(f"#{n}" for n in g["prs"])
        lines.append(f'{g["key"]} · {prs} · {g["owner"]}: {g["question"]} ({g["criterion"]})')
        lines.append(f'    Recommended: {g["recommend"] + " · " if g["recommend"] else ""}{g["unblock"]}')
        lines.append(f'    Answer: "accept {g["key"]}", "waive {g["key"]}", '
                     f'"rescope {g["key"]} to <follow-up>" or "reject {g["key"]}"')
    return lines


def decide(key, answer, instruction, scope=None, actor=None, repo=None, bundle=None):
    """Record an owner's answer on every saved assessment carrying the decision `key`, as a new record.

    accept, waive and rescope add a waiver whose source is the owner's words; reject records the answer
    and leaves the decision blocking. A code or reviewer-incomplete decision refuses every answer, and
    nothing is recorded. With `bundle`, the round's assessments file, its matching entries are replaced
    too, so the write helpers see the answer; each must first equal the saved record. Returns
    [(number, unresolved decisions)] for every PR the key matched."""
    if answer not in ANSWERS:
        raise ValueError("answer is one of " + ", ".join(ANSWERS))
    if not instruction:
        raise ValueError("record the owner's exact words with --instruction")
    if answer == "rescope" and not scope:
        raise ValueError("rescope needs --scope naming what moves to the follow-up")
    at, touched, changed = _now(), [], []
    for number, saved in sorted(assessments(repo).items()):
        if not any(decision_key(number, d) == key for d in saved["decisions"]):
            continue
        item = json.loads(json.dumps({k: v for k, v in saved.items() if k not in ("round", "recorded_at")}))
        fresh = False
        for d in item["decisions"]:
            if decision_key(number, d) != key:
                continue
            if d["kind"] not in OWNED:
                raise ValueError(f'#{number} {d["id"]} is a {d["kind"]} decision; an owner answer cannot settle it. '
                                 "Nothing recorded")
            if (d.get("waiver") or {}).get("answer") == answer or (answer == "reject" and d.get("rejected")):
                continue
            fresh = True
            d.pop("waiver", None)
            d.pop("rejected", None)
            who = actor or d["owner"]
            if answer == "reject":
                d["rejected"] = {"actor": who, "source": instruction, "at": at}
            else:
                d["waiver"] = {"actor": who, "source": instruction, "at": at, "answer": answer,
                               "scope": scope or f'{answer} {key} on #{number} at {item["head"]}',
                               "criterion": d["criterion"]}
        validate_assessment(item)
        touched.append(item)
        if fresh:
            changed.append((saved, item))
    if not touched:
        raise ValueError(f"no saved assessment carries decision {key}; `ledger.py waiting` lists the open ones")
    if bundle is not None:
        entries = {a.get("number"): a for a in bundle.get("assessments", [])}
        for saved, item in changed:
            if item["number"] in entries and entries[item["number"]] != {
                    k: v for k, v in saved.items() if k not in ("round", "recorded_at")}:
                raise ValueError(f'#{item["number"]} in the assessments file differs from its saved record; '
                                 "run `ledger.py record` with it first. Nothing recorded")
    for saved, item in changed:
        record_assessment(saved["round"], item, repo)
    if bundle is not None:
        answered = {item["number"]: item for _, item in changed}
        bundle["assessments"] = [answered.get(a.get("number"), a) for a in bundle.get("assessments", [])]
    return [(item["number"], unresolved(item)) for item in touched]


def handled_requests(repo=None):
    """Last handled event per PR/target, retaining its original evidence identity."""
    latest = {}
    for assessment in assessment_history(repo):
        for marker in assessment.get("request_events", []):
            latest[(assessment["number"], marker["target"])] = {
                **marker, **{k: assessment[k] for k in ("number", "head", "base", "evidence_inputs", "assessed_at")}}
    return list(latest.values())


# The work level the user picked caps the writes. Approval is a separate yes/no at
# every level above assess. The writes outside the level table are separate: each one
# is governed by a decision kind in review_config.KINDS (auto, ask or never), or, with
# no kind, needs its own one-PR grant. authority.py writes and extends the record.
LEVELS = {
    "assess": (),
    "review": ("comment", "request-changes"),
    "moderate": ("comment", "request-changes", "update-branch", "push-fix"),
    "major": ("comment", "request-changes", "update-branch", "push-fix", "delegate"),
}
SEPARATE = ("dismiss-bot", "dismiss-human", "enqueue", "enable-auto-merge", "sweep-auto-merge", "reapprove",
            "land-own-pr")
# Writes that can make a PR merge, directly or by releasing an author's auto-merge.
LANDING = ("approve", *SEPARATE)
GOVERNED = {action: kind for kind, entry in KINDS.items() for action in entry["actions"]}


def standing_actions(level, approvals, policies):
    """The writes a level, approvals choice and policies allow on every scoped PR without asking."""
    actions = [*LEVELS[level], *(["approve"] if approvals and level != "assess" else [])]
    return actions + [action for kind, mode in policies.items() if mode == "auto" and supports(kind, level, approvals)
                      for action in KINDS[kind]["actions"]]


def possible_landing(actions, grants):
    return any(action in LANDING for action in [*actions, *(g["action"] for g in grants)])


def check_authority(authority, repo, number, action):
    if authority.get("version") != 2:
        raise ValueError("authority file predates decision policies; regenerate it with authority.py init")
    level, approvals, policies = authority.get("level"), authority.get("approvals"), authority.get("policies")
    if level not in LEVELS or type(approvals) is not bool or not isinstance(policies, dict) \
            or set(policies) != set(KINDS) or any(mode not in MODES for mode in policies.values()):
        raise ValueError("authority requires a work level, approvals and a mode for every decision kind; "
                         "regenerate it with authority.py init")
    grants = authority.get("grants", [])
    actions = standing_actions(level, approvals, policies)
    if authority.get("actions") != actions or authority.get("possible_landing") != possible_landing(actions, grants):
        raise ValueError("authority actions do not follow from its level and policies; it was edited by hand. "
                         "Regenerate it with authority.py init, and add one-PR writes with authority.py grant")
    if authority.get("repository") != repo or number not in authority.get("prs", []) or not authority.get("instruction"):
        raise ValueError("out-of-scope authority: record instruction, repository and exact PRs")
    kind = GOVERNED.get(action)
    if kind and policies[kind] == "never":
        raise ValueError(f"{action} on #{number} is refused: the {kind} policy is never")
    if action in actions:
        return
    if action not in SEPARATE:
        raise ValueError(f"{action} is outside the {level} level" + (" without approvals" if action == "approve" else "")
                         + "; ask before raising the level")
    if any(g.get("pr") == number and g.get("action") == action for g in grants):
        return
    ask = f'the {kind} policy is ask. Ask: "{KINDS[kind]["question"]}"' if kind else "it needs its own instruction"
    raise ValueError(f"{action} on #{number} is held: {ask} After a yes, record it with "
                     f'authority.py grant <authority.json> --pr {number} --action {action} --instruction "<their words>"')


def current_assessment(bundle, repo, number, live):
    """The PR's one saved assessment and its freshness verdict; raises when the verdict is Stale."""
    from freshness import Stale, classify
    if bundle.get("repository") != repo:
        raise ValueError("assessment belongs to a different repository")
    matches = [a for a in bundle.get("assessments", []) if a.get("number") == number]
    if len(matches) != 1:
        raise ValueError("one current assessment required for this PR")
    assessment = matches[0]
    validate_assessment(assessment)
    discussed = assessment["evidence_inputs"]["forge"] != live.get("forge")
    verdict = classify(assessment, live, policy=review_config(".", bundle.get("review_config"))["revision"],
                       repo=repo, number=number, writes=writes(repo) if discussed else [])
    if isinstance(verdict, Stale):
        raise ValueError(verdict.message())
    return assessment, verdict


def require_resolved(assessment):
    blockers = unresolved(assessment)
    if blockers:
        raise ValueError("unresolved decisions: " + "; ".join(f'{d["owner"]}: {d["unblock"]}' for d in blockers))


def check_clearance(bundle, repo, number, live):
    """Fresh or Benign verdict for a current assessment with no unresolved decisions; raises otherwise."""
    assessment, verdict = current_assessment(bundle, repo, number, live)
    require_resolved(assessment)
    return verdict


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gh_said(stderr=""):
    """The `gh` a helper ran and the first line of its error. A helper can run a different `gh` than
    the shell does, or run without the shell's token, so `gh auth status` passing there proves nothing here."""
    path = shutil.which("gh")
    if not path:
        return "no `gh` on PATH"
    lines = (stderr or "").strip().splitlines()
    return f"{path} said: {lines[0]}" if lines else f"{path} failed without an error message"


_repo_error = ""


def repo_slug():
    global _repo_error
    try:
        r = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner",
                            "-q", ".nameWithOwner"], capture_output=True, text=True)
    except OSError as error:
        _repo_error = str(error)
        return ""
    _repo_error = r.stderr
    return r.stdout.strip() if r.returncode == 0 else ""


def no_repo():
    return (f"could not determine the repo: {gh_said(_repo_error)}. If `gh auth status` passes in your shell, "
            "this process runs a different `gh` or lacks its token")


def state_dir(repo=None):
    repo = repo or repo_slug()
    if not repo:
        raise SystemExit(no_repo())
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

def record_write(repo, number, action, head, url=None, accepted=None, conditions=None):
    """One accepted write by a helper. Never a proposed action or a failed request.
    `accepted` is a Benign freshness record: the moved inputs the write went ahead on, and why.
    `conditions` is what an own-PR landing observed for each condition it went ahead on."""
    _append("writes", {"number": number, "action": action, "head": head, "url": url, "at": _now(),
                       **({"accepted": accepted} if accepted else {}),
                       **({"conditions": conditions} if conditions else {})}, repo)


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


def relation_blockers(pairs, recorded):
    """Each related pair needs a relation on either PR's assessment from this round."""
    latest = {a["number"]: a for a in recorded}
    judged = lambda n, other: any(r["pr"] == other for r in (latest.get(n) or {}).get("relations", []))
    return [f'PRs #{a} and #{b}: related ({", ".join(pair["files"][:3] + pair["mentions"]) or "named"}) '
            f"but neither assessment records a relation to the other"
            for pair in pairs for a, b in [pair["prs"]] if not (judged(a, b) or judged(b, a))]


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


def heads(repo=None, before=None):
    """Head SHA each PR carried the last time it was reviewed. With `before`, only what was
    recorded earlier than that time: a round's own records are not an earlier look."""
    earlier = lambda record: before is None or (record.get("recorded_at") or "") < before
    out = {}
    for f in _read("findings", repo):
        if f.get("pr") and f.get("head") and earlier(f):
            out[f["pr"]] = f["head"]
    for assessment in assessment_history(repo):
        if earlier(assessment):
            out[assessment["number"]] = assessment["head"]
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
            sys.exit(no_repo())
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

    if cmd in ("waiting", "decide"):
        import argparse
        parser = argparse.ArgumentParser(prog=f"ledger.py {cmd}")
        if cmd == "decide":
            parser.add_argument("key", help='the decision\'s subject, such as "adr:183", or "<pr>/<decision id>"')
            parser.add_argument("--answer", required=True, choices=ANSWERS)
            parser.add_argument("--instruction", required=True, help="the owner's exact words")
            parser.add_argument("--scope", help="what the answer covers; required for rescope")
            parser.add_argument("--actor", help="who answered; defaults to each decision's owner")
        parser.add_argument("--assessments", help="the round's assessments file; decide updates it in place")
        args = parser.parse_args(sys.argv[2:])
        repo = repo_slug()
        if not repo:
            sys.exit(no_repo())
        bundle = None
        if args.assessments:
            try:
                with open(args.assessments) as f:
                    bundle = json.load(f)
            except (OSError, ValueError) as error:
                sys.exit(f"could not read the assessments: {error}")
            if not isinstance(bundle, dict) or bundle.get("repository") != repo:
                sys.exit(f'expected {{"repository": "{repo}", "assessments": [...]}}')
        if cmd == "waiting":
            groups = waiting(bundle["assessments"] if bundle else assessments(repo).values())
            print(f"Waiting on you: {len(groups)} decision(s)" if groups else "Waiting on you: nothing")
            for line in waiting_lines(groups):
                print("  " + line)
            return
        try:
            results = decide(args.key, args.answer, args.instruction, args.scope, args.actor, repo, bundle)
        except ValueError as error:
            sys.exit(str(error))
        if bundle is not None:
            with open(args.assessments, "w") as f:
                json.dump(bundle, f, indent=2)
        print(f'{args.key}: {args.answer}, from "{args.instruction}"')
        for number, blockers in results:
            print(f"  #{number} " + ("still blocked: " + "; ".join(
                f'{d["owner"]}: {d["unblock"]} ({decision_key(number, d)}'
                + (", rejected" if d.get("rejected") else "") + ")" for d in blockers) if blockers
                                    else "clear: nothing unresolved in its saved assessment; with approvals on, "
                                         "approve it with review_write.py approve"))
        return

    if cmd == "end":
        rid, rest = (sys.argv[2] if len(sys.argv) > 2 else None), sys.argv[3:]
        options = dict(zip(rest[::2], rest[1::2]))
        if not rid or len(rest) != 4 or set(options) != {"--scope", "--report"}:
            sys.exit("usage: ledger.py end <round-id> --scope <scope.json> --report <round.json>")
        repo = repo_slug()
        if not repo:
            sys.exit(no_repo())
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
        from related import related_path
        try:
            pairs = json.loads(related_path(options["--scope"]).read_text())
        except (OSError, ValueError):
            blockers.append(f'related pairs unknown: {related_path(options["--scope"])} unreadable; '
                            "run queue.py <base> --scope <scope.json> again")
        else:
            blockers += relation_blockers(pairs, [a for a in assessment_history(repo) if a.get("round") == rid])
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

#!/usr/bin/env python3
"""gh_ci_baseline.py --workflow <file-or-id> [--repo owner/name] [--branch B]
                    [--protected-branch B] [--limit N] [--json]

The baseline and contract pass for GitHub Actions. For one workflow it prints:

  1. the required status checks on the protected branch, read from BOTH places
     GitHub keeps them, and whether this workflow emits each one;
  2. the recent runs, split by event and by the workflow revision they ran, with
     failures, cancellations and re-runs counted apart from the baseline;
  3. per event, elapsed time, queue time, raw runner time and rounded job-minutes
     over successful runs of the current workflow revision;
  4. per job, when it starts and ends relative to the run, so serial
     dependencies show without parsing `needs:`, and the steps that dominate it.

It only reads. Every call is a GET through `gh api` or `gh run list`.

Run it once per workflow, before forming any opinion about where time goes.
Without --workflow it lists the repository's workflows and their state, and exits.
"""
import argparse, json, math, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Percentiles from a handful of runs are noise that reads like a measurement.
# Below these sizes the report shows the individual values instead.
MIN_FOR_P50 = 5
MIN_FOR_P90 = 10
TOP_STEPS = 5


def gh(*args):
    """Run gh and return (ok, parsed JSON or stderr text)."""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout).strip()
    try:
        return True, json.loads(proc.stdout) if proc.stdout.strip() else None
    except ValueError:
        return True, proc.stdout


def api(path):
    return gh("api", "-H", "Accept: application/vnd.github+json", path)


def ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def seconds(start, end):
    a, b = ts(start), ts(end)
    return (b - a).total_seconds() if a and b else None


def fmt(secs):
    if secs is None:
        return "?"
    secs = int(round(secs))
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60:02d}s"
    return f"{secs // 3600}h {secs % 3600 // 60:02d}m"


def nearest_rank(values, pct):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def summarize(values):
    """p50/p90 only where the sample earns them; otherwise the raw values."""
    values = [v for v in values if v is not None]
    n = len(values)
    if n == 0:
        return "no runs"
    if n < MIN_FOR_P50:
        listed = ", ".join(fmt(v) for v in sorted(values))
        return f"n={n}: {listed} (too few for percentiles)"
    parts = [f"p50 {fmt(nearest_rank(values, 50))}"]
    if n >= MIN_FOR_P90:
        parts.append(f"p90 {fmt(nearest_rank(values, 90))}")
    parts.append(f"range {fmt(min(values))}–{fmt(max(values))}")
    return f"n={n}: " + ", ".join(parts)


def median(values):
    values = [v for v in values if v is not None]
    return nearest_rank(values, 50) if values else None


# --- contracts ---------------------------------------------------------------

def required_checks(repo, branch):
    """Required contexts from rulesets and from classic protection, separately.

    GitHub stores them in two unrelated places, and each API is blind to the
    other. `branches/<b>` can say `protected: true` while listing no required
    checks, because a ruleset is what requires them. Reading one source and
    reporting "no required checks" is the commonest wrong answer here.
    """
    out = {"branch": branch, "rulesets": None, "classic": None, "strict": None, "notes": []}

    ok, rules = api(f"repos/{repo}/rules/branches/{branch}")
    if ok and isinstance(rules, list):
        contexts = []
        for rule in rules:
            if rule.get("type") == "required_status_checks":
                params = rule.get("parameters") or {}
                contexts += [c["context"] for c in params.get("required_status_checks", [])]
                if params.get("strict_required_status_checks_policy"):
                    out["strict"] = True
        out["rulesets"] = contexts
    else:
        out["notes"].append(f"rulesets unreadable: {rules}")

    ok, classic = api(f"repos/{repo}/branches/{branch}/protection/required_status_checks")
    if ok and isinstance(classic, dict):
        out["classic"] = classic.get("contexts") or []
        if classic.get("strict"):
            out["strict"] = True
    elif "Branch not protected" in str(classic) or "Required status checks not enabled" in str(classic):
        out["classic"] = []
    else:
        # A plain 404 or 403 here means no permission to read protection, not
        # an unprotected branch. Report it as unknown rather than as empty.
        out["notes"].append(f"classic protection unreadable (needs admin read): {classic}")
    return out


# --- runs --------------------------------------------------------------------

def list_workflows(repo):
    ok, data = api(f"repos/{repo}/actions/workflows?per_page=100")
    if not ok:
        sys.exit(f"cannot list workflows: {data}")
    return data.get("workflows", [])


def workflow_blob(repo, path, ref, cache):
    """The workflow file's blob sha at a ref. Two runs with the same blob ran
    the same topology; a different blob means history from another design."""
    if ref not in cache:
        ok, data = api(f"repos/{repo}/contents/{path}?ref={ref}")
        cache[ref] = data.get("sha") if ok and isinstance(data, dict) else None
    return cache[ref]


def fetch_jobs(repo, run_id):
    # The default filter returns the latest attempt only, which is the one
    # whose verdict counts; earlier attempts are counted through `attempt`.
    ok, data = api(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")
    return data.get("jobs", []) if ok and isinstance(data, dict) else []


def measure(run, jobs):
    """Run-level figures from its jobs. Elapsed runs from the attempt's start
    to the last job's end, so a run re-opened later is not inflated."""
    start = run.get("startedAt") or run.get("createdAt")
    # A skipped job reports start == end. Counting it as a zero-second job
    # drags its median to nothing, so it is named and kept out of durations.
    skipped = sorted({j["name"] for j in jobs if j.get("conclusion") == "skipped"})
    done = [j for j in jobs
            if j.get("started_at") and j.get("completed_at") and j.get("conclusion") != "skipped"]
    if not done:
        return None
    last_end = max(j["completed_at"] for j in done)
    job_rows = []
    for j in done:
        duration = seconds(j["started_at"], j["completed_at"])
        steps = [
            (s["name"], seconds(s.get("started_at"), s.get("completed_at")))
            for s in j.get("steps") or []
            if s.get("started_at") and s.get("completed_at")
        ]
        labels = j.get("labels") or []
        job_rows.append({
            "name": j["name"],
            "conclusion": j.get("conclusion"),
            "labels": labels,
            "self_hosted": "self-hosted" in labels,
            "queue": seconds(j.get("created_at"), j["started_at"]),
            "start_offset": seconds(start, j["started_at"]),
            "end_offset": seconds(start, j["completed_at"]),
            "duration": duration,
            "steps": steps,
        })
    hosted = [r for r in job_rows if not r["self_hosted"]]
    return {
        "elapsed": seconds(start, last_end),
        "runner_time": sum(r["duration"] or 0 for r in job_rows),
        # GitHub bills each hosted job rounded up to the whole minute. This is
        # the rounded figure before any OS multiplier, allowance or free tier.
        "rounded_minutes": sum(math.ceil((r["duration"] or 0) / 60) for r in hosted),
        "queue": max((r["queue"] or 0) for r in job_rows),
        "jobs": job_rows,
        "skipped": skipped,
    }


# --- report ------------------------------------------------------------------

def print_contracts(checks, emitted):
    print(f"\n## Required checks on {checks['branch']}")
    for source in ("rulesets", "classic"):
        contexts = checks[source]
        if contexts is None:
            print(f"  {source:9} unknown")
        elif not contexts:
            print(f"  {source:9} none")
        else:
            for c in contexts:
                mark = "emitted by this workflow" if c in emitted else "NOT emitted by this workflow"
                print(f"  {source:9} {c}  — {mark}")
    if checks["strict"]:
        print("  strict: a PR must be up to date with the branch before it can merge")
    for note in checks["notes"]:
        print(f"  ! {note}")


def print_baseline(event, rows):
    print(f"\n## Baseline — {event}, successful runs of the current workflow revision")
    if not rows:
        print("  no comparable runs")
        return
    print(f"  elapsed          {summarize([r['elapsed'] for r in rows])}")
    print(f"  queue (longest)  {summarize([r['queue'] for r in rows])}")
    print(f"  raw runner time  {summarize([r['runner_time'] for r in rows])}")
    minutes = [r["rounded_minutes"] for r in rows]
    print(f"  rounded minutes  median {median(minutes)} per run (hosted jobs, before multipliers)")

    by_job = {}
    for r in rows:
        for j in r["jobs"]:
            by_job.setdefault(j["name"], []).append(j)
    total_runner = median([r["runner_time"] for r in rows]) or 1
    print("\n  Jobs in start order. 'starts' and 'ends' are offsets from the run's start;")
    print("  a job that starts when another ends is waiting on it.")
    for name, jobs in sorted(by_job.items(), key=lambda kv: median([j["start_offset"] for j in kv[1]]) or 0):
        dur = median([j["duration"] for j in jobs])
        print(f"\n  {name}  [{','.join(jobs[0]['labels'])}]")
        print(f"    starts +{fmt(median([j['start_offset'] for j in jobs]))}, "
              f"ends +{fmt(median([j['end_offset'] for j in jobs]))}, "
              f"{100 * (dur or 0) / total_runner:.0f}% of runner time")
        print(f"    duration {summarize([j['duration'] for j in jobs])}")
        steps = {}
        for j in jobs:
            for step, secs in j["steps"]:
                steps.setdefault(step, []).append(secs)
        ranked = sorted(steps.items(), key=lambda kv: -(median(kv[1]) or 0))[:TOP_STEPS]
        for step, secs in ranked:
            step_med = median(secs) or 0
            if step_med < 1:
                continue
            print(f"      {fmt(step_med):>8}  {100 * step_med / (dur or 1):3.0f}%  {step[:70]}")

    skipped = sorted({name for r in rows for name in r["skipped"]})
    if skipped:
        print(f"\n  skipped on this event: {', '.join(skipped)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="owner/name; defaults to the current checkout's repository")
    ap.add_argument("--workflow", help="workflow file name (ci.yml) or id")
    ap.add_argument("--branch", help="only runs on this head branch")
    ap.add_argument("--protected-branch", help="branch whose required checks to read; defaults to the default branch")
    ap.add_argument("--limit", type=int, default=30, help="runs to fetch (default 30)")
    ap.add_argument("--json", action="store_true", help="print the raw measurements as JSON")
    args = ap.parse_args()

    repo = args.repo
    if not repo:
        ok, data = gh("repo", "view", "--json", "nameWithOwner")
        if not ok:
            sys.exit(f"cannot resolve the repository; pass --repo: {data}")
        repo = data["nameWithOwner"]
    ok, meta = gh("repo", "view", repo, "--json", "visibility,defaultBranchRef")
    if not ok:
        sys.exit(f"cannot read {repo}: {meta}")
    default_branch = meta["defaultBranchRef"]["name"]

    workflows = list_workflows(repo)
    if not args.workflow:
        # `gh run list` keeps showing runs of deleted workflows, so a name seen
        # in run history is not proof the workflow still exists. This is.
        print(f"Workflows in {repo}:")
        for w in workflows:
            print(f"  {w['path']:45} {w['state']:20} {w['name']}")
        print("\nPass --workflow <file> to measure one.")
        return 2
    match = [w for w in workflows
             if args.workflow in (str(w["id"]), w["path"], w["path"].rsplit("/", 1)[-1], w["name"])]
    if not match:
        sys.exit(f"no workflow {args.workflow!r} in {repo}; run without --workflow to list them")
    workflow = match[0]

    run_args = ["run", "list", "-R", repo, "--workflow", str(workflow["id"]), "--limit", str(args.limit),
                "--json", "databaseId,event,headBranch,headSha,status,conclusion,createdAt,startedAt,attempt"]
    if args.branch:
        run_args += ["--branch", args.branch]
    ok, runs = gh(*run_args)
    if not ok:
        sys.exit(f"cannot list runs: {runs}")

    blobs = {}
    current = workflow_blob(repo, workflow["path"], default_branch, blobs)
    completed = [r for r in runs if r["status"] == "completed"]
    for r in completed:
        r["revision"] = "current" if workflow_blob(repo, workflow["path"], r["headSha"], blobs) == current else "other"

    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = list(pool.map(lambda r: fetch_jobs(repo, r["databaseId"]), completed))
    for r, j in zip(completed, jobs):
        r["measure"] = measure(r, j)

    checks = required_checks(repo, args.protected_branch or default_branch)
    emitted = {j["name"] for r in completed if r.get("measure") for j in r["measure"]["jobs"]}

    if args.json:
        json.dump({"repo": repo, "workflow": workflow, "visibility": meta["visibility"],
                   "required_checks": checks, "runs": completed}, sys.stdout, indent=2)
        print()
        return 0

    print(f"# {repo} — {workflow['path']} ({workflow['state']})")
    print(f"visibility {meta['visibility'].lower()}; default branch {default_branch}")
    if meta["visibility"] == "PUBLIC":
        print("public repository: standard GitHub-hosted runners are not billed")
    if workflow["state"] != "active":
        print(f"! this workflow is {workflow['state']}; its history describes a pipeline that no longer runs")
    print_contracts(checks, emitted)

    print(f"\n## Runs fetched: {len(runs)} ({len(runs) - len(completed)} still in progress)")
    events = sorted({r["event"] for r in completed})
    for event in events:
        rows = [r for r in completed if r["event"] == event]
        tally = {}
        for r in rows:
            key = (r["revision"], r["conclusion"])
            tally[key] = tally.get(key, 0) + 1
        retried = sum(1 for r in rows if (r.get("attempt") or 1) > 1)
        parts = ", ".join(f"{n} {rev}/{concl}" for (rev, concl), n in sorted(tally.items()))
        print(f"  {event:20} {parts}; {retried} re-run")
    if any(r["revision"] == "other" for r in completed):
        print("  'other' runs used a different workflow file and are kept out of the baseline")

    for event in events:
        rows = [r["measure"] for r in completed
                if r["event"] == event and r["revision"] == "current"
                and r["conclusion"] == "success" and r.get("measure")]
        print_baseline(event, rows)

    print("\n## Not measured here")
    print("  cache hits — the jobs API does not report them; read the cache step logs")
    print("  critical path — inferred from job start and end offsets; confirm against `needs:`")
    print("  billed cost — rounded minutes exclude OS multipliers, allowances and free tiers")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Agent-free registry operations. Semantic extraction and evidence review stay with readers."""

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from contracts import VERSION, schema, validate

ROOT = ".business-rules"
KINDS = {"sources": "source", "rules": "rule", "decisions": "decision", "bindings": "binding"}
SCHEMA_PATH = "schema/registry-v1.json"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def tool_digest():
    here = Path(__file__).resolve().parent
    return digest({name: (here / name).read_text() for name in ("rules.py", "contracts.py")})


def parse(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON number {value}")))


def load(path):
    return parse(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".rules-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def locked(root):
    """A crashed writer releases its lock; retries converge from validated files."""
    import fcntl
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".write.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps require a timezone")
    return result


def git(repo, *args):
    run = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if run.returncode:
        raise ValueError(run.stderr.strip())
    return run.stdout


def commit(repo, ref):
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def read_registry(root):
    docs = {"config.json": load(root / "config.json"), SCHEMA_PATH: load(root / SCHEMA_PATH)}
    for folder in KINDS:
        for path in sorted((root / folder).rglob("*.json")):
            docs[path.relative_to(root).as_posix()] = load(path)
    return docs


def at_commit(repo, sha):
    names = git(repo, "ls-tree", "-r", "--name-only", sha, ROOT).splitlines()
    docs = {}
    for name in names:
        rel = name[len(ROOT) + 1:]
        if rel in ("config.json", SCHEMA_PATH) or (rel.split("/")[0] in KINDS and rel.endswith(".json")):
            docs[rel] = parse(git(repo, "show", f"{sha}:{name}"))
    if "config.json" not in docs or SCHEMA_PATH not in docs:
        raise ValueError(f"{sha}: no registry; bootstrap it separately before PR auditing")
    return docs


def records(docs, folder):
    return [v for k, v in docs.items() if k.startswith(folder + "/")]


def target(rule, revision):
    item = rule["revisions"][revision - 1]
    return {"rule_id": rule["id"], "revision": revision,
            "digest": digest({"id": rule["id"], "domain": rule["domain"], "revision": item})}


def validate_registry(docs, baseline=None):
    config = docs["config.json"]
    validate("config", config)
    if config["tool_digest"] != tool_digest():
        raise ValueError("validator digest differs from config; use the pinned tool bundle")
    if docs.get(SCHEMA_PATH) != schema():
        raise ValueError("exported schema differs from the pinned tool bundle")
    authorities = {}
    domain_heads = {}
    for authority in config["authorities"]:
        aid, domain = authority["id"], authority["domain"]
        if aid in authorities:
            raise ValueError(f"duplicate authority {aid}")
        previous = domain_heads.get(domain)
        if authority["supersedes"] != previous:
            raise ValueError(f"{aid}: authority transfer must name the previous domain authority")
        if previous and authority["authorized_by"] != authorities[previous]["actor"]:
            raise ValueError(f"{aid}: transfer requires previous owner's recorded authorization")
        if not previous and authority["authorized_by"] is not None:
            raise ValueError(f"{aid}: bootstrap owner has no predecessor")
        authorities[aid] = authority
        domain_heads[domain] = aid
    if not authorities:
        raise ValueError("designate at least one domain owner with source evidence")
    rules, sources, decisions = {}, {}, {}
    for path, value in docs.items():
        if path in ("config.json", SCHEMA_PATH):
            continue
        folder = path.split("/")[0]
        validate(KINDS[folder], value)
        expected = f"{folder}/{value['id']}.json"
        if folder == "rules":
            expected = f"rules/{value['domain']}/{value['id']}.json"
        if path != expected:
            raise ValueError(f"{path}: canonical path is {expected}")
        collection = {"rules": rules, "sources": sources, "decisions": decisions}.get(folder)
        if collection is not None:
            if value["id"] in collection:
                raise ValueError(f"duplicate {folder} ID {value['id']}")
            collection[value["id"]] = value
    claims = set()
    for rule in rules.values():
        if rule["domain"] not in domain_heads or not rule["revisions"]:
            raise ValueError(f"{rule['id']}: missing domain authority or revisions")
        for number, revision in enumerate(rule["revisions"], 1):
            if revision["revision"] != number:
                raise ValueError(f"{rule['id']}: revisions must be consecutive")
            key = (revision["source_id"], revision["claim_id"])
            if key in claims or key[0] not in sources:
                raise ValueError(f"{rule['id']}: duplicate claim or missing source {key}")
            claims.add(key)
            for relation in revision["relations"]:
                other = rules.get(relation["rule_id"])
                if not other or relation["revision"] > len(other["revisions"]):
                    raise ValueError(f"{rule['id']}: unresolved revision relationship")
    edges = {(r["id"], v["revision"]): [(e["rule_id"], e["revision"]) for e in v["relations"]]
             for r in rules.values() for v in r["revisions"]}
    seen, active = set(), set()

    def visit(node):
        if node in active:
            raise ValueError(f"cyclic meaning-changing relationship at {node}")
        if node in seen:
            return
        active.add(node)
        for child in edges[node]:
            visit(child)
        active.remove(node)
        seen.add(node)
    for node in edges:
        visit(node)
    terminal = {}
    for decision in decisions.values():
        authority = authorities.get(decision["authority_id"])
        source = sources.get(decision["source_id"])
        if not authority or decision["actor"] != authority["actor"]:
            raise ValueError(f"{decision['id']}: actor does not match designated authority")
        if not source or not source["authority_evidence"]:
            raise ValueError(f"{decision['id']}: source lacks verified authority evidence")
        if timestamp(decision["effective_at"]) < timestamp(decision["decided_at"]):
            raise ValueError(f"{decision['id']}: effective time precedes decision")
        if not decision["targets"]:
            raise ValueError(f"{decision['id']}: decision needs exact targets")
        for item in decision["targets"]:
            check_target(item, rules)
            if rules[item["rule_id"]]["domain"] != authority["domain"]:
                raise ValueError(f"{decision['id']}: authority belongs to another domain")
            key = (item["rule_id"], item["revision"])
            if decision["kind"] != "waive":
                if key in terminal:
                    raise ValueError(f"{key}: already decided; propose a new revision")
                terminal[key] = decision
        if decision["kind"] == "waive":
            if decision["waiver"] is None or len(decision["targets"]) != 1:
                raise ValueError("waiver needs one rule revision and an exact finding/commit scope")
            if timestamp(decision["waiver"]["expires_at"]) <= timestamp(decision["effective_at"]):
                raise ValueError("waiver must expire after taking effect")
        elif decision["waiver"] is not None:
            raise ValueError("only waiver decisions carry waiver scope")
    for rule in rules.values():
        approvals = [terminal.get((rule["id"], v["revision"])) for v in rule["revisions"]]
        approvals = [d for d in approvals if d and d["kind"] == "approve"]
        times = [timestamp(d["effective_at"]) for d in approvals]
        if times != sorted(set(times)):
            raise ValueError(f"{rule['id']}: approved revisions require increasing effective times")
        for revision in rule["revisions"]:
            approval = terminal.get((rule["id"], revision["revision"]))
            if not approval or approval["kind"] != "approve":
                continue
            for relation in revision["relations"]:
                parent = terminal.get((relation["rule_id"], relation["revision"]))
                if not parent or parent["kind"] != "approve" or timestamp(parent["effective_at"]) > timestamp(approval["effective_at"]):
                    raise ValueError("approved rules need approved relationship targets effective no later than themselves")
                if relation["type"] == "supersedes" and relation["rule_id"] != rule["id"]:
                    retirements = [t for t in approval["targets"] if t["rule_id"] == relation["rule_id"]
                                   and rules[t["rule_id"]]["revisions"][t["revision"] - 1]["action"] == "retire"]
                    if not retirements:
                        raise ValueError("cross-rule replacement must approve predecessor retirement in the same decision")
    for binding in records(docs, "bindings"):
        validate_binding(binding, rules)
    if baseline is not None:
        validate_baseline(docs, baseline, authorities, domain_heads)
    return rules, decisions


def check_target(item, rules):
    rule = rules.get(item["rule_id"])
    if not rule or item["revision"] > len(rule["revisions"]) or item != target(rule, item["revision"]):
        raise ValueError(f"{item['rule_id']}@{item['revision']}: target digest or revision differs")


def validate_baseline(docs, baseline, authorities, domain_heads):
    old_config = baseline["config.json"]
    new_config = docs["config.json"]
    for key in ("registry_id", "schema_version", "tool_version", "tool_digest"):
        if old_config[key] != new_config[key]:
            raise ValueError(f"baseline {key} changed; requires an explicit registry migration")
    old_authorities = old_config["authorities"]
    if new_config["authorities"][:len(old_authorities)] != old_authorities:
        raise ValueError("baseline authority history changed")
    old_ids = {a["id"] for a in old_authorities}
    for authority in new_config["authorities"][len(old_authorities):]:
        bootstrap = authority["supersedes"] is None and not any(
            rule["domain"] == authority["domain"] for rule in records(docs, "rules"))
        if bootstrap:
            continue
        if authority["supersedes"] not in old_ids:
            raise ValueError("new authority needs a transfer from the trusted baseline; bootstrap domains separately")
    for path, old in baseline.items():
        if path == "config.json":
            continue
        new = docs.get(path)
        if path.startswith("rules/") and new:
            prefix = {**new, "revisions": new["revisions"][:len(old["revisions"])]}
            if prefix == old:
                continue
        if new != old:
            raise ValueError(f"baseline history changed or removed: {path}")
    for path, decision in docs.items():
        if path.startswith("decisions/") and path not in baseline:
            authority = authorities[decision["authority_id"]]
            if domain_heads[authority["domain"]] != authority["id"]:
                raise ValueError(f"{decision['id']}: superseded owner cannot approve new decisions")


def validate_binding(binding, rules):
    payload = {k: v for k, v in binding.items() if k != "id"}
    catalogue = binding["catalogue"]
    if binding["id"] != digest(payload) or binding["catalogue_digest"] != digest(catalogue):
        raise ValueError("binding content digest differs")
    if not isinstance(catalogue.get("meta"), dict) or catalogue["meta"].get("commit") != binding["code_commit"]:
        raise ValueError("binding commit differs from catalogue")
    observations = catalogue.get("rules")
    if not isinstance(observations, list) or any(not isinstance(r, dict) or "id" not in r for r in observations):
        raise ValueError("catalogue needs identified observation records")
    ids = [r["id"] for r in observations]
    mappings = binding["mappings"]
    if len(set(ids)) != len(ids) or sorted(ids) != sorted(m["observation_id"] for m in mappings):
        raise ValueError("mapping must cover every observation exactly once")
    for mapping in mappings:
        count = len(mapping["candidates"])
        if len({digest(c) for c in mapping["candidates"]}) != count:
            raise ValueError("mapping candidates must be distinct")
        if not ((mapping["status"] == "matched" and count == 1) or
                (mapping["status"] == "ambiguous" and count >= 2) or
                (mapping["status"] == "unmatched" and count == 0)):
            raise ValueError("mapping status and candidate count disagree")
        for item in mapping["candidates"]:
            check_target(item, rules)


def selected(docs, as_of):
    rules = {r["id"]: r for r in records(docs, "rules")}
    result = {}
    for decision in records(docs, "decisions"):
        if decision["kind"] != "approve" or timestamp(decision["effective_at"]) > timestamp(as_of):
            continue
        for item in decision["targets"]:
            if item["revision"] > result.get(item["rule_id"], {}).get("revision", 0):
                result[item["rule_id"]] = item
    return {rid: item for rid, item in result.items()
            if rules[rid]["revisions"][item["revision"] - 1]["action"] != "retire"}


def add(docs, path, value):
    if path in docs and docs[path] != value:
        raise ValueError(f"immutable record already exists: {path}")
    docs[path] = value


def mutate(args):
    root = Path(args.registry).resolve()
    with locked(root):
        docs = read_registry(root)
        validate_registry(docs)
        before = copy.deepcopy(docs)
        if args.command == "source":
            value = load(args.input)
            validate("source", value)
            add(docs, f"sources/{value['id']}.json", value)
        elif args.command == "capture":
            capture = load(args.input)
            validate("capture", capture)
            source, claim = capture["source"], capture["claim"]
            if claim["source_id"] != source["id"]:
                raise ValueError("capture source and claim source differ")
            add(docs, f"sources/{source['id']}.json", source)
            path = f"rules/{capture['domain']}/{capture['rule_id']}.json"
            rule = docs.setdefault(path, {"schema_version": 1, "id": capture["rule_id"],
                                          "domain": capture["domain"], "revisions": []})
            prior = [v for v in rule["revisions"] if (v["source_id"], v["claim_id"]) ==
                     (claim["source_id"], claim["claim_id"])]
            if prior:
                if prior[0] != {"revision": prior[0]["revision"], **claim}:
                    raise ValueError("source claim replay differs; retain it and use a new claim ID for a correction")
            else:
                rule["revisions"].append({"revision": len(rule["revisions"]) + 1, **claim})
        elif args.command == "decide":
            decision = load(args.input)
            validate("decision", decision)
            add(docs, f"decisions/{decision['id']}.json", decision)
        elif args.command == "reconcile":
            catalogue = load(args.catalogue)
            mappings = load(args.mapping) if args.mapping else [
                {"observation_id": r["id"], "status": "unmatched", "candidates": []}
                for r in catalogue["rules"]]
            value = {"schema_version": 1, "catalogue_digest": digest(catalogue),
                     "code_commit": catalogue["meta"]["commit"], "catalogue": catalogue, "mappings": mappings}
            value["id"] = digest(value)
            add(docs, f"bindings/{value['id']}.json", value)
        validate_registry(docs, before)
        changed = [p for p in docs if docs[p] != before.get(p)]
        # Sources land before consumers. An interrupted capture leaves an unused source,
        # not a dangling revision; replay completes the same operation.
        for path in sorted(changed, key=lambda p: (not p.startswith("sources/"), p)):
            write(root / path, docs[path])
        print(json.dumps({"changed": changed, "registry_digest": digest(docs)}))


def same_code(repo, first, second):
    # Recording an observation or waiver changes Git HEAD. Ignore only registry
    # metadata, never source, tests, or application configuration.
    commit(repo, first)
    return not git(repo, "diff", "--name-only", first, second, "--", ".", f":(exclude){ROOT}").strip()


def make_report(args):
    base_sha, head_sha = commit(args.repo, args.base), commit(args.repo, args.head)
    base, head = at_commit(args.repo, base_sha), at_commit(args.repo, head_sha)
    validate_registry(base)
    validate_registry(head, base)
    context = {"schema_version": 1, "base_commit": base_sha, "head_commit": head_sha,
               "base_registry_digest": digest(base), "head_registry_digest": digest(head), "as_of": args.as_of}
    timestamp(args.as_of)
    policies = {"base": selected(base, args.as_of), "head": selected(head, args.as_of)}
    if args.command == "audit-context":
        print(json.dumps({**context, "scope": [], "exclusions": [], "limitations": [],
                          "binding_ids": [], "assessments": [], "unrecorded": [], "selected_policies": policies}, indent=2))
        return
    audit = load(args.input)
    validate("audit", audit)
    for key, value in context.items():
        if audit[key] != value:
            raise ValueError(f"audit {key} is stale or differs from requested context")
    if not audit["scope"]:
        raise ValueError("audit must name the examined scope")
    expected = {(code_side, policy_side, rid, item["revision"])
                for code_side, policy_side in (("base", "base"), ("head", "base"), ("head", "head"))
                for rid, item in policies[policy_side].items()}
    assessed, ids, findings = set(), set(), []
    decisions = {d["id"]: d for d in records(head, "decisions")}
    for assessment in audit["assessments"]:
        key = (assessment["code_side"], assessment["policy_side"], assessment["rule_id"], assessment["revision"])
        if key not in expected or key in assessed or assessment["id"] in ids:
            raise ValueError("assessment repeats or names a non-selected policy comparison")
        assessed.add(key)
        ids.add(assessment["id"])
        outcome = assessment["outcome"]
        if outcome != "not-assessed" and (not assessment["evidence"] or assessment["method"] == "not-assessed"):
            raise ValueError("assessed outcomes require evidence and a method")
        if outcome in ("violation", "confirmed-conflict", "potential-conflict") and not assessment["scenario"]:
            raise ValueError("violations and conflicts require a concrete scenario")
        disposition = "must-resolve" if outcome in ("violation", "confirmed-conflict") else "advisory"
        if assessment["waiver_id"]:
            decision = decisions.get(assessment["waiver_id"])
            rule_target = policies[assessment["policy_side"]][assessment["rule_id"]]
            code_sha = base_sha if assessment["code_side"] == "base" else head_sha
            if (not decision or decision["kind"] != "waive" or decision["targets"] != [rule_target]
                    or decision["waiver"]["finding_id"] != assessment["id"]
                    or not same_code(args.repo, decision["waiver"]["code_commit"], code_sha)
                    or not timestamp(decision["effective_at"]) <= timestamp(args.as_of) < timestamp(decision["waiver"]["expires_at"])):
                raise ValueError("waiver is missing, expired, or does not cover this exact finding/revision/commit")
            disposition = "waived"
        findings.append({**assessment, "disposition": disposition})
    for finding in findings:
        if ((finding["code_side"], finding["policy_side"], finding["outcome"], finding["disposition"]) ==
                ("base", "base", "violation", "must-resolve") and any(
                    f["code_side"] == "head" and f["policy_side"] == "base" and
                    f["rule_id"] == finding["rule_id"] and f["revision"] == finding["revision"] and
                    f["outcome"] == "conforms" for f in findings)):
            finding["disposition"] = "resolved-in-head"
        replacement = policies["head"].get(finding["rule_id"])
        if (finding["code_side"], finding["policy_side"], finding["outcome"], finding["disposition"]) != ("head", "base", "violation", "must-resolve"):
            continue
        if replacement and replacement["revision"] != finding["revision"] and any(
                f["code_side"] == "head" and f["policy_side"] == "head" and
                f["rule_id"] == finding["rule_id"] and f["revision"] == replacement["revision"] and
                f["outcome"] == "conforms" for f in findings):
            finding["disposition"] = "approved-policy-change"
    missing = [{"id": "gap-" + digest([c, p, r, v])[:24], "code_side": c, "policy_side": p, "rule_id": r, "revision": v,
                "outcome": "not-assessed", "disposition": "advisory", "method": "not-assessed",
                "evidence": [], "scenario": None, "waiver_id": None}
               for c, p, r, v in sorted(expected - assessed)]
    changed = git(args.repo, "diff", "--name-only", base_sha, head_sha).splitlines()
    stale = []
    bindings = {b["id"]: b for b in records(head, "bindings")}
    if len(set(audit["binding_ids"])) != len(audit["binding_ids"]) or any(b not in bindings for b in audit["binding_ids"]):
        raise ValueError("select distinct binding IDs present in the head registry")
    for bid in audit["binding_ids"]:
        binding = bindings[bid]
        try:
            fresh = same_code(args.repo, binding["code_commit"], head_sha)
        except ValueError:
            fresh = False
        if not fresh:
            stale.append(binding["id"])
    dependencies = head["config.json"]["dependencies"]
    report = {**audit, "assessments": findings + missing, "changed_paths": changed,
              "stale_bindings": stale, "external_dependencies_not_assessed": dependencies,
              "ci_gate": "not-evaluated", "evidence_trust": "reader-supplied; schema validation is not execution proof"}
    if any(f["disposition"] == "must-resolve" for f in findings):
        report["summary"] = "must-resolve"
    elif not expected or missing or stale or any(f["outcome"] != "conforms" for f in findings) or audit["unrecorded"] or dependencies or audit["exclusions"] or audit["limitations"]:
        report["summary"] = "review-required"
    else:
        report["summary"] = "reported-conformance-within-scope"
    validate("report", report)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write(out / "audit.json", report)
    lines = ["# Business rule audit", "", f"**{report['summary']}**", "",
             f"Code: `{base_sha}` → `{head_sha}`. Policy as of `{args.as_of}`.", "",
             "Reader-supplied evidence; this report does not execute checks or establish production conformance.", "",
             "## Scope", *[f"- {s}" for s in audit["scope"]], "", "## Assessments"]
    for finding in report["assessments"]:
        lines += [f"- **{finding['rule_id']}@{finding['revision']}** — code {finding['code_side']}, policy {finding['policy_side']}: "
                  f"{finding['outcome']} ({finding['disposition']})."]
        if finding.get("scenario"):
            lines.append(f"  - Scenario: {finding['scenario']}")
        for evidence in finding.get("evidence", []):
            lines.append(f"  - {evidence['locator']}: {evidence['text']}")
    lines += ["", "## Limits and uncovered behavior",
              *[f"- {s}" for s in audit["exclusions"] + audit["limitations"]],
              *[f"- Unrecorded: {u['description']}" for u in audit["unrecorded"]],
              f"- {len(stale)} binding snapshots have changed or unavailable source; recheck affected code.",
              f"- {len(dependencies)} external policy dependencies were not assessed.",
              "- CI gate: not evaluated. Successful report generation means the report contract is valid."]
    (out / "audit.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"summary": report["summary"], "json": str(out / "audit.json"), "markdown": str(out / "audit.md")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schema", help="print the canonical JSON Schema definitions")
    commands.add_parser("tool-digest", help="print the exact two-file validator bundle digest")
    init = commands.add_parser("init", help="initialize a registry using an explicitly designated owner")
    init.add_argument("--registry", required=True)
    init.add_argument("--id", required=True)
    init.add_argument("--domain", required=True)
    init.add_argument("--owner", required=True)
    init.add_argument("--authority-source", required=True)
    for name in ("source", "capture", "decide", "reconcile", "validate", "select", "target"):
        command = commands.add_parser(name)
        command.add_argument("--registry", required=True)
        if name in ("source", "capture", "decide"):
            command.add_argument("--input", required=True)
        if name == "reconcile":
            command.add_argument("--catalogue", required=True)
            command.add_argument("--mapping")
        if name == "validate":
            command.add_argument("--baseline", help="trusted Git commit, requires --repo")
            command.add_argument("--repo")
        if name == "select":
            command.add_argument("--as-of", required=True)
        if name == "target":
            command.add_argument("--rule", required=True)
            command.add_argument("--revision", type=int, required=True)
    for name in ("audit-context", "report"):
        command = commands.add_parser(name)
        for flag in ("repo", "base", "head", "as-of"):
            command.add_argument("--" + flag, required=True)
        if name == "report":
            command.add_argument("--input", required=True)
            command.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.command == "schema":
        print(json.dumps(schema(), indent=2))
    elif args.command == "tool-digest":
        print(tool_digest())
    elif args.command == "init":
        root = Path(args.registry).resolve()
        with locked(root):
            config = {"schema_version": 1, "tool_version": VERSION, "tool_digest": tool_digest(),
                      "registry_id": args.id, "dependencies": [], "authorities": [
                          {"id": "owner-1", "domain": args.domain, "actor": args.owner,
                           "source": args.authority_source, "supersedes": None, "authorized_by": None}]}
            validate_registry({"config.json": config, SCHEMA_PATH: schema()})
            if (root / "config.json").exists() and load(root / "config.json") != config:
                raise ValueError("registry already initialized with different settings")
            write(root / "config.json", config)
            write(root / "schema" / "registry-v1.json", schema())
            if not (root / ".gitignore").exists():
                (root / ".gitignore").write_text(".write.lock\n.rules-*\n")
        print("initialized; owner designation is a recorded assertion, not identity authentication")
    elif args.command in ("source", "capture", "decide", "reconcile"):
        mutate(args)
    elif args.command in ("audit-context", "report"):
        make_report(args)
    else:
        docs = read_registry(Path(args.registry))
        baseline = None
        if args.command == "validate" and args.baseline:
            if not args.repo:
                raise ValueError("--baseline requires --repo")
            baseline = at_commit(args.repo, commit(args.repo, args.baseline))
            validate_registry(baseline)
        rules, _ = validate_registry(docs, baseline)
        if args.command == "select":
            timestamp(args.as_of)
            print(json.dumps(selected(docs, args.as_of), indent=2))
        elif args.command == "target":
            if args.rule not in rules or not 1 <= args.revision <= len(rules[args.rule]["revisions"]):
                raise ValueError("unknown rule revision")
            print(json.dumps(target(rules[args.rule], args.revision), indent=2))
        else:
            print(json.dumps({"valid": True, "rules": len(rules), "registry_digest": digest(docs),
                              "baseline_checked": baseline is not None, "semantic_consistency": "not-assessed"}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"rules: {error}", file=sys.stderr)
        sys.exit(2)

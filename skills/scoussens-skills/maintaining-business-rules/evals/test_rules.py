"""Public-CLI contracts and a disposable application's conversation-to-audit loop."""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
CLI = SKILL / "scripts" / "rules.py"
AS_OF = "2026-03-01T12:00:00Z"
RULE = "BR-ORD-0042"


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


class RegistryWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.repo = self.work / "shop"
        shutil.copytree(SKILL / "evals" / "fixtures" / "shop", self.repo)
        self.registry = self.repo / ".business-rules"
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.cli("init", "--registry", self.registry, "--id", "shop", "--domain", "orders",
                 "--owner", "Order operations owner", "--authority-source", "fixture:setup#owner")
        self.capture = json.loads((SKILL / "assets" / "capture.example.json").read_text())
        self.import_json("capture", self.capture)

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, "-B", str(CLI), *map(str, args)],
                                text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        return result

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.repo), *args], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def save(self, message):
        self.git("add", ".")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def import_json(self, command, data, ok=True):
        path = self.work / "input.json"
        write(path, data)
        return self.cli(command, "--registry", self.registry, "--input", path, ok=ok)

    def target(self, revision=1, rule=RULE):
        return json.loads(self.cli("target", "--registry", self.registry, "--rule", rule,
                                   "--revision", revision).stdout)

    def decision(self, revision=1, **changes):
        return {"schema_version": 1, "id": f"decision-{revision}", "kind": "approve",
                "authority_id": "owner-1", "actor": "Order operations owner",
                "source_id": "conversation-001", "decided_at": "2026-01-01T12:00:00Z",
                "effective_at": f"2026-01-{revision:02d}T12:00:00Z",
                "targets": [self.target(revision)], "waiver": None, **changes}

    def select(self, time=AS_OF):
        return json.loads(self.cli("select", "--registry", self.registry, "--as-of", time).stdout)

    def amend(self):
        capture = copy.deepcopy(self.capture)
        capture["claim"]["claim_id"] = "message-18-packing-cutoff"
        capture["source"].update(id="conversation-002", locator="fixture:conversation-002#message-18",
                                 excerpt="Replace the earlier policy: customers can cancel only new orders, not packing or shipped orders.")
        capture["claim"].update(source_id="conversation-002", statement="Customers may cancel only new orders.",
                                 outcome="Allow new; deny packing and shipped.",
                                 examples=[{"given": "Customer cancels a packing order.", "expect": "Deny cancellation."}])
        self.import_json("capture", capture)

    def context(self, base, head, as_of=AS_OF):
        data = json.loads(self.cli("audit-context", "--repo", self.repo, "--base", base,
                                   "--head", head, "--as-of", as_of).stdout)
        data.pop("selected_policies")
        data["scope"] = ["Customer cancellation through orders.py for new, packing and shipped orders."]
        return data

    def assessment(self, code_side, policy_side, revision, outcome):
        return {"id": f"{code_side}-{policy_side}", "rule_id": RULE, "revision": revision,
                "code_side": code_side, "policy_side": policy_side, "outcome": outcome,
                "method": "executed-test", "evidence": [{"locator": "fixture:executed-cancellation-scenarios",
                    "text": "Ran orders.py for new, packing, shipped; compared allowed with the approved examples."}],
                "scenario": "Customer requests cancellation of a packing order." if outcome == "violation" else None,
                "waiver_id": None}

    def report(self, audit, ok=True):
        path = self.work / "audit-input.json"
        write(path, audit)
        self.cli("report", "--repo", self.repo, "--base", audit["base_commit"], "--head", audit["head_commit"],
                 "--as-of", audit["as_of"], "--input", path, "--out", self.work / "report", ok=ok)
        if ok:
            return json.loads((self.work / "report" / "audit.json").read_text())

    def run_shop(self):
        return [json.loads(subprocess.check_output([sys.executable, "-B", str(self.repo / "orders.py"), status],
                                                  text=True))["allowed"] for status in ("new", "packing", "shipped")]

    def test_capture_approval_replay_and_unknown_exceptions(self):
        self.assertEqual(self.select(), {})
        self.assertEqual(json.loads(self.import_json("capture", self.capture).stdout)["changed"], [])
        changed = copy.deepcopy(self.capture)
        changed["claim"]["outcome"] = "Deny all requests."
        self.assertIn("replay differs", self.import_json("capture", changed, ok=False).stderr)
        self.import_json("decide", self.decision())
        self.assertEqual(self.select()[RULE]["revision"], 1)
        self.assertEqual(json.loads(self.import_json("decide", self.decision()).stdout)["changed"], [])
        rule = json.loads((self.registry / "rules" / "orders" / f"{RULE}.json").read_text())
        self.assertEqual(rule["revisions"][0]["exceptions"], {"knowledge": "unknown", "items": []})
        self.assertIn("support", rule["revisions"][0]["questions"][0])

    def test_authority_and_exact_revision_binding(self):
        for mutation, message in (({"actor": "Someone else"}, "actor does not match"),
                                  ({"authority_id": "missing"}, "actor does not match")):
            self.assertIn(message, self.import_json("decide", self.decision(**mutation), ok=False).stderr)
        data = self.decision()
        data["targets"][0]["digest"] = "0" * 64
        self.assertIn("digest", self.import_json("decide", data, ok=False).stderr)
        source = copy.deepcopy(self.capture["source"])
        source.update(id="anonymous-form", kind="questionnaire", authority_evidence=None)
        self.import_json("source", source)
        self.assertIn("authority evidence", self.import_json("decide", self.decision(source_id="anonymous-form"), ok=False).stderr)
        self.assertEqual(self.select(), {})

    def test_history_and_future_effectivity(self):
        self.import_json("decide", self.decision())
        base = self.save("approved baseline")
        self.amend()
        self.assertEqual(self.select()[RULE]["revision"], 1)
        self.import_json("decide", self.decision(2, source_id="conversation-002", effective_at="2026-04-01T00:00:00Z"))
        self.assertEqual(self.select()[RULE]["revision"], 1)
        self.assertEqual(self.select("2026-04-01T00:00:00Z")[RULE]["revision"], 2)
        self.cli("validate", "--registry", self.registry, "--repo", self.repo, "--baseline", base)
        old = json.loads((self.registry / "decisions" / "decision-1.json").read_text())
        old["effective_at"] = "2026-01-01T13:00:00Z"
        write(self.registry / "decisions" / "decision-1.json", old)
        self.assertIn("history changed", self.cli("validate", "--registry", self.registry, "--repo", self.repo,
                                                  "--baseline", base, ok=False).stderr)

    def test_rejection_and_atomic_cross_rule_replacement(self):
        self.import_json("decide", self.decision())
        self.amend()
        self.import_json("decide", self.decision(2, kind="reject", source_id="conversation-002"))
        self.assertEqual(self.select()[RULE]["revision"], 1)
        retirement = copy.deepcopy(self.capture)
        retirement["claim"].update(claim_id="retirement", action="retire")
        self.import_json("capture", retirement)
        successor = copy.deepcopy(self.capture)
        successor["rule_id"] = "BR-ORD-0043"
        successor["claim"].update(claim_id="replacement", relations=[
            {"type": "supersedes", "rule_id": RULE, "revision": 1}])
        self.import_json("capture", successor)
        decision = self.decision(3, id="replace", targets=[self.target(rule="BR-ORD-0043")])
        self.assertIn("same decision", self.import_json("decide", decision, ok=False).stderr)
        decision["targets"].append(self.target(3))
        self.import_json("decide", decision)
        self.assertEqual(set(self.select()), {"BR-ORD-0043"})

    def test_concurrent_capture_replays_append_once(self):
        capture = copy.deepcopy(self.capture)
        capture["claim"]["claim_id"] = "second-interpretation"
        path = self.work / "concurrent.json"
        write(path, capture)
        processes = [subprocess.Popen([sys.executable, "-B", str(CLI), "capture", "--registry",
                     str(self.registry), "--input", str(path)], text=True, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE) for _ in range(4)]
        changed = 0
        for process in processes:
            out, err = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, err)
            changed += bool(json.loads(out)["changed"])
        self.assertEqual(changed, 1)
        rule = json.loads((self.registry / "rules" / "orders" / f"{RULE}.json").read_text())
        self.assertEqual(len(rule["revisions"]), 2)

    def test_baseline_prevents_owner_replacement_and_erased_policy(self):
        self.import_json("decide", self.decision())
        base = self.save("approved baseline")
        config = json.loads((self.registry / "config.json").read_text())
        config["authorities"][0]["source"] = "fixture:rewritten-authority"
        write(self.registry / "config.json", config)
        self.assertIn("authority history", self.cli("validate", "--registry", self.registry, "--repo", self.repo,
                                                    "--baseline", base, ok=False).stderr)
        self.git("restore", ".business-rules/config.json")
        (self.registry / "decisions" / "decision-1.json").unlink()
        self.assertIn("history changed", self.cli("validate", "--registry", self.registry, "--repo", self.repo,
                                                  "--baseline", base, ok=False).stderr)
        rule_path = self.registry / "rules" / "orders" / f"{RULE}.json"
        rule = json.loads(rule_path.read_text())
        rule["revisions"][0]["outcome"] = "Allow shipped orders too."
        write(rule_path, rule)
        write(self.registry / "decisions" / "decision-1.json", self.decision())
        self.cli("validate", "--registry", self.registry)
        self.assertIn("history changed", self.cli("validate", "--registry", self.registry, "--repo", self.repo,
                                                  "--baseline", base, ok=False).stderr)

    def test_new_domain_requires_separate_bootstrap_and_owner_transfer_keeps_history(self):
        self.import_json("decide", self.decision())
        base = self.save("trusted owners and policy")
        config_path = self.registry / "config.json"
        config = json.loads(config_path.read_text())
        config["authorities"].append({"id": "billing-owner", "domain": "billing", "actor": "Billing owner",
            "source": "fixture:setup#billing-owner", "supersedes": None, "authorized_by": None})
        write(config_path, config)
        self.cli("validate", "--registry", self.registry, "--repo", self.repo, "--baseline", base)
        capture = copy.deepcopy(self.capture)
        capture.update(domain="billing", rule_id="BR-BILL-001")
        capture["claim"]["claim_id"] = "billing-policy"
        self.import_json("capture", capture)
        self.assertIn("bootstrap domains separately", self.cli("validate", "--registry", self.registry,
                    "--repo", self.repo, "--baseline", base, ok=False).stderr)
        (self.registry / "rules" / "billing" / "BR-BILL-001.json").unlink()
        self.save("separate domain designation")
        config["authorities"].append({"id": "owner-2", "domain": "orders", "actor": "Replacement owner",
            "source": "fixture:setup#owner-transfer", "supersedes": "owner-1", "authorized_by": "Order operations owner"})
        write(config_path, config)
        self.amend()
        self.assertIn("superseded owner", self.import_json("decide", self.decision(2, source_id="conversation-002"), ok=False).stderr)
        self.import_json("decide", self.decision(2, source_id="conversation-002", authority_id="owner-2", actor="Replacement owner"))
        self.cli("validate", "--registry", self.registry, "--repo", self.repo, "--baseline", base)
        self.assertEqual(self.select()[RULE]["revision"], 2)

    def test_relationships_are_revision_pinned_and_need_approval(self):
        capture = copy.deepcopy(self.capture)
        capture["rule_id"] = "BR-ORD-0043"
        capture["claim"]["claim_id"] = "support-exception"
        capture["claim"]["relations"] = [{"type": "exception_to", "rule_id": RULE, "revision": 1}]
        self.import_json("capture", capture)
        decision = self.decision(id="exception", targets=[self.target(rule="BR-ORD-0043")])
        self.assertIn("approved relationship", self.import_json("decide", decision, ok=False).stderr)
        self.import_json("decide", self.decision())
        self.import_json("decide", decision)
        self.amend()
        self.import_json("decide", self.decision(2, source_id="conversation-002"))
        exception = json.loads((self.registry / "rules" / "orders" / "BR-ORD-0043.json").read_text())
        self.assertEqual(exception["revisions"][0]["relations"][0]["revision"], 1)

    def test_full_loop_violation_and_approved_policy_amendment(self):
        self.import_json("decide", self.decision())
        base = self.save("customer cancellation policy")
        self.assertEqual(self.run_shop(), [True, True, False])
        app = self.repo / "orders.py"
        app.write_text(app.read_text().replace('(\"new\", \"packing\")', '(\"new\",)'))
        head = self.save("packing cutoff without policy change")
        self.assertEqual(self.run_shop(), [True, False, False])
        audit = self.context(base, head)
        audit["assessments"] = [self.assessment("base", "base", 1, "conforms"),
                                self.assessment("head", "base", 1, "violation"),
                                self.assessment("head", "head", 1, "violation")]
        self.assertEqual(self.report(audit)["summary"], "must-resolve")
        self.amend()
        unapproved_head = self.save("proposed policy does not erase violation")
        unapproved = self.context(base, unapproved_head)
        unapproved["assessments"] = audit["assessments"]
        self.assertEqual(self.report(unapproved)["summary"], "must-resolve")
        self.import_json("decide", self.decision(2, source_id="conversation-002"))
        approved_head = self.save("owner approves packing cutoff")
        approved = self.context(base, approved_head)
        approved["assessments"] = [self.assessment("base", "base", 1, "conforms"),
                                   self.assessment("head", "base", 1, "violation"),
                                   self.assessment("head", "head", 2, "conforms")]
        report = self.report(approved)
        self.assertEqual(report["summary"], "review-required")
        self.assertEqual(report["assessments"][1]["disposition"], "approved-policy-change")
        self.assertIn("approved-policy-change", (self.work / "report" / "audit.md").read_text())
        stale = copy.deepcopy(approved)
        stale["head_registry_digest"] = "0" * 64
        self.report(stale, ok=False)
        incomplete = self.context(base, approved_head)
        report = self.report(incomplete)
        self.assertEqual(report["summary"], "review-required")
        self.assertEqual(len(report["assessments"]), 3)
        self.assertTrue(all(a["outcome"] == "not-assessed" for a in report["assessments"]))

    def test_repair_preserves_history_without_an_unresolved_head_violation(self):
        self.import_json("decide", self.decision())
        app = self.repo / "orders.py"
        original = app.read_text()
        app.write_text(original.replace('(\"new\", \"packing\")', '(\"new\",)'))
        base = self.save("existing cancellation defect")
        self.assertEqual(self.run_shop(), [True, False, False])
        app.write_text(original)
        head = self.save("repair cancellation without changing policy")
        self.assertEqual(self.run_shop(), [True, True, False])
        audit = self.context(base, head)
        historical = self.assessment("base", "base", 1, "violation")
        audit["assessments"] = [historical, self.assessment("head", "base", 1, "conforms"),
                                self.assessment("head", "head", 1, "conforms")]
        report = self.report(audit)
        self.assertEqual(report["assessments"][0], {**historical, "disposition": "resolved-in-head"})
        self.assertEqual(report["summary"], "review-required")
        self.assertEqual(report["ci_gate"], "not-evaluated")
        self.assertIn("violation (resolved-in-head)", (self.work / "report" / "audit.md").read_text())
        for outcome in ("violation", "not-assessed", None):
            with self.subTest(head_base=outcome):
                incomplete = copy.deepcopy(audit)
                if outcome is None:
                    del incomplete["assessments"][1]
                else:
                    incomplete["assessments"][1] = self.assessment("head", "base", 1, outcome)
                report = self.report(incomplete)
                self.assertEqual(report["assessments"][0]["disposition"], "must-resolve")
                self.assertEqual(report["summary"], "must-resolve")

    def test_waiver_is_scoped_expiring_and_metadata_commit_safe(self):
        self.import_json("decide", self.decision())
        base = self.save("baseline")
        app = self.repo / "orders.py"
        app.write_text(app.read_text().replace('(\"new\", \"packing\")', '(\"new\",)'))
        broken = self.save("violation")
        waiver = self.decision(id="waiver-1", kind="waive", waiver={"finding_id": "head-base",
            "code_commit": broken, "expires_at": "2026-03-02T12:00:00Z", "reason": "Fixture owner accepts a one-day exception."})
        self.import_json("decide", waiver)
        head = self.save("record scoped waiver")
        audit = self.context(base, head)
        finding = self.assessment("head", "base", 1, "violation")
        finding["waiver_id"] = "waiver-1"
        audit["assessments"] = [finding]
        self.assertEqual(self.report(audit)["assessments"][0]["disposition"], "waived")
        audit["as_of"] = "2026-03-02T12:00:00Z"
        self.report(audit, ok=False)
        app.write_text(app.read_text() + "\n# Source changed after waiver.\n")
        later = self.save("changed source")
        audit = self.context(base, later)
        audit["assessments"] = [finding]
        self.report(audit, ok=False)

    def test_catalogue_mapping_does_not_promote_or_reuse_display_identity(self):
        source_commit = self.save("source snapshot")
        catalogue = {"meta": {"commit": source_commit, "verification": {"rules_checked": 1}},
                     "rules": [{"id": "BR-OR-001", "statement": "Customer cancellation", "exceptions": [],
                                "engineering": [{"file": "orders.py", "lines": "5-6", "role": "decides"}]}]}
        cat = self.work / "catalogue.json"
        write(cat, catalogue)
        args = ("reconcile", "--registry", self.registry, "--catalogue", cat)
        self.cli(*args)
        self.assertEqual(self.select(), {})
        mapping = [{"observation_id": "BR-OR-001", "status": "matched", "candidates": [self.target()]}]
        path = self.work / "mapping.json"
        write(path, mapping)
        self.cli(*args, "--mapping", path)
        self.assertEqual(json.loads(self.cli(*args, "--mapping", path).stdout)["changed"], [])
        catalogue["rules"][0]["id"] = "BR-OR-002"
        catalogue["rules"][0]["engineering"][0]["file"] = "renamed/orders.py"
        write(cat, catalogue)
        self.cli(*args, "--mapping", path, ok=False)
        mapping[0]["observation_id"] = "BR-OR-002"
        write(path, mapping)
        self.cli(*args, "--mapping", path)
        self.assertEqual(self.target()["rule_id"], RULE)
        self.assertEqual(self.select(), {})

    def test_selected_binding_freshness_ignores_only_registry_metadata(self):
        self.import_json("decide", self.decision())
        base = self.save("source and approved policy")
        catalogue = {"meta": {"commit": base}, "rules": [{"id": "BR-OR-001", "exceptions": []}]}
        path = self.work / "catalogue.json"
        write(path, catalogue)
        self.cli("reconcile", "--registry", self.registry, "--catalogue", path)
        bid = next((self.registry / "bindings").glob("*.json")).stem
        head = self.save("binding metadata only")
        audit = self.context(base, head)
        audit["binding_ids"] = [bid]
        audit["assessments"] = [self.assessment(c, p, 1, "conforms")
                                 for c, p in (("base", "base"), ("head", "base"), ("head", "head"))]
        self.assertEqual(self.report(audit)["stale_bindings"], [])
        (self.repo / "orders.py").rename(self.repo / "renamed_orders.py")
        later = self.save("move application code")
        updated = self.context(base, later)
        updated["binding_ids"] = [bid]
        updated["assessments"] = audit["assessments"]
        report = self.report(updated)
        self.assertEqual(report["stale_bindings"], [bid])
        self.assertEqual(report["summary"], "review-required")
        updated["binding_ids"] = []
        self.assertEqual(self.report(updated)["stale_bindings"], [])

    def test_malformed_input_and_tool_pin_fail_closed(self):
        invalid = copy.deepcopy(self.capture)
        invalid["rule_id"] = "../../escape"
        self.import_json("capture", invalid, ok=False)
        self.assertFalse((self.work / "escape.json").exists())
        invalid = copy.deepcopy(self.capture)
        invalid["source"]["schema_version"] = True
        self.import_json("capture", invalid, ok=False)
        config = json.loads((self.registry / "config.json").read_text())
        config["tool_digest"] = "0" * 64
        write(self.registry / "config.json", config)
        self.assertIn("pinned tool", self.cli("validate", "--registry", self.registry, ok=False).stderr)

    def test_actual_catalogue_build_integrates_without_changing_catalogue_contract(self):
        default = SKILL.parent / "business-rules-catalogue"
        catalogue_skill = Path(os.environ.get("BR_CATALOGUE_SKILL", default))
        script = catalogue_skill / "scripts" / "br.py"
        if not script.exists():
            self.skipTest("install business-rules-catalogue or set BR_CATALOGUE_SKILL for integration")
        source_commit = self.save("clean source for discovery")
        work = self.work / "discovery"

        def br(*args):
            run = subprocess.run([sys.executable, "-B", str(script), *map(str, args)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            return run

        br("init", "--repo", self.repo, "--work", work)
        br("survey", "--work", work)
        scope = json.loads((work / "scope.draft.json").read_text())
        scope["areas"] = [{"id": "orders", "code": "OR", "title": "Orders", "tier": "business",
                           "paths": ["orders.py"], "summary": "Customer cancellation."}]
        scope["stages"] = [{"id": "cancel", "label": "Cancel", "lane": "main", "description": "Customer cancellation."}]
        write(work / "scope.json", scope)
        br("survey", "--work", work)
        br("partition", "--work", work)
        observation = {"key": "cancel", "title": "Customer cancellation", "stage": "cancel", "kind": "authorization",
                       "statement": "Customers can cancel new or packing orders.", "applies_when": "A customer requests cancellation.",
                       "exceptions": [], "example": "Packing allows cancellation.", "on_violation": "Return false.", "terms": [],
                       "surfaces": [{"kind": "internal", "name": "orders.py CLI", "ref": "orders.py:10"}],
                       "engineering": [{"role": "decides", "file": "orders.py", "symbol": "can_cancel", "lines": "5-6"}],
                       "flags": [], "related": [], "confidence": "high"}
        write(work / "out" / "W1.json", {"worker": "W1", "areas": [{"area": "orders", "modules": [
            {"module": "orders.py", "title": "Cancellation", "stage": "cancel", "summary": "Eligibility.", "rules": [observation]}]}]})
        br("check", "--work", work)
        br("batches", "--work", work)
        # Prepared checker fixtures exercise the build contract, not independent agent accuracy.
        for batch in (work / "verify").glob("in*.json"):
            verdicts = [{"worker": item["worker"], "area": item["area"], "key": item["key"],
                         "rule_verdict": "correct", "rule_revision": None, "flags": []}
                        for item in json.loads(batch.read_text())]
            write(batch.with_name(batch.name.replace("in", "out")), verdicts)
        br("build", "--work", work)
        self.cli("reconcile", "--registry", self.registry, "--catalogue", work / "build" / "catalogue.json")
        binding = json.loads(next((self.registry / "bindings").glob("*.json")).read_text())
        self.assertEqual(binding["code_commit"], source_commit)
        self.assertEqual(binding["catalogue"]["meta"]["verification"]["rules_checked"], 1)
        self.assertEqual(binding["mappings"][0]["status"], "unmatched")
        self.assertEqual(self.select(), {})


if __name__ == "__main__":
    unittest.main()

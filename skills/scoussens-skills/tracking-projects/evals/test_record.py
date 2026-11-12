"""Run with python3 -B -m unittest discover -s <this directory> -v."""

from pathlib import Path
from functools import partial
import html
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from threading import Thread
import unittest

SKILL = Path(__file__).resolve().parent.parent
EXAMPLE = (SKILL / "assets" / "example-record.md").read_text(encoding="utf-8")
SCRIPT = SKILL / "scripts" / "record.py"
sys.path.insert(0, str(SKILL / "scripts"))
from record import overview, parse, problems


def check(text):
    return problems(parse(text))


class Check(unittest.TestCase):
    def test_example_record_passes(self):
        self.assertEqual(check(EXAMPLE), [])

    def test_open_owner_item_without_holding_up_is_named(self):
        text = EXAMPLE.replace("  - **Holding up:** nothing yet.\n", "")
        found = check(text)
        self.assertEqual(len(found), 1)
        self.assertIn("Should bars change", found[0])
        self.assertIn("Holding up", found[0])

    def test_empty_required_field_is_not_decision_ready(self):
        text = EXAMPLE.replace("  - **Holding up:** nothing yet.", "  - **Holding up:**")
        found = check(text)
        self.assertEqual(len(found), 1)
        self.assertIn("Holding up", found[0])

    def test_nested_detail_does_not_count_as_a_field(self):
        # The ID item keeps its nested Context detail; drop its top-level Why.
        text = EXAMPLE.replace(
            "  - **Why:** the Object link is what", "    - **Why:** the Object link is what"
        )
        found = check(text)
        self.assertEqual(len(found), 1)
        self.assertIn("Which ID does", found[0])
        self.assertIn("Why", found[0])

    def test_checked_item_needs_a_dated_ruling(self):
        text = EXAMPLE.replace(
            "  - **Ruled 2026-11-05 by the owner:** approved as recommended. ", "  - "
        )
        found = check(text)
        self.assertEqual(len(found), 1)
        self.assertIn("checked off without the ruling", found[0])

    def test_ruling_written_in_the_title_counts(self):
        text = EXAMPLE.replace(
            "- [x] **Do saved layouts survive a local reset?**\n  - **Ruled 2026-11-05 by the owner:** approved as recommended. ",
            "- [x] **The owner approved questions 1-4 as recommended on 2026-11-05.**\n  - ",
        )
        self.assertEqual(check(text), [])

    def test_dropdown_chip_in_a_table_fails(self):
        text = EXAMPLE.replace("| Held |", "| {{dropdown:Idle|*Held:yellow}} |")
        found = check(text)
        self.assertTrue(any("dropdown chip inside a table under Lanes" in p for p in found), found)

    def test_done_rows_need_a_date_and_a_where(self):
        text = EXAMPLE.replace("| 2026-11-04 | Ruling | The owner approved building ticket 96 | Lane 3 |",
                               "| Nov 4 | Ruling | The owner approved building ticket 96 |  |")
        found = check(text)
        self.assertEqual(len(found), 2, found)
        self.assertTrue(any('date "Nov 4"' in p for p in found))
        self.assertTrue(any("empty Where" in p for p in found))

    def test_unknown_history_kind_is_named(self):
        found = check(EXAMPLE.replace("| Ruling |", "| Approved |"))
        self.assertEqual(len(found), 1, found)
        self.assertIn("Kind must be Delivery, Ruling, Other or Unclassified", found[0])

    def test_missing_section_and_last_updated(self):
        text = EXAMPLE.replace("### Stopped", "### Parked").replace("Last updated: 2026-11-05", "")
        found = check(text)
        self.assertIn("missing section: Stopped", found)
        self.assertIn("no `Last updated: YYYY-MM-DD` line", found)

    def test_items_inside_code_blocks_are_ignored(self):
        text = EXAMPLE.replace(
            "### Decisions already approved",
            "```markdown\n- [ ] **Example only?**\n```\n\n### Decisions already approved",
        )
        text = text.replace("### Needs the owner\n", "### Needs the owner\n\n```markdown\n- [ ] **Example only?**\n```\n")
        self.assertEqual(check(text), [])

    def test_cli_exit_codes(self):
        ok = subprocess.run([sys.executable, "-B", str(SCRIPT), "check", str(SKILL / "assets" / "example-record.md")],
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        template = SKILL / "assets" / "tracking-document.template.md"
        bad = subprocess.run([sys.executable, "-B", str(SCRIPT), "check", str(template)], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("FAIL", bad.stdout)


class Parse(unittest.TestCase):
    def test_counts_and_fields(self):
        record = parse(EXAMPLE)
        self.assertEqual(record["title"], "layout-rebuild: work done and remaining")
        self.assertEqual(record["last_updated"], "2026-11-05")
        self.assertEqual([l["state"] for l in record["lanes"]], ["Idle", "Held", "Working"])
        self.assertEqual(len(record["done"]), 4)
        needs = [i for i in record["items"] if i["section"] == "needs"]
        self.assertEqual([i["checked"] for i in needs], [False, False, True])
        self.assertEqual(needs[0]["fields"]["recommendation"], "A: keep the document linked to the shared Object and store the original source record in a separate column.")
        self.assertTrue(needs[0]["fields"]["context"].startswith("the local column points at the Object"))
        self.assertEqual(sum(1 for i in record["items"] if i["section"] == "research"), 2)

    def test_field_written_as_nested_bullets_takes_the_first_bullet(self):
        text = EXAMPLE.replace(
            "  - **Recommendation:** keep 4 cards and the current snapping; treat a change as its own later piece.",
            "  - **Recommendation:**\n    - Keep 4 cards for now.\n    - Revisit with the geometry piece.",
        )
        bars = [i for i in parse(text)["items"] if i["title"].startswith("Should bars")][0]
        self.assertEqual(bars["fields"]["recommendation"], "Keep 4 cards for now.")
        self.assertIn("Keep 4 cards for now.", overview(parse(text)))
        self.assertIn("Revisit with the geometry piece.", overview(parse(text)))


class Overview(unittest.TestCase):
    def page(self, text=EXAMPLE):
        return overview(parse(text))

    def test_deliveries_exclude_rulings_other_and_unclassified_history(self):
        text = EXAMPLE.split("## Done")[0] + """## Done

| Date | Kind | What | Where |
| --- | --- | --- | --- |
| 2026-11-10 | Ruling | Owner approved the delivered design. CI failed in an earlier build | [decision commit](https://example.org/commit/ruling) |
| 2026-11-09 | Delivery | Implemented the owner approval audit. Checks: 7. CI green | [code](https://example.org/commit/code) |
| 2026-11-08 | Other | Reviewed the rollback plan. CI failed | Planning |
| 2026-11-07 | | Legacy entry says delivered, but has no classification | [legacy](https://example.org/commit/legacy) |
"""
        page = self.page(text)
        delivered = re.search(r'<section id="done".*?</section>', page, re.S).group()
        ruled = re.search(r'<section id="ruled".*?</section>', page, re.S).group()
        self.assertIn("Implemented the owner approval audit", delivered)
        self.assertNotIn("Owner approved the delivered design", delivered)
        self.assertNotIn("Legacy entry says delivered", delivered)
        self.assertNotIn("Reviewed the rollback plan", delivered)
        self.assertIn("Owner approved the delivered design", ruled)
        self.assertIn("1 CI green, 0 failed", page)
        history = re.search(r'<section id="history".*?</section>', page, re.S).group()
        for entry in ("Owner approved the delivered design", "Implemented the owner approval audit",
                      "Reviewed the rollback plan", "Legacy entry says delivered", "Unclassified"):
            self.assertIn(entry, history)
        legacy = self.page(EXAMPLE.split("## Done")[0] + """## Done

| Date | What | Where |
| --- | --- | --- |
| 2026-11-01 | Untyped historical delivery | [commit](https://example.org/commit/old) |
""")
        self.assertIn("No deliveries recorded.", legacy)
        self.assertIn("Untyped historical delivery", legacy)
        self.assertIn("Unclassified", legacy)

    def test_blocking_decision_comes_first_with_option_spelled_out(self):
        text = EXAMPLE.replace("A: keep the document linked to the shared Object and store the original source record in a separate column.", "A.")
        page = self.page(text)
        first = page.index("Which ID does")
        idle = page.index("Should bars change")
        self.assertLess(first, idle)
        self.assertIn("A: keep the column pointing at the Object", page)

    def test_blocking_order_ignores_record_order(self):
        # Put the "nothing yet" item first in the record; the page still leads with the blocking one.
        record = parse(EXAMPLE)
        needs = [i for i in record["items"] if i["section"] == "needs"]
        record["items"] = [needs[1], needs[0]] + [i for i in record["items"] if i not in needs[:2]]
        page = overview(record)
        self.assertLess(page.index("Which ID does"), page.index("Should bars change"))

    def test_ci_badges_read_not_green_as_failed(self):
        page = self.page()
        delivered = re.search(r'<section id="done".*?</section>', page, re.S).group()
        rows = re.findall(r'<span class="ci (\w+)">', delivered)
        self.assertEqual(rows, ["pass", "pass", "fail"])
        self.assertIn("2 CI green, 1 failed", page)

    def test_text_is_escaped_and_only_web_links_render(self):
        text = EXAMPLE.replace(
            "Should bars change from 4 cards to 6 that snap only to 0, 1 or 6?",
            "<script>alert(1)</script> [x](javascript:alert(1))?",
        )
        page = self.page(text)
        self.assertNotIn("<script>alert", page)
        self.assertNotIn('href="javascript', page)
        self.assertIn("&lt;script&gt;", page)

    def test_detail_keeps_context_sources_rulings_and_entire_history(self):
        text = EXAMPLE.rstrip() + "\n" + "\n".join(
            f"| 2026-11-03 | Delivery | Earlier delivery {n}. Checks: historical check {n} | [commit](https://example.org/commit/{n}) |"
            for n in range(13)
        )
        self.assertEqual(len(parse(text)["done"]), 17)
        page = self.page(text)
        for detail in ["baseline/schema.sql:5010", "services/dimensions/write/node.py:2166-2177",
                       "one more column to fill on write.", "The rest of that piece is being built.",
                       "manual review. Comment on the decision in this record",
                       "Comments alone do not start review.", 'href="https://example.org/threads/T-orchestrator"',
                       'href="https://example.org/threads/T-research-k10"',
                       "Ruled 2026-11-05 by the owner", "Sign out", "One active Book per Spine",
                       "Follow-up post to the architect", "identity rows built locally and uncommitted",
                       'href="https://example.org/runs/42017580376"', "historical check 12"]:
            with self.subTest(detail=detail):
                self.assertIn(detail, page)

    def test_writes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "overview.html"
            run = subprocess.run([sys.executable, "-B", str(SCRIPT), "overview",
                                  str(SKILL / "assets" / "example-record.md"), str(out)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(out.read_text(encoding="utf-8").startswith("<!doctype html>"))


@unittest.skipUnless(os.environ.get("TRACKING_BROWSER_TEST") == "1" and shutil.which("agent-browser"),
                     "set TRACKING_BROWSER_TEST=1 with agent-browser installed")
class OverviewBrowser(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.page = Path(tmp.name) / "overview.html"
        self.page.write_text(overview(parse(EXAMPLE)), encoding="utf-8")
        self.session = f"tracker-{os.getpid()}"
        self.addCleanup(subprocess.run, ["agent-browser", "--session", self.session, "close"],
                        capture_output=True, timeout=60)
        self.browser("open", self.page.as_uri())
        self.browser("set", "viewport", "1100", "900", "2")

    def browser(self, *args):
        run = subprocess.run(["agent-browser", "--session", self.session, *args, "--json"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr or run.stdout)
        response = json.loads(run.stdout)
        self.assertTrue(response["success"], response)
        return response["data"]

    def evaluate(self, code):
        return self.browser("eval", code)["result"]

    def selected(self, panel):
        self.browser("wait", "--fn", f"document.querySelector('#tab-{panel}').getAttribute('aria-selected') === 'true'")
        self.assertEqual(self.evaluate("[...document.querySelectorAll('[role=tabpanel]')].filter(p => !p.hidden).map(p => p.id)"), [panel])

    def test_tabs_stay_inside_sandboxed_srcdoc(self):
        host = self.page.with_name("host.html")
        host.write_text('<!doctype html><iframe id="tracker" sandbox="allow-scripts" '
                        'style="width:100%;height:800px" srcdoc="'
                        + html.escape(self.page.read_text(), quote=True) + '"></iframe>', encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(host.parent)))
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        Thread(target=server.serve_forever, daemon=True).start()
        self.browser("open", f"http://127.0.0.1:{server.server_port}/host.html")
        self.evaluate("window.frameLoads = 0; document.querySelector('#tracker').addEventListener('load', () => window.frameLoads++)")

        def activate(role, name):
            snapshot = self.browser("snapshot", "-i")
            ref = next(ref for ref, value in snapshot["refs"].items()
                       if value["role"] == role and value["name"] == name)
            self.browser("click", "@" + ref)
            return self.browser("snapshot", "-i")

        snapshot = activate("tab", "Needs the owner")
        self.assertIn('tab "Needs the owner" [selected', snapshot["snapshot"])
        snapshot = activate("tab", "History")
        self.assertIn('tab "History" [selected', snapshot["snapshot"])
        for name in ("Needs the owner", "Owner ruled", "Open to veto", "Lanes", "Delivered", "Stopped"):
            activate("tab", "Overview")
            snapshot = activate("button", name)
            self.assertIn(f'tab "{name}" [selected', snapshot["snapshot"])
        activate("tab", "Overview")
        activate("button", "Which ID does a document's object link hold?")
        self.assertIn("one more column to fill on write", self.browser("snapshot")["snapshot"])
        activate("tab", "Overview")
        snapshot = activate("button", "2, data")
        self.assertIn('tab "Lanes" [selected', snapshot["snapshot"])
        self.assertIn("layout-rebuild-data", self.browser("snapshot")["snapshot"])
        self.assertEqual(sum(value["role"] == "Iframe" for value in snapshot["refs"].values()), 1)
        self.assertEqual(self.evaluate("window.frameLoads"), 0, "A tracker control navigated the frame away")

    def test_tiles_decisions_lanes_and_keyboard(self):
        self.selected("overview")
        for panel, expected in [("needs", "Which ID does"), ("ruled", "Ruled 2026-11-05"),
                                ("research", "One active Book per Spine"), ("lanes", "identity rows built locally"),
                                ("done", "Checks: check 476"), ("stopped", "No further posts")]:
            with self.subTest(panel=panel):
                self.browser("click", f'.tile button[data-target="{panel}"]')
                self.selected(panel)
                self.assertIn(expected, self.evaluate(f"document.querySelector('#{panel}').innerText"))
                self.browser("click", "#tab-overview")
                self.selected("overview")

        self.assertEqual(self.evaluate("document.querySelector('.tile:has([data-target=done]) .n').innerText"), "3")
        self.browser("click", "#tab-done")
        self.assertNotIn("approved building ticket 96", self.evaluate("document.querySelector('#done').innerText"))
        self.browser("click", '#done button[data-target="history"]')
        self.selected("history")
        self.assertIn("approved building ticket 96", self.evaluate("document.querySelector('#history').innerText"))
        self.browser("click", "#tab-ruled")
        self.assertIn("approved building ticket 96", self.evaluate("document.querySelector('#ruled').innerText"))
        self.browser("click", "#tab-overview")
        self.browser("click", ".queue li:first-child button")
        self.selected("needs")
        self.assertTrue(self.evaluate("document.querySelector('.decision').open"))
        decision_text = self.evaluate("document.querySelector('.decision').innerText")
        for expected in ["Recommendation", "Why this recommendation", "Tradeoff", "one more column",
                         "baseline/schema.sql:5010", "The rest of that piece is being built."]:
            self.assertIn(expected, decision_text)
        self.browser("click", ".decision[open] .evidence summary")
        self.assertIn("2 of 32 documents linked", self.evaluate("document.querySelector('.evidence').innerText"))
        self.assertEqual(self.evaluate("document.querySelector('.evidence a').href"), "https://example.org/threads/T-research-k10")
        self.assertEqual(self.evaluate("location.hash"), "")
        self.browser("click", "#tab-overview")
        self.selected("overview")
        self.browser("click", ".lane.held button")
        self.selected("lanes")
        self.assertIn("layout-rebuild-data", self.evaluate("document.activeElement.innerText"))

        self.browser("focus", "#tab-lanes")
        self.browser("press", "ArrowRight")
        self.selected("done")
        self.browser("press", "End")
        self.selected("stopped")
        self.browser("press", "Home")
        self.selected("overview")
        self.browser("press", "ArrowRight")
        self.selected("needs")
        self.browser("focus", ".decision summary")
        self.browser("press", "Enter")
        self.assertFalse(self.evaluate("document.querySelector('.decision').open"))
        self.browser("press", "Enter")
        self.assertTrue(self.evaluate("document.querySelector('.decision').open"))
        for width in (390, 1100):
            self.browser("set", "viewport", str(width), "900", "2")
            for panel in ("overview", "needs", "lanes", "done", "history", "ruled"):
                self.browser("click", f"#tab-{panel}")
                self.selected(panel)
                self.assertTrue(self.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, panel))
        self.browser("reload")
        self.selected("overview")
        self.assertEqual(self.browser("errors")["errors"], [])


if __name__ == "__main__":
    unittest.main()

"""Run with python3 -B -m unittest discover -s <this directory> -v."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile
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
        text = EXAMPLE.replace("| 2026-11-04 | The owner approved building ticket 96 | Lane 3 |",
                               "| Nov 4 | The owner approved building ticket 96 |  |")
        found = check(text)
        self.assertEqual(len(found), 2, found)
        self.assertTrue(any('date "Nov 4"' in p for p in found))
        self.assertTrue(any("empty Where" in p for p in found))

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
        self.assertEqual(needs[0]["fields"]["recommendation"], "A.")
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


class Overview(unittest.TestCase):
    def page(self, text=EXAMPLE):
        return overview(parse(text))

    def test_blocking_decision_comes_first_with_option_spelled_out(self):
        page = self.page()
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
        rows = re.findall(r'<span class="ci (\w+)">', page)
        self.assertEqual(rows, ["pass", "pass", "fail", "none"])
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

    def test_writes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "overview.html"
            run = subprocess.run([sys.executable, "-B", str(SCRIPT), "overview",
                                  str(SKILL / "assets" / "example-record.md"), str(out)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(out.read_text(encoding="utf-8").startswith("<!doctype html>"))


if __name__ == "__main__":
    unittest.main()

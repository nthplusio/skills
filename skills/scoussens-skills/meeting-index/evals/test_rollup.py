"""Exercise the installed rollup CLI from a foreign working directory."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]


class RollupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.installed = root / "installed skills" / "meeting-index"
        shutil.copytree(SKILL / "scripts", self.installed / "scripts")
        self.cwd = root / "unrelated project"
        self.cwd.mkdir()
        self.records = self.cwd / "meeting records.json"

    def run_cli(self, records, *args):
        self.records.write_text(json.dumps(records), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(self.installed / "scripts" / "rollup.py"),
             str(self.records), *args],
            cwd=self.cwd, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def rollup(self, records, offset):
        return json.loads(self.run_cli(
            records, "--offset-hours", str(offset), "--json",
        ).stdout)

    def test_equivalent_instants_keep_source_ids_and_share_local_time(self):
        starts = ["2026-01-15T15:00:00Z", "2026-01-15T10:00:00-05:00",
                  "2026-01-15T20:30:00+05:30", "2026-01-15T15:00:00"]
        records = [dict(id=str(i), start=start, duration_ms=60000)
                   for i, start in enumerate(starts)]
        result = self.rollup(records, -5)
        self.assertEqual(result["counted"], 4)
        self.assertEqual(result["total_minutes"], 4)
        self.assertEqual(len(result["days"]), 1)
        day = result["days"][0]
        self.assertEqual(day["date"], "2026-01-15")
        self.assertEqual([e["id"] for e in day["entries"]], ["0", "1", "2", "3"])
        self.assertEqual([(e["utc"], e["local"]) for e in day["entries"]],
                         [("15:00", "10:00")] * 4)

    def test_midnight_boundaries_with_negative_and_fractional_positive_offsets(self):
        cases = [
            (-5, "2026-01-01T10:29:59+05:30", "2026-01-01T10:30:00+05:30",
             "2025-12-31", "2026-01-01"),
            (5.5, "2026-01-31T13:29:59-05:00", "2026-01-31T13:30:00-05:00",
             "2026-01-31", "2026-02-01"),
        ]
        for offset, before, boundary, previous_date, next_date in cases:
            with self.subTest(offset=offset):
                result = self.rollup([
                    dict(id="boundary", start=boundary, duration_ms=120000),
                    dict(id="before", start=before, duration_ms=60000),
                ], offset)
                self.assertEqual([d["date"] for d in result["days"]],
                                 [previous_date, next_date])
                self.assertEqual([d["minutes"] for d in result["days"]], [1, 2])
                self.assertEqual([d["entries"][0]["local"] for d in result["days"]],
                                 ["23:59", "00:00"])
                self.assertEqual([d["entries"][0]["id"] for d in result["days"]],
                                 ["before", "boundary"])

    def test_daylight_saving_requires_separate_fixed_offset_runs(self):
        cases = [
            ("2026-03-08T01:59:00-06:00", "2026-03-08T03:00:00-05:00",
             -6, -5, "01:59", "03:00", "02:00"),
            ("2026-11-01T01:59:00-05:00", "2026-11-01T01:00:00-06:00",
             -5, -6, "01:59", "01:00", "02:00"),
        ]
        for before, after, old_offset, new_offset, old_local, new_local, fixed_local in cases:
            with self.subTest(transition=after):
                records = [dict(id="before", start=before, duration_ms=60000),
                           dict(id="after", start=after, duration_ms=120000)]
                fixed = self.rollup(list(reversed(records)), old_offset)
                self.assertEqual([e["id"] for e in fixed["days"][0]["entries"]],
                                 ["before", "after"])
                self.assertEqual([e["local"] for e in fixed["days"][0]["entries"]],
                                 [old_local, fixed_local])
                first = self.rollup(records[:1], old_offset)
                second = self.rollup(records[1:], new_offset)
                self.assertEqual(first["days"][0]["entries"][0]["local"], old_local)
                self.assertEqual(second["days"][0]["entries"][0]["local"], new_local)
                self.assertEqual(first["total_minutes"] + second["total_minutes"], 3)

    def test_incomplete_listing_unknown_times_and_duration_floor_stay_visible(self):
        listing = {"truncated": True, "scanned": 40, "data": [
            dict(id="short", start="2026-01-15T10:00:00-05:00", duration_ms=59000),
            dict(id="floor", start="2026-01-15T15:00:00Z", duration_ms=60000),
            dict(id="missing", duration_ms=120000),
            dict(id="invalid", start="not a timestamp", duration_ms=180000),
        ]}
        run = self.run_cli(listing, "--offset-hours", "-5", "--min-seconds", "60", "--json")
        self.assertIn("truncated=true", run.stderr)
        self.assertIn("40", run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["counted"], 3)
        self.assertEqual(result["total_minutes"], 6)
        self.assertEqual([e["id"] for e in result["skipped"]], ["short"])
        self.assertEqual(result["skipped"][0]["local"], "10:00")
        self.assertEqual(result["days"][0]["entries"][0]["id"], "floor")
        unknown = result["days"][1]
        self.assertEqual(unknown["date"], "unknown")
        self.assertEqual([e["id"] for e in unknown["entries"]], ["missing", "invalid"])
        self.assertTrue(all(e["local"] == "??:??" for e in unknown["entries"]))
        text = self.run_cli(listing, "--offset-hours", "-5", "--min-seconds", "60").stdout
        self.assertIn("UTC-5", text)
        self.assertIn("unknown, unknown", text)
        self.assertIn("Below the duration floor (1), not counted", text)


if __name__ == "__main__":
    unittest.main()

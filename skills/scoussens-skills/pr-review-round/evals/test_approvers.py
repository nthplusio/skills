"""approvers.py's public CLI against a local forge double; never contacts GitHub."""
import base64
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import approvers

CODEOWNERS = """# Owners
*              @org/core
src/           @author @bob @carol
docs/*.md      @dana   # direct children only
"""
LAST_PUSH = [{"type": "pull_request", "parameters": {"require_last_push_approval": True,
                                                     "required_approving_review_count": 1}}]


class ApproversTests(unittest.TestCase):
    def run_cli(self, owners=None, rules=LAST_PUSH, pusher="bob"):
        """`owners` maps a CODEOWNERS location to its text, or to None for a read that fails."""
        owners = {"CODEOWNERS": CODEOWNERS} if owners is None else owners
        reads = {
            "repos/owner/repo/pulls/17": {"user": {"login": "author"}, "base": {"ref": "main"},
                                          "head": {"ref": "feature", "repo": {"full_name": "owner/repo"}}},
            "repos/owner/repo/pulls/17/files?per_page=100": [[{"filename": "src/app.py"}, {"filename": "docs/guide.md"},
                                                              {"filename": "docs/deep/notes.md"}]],
            "repos/owner/repo/rules/branches/main?per_page=100": rules,
            "repos/owner/repo/activity?ref=refs/heads/feature&per_page=1": [{"actor": {"login": pusher}}],
        }
        for location in approvers.LOCATIONS:
            path = f"repos/owner/repo/contents/{location}?ref=main"
            if location in owners:
                reads[path] = None if owners[location] is None else {
                    "content": base64.b64encode(owners[location].encode()).decode()}

        def forge(command, **kwargs):
            if command[2] not in reads:
                return subprocess.CompletedProcess(command, 1, "", "gh: Not Found (HTTP 404)")
            if reads[command[2]] is None:
                return subprocess.CompletedProcess(command, 1, "", "gh: Server Error (HTTP 502)")
            return subprocess.CompletedProcess(command, 0, json.dumps(reads[command[2]]), "")

        output = io.StringIO()
        with patch.object(sys, "argv", ["approvers.py", "17", "--repo", "owner/repo"]), \
                patch.object(subprocess, "run", side_effect=forge), contextlib.redirect_stdout(output):
            code = approvers.main()
        return output.getvalue(), code

    def test_code_owners_of_the_changed_files_without_the_author_and_last_pusher(self):
        output, code = self.run_cli()
        self.assertEqual(code, 0, output)
        listed = output.split("approvers:\n")[1].splitlines()
        self.assertEqual(listed, ["  @carol  owns src/app.py", "  @dana  owns docs/guide.md",
                                  "  @org/core  owns docs/deep/notes.md"])
        self.assertIn("left out @author: author", output)
        self.assertIn("left out @bob: last pusher; main requires approval of the last push by someone else", output)
        self.assertIn("CODEOWNERS: CODEOWNERS at main", output)
        # Without a last-push rule, the last pusher can approve.
        output, code = self.run_cli(rules=[])
        self.assertIn("  @bob  owns src/app.py", output)
        self.assertNotIn("left out @bob", output)
        # The first location GitHub reads wins.
        output, code = self.run_cli(owners={".github/CODEOWNERS": "* @erin\n", "CODEOWNERS": CODEOWNERS})
        self.assertIn("  @erin  owns src/app.py, docs/guide.md, docs/deep/notes.md", output)

    def test_unreadable_inputs_print_as_unknown_not_as_no_approvers(self):
        output, code = self.run_cli(owners={".github/CODEOWNERS": None, "CODEOWNERS": CODEOWNERS})
        self.assertEqual(code, 1, output)
        self.assertIn("approvers: unknown (CODEOWNERS unreadable at .github/CODEOWNERS", output)
        self.assertNotIn("@carol", output)
        output, code = self.run_cli(rules=None, pusher=None)
        self.assertEqual(code, 1, output)
        self.assertIn("unknown: last pusher unreadable; review rules unreadable", output)
        # A repository with no CODEOWNERS file is a known answer, not an unknown one.
        output, code = self.run_cli(owners={})
        self.assertEqual(code, 0, output)
        self.assertIn("approvers: no CODEOWNERS file at main; any other collaborator with write access", output)


if __name__ == "__main__":
    unittest.main()

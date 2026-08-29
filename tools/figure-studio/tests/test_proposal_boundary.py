from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from verify_figure_proposal_diff import BoundaryError, validate_proposal


class ProposalBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.base = root / "base"
        self.proposal = root / "proposal"
        relative = Path("figure-studio/public/figures/figure-01/make_figure.py")
        target = self.base / relative
        target.parent.mkdir(parents=True)
        original = b"print('original')\n"
        target.write_bytes(original)
        allowlist = {
            "schema_version": 1,
            "status": "public-ready",
            "repository_root": "figure-studio/public",
            "allowed_sha256": {
                "figures/figure-01/make_figure.py": hashlib.sha256(original).hexdigest()
            },
        }
        allowlist_path = self.base / "figure-studio/public/PROPOSAL_ALLOWLIST.json"
        allowlist_path.write_text(json.dumps(allowlist), encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.base)], check=True)
        subprocess.run(["git", "-C", str(self.base), "add", "."], check=True)
        shutil.copytree(self.base, self.proposal, ignore=shutil.ignore_patterns(".git"))
        subprocess.run(["git", "init", "-q", str(self.proposal)], check=True)
        subprocess.run(["git", "-C", str(self.proposal), "add", "."], check=True)
        (self.proposal / relative).write_text("print('revised')\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_exact_allowed_change_passes(self) -> None:
        changed = validate_proposal(self.base, self.proposal)
        self.assertEqual(
            changed,
            ["figure-studio/public/figures/figure-01/make_figure.py"],
        )

    def test_unreviewed_changed_path_fails(self) -> None:
        notes = self.proposal / "figure-studio/public/figures/figure-01/notes.txt"
        notes.write_text("restricted notes\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.proposal), "add", str(notes)], check=True)
        with self.assertRaisesRegex(BoundaryError, "unreviewed path"):
            validate_proposal(self.base, self.proposal)

    def test_unchanged_gitlink_does_not_break_exact_diff_validation(self) -> None:
        gitlink = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        for repository in (self.base, self.proposal):
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"160000,{gitlink},vendor/example-submodule",
                ],
                check=True,
            )
        changed = validate_proposal(self.base, self.proposal)
        self.assertEqual(
            changed,
            ["figure-studio/public/figures/figure-01/make_figure.py"],
        )


if __name__ == "__main__":
    unittest.main()

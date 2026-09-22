import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.restore_research import main


class RestoreResearchTests(unittest.TestCase):
    def run_restore(self, responses, bootstrap="false"):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                with patch.dict(os.environ, {"GITHUB_REPOSITORY":"owner/repo", "GH_API_TOKEN":"test", "RESEARCH_ALLOW_BOOTSTRAP":bootstrap}), patch("scripts.restore_research.requests.get", side_effect=responses):
                    main()
                path=Path("research-state/state.json")
                return json.loads(path.read_text()) if path.exists() else None
            finally:
                os.chdir(previous)

    def test_bootstrap_requires_explicit_authorization(self):
        response=Mock(); response.json.return_value={"artifacts":[]}
        with self.assertRaises(RuntimeError):
            self.run_restore([response])
        self.assertIsNone(self.run_restore([response], "true"))

    def test_api_failure_never_becomes_empty_history(self):
        response=Mock(); response.raise_for_status.side_effect=RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            self.run_restore([response], "true")

    def test_expired_newest_fails_instead_of_using_old_ledger(self):
        response=Mock(); response.json.return_value={"artifacts":[{"id":1,"name":"research-ledger-v1","created_at":"2026-01-01","expired":True,"workflow_run":{"head_branch":"main"}}]}
        with self.assertRaises(RuntimeError):
            self.run_restore([response], "true")

    def test_restores_main_artifact_and_preserves_full_state(self):
        state={"schema_version":1,"records":[],"last_at":"2026-01-01T00:00:00+00:00"}
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,"w") as archive:
            archive.writestr("state.json",json.dumps(state))
        listing=Mock(); listing.json.return_value={"artifacts":[{"id":2,"name":"research-ledger-v1","created_at":"2026-01-01","expired":False,"workflow_run":{"head_branch":"main"}}]}
        download=Mock(); download.content=buffer.getvalue()
        self.assertEqual(self.run_restore([listing,download]),state)


if __name__ == "__main__":
    unittest.main()

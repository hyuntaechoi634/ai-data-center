from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from studio.agent import AgentCancelled, ResponsesFigureAgent, _clean_generated_text


class BackgroundAgentTests(unittest.TestCase):
    @staticmethod
    def _workspace(root: Path) -> Path:
        workspace = root / "workspace"
        (workspace / "figures" / "figure-06").mkdir(parents=True)
        (workspace / "project.json").write_text(
            json.dumps({"entrypoint": "figures/figure-06/make_figure.py"}),
            encoding="utf-8",
        )
        return workspace

    def test_background_response_is_polled_to_completion(self) -> None:
        class Agent(ResponsesFigureAgent):
            def __init__(self) -> None:
                super().__init__()
                self.payload = None
                self.polls = []

            def _request(self, payload: dict) -> dict:
                self.payload = payload
                return {"id": "resp_background123", "status": "queued"}

            def _response_request(self, response_id: str, action: str = "") -> dict:
                self.polls.append((response_id, action))
                return {
                    "id": response_id,
                    "status": "completed",
                    "output_text": json.dumps(
                        {"summary": "No change is needed.", "files": []}
                    ),
                }

        with tempfile.TemporaryDirectory() as temporary:
            workspace = self._workspace(Path(temporary))
            agent = Agent()
            response_ids = []
            with (
                mock.patch.object(agent, "_workspace_context", return_value="bounded"),
                mock.patch.object(agent, "_image_inputs", return_value=[]),
                mock.patch("studio.agent.time.sleep"),
            ):
                result = agent.run(
                    workspace,
                    "Keep the current figure",
                    ["jpg"],
                    [],
                    [],
                    on_response_id=response_ids.append,
                )
        self.assertFalse(result.changed)
        self.assertTrue(agent.payload["background"])
        self.assertEqual(response_ids, ["resp_background123"])
        self.assertEqual(agent.polls, [("resp_background123", "")])

    def test_generated_summary_separator_is_normalized(self) -> None:
        self.assertEqual(
            _clean_generated_text("Low" + chr(0xB7) + "High"),
            "Low, High",
        )

    def test_background_response_can_be_cancelled(self) -> None:
        cancel_event = threading.Event()

        class Agent(ResponsesFigureAgent):
            def __init__(self) -> None:
                super().__init__()
                self.actions = []

            def _request(self, payload: dict) -> dict:
                cancel_event.set()
                return {"id": "resp_cancel123456", "status": "in_progress"}

            def _response_request(self, response_id: str, action: str = "") -> dict:
                self.actions.append((response_id, action))
                return {"id": response_id, "status": "cancelled"}

        with tempfile.TemporaryDirectory() as temporary:
            agent = Agent()
            workspace = Path(temporary) / "workspace"
            with (
                mock.patch.object(agent, "_workspace_context", return_value="bounded"),
                mock.patch.object(agent, "_image_inputs", return_value=[]),
                self.assertRaises(AgentCancelled),
            ):
                agent.run(
                    workspace,
                    "Cancel the revision",
                    ["jpg"],
                    [],
                    [],
                    cancel_event=cancel_event,
                )
        self.assertEqual(agent.actions, [("resp_cancel123456", "cancel")])


if __name__ == "__main__":
    unittest.main()

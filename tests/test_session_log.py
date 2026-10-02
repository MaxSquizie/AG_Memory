from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from ah.agent.llm_agent import LLMAgent, LLMAgentSettings
from ah.diagnostics import session_log
from ah.llm.process_backend import LLMResponse
from ah.projection.contracts import AgentContext


class SessionLogTests(unittest.TestCase):
    def tearDown(self) -> None:
        session_log._active = None

    def test_jsonl_captures_full_llm_payload_and_latest_alias(self) -> None:
        with TemporaryDirectory() as td:
            logs_dir = Path(td)
            logger = session_log.start_session(logs_dir, extra={"backend": "test"})
            session_log.log_llm_request(
                sequence=3,
                req_id="abc",
                role="agent_repair",
                prompt="CURRENT USER INPUT:\nпривет\n\nBAD DRAFT:\n\nReturn only",
                system="repair",
                response_text="Return only the final assistant utterance.",
            )
            records = [
                json.loads(line)
                for line in logger.jsonl_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(records[0]["kind"], "session_start")
            self.assertEqual(records[1]["kind"], "llm_request")
            self.assertEqual(records[1]["role"], "agent_repair")
            self.assertIn("BAD DRAFT", records[1]["prompt"])
            self.assertEqual(logger.latest_jsonl.read_text(encoding="utf-8"), logger.jsonl_path.read_text(encoding="utf-8"))
            self.assertIn("agent_repair", logger.latest_text.read_text(encoding="utf-8"))

    def test_agent_repair_with_empty_draft_is_logged(self) -> None:
        class EchoBackend:
            def __init__(self) -> None:
                self.roles: list[str] = []

            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "agent":
                    return LLMResponse("# CURRENT INPUT\nпривет", {})
                return LLMResponse("Ок, понял.", {})

        with TemporaryDirectory() as td:
            session_log.start_session(Path(td))
            backend = EchoBackend()
            agent = LLMAgent(backend, LLMAgentSettings(repair_attempts=1))
            answer = agent.respond(AgentContext("привет", (), (), "# CURRENT INPUT\nпривет"))
            self.assertEqual(answer, "Ок, понял.")
            self.assertEqual(backend.roles, ["agent", "agent_repair"])
            kinds = [
                json.loads(line)["kind"]
                for line in (Path(td) / "latest.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertIn("agent_sanitize", kinds)
            self.assertIn("agent_repair", kinds)


if __name__ == "__main__":
    unittest.main()

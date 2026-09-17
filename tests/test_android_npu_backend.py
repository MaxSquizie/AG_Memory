from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from shutil import copytree
import json
import unittest

from ah.config import load_config
from ah.llm.android_npu_backend import AndroidNpuBackend, register_engine
from ah.llm.factory import build_llm_backend


def _prepare_android_root(root: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    copytree(repo / "prompts", root / "prompts")
    config_dir = root / "config"
    config_dir.mkdir()
    src = repo / "config" / "android.toml"
    (config_dir / "android.toml").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")



class AndroidNpuBackendTests(unittest.TestCase):
    def tearDown(self) -> None:
        register_engine(None)

    def test_android_toml_selects_npu_backend(self) -> None:
        cfg = load_config(Path(__file__).resolve().parents[1] / "config" / "android.toml")
        self.assertEqual(cfg.llm.backend, "android_npu")
        backend = build_llm_backend(cfg)
        self.assertIsInstance(backend, AndroidNpuBackend)

    def test_generate_uses_registered_engine_and_rejects_choice_outputs(self) -> None:
        cfg = load_config(Path(__file__).resolve().parents[1] / "config" / "android.toml")
        backend = AndroidNpuBackend(cfg)
        register_engine(lambda prompt, system, override, role: f"{role}:{prompt[:8]}")
        backend.start()
        response = backend.generate("HELLO", system="sys", override={"max_new_tokens": 8}, role="perception_act_type")
        self.assertEqual(response.text, "perception_act_type:HELLO")
        with self.assertRaises(RuntimeError):
            backend.generate("x", override={"choice_outputs": ["A", "B"]})
        backend.stop()

    def test_bridge_sessions_and_fail_closed_turn(self) -> None:
        from ah import android_bridge

        register_engine(lambda prompt, system, override, role: "UNCLEAR")
        with TemporaryDirectory() as td:
            root = Path(td)
            _prepare_android_root(root)
            try:
                sid = android_bridge.start(str(root))
                self.assertTrue(sid)
                listed = android_bridge.list_sessions(str(root))
                self.assertEqual(listed[0]["id"], sid)
                payload = json.loads(android_bridge.send("Привет"))
                self.assertEqual(payload["user_text"], "Привет")
                self.assertIn(payload["status"], {"ok", "error"})
                snap = android_bridge.snapshot()
                self.assertIn("nodes", snap)
                self.assertIn("tick", snap)
                self.assertEqual(snap["session_id"], sid)
            finally:
                android_bridge.stop()
                register_engine(None)

    def test_bridge_logs_protocol_mismatch_across_turns(self) -> None:
        from ah import android_bridge

        register_engine(lambda prompt, system, override, role: "Sure, ASSERTION")
        with TemporaryDirectory() as td:
            root = Path(td)
            _prepare_android_root(root)
            try:
                sid = android_bridge.start(str(root))
                first = json.loads(android_bridge.send("Привет"))
                second = json.loads(android_bridge.send("Как дела?"))
                self.assertEqual(first["status"], "error")
                self.assertEqual(first["fail_kind"], "perception")
                self.assertEqual(first["response_error"], "не разобрал")
                self.assertIsNotNone(first.get("last_failed_probe"))
                self.assertIn("Sure, ASSERTION", first["last_failed_probe"]["raw_preview"]["repr"])
                self.assertTrue(first.get("error_log"))
                self.assertIn("слой: perception", first["error_log"])
                self.assertIn("Sure, ASSERTION", first["error_log"])
                chat = android_bridge.messages()
                error_messages = [item["text"] for item in chat if item.get("kind") == "error"]
                self.assertTrue(error_messages)
                self.assertIn("слой: perception", error_messages[-1])
                self.assertIn("Sure, ASSERTION", error_messages[-1])
                self.assertIn("память:", error_messages[-1])
                self.assertEqual(second["fail_kind"], "perception")
                snap = android_bridge.snapshot()
                self.assertGreaterEqual(snap.get("node_count") or len(snap.get("nodes") or []), 2)
                names = " ".join(str(node.get("semantic") or "") for node in snap.get("nodes") or [])
                self.assertTrue("Пользователь" in names or "АГент" in names or len(snap.get("nodes") or []) >= 2)
                debug = android_bridge.debug_log()
                self.assertIn("## turns.jsonl", debug)
                self.assertIn("Привет", debug)
                self.assertIn("Как дела?", debug)
                self.assertIn("perception", debug)
                turns_path = root / "sessions" / sid / "logs" / "turns.jsonl"
                turns = [
                    json.loads(line)
                    for line in turns_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                self.assertEqual(len(turns), 2)
                self.assertEqual(turns[0]["fail_kind"], "perception")
                self.assertEqual(turns[1]["user_text"], "Как дела?")
            finally:
                android_bridge.stop()
                register_engine(None)


if __name__ == "__main__":
    unittest.main()

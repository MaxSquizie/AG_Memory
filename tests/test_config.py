from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ah.config import load_config
from ah.integration import IntegrationConfig
from ah.llm import LocalLLMProcessBackend


class ConfigTests(unittest.TestCase):
    def test_central_config_resolves_model_path_and_drives_integration(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            cfg_dir = root / "config"
            cfg_dir.mkdir()
            model = root / "models" / "qwen"
            model.mkdir(parents=True)
            cfg_path = cfg_dir / "test.toml"
            cfg_path.write_text(
                '''
[paths]
project_dir = ".."
llm_model_dir = "../models/qwen"
data_dir = "../data"
persistence_file = "../data/memory.json"
logs_dir = "../logs"

[integration]
initial_hypernode_weight = 0.47
experience_hypernode_weight = 0.31
follow_link_weight = 0.21
cause_link_weight = 0.19

[workspace]
threshold = 0.42
''',
                encoding="utf-8",
            )
            cfg = load_config(cfg_path)
            self.assertEqual(cfg.paths.llm_model_dir, model.resolve())
            self.assertEqual(cfg.workspace.threshold, 0.42)
            integration = IntegrationConfig.from_settings(cfg.integration)
            self.assertEqual(integration.initial_hypernode_weight, 0.47)
            self.assertEqual(integration.cause_link_weight, 0.19)

    def test_llm_command_contains_only_configured_model_path(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            model = root / "model"
            model.mkdir()
            cfg = root / "config.toml"
            cfg.write_text(
                f'''
[paths]
project_dir = "."
llm_model_dir = "{model.as_posix()}"
data_dir = "data"
persistence_file = "data/memory.json"
logs_dir = "logs"

[llm]
enabled = true
backend = "builtin_process"
loader_type = "auto"
''',
                encoding="utf-8",
            )
            app = load_config(cfg)
            command = LocalLLMProcessBackend(app).build_command()
            self.assertIn(str(model.resolve()), command)
            self.assertIn("ah.llm.worker", command)


if __name__ == "__main__":
    unittest.main()

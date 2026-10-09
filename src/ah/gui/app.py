from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def _imports():
    try:
        from PySide6.QtWidgets import QApplication
        import vispy  # noqa: F401
    except Exception as exc:
        raise SystemExit(
            "GUI extras are not installed. Install with: pip install -e .[gui]\n"
            f"Original import error: {exc}"
        ) from exc
    return QApplication


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AH Agent desktop GUI")
    default = Path(__file__).resolve().parents[3] / "config" / "default.toml"
    env_config = os.environ.get("AH_CONFIG", "").strip()
    if env_config:
        default = Path(env_config).expanduser()
    p.add_argument("--config", default=str(default))
    return p.parse_args()


def _auto_provision_formalizer_config(config_path: Path) -> Path | None:
    """Return an isolated TEST_ONLY fixture config to run against when the configured
    session lacks formalizer resources, else ``None`` (use the configured session as-is).

    Only this GUI convenience path self-provisions; production ``RuntimeServices.build()``
    stays strict. Reuses a previously prepared fixture and never overwrites one.
    """
    from ah.config import load_config
    try:
        cfg = load_config(config_path)
    except Exception:  # noqa: BLE001 - unreadable config: keep the normal startup path
        return None
    data_dir = Path(cfg.paths.data_dir)
    release = data_dir / cfg.formalizer.resource_release_filename
    review = data_dir / cfg.formalizer.review_records_filename
    if release.is_file() and review.is_file():
        return None  # resources present; run the configured session normally
    root = Path(__file__).resolve().parents[3]
    fixture = root / "artifacts" / "gui-local"
    existing = fixture / "gui.toml"
    if existing.is_file():
        return existing  # reuse a previously prepared isolated session
    if fixture.exists():
        return None  # partial/unknown state; do not touch, fall back to inspectable startup
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from tools.prepare_formalizer_v7_gui import prepare
        return Path(prepare(config_path, fixture))
    except Exception as exc:  # noqa: BLE001 - degrade to inspectable startup, never crash the GUI
        print(f"[ah.gui] auto-provision of formalizer resources failed: {exc}", file=sys.stderr)
        return None


def main() -> None:
    QApplication = _imports()
    from ah.bootstrap import RuntimeServices
    from ah.config import load_config
    from ah.diagnostics.session_log import start_session
    from ah.gui.merged_main_window import MainWindow
    from ah.gui.theme import apply_theme

    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    provisioned = _auto_provision_formalizer_config(config_path)
    if provisioned is not None and str(provisioned.resolve()) != str(config_path):
        # Re-exec against the isolated fixture so formalization is available; the second
        # pass finds resources present in that data_dir and proceeds without re-provisioning.
        os.execv(sys.executable, [sys.executable, "-m", "ah.gui.app", "--config", str(provisioned)])
    config = load_config(config_path)
    start_session(config.paths.logs_dir, extra={
        "entry": "gui", "config": str(config_path),
        "backend": config.llm.backend,
        "ollama_model": config.llm.ollama_model,
        "lmstudio_model": config.llm.lmstudio_model,
    })
    services = RuntimeServices.build(config, allow_missing_formalizer_resources=True)
    if services.formalizer_resource_error:
        print(services.formalizer_resource_error, file=sys.stderr)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("AH Agent")
    apply_theme(app)
    window = MainWindow(services, config_path)
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()

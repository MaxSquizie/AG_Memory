from __future__ import annotations

import argparse
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
    p.add_argument("--config", default=str(default))
    return p.parse_args()


def main() -> None:
    QApplication = _imports()
    from ah.bootstrap import RuntimeServices
    from ah.config import load_config
    from ah.gui.main_window import MainWindow

    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    services = RuntimeServices.build(config)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("AH Agent")
    window = MainWindow(services, config_path)
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()

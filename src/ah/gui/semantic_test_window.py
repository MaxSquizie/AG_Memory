from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from PySide6.QtCore import QProcess, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
)

from .main_window import MainWindow as _BaseMainWindow


@dataclass(frozen=True, slots=True)
class _SemanticSuite:
    kind: str
    label: str
    cases_filename: str | None = None
    oracle_filename: str | None = None
    runs_dirname: str | None = None
    pytest_targets: tuple[str, ...] = ()


class MainWindow(_BaseMainWindow):
    """GUI surface exposing only tests that evaluate semantic formalization.

    Historical buttons are kept alive but hidden so inherited worker-completion
    handlers may still safely toggle them.  The visible surface is one selector and
    one run button.  Text->semantic-oracle suites keep using the production
    acceptance runner; typed GoalCompiler contracts use narrow pytest targets because
    their fixtures require preloaded canonical memory and cannot be represented by a
    standalone text/oracle pair without weakening the test.
    """

    _SEMANTIC_SUITES: tuple[_SemanticSuite, ...] = (
        _SemanticSuite(
            "acceptance",
            "Core · semantic formalization",
            "acceptance_cases.txt",
            "acceptance_oracle.json",
            "acceptance_runs",
        ),
        _SemanticSuite(
            "acceptance",
            "M1 · adversarial semantics",
            "acceptance_cases_m1_adversarial.txt",
            "acceptance_oracle_m1_adversarial.json",
            "acceptance_runs_m1_adversarial",
        ),
        _SemanticSuite(
            "acceptance",
            "M1 · inversion",
            "acceptance_inversion/cases.txt",
            "acceptance_inversion/oracle.json",
            "acceptance_runs_m1_inversion",
        ),
        _SemanticSuite(
            "acceptance",
            "M1 · ellipsis",
            "acceptance_ellipsis/cases.txt",
            "acceptance_ellipsis/oracle.json",
            "acceptance_runs_m1_ellipsis",
        ),
        _SemanticSuite(
            "acceptance",
            "M1 · typo / noise",
            "acceptance_typo/cases.txt",
            "acceptance_typo/oracle.json",
            "acceptance_runs_m1_typo",
        ),
        _SemanticSuite(
            "acceptance",
            "Logic · AND / OR / XOR / NOT / IMPLIES",
            "acceptance_logic/cases.txt",
            "acceptance_logic/oracle.json",
            "acceptance_runs_logic",
        ),
        _SemanticSuite(
            "acceptance",
            "Modal / attitude semantics",
            "acceptance_modal/cases.txt",
            "acceptance_modal/oracle.json",
            "acceptance_runs_modal",
        ),
        _SemanticSuite("hidden_valency", "Hidden valency · semantic micro-probe"),
        _SemanticSuite(
            "pytest",
            "GoalCompiler · quantified",
            pytest_targets=(
                "tests/test_quantified_goal_acceptance_2605.py",
                "tests/test_quantified_goal_compiler_2605.py",
            ),
        ),
        _SemanticSuite(
            "pytest",
            "GoalCompiler · counterfactual",
            pytest_targets=(
                "tests/test_counterfactual_goal_acceptance_2605.py",
                "tests/test_counterfactual_goal_compiler_2605.py",
            ),
        ),
        _SemanticSuite(
            "pytest",
            "GoalCompiler · association",
            pytest_targets=(
                "tests/test_association_goal_acceptance_2606.py",
                "tests/test_association_goal_compiler_2606.py",
                "tests/test_association_goal_guards_2606.py",
            ),
        ),
        _SemanticSuite(
            "pytest",
            "GoalCompiler · all current",
            pytest_targets=(
                "tests/test_quantified_goal_acceptance_2605.py",
                "tests/test_quantified_goal_compiler_2605.py",
                "tests/test_counterfactual_goal_acceptance_2605.py",
                "tests/test_counterfactual_goal_compiler_2605.py",
                "tests/test_association_goal_acceptance_2606.py",
                "tests/test_association_goal_compiler_2606.py",
                "tests/test_association_goal_guards_2606.py",
            ),
        ),
    )

    _HIDDEN_LEGACY_CHAT_BUTTONS = (
        "acceptance_button",
        "m1_adversarial_button",
        "m1_inversion_button",
        "m1_ellipsis_button",
        "m1_typo_button",
        "document_acceptance_button",
        "hidden_valency_button",
        "m2_acceptance_button",
    )
    _HIDDEN_NON_SEMANTIC_METRIC_BUTTON_TEXTS = frozenset(
        {
            "Запустить M2 acceptance",
            "Запустить M3 GC acceptance",
        }
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._semantic_test_process: QProcess | None = None
        self._semantic_process_output: list[str] = []
        self._install_semantic_test_controls()

    def _install_semantic_test_controls(self) -> None:
        # Do not delete inherited widgets: old async completion slots reference them.
        # Hiding removes obsolete/redundant controls from the actual operator UI while
        # preserving binary compatibility with MainWindow internals.
        for name in self._HIDDEN_LEGACY_CHAT_BUTTONS:
            widget = getattr(self, name, None)
            if widget is not None:
                widget.hide()

        # M2 proof tracing and M3 GC remain available as metric/diagnostic panels,
        # but their acceptance launchers do not belong in the semantic-test surface.
        for button in self.metrics_panel.findChildren(QPushButton):
            if button.text() in self._HIDDEN_NON_SEMANTIC_METRIC_BUTTON_TEXTS:
                button.hide()

        parent = self.chat_input.parentWidget()
        layout = None if parent is None else parent.layout()
        if layout is None:
            raise RuntimeError("chat dock layout is unavailable for semantic tests")

        row = QHBoxLayout()
        title = QLabel("Semantic tests")
        title.setToolTip(
            "Только проверки text→semantic formalization и typed GoalCompiler. "
            "Document/M2 inference/M3 GC здесь намеренно отсутствуют."
        )
        row.addWidget(title)

        self.semantic_suite = QComboBox()
        self.semantic_suite.setObjectName("semanticSuiteSelector")
        for suite in self._SEMANTIC_SUITES:
            self.semantic_suite.addItem(suite.label)
        self.semantic_suite.setMinimumContentsLength(28)
        row.addWidget(self.semantic_suite, 1)

        self.semantic_test_button = QPushButton("Запустить semantic test")
        self.semantic_test_button.setObjectName("semanticTestRunButton")
        self.semantic_test_button.clicked.connect(self._run_selected_semantic_suite)
        row.addWidget(self.semantic_test_button)

        self.semantic_test_status = QLabel("READY")
        self.semantic_test_status.setObjectName("semanticTestStatus")
        self.semantic_test_status.setMinimumWidth(70)
        row.addWidget(self.semantic_test_status)
        layout.addLayout(row)

    def _selected_semantic_suite(self) -> _SemanticSuite:
        index = self.semantic_suite.currentIndex()
        if not 0 <= index < len(self._SEMANTIC_SUITES):
            raise RuntimeError("semantic test suite selection is invalid")
        return self._SEMANTIC_SUITES[index]

    def _semantic_test_busy(self) -> bool:
        process = self._semantic_test_process
        process_busy = process is not None and process.state() != QProcess.NotRunning
        return bool(
            process_busy
            or getattr(self, "_acceptance_worker", None) is not None
            or getattr(self, "_hidden_valency_worker", None) is not None
        )

    @Slot()
    def _run_selected_semantic_suite(self) -> None:
        if self._semantic_test_busy():
            QMessageBox.information(
                self,
                "Semantic tests",
                "Сначала дождитесь завершения текущей семантической проверки.",
            )
            return

        suite = self._selected_semantic_suite()
        self.semantic_test_status.setText("RUNNING")
        self.semantic_test_button.setEnabled(False)
        self.semantic_suite.setEnabled(False)

        if suite.kind == "acceptance":
            assert suite.cases_filename is not None
            assert suite.oracle_filename is not None
            assert suite.runs_dirname is not None
            self._run_acceptance_pair(
                cases_filename=suite.cases_filename,
                oracle_filename=suite.oracle_filename,
                runs_dirname=suite.runs_dirname,
                label=suite.label,
                title=suite.label,
            )
            # Validation may fail synchronously before a worker is created.
            if getattr(self, "_acceptance_worker", None) is None:
                self._semantic_suite_idle("READY")
            return

        if suite.kind == "hidden_valency":
            self._run_hidden_valency_diagnostic()
            if getattr(self, "_hidden_valency_worker", None) is None:
                self._semantic_suite_idle("READY")
            return

        if suite.kind == "pytest":
            self._run_semantic_pytest(suite)
            return

        self._semantic_suite_idle("ERROR")
        raise RuntimeError(f"unsupported semantic suite kind: {suite.kind}")

    def _run_semantic_pytest(self, suite: _SemanticSuite) -> None:
        if not suite.pytest_targets:
            self._semantic_suite_idle("ERROR")
            raise RuntimeError("semantic pytest suite has no targets")

        repo_root = Path(__file__).resolve().parents[3]
        missing = tuple(
            target
            for target in suite.pytest_targets
            if not (repo_root / target).is_file()
        )
        if missing:
            self._semantic_suite_idle("ERROR")
            QMessageBox.critical(
                self,
                suite.label,
                "Не найдены semantic test targets:\n" + "\n".join(missing),
            )
            return

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.setWorkingDirectory(str(repo_root))
        process.readyReadStandardOutput.connect(self._semantic_pytest_output)
        process.finished.connect(self._semantic_pytest_finished)
        process.errorOccurred.connect(self._semantic_pytest_error)
        self._semantic_test_process = process
        self._semantic_process_output = []

        self.chat_history.append(
            f"<b>{self._html(suite.label)}</b>: pytest "
            + self._html(" ".join(suite.pytest_targets))
        )
        process.start(
            sys.executable,
            ["-m", "pytest", "-q", *suite.pytest_targets],
        )

    @Slot()
    def _semantic_pytest_output(self) -> None:
        process = self._semantic_test_process
        if process is None:
            return
        chunk = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if chunk:
            self._semantic_process_output.append(chunk)

    @Slot(int, QProcess.ExitStatus)
    def _semantic_pytest_finished(
        self,
        exit_code: int,
        _exit_status: QProcess.ExitStatus,
    ) -> None:
        self._semantic_pytest_output()
        output = "".join(self._semantic_process_output).strip()
        label = self._selected_semantic_suite().label
        status = "PASS" if exit_code == 0 else "FAIL"
        self.chat_history.append(
            f"<b>{self._html(label)} {status}</b><br>"
            f"<pre>{self._html(output[-12000:] or '(no pytest output)')}</pre>"
        )
        self._semantic_test_process = None
        self._semantic_process_output = []
        self._semantic_suite_idle(status)

    @Slot(QProcess.ProcessError)
    def _semantic_pytest_error(self, error: QProcess.ProcessError) -> None:
        process = self._semantic_test_process
        if process is None:
            return
        # FailedToStart does not reliably produce a useful finished callback on all
        # Qt backends, so recover the UI explicitly. Runtime crashes normally still
        # proceed through finished where the captured stderr is shown.
        if error == QProcess.FailedToStart:
            label = self._selected_semantic_suite().label
            message = process.errorString() or "pytest process failed to start"
            self.chat_history.append(
                f"<b>{self._html(label)} ERROR:</b> {self._html(message)}"
            )
            self._semantic_test_process = None
            self._semantic_process_output = []
            self._semantic_suite_idle("ERROR")

    def _semantic_suite_idle(self, status: str) -> None:
        self.semantic_test_status.setText(status)
        self.semantic_test_button.setEnabled(True)
        self.semantic_suite.setEnabled(True)

    @Slot()
    def _acceptance_worker_finished(self) -> None:
        super()._acceptance_worker_finished()
        if hasattr(self, "semantic_test_button"):
            self._semantic_suite_idle("DONE")

    @Slot()
    def _hidden_valency_worker_finished(self) -> None:
        super()._hidden_valency_worker_finished()
        if hasattr(self, "semantic_test_button"):
            self._semantic_suite_idle("DONE")

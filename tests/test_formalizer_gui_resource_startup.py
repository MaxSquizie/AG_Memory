"""Missing releases keep the GUI inspectable without weakening production writes."""
from dataclasses import replace
from pathlib import Path

import pytest

from ah.bootstrap import RuntimeServices
from ah.config import load_config
from ah.core import AHCore
from ah.formalizer.resources.loader import ResourceMissing

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config(tmp_path):
    cfg = load_config(ROOT / 'config/lmstudio.toml')
    return replace(cfg, paths=replace(cfg.paths, data_dir=tmp_path,
                   persistence_file=tmp_path / 'memory.json', logs_dir=tmp_path / 'logs'),
                   persistence=replace(cfg.persistence, enabled=False, load_on_start=False))


def test_strict_startup_lists_both_absent_files_without_creating_wal(config):
    with pytest.raises(ResourceMissing) as exc:
        RuntimeServices.build(config, core=AHCore())
    assert str(config.paths.data_dir / 'formalizer_release.json') in str(exc.value)
    assert str(config.paths.data_dir / 'formalizer_reviews.json') in str(exc.value)
    assert not (config.paths.data_dir / config.formalizer.journal_filename).exists()


def test_gui_inspection_mode_keeps_model_but_disables_formalization(config):
    services = RuntimeServices.build(config, core=AHCore(), allow_missing_formalizer_resources=True)
    assert services.llm is not None
    assert services.perception is None
    assert services.formalizer_status.startswith('RESOURCE_MISSING')
    assert 'prepare_formalizer_v7_gui.py' in services.formalizer_resource_error
    with pytest.raises(ResourceMissing, match='formalizer_reviews.json'):
        services.create_orchestrator()
    assert not (config.paths.data_dir / 'formalizer_release.json').exists()
    assert not (config.paths.data_dir / 'formalizer_reviews.json').exists()


def test_gui_reload_keeps_resource_error_explicit(config):
    services = RuntimeServices.build(config, core=AHCore(), allow_missing_formalizer_resources=True)
    services.apply_config(config)
    assert services.perception is None
    assert services.formalizer_resource_error
    disabled = replace(config, llm=replace(config.llm, enabled=False))
    services.apply_config(disabled)
    assert services.formalizer_resource_error is None
    assert services.formalizer_status == 'DISABLED'


def test_disabled_llm_does_not_require_release(config):
    cfg = replace(config, llm=replace(config.llm, enabled=False))
    services = RuntimeServices.build(cfg, core=AHCore())
    assert services.perception is None
    assert services.formalizer_resource_error is None


def test_inspection_mode_does_not_hide_unrelated_runtime_failure(config, monkeypatch):
    from ah import bootstrap
    def corrupted(*args, **kwargs):
        raise RuntimeError('INTEGRITY_ERROR: damaged WAL')
    monkeypatch.setattr(bootstrap, '_build_formalizer_adapter', corrupted)
    with pytest.raises(RuntimeError, match='damaged WAL'):
        RuntimeServices.build(config, core=AHCore(), allow_missing_formalizer_resources=True)


def test_invalid_review_file_is_reported_without_opening_journal(config):
    (config.paths.data_dir / 'formalizer_release.json').write_text('{}', encoding='utf-8')
    (config.paths.data_dir / 'formalizer_reviews.json').write_text('broken', encoding='utf-8')
    services = RuntimeServices.build(config, core=AHCore(), allow_missing_formalizer_resources=True)
    assert 'invalid trusted review file' in services.formalizer_resource_error
    assert services.perception is None
    assert not (config.paths.data_dir / config.formalizer.journal_filename).exists()

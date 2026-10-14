"""Validate the actual session catalog and preserve snapshots on failed startup."""
from dataclasses import replace

import pytest

from ah.bootstrap import RuntimeServices
from ah.config import load_config
from ah.core import AHCore, JsonPersistence
from ah.core.journal import JournalChannel
from ah.formalizer.canonical_ledger import digest
from ah.gui.config_store import ConfigDocument
from ah.model import ActantRole
from tools.prepare_formalizer_v7_gui import check_composition_session, prepare
from test_formalizer_v7_gui_fixture import source_config


def session(tmp_path):
    return prepare(source_config(tmp_path), tmp_path/'session', profile='composition')


def files(directory):
    return {str(p.relative_to(directory)): p.read_bytes()
            for p in directory.rglob('*') if p.is_file()}


def test_missing_catalog_reports_actual_cause_and_does_not_modify_session(tmp_path):
    path = session(tmp_path)
    cfg = load_config(path)
    JsonPersistence(cfg.paths.persistence_file, cfg.persistence).save(AHCore())
    before = files(path.parent)
    with pytest.raises(ValueError, match='шаблон отсутствует') as exc:
        check_composition_session(path)
    assert 'fixture:T:ARRIVE' in str(exc.value)
    assert str(cfg.paths.persistence_file) in str(exc.value)
    assert files(path.parent) == before


@pytest.mark.parametrize('field', ['enabled', 'load_on_start'])
def test_preflight_rejects_disabled_seed_loading(tmp_path, field):
    path = session(tmp_path)
    doc = ConfigDocument(path)
    doc.set('persistence.'+field, False)
    doc.save()
    before = files(path.parent)
    with pytest.raises(ValueError, match='Загрузка подготовленной памяти отключена'):
        check_composition_session(path)
    assert files(path.parent) == before


def test_preflight_reports_missing_memory_file(tmp_path):
    path = session(tmp_path)
    load_config(path).paths.persistence_file.unlink()
    before = files(path.parent)
    with pytest.raises(ValueError, match='Файл памяти с каталогом шаблонов отсутствует'):
        check_composition_session(path)
    assert files(path.parent) == before


def test_preflight_distinguishes_changed_roles_from_missing_template(tmp_path):
    path = session(tmp_path)
    cfg = load_config(path)
    persistence = JsonPersistence(cfg.paths.persistence_file, cfg.persistence)
    core = persistence.load().core
    core.expand_template_roles('fixture:T:ARRIVE', (ActantRole.OBJECT,))
    persistence.save(core)
    with pytest.raises(ValueError, match='роли не совпадают') as exc:
        check_composition_session(path)
    assert 'OBJECT' in str(exc.value) and 'SUBJECT' in str(exc.value)


def test_preflight_checks_recovered_catalog_without_writing_original_wal(tmp_path):
    path = session(tmp_path)
    cfg = load_config(path)
    persistence = JsonPersistence(cfg.paths.persistence_file, cfg.persistence)
    snapshot = persistence.export(persistence.load().core)
    journal = JournalChannel(cfg.paths.data_dir/cfg.formalizer.journal_filename)
    journal.append('canonical', {'kind': 'canonical_unit', 'snapshot': snapshot,
                                'snapshot_hash': digest(snapshot)})
    persistence.save(AHCore())  # The newer catalog is in the WAL.
    before = files(path.parent)
    check_composition_session(path)
    assert files(path.parent) == before


def test_failed_gui_start_cannot_overwrite_unloaded_valid_snapshot(tmp_path):
    path = session(tmp_path)
    cfg = load_config(path)
    before = cfg.paths.persistence_file.read_bytes()
    cfg = replace(cfg, persistence=replace(cfg.persistence, load_on_start=False))
    services = RuntimeServices.build(cfg, allow_missing_formalizer_resources=True)
    assert services.perception is None
    assert 'шаблон отсутствует' in services.formalizer_resource_error
    assert 'загрузка при запуске: False' in services.formalizer_resource_error
    assert not services.persistence.settings.enabled
    services.save()
    services.persistence.maybe_autosave(services.core, ignition=services.ignition,
                                      context=services.context)
    services.stop()
    assert cfg.paths.persistence_file.read_bytes() == before
    check_composition_session(path)


def test_seed_survives_lifecycle_save_and_restart(tmp_path):
    path = session(tmp_path)
    cfg = load_config(path)
    services = RuntimeServices.build(cfg)
    for _ in range(50):
        services.ignition.tick()
    services.save()
    restarted = RuntimeServices.build(cfg)
    assert restarted.perception._formalizer.native_available
    check_composition_session(path)

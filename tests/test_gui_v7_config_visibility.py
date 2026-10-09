"""Retired parser settings stay in TOML but cannot masquerade as V7 controls."""
from pathlib import Path
import os
import tomllib

import pytest

from ah.gui.config_store import ConfigDocument, is_visible_config_setting

PROJECT=Path(__file__).resolve().parents[1]
LEGACY_PATHS=(
    'paths.perception_prompt_path','paths.perception_prompt_dir',
    'llm.perception.protocol','llm.perception.probe_retry_attempts',
    'llm.perception.ground_actants','llm.perception.max_actants_per_act',
    'llm.perception.predicate_symbol_language','llm.perception.embedding_model',
    'llm.perception.max_new_tokens','llm.perception.temperature',
    'llm.perception.top_p','llm.perception.top_k',
    'llm.perception.repetition_penalty','llm.perception.no_repeat_ngram_size',
    'llm.perception.use_cache',
)


def copy_config(tmp_path):
    target=tmp_path/'config.toml'
    target.write_text((PROJECT/'config/lmstudio.toml').read_text(encoding='utf-8')
                      +'\n[formalizer]\nnative_commit = true\n',encoding='utf-8')
    return target


def tree_paths(editor):
    from PySide6.QtCore import Qt
    result={}
    for i in range(editor.tree.topLevelItemCount()):
        section=editor.tree.topLevelItem(i)
        for j in range(section.childCount()):
            item=section.child(j)
            result[item.data(0,Qt.ItemDataRole.UserRole)]=item
    return result


def test_visibility_hides_only_retired_parser_controls():
    assert all(not is_visible_config_setting(path) for path in LEGACY_PATHS)
    assert not is_visible_config_setting('llm.perception.unknown_legacy_setting')
    assert is_visible_config_setting('llm.perception.morphology_backend')
    for path in ('paths.agent_prompt_path','paths.system_prompt_path','llm.agent.temperature',
                 'llm.agent.max_new_tokens','llm.enable_thinking','llm.backend',
                 'formalizer.native_commit','paths.data_dir'):
        assert is_visible_config_setting(path)


def test_document_preserves_hidden_settings_when_visible_agent_parameter_saved(tmp_path):
    path=copy_config(tmp_path)
    document=ConfigDocument(path)
    before={key:document.get(key) for key in LEGACY_PATHS}
    document.set('llm.agent.temperature',0.37)
    document.save()
    after=ConfigDocument(path)
    assert {key:after.get(key) for key in LEGACY_PATHS}==before
    assert after.get('llm.agent.temperature')==0.37
    # Filtering the UI never filters the underlying editable/persisted document.
    assert set(LEGACY_PATHS)<=set(entry.path for entry in after.entries())


@pytest.fixture
def qt_app():
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    QtWidgets=pytest.importorskip('PySide6.QtWidgets')
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_real_config_tree_excludes_retired_settings_and_keeps_agent(tmp_path,qt_app):
    from ah.gui.config_editor import ConfigEditor
    editor=ConfigEditor(copy_config(tmp_path))
    try:
        paths=tree_paths(editor)
        assert not set(LEGACY_PATHS)&set(paths)
        assert {path for path in paths if path.startswith('llm.perception.')}=={
            'llm.perception.morphology_backend'}
        assert 'llm.agent.temperature' in paths and 'paths.agent_prompt_path' in paths
        assert 'formalizer.native_commit' in paths
    finally:editor.close()


def test_real_editor_save_preserves_hidden_values_and_uses_visible_controls(tmp_path,qt_app):
    from ah.gui.config_editor import ConfigEditor
    path=copy_config(tmp_path)
    before=tomllib.loads(path.read_text(encoding='utf-8'))
    editor=ConfigEditor(path)
    saved=[]
    editor.config_saved.connect(lambda config,changed:saved.append(changed))
    try:
        items=tree_paths(editor)
        items['llm.agent.temperature'].setText(1,'0.37')
        items['llm.perception.morphology_backend'].setText(1,'none')
        assert editor.document.changed_paths()==('llm.agent.temperature',
                                                'llm.perception.morphology_backend')
        editor._save()
        qt_app.processEvents()
        after=tomllib.loads(path.read_text(encoding='utf-8'))
        assert after['paths']['perception_prompt_path']==before['paths']['perception_prompt_path']
        assert after['paths']['perception_prompt_dir']==before['paths']['perception_prompt_dir']
        for key,value in before['llm']['perception'].items():
            assert after['llm']['perception'][key]==('none' if key=='morphology_backend' else value)
        assert after['llm']['agent']['temperature']==0.37
        assert saved==[('llm.agent.temperature','llm.perception.morphology_backend')]
        assert not set(LEGACY_PATHS)&set(tree_paths(editor))
        assert not editor.document.dirty
    finally:editor.close()

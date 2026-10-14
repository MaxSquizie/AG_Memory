from copy import deepcopy
import json
import pytest
from ah.gui.formalization_inspection import Inspection,preview

_QT_APP=None

def qt_application():
    global _QT_APP
    from PySide6.QtWidgets import QApplication
    _QT_APP=QApplication.instance() or QApplication([])
    return _QT_APP


@pytest.fixture(scope='session')
def qt_session():
    pytest.importorskip('PySide6')
    app=qt_application()
    yield app
    from PySide6.QtCore import QCoreApplication,QEvent
    for widget in app.topLevelWidgets():widget.close();widget.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    app.processEvents()


def snapshot():
    return {'source_text':'😀 Каждый студент читает.', 'state':{
        'frames':[{'frame_id':'f','anchor_span':'читает','source_range':[17,23],
            'predicate_token_ref':'p','semantic':{'operator_forest':[{'operator':'NOT','operands':[{'frame_ref':'f'}]}]}}],
        'evidence':[{'token_id':'p','span':'читает','start':17,'end':23},
                    {'token_id':'u','span':'студент','start':9,'end':16}],
        'decisions':{'d':{'frame_id':'f','slot_id':'predicate_value','outcome':'RESOLVED',
                          'last_prompt':'ACTUAL PROMPT','raw_response':'1'}},
        'syntax_trace':[{'kind':'SCOPE_BOUNDARY','boundary_ref':'b','source_range':[2,23]}],
        'diagnostics':[],'structural_hash':'structure'},
        'commit_receipt':{'terminal':'APPLIED','observation_id':'o','committed_fragments':['f']}}


def test_index_links_source_raw_choices_and_human_notes_are_read_only():
    data=snapshot();before=deepcopy(data);index=Inspection(data)
    assert index.by_ref['d'].source_range==[17,23]
    assert 'f' in index.links(index.by_ref['d'])
    assert index.by_ref['b'].category=='Границы условий'
    assert index.by_ref['u|unanchored'].status=='UNANCHORED ≠ ERROR'
    note=index.note(index.by_ref['f'],'Ожидалась другая область','Неточность')
    assert note['observation_id']=='o' and note['source_sha256']==index.source_sha256
    assert note['authority']=='HUMAN_REVIEW_ONLY'
    assert data==before


def test_trace_pagination_and_preview_bound_memory():
    data=snapshot();data['state']['syntax_trace']=[{'kind':'DOMAIN','states':{'large':'x'*200000}} for _ in range(1000)]
    index=Inspection(data);rows,count=index.page('Трасса',offset=150)
    assert count==1000 and len(rows)==150 and rows[0].ref=='trace:150'
    assert len(preview(rows[0].record,limit=1000))<1200


def test_gui_inspector_selects_unicode_span_and_reopens_review(tmp_path,qt_session):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from ah.gui.formalization_inspector import FormalizationInspector
    app=qt_application()
    window=FormalizationInspector();window.set_snapshot(snapshot())
    entry=window.inspection.by_ref['f'];window.show_source(entry.source_range)
    assert window.source.textCursor().selectedText()=='читает'
    note=window.inspection.note(entry,'Проверить','Нужна проверка')
    p=tmp_path/'review.json';p.write_text(json.dumps({'schema':'formalization-review-1','snapshot':snapshot(),'notes':[note]}))
    window.load_path(p);assert window.notes==[note]
    window.close()


def test_stopped_report_does_not_display_previous_result(tmp_path,qt_session):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from ah.gui.formalization_inspector import FormalizationInspector
    app=qt_application()
    window=FormalizationInspector();window.set_snapshot(snapshot())
    p=tmp_path/'report.json';p.write_text(json.dumps({'schema':'document-reading-1','error':{'message':'provider stopped'}}))
    window.load_path(p)
    assert not window.inspection.text
    assert window.inspection.snapshot['commit_receipt']=={}
    assert window.inspection.by_ref['diagnostic:0'].record['detail']['message']=='provider stopped'
    window.close()


def test_document_text_entry_and_new_run_clear_previous_receipt(qt_session):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from ah.gui.document_panel import DocumentPanelWidget
    app=qt_application()
    panel=DocumentPanelWidget();seen=[];panel.text_requested.connect(seen.append)
    panel.text_input.setPlainText('  Каждый студент читает.\n');panel.text_button.click()
    assert seen==['  Каждый студент читает.\n']
    panel.set_reading_report({'source_path':'source.txt','status':'EXECUTED','elapsed_seconds':1,
        'output_dir':'previous','source_ref':'old'})
    assert panel.inspect_button.isEnabled()
    panel.begin_reading();panel.set_busy(True)
    assert panel._report_path is None and panel._source_ref is None
    assert not panel.inspect_button.isEnabled() and not panel.text_button.isEnabled()
    panel.close()


def test_native_graph_projection_is_addressed_bounded_and_not_aliased():
    from types import SimpleNamespace
    from ah.formalizer.diagnostic_graph import capture
    nodes={'root':{'function_id':'FORALL','operands':[{'bound_var':1},'body']},
           'body':{'actants':{'SUBJECT':{'bound_var':1}},'source_ref':'p'},
           'unrelated':{'secret':'must not be projected'}}
    store=SimpleNamespace(ledger=SimpleNamespace(data={'nodes':nodes}))
    result=capture(store,['root']);assert set(result['nodes'])=={'root','body'}
    assert capture(store,['root'],limit=1)['truncated']
    data=snapshot();data['committed_graph']=result;index=Inspection(data)
    assert index.by_ref['root'].status=='RECEIPT'
    assert index.by_ref['body'].status=='STRUCTURAL DESCENDANT'
    result['nodes']['body']['actants'].clear()
    assert nodes['body']['actants']=={'SUBJECT':{'bound_var':1}}


def test_readable_default_navigation_and_optional_raw_data(qt_session,tmp_path):
    from PySide6.QtCore import QUrl
    from ah.gui.formalization_inspector import FormalizationInspector
    from test_formalization_readable import sample
    w=FormalizationInspector();data=sample();before=deepcopy(data);w.set_snapshot(data)
    assert w.tabs.currentIndex()==0 and not w.technical.toPlainText()
    assert 'Как система поняла текст' in w.detail.toPlainText()
    w.follow_link(QUrl('review:gap'))
    assert w.current.ref=='gap' and not w.search.text()
    assert w.source.textCursor().selectedText()=='читает'
    assert 'Тот же связанный участник' in w.detail.toPlainText()
    assert not w.technical.toPlainText()
    w.tabs.setCurrentIndex(1)
    assert 'raw_response' in w.technical.toPlainText()
    assert data==before
    w.close()

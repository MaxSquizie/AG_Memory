"""Source-linked native trace browser, opened on demand, never a runtime writer."""
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QTextCursor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QLineEdit,
    QPushButton,QSplitter,QPlainTextEdit,QTreeWidget,QTreeWidgetItem,QFileDialog,QMessageBox,QTextEdit,QHeaderView,QTextBrowser,QTabWidget)
from .formalization_inspection import Inspection,Entry,preview
from .formalization_readable import ReadableInspection,STATUS,document
from urllib.parse import unquote


class FormalizationInspector(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('Проверка формализации');self.resize(1250,900)
        self.inspection=None;self.notes=[];self.offset=0;self.current=None;self.path=None;self._notes_by_source={}
        root=QVBoxLayout(self);bar=QHBoxLayout()
        open_button=QPushButton('Открыть сохранённый разбор…');open_button.clicked.connect(self.open_file);bar.addWidget(open_button)
        readable=QPushButton('Сохранить читаемый отчёт…');readable.clicked.connect(self.export_readable);bar.addWidget(readable)
        export=QPushButton('Сохранить для повторного открытия…');export.clicked.connect(self.export);bar.addWidget(export);root.addLayout(bar)
        self.summary=QLabel('Откройте сохранённый разбор. В обзоре появится понятное описание результата.');self.summary.setWordWrap(True);root.addWidget(self.summary)
        self.category=QComboBox();self.category.addItem('Все разделы','')
        self.search=QLineEdit();self.search.setPlaceholderText('Найти слово, действие или вопрос')
        filters=QHBoxLayout();filters.addWidget(self.category);filters.addWidget(self.search,1);root.addLayout(filters)
        split=QSplitter(Qt.Orientation.Horizontal);root.addWidget(split,1)
        self.rows=QTreeWidget();self.rows.setHeaderLabels(['Часть разбора']);split.addWidget(self.rows)
        self.rows.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        right=QSplitter(Qt.Orientation.Vertical);split.addWidget(right)
        self.source=QPlainTextEdit();self.source.setReadOnly(True);right.addWidget(self.source)
        self.tabs=QTabWidget();right.addWidget(self.tabs)
        self.detail=QTextBrowser();self.detail.setOpenLinks(False);self.detail.anchorClicked.connect(self.follow_link)
        self.tabs.addTab(self.detail,'Понятное описание')
        self.technical=QPlainTextEdit();self.technical.setReadOnly(True)
        self.tabs.addTab(self.technical,'Технические данные');self.tabs.currentChanged.connect(self.show_technical)
        split.setSizes([300,950]);right.setSizes([140,650])
        nav=QHBoxLayout();prev=QPushButton('←');nxt=QPushButton('→');self.page_label=QLabel()
        prev.clicked.connect(lambda:self.move(-150));nxt.clicked.connect(lambda:self.move(150))
        nav.addWidget(prev);nav.addWidget(nxt);nav.addWidget(self.page_label);root.addLayout(nav)
        self.links=QComboBox();jump=QPushButton('Перейти к связанному объекту');jump.clicked.connect(self.jump)
        linkrow=QHBoxLayout();linkrow.addWidget(self.links,1);linkrow.addWidget(jump);root.addLayout(linkrow)
        self.comment=QLineEdit();self.comment.setPlaceholderText('Что неверно, что ожидалось или что нужно проверить')
        self.verdict=QComboBox();self.verdict.addItems(['Нужна проверка','Ошибка','Неточность','Проверено вручную'])
        add=QPushButton('Добавить замечание');add.clicked.connect(self.add_note)
        review=QHBoxLayout();review.addWidget(self.verdict);review.addWidget(self.comment,1);review.addWidget(add);root.addLayout(review)
        self.notes_status=QLabel('Замечания хранятся только в экспорте; AH не изменяется.');root.addWidget(self.notes_status)
        self.category.currentIndexChanged.connect(self.reset_page);self.search.returnPressed.connect(self.reset_page)
        self.rows.currentItemChanged.connect(self.selected)

    def set_snapshot(self,snapshot,*,path=None,notes=()):
        if self.inspection:self._notes_by_source[self.inspection.source_sha256]=list(self.notes)
        self.inspection=Inspection(snapshot);self.path=path
        overview=Entry('Обзор','human-overview','Как система поняла текст','',{})
        self.inspection.entries.insert(0,overview);self.inspection.by_ref[overview.ref]=overview
        self.readable=ReadableInspection(self.inspection)
        for e in self.inspection.entries:e.label=self.readable.title(e)
        self.notes=list(notes) if notes else self._notes_by_source.get(self.inspection.source_sha256,[])
        self.offset=0;self.current=None
        self.category.blockSignals(True);self.category.clear();self.category.addItem('Все разделы','')
        order=['Обзор','Граф AH','Формулы','Фреймы','Границы условий','Решения','Привязки','Морфология','Без привязки','Диагностика','Пробы','Контекст','Области','Трасса','Результат']
        categories={e.category for e in self.inspection.entries}
        for name in order:
            if name in categories:self.category.addItem(name,name)
        self.category.setCurrentIndex(1)
        self.category.blockSignals(False);self.search.clear();self.detail.clear();self.links.clear();self.technical.clear();self.tabs.setCurrentIndex(0)
        receipt=snapshot.get('commit_receipt',{});state=self.inspection.state
        self.summary.setText(f"{STATUS.get(receipt.get('terminal'),'Запись результата не подтверждена')} · записанных фрагментов: {len(receipt.get('committed_fragments',[]))} · "
            f"диагностических сообщений: {len(state.get('diagnostics',[]))}\n"
            'Сравните вложенные условия и участников с исходным текстом. Нажатие на действие открывает его разбор.')
        self.notes_status.setText(f'Замечаний: {len(self.notes)}. Экспортируйте их для сохранения. AH не изменяется.')
        self.show_source(None);self.render()

    def load_path(self,path):
        path=Path(path);value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema')=='document-reading-1':
            report=value;artifact=path.parent/'interpretation.json'
            value=json.loads(artifact.read_text(encoding='utf-8')) if artifact.is_file() else {
                'state':{'diagnostics':[{'code':'RUN_WITHOUT_IR','detail':report.get('error')}]},'commit_receipt':{}}
        if value.get('schema')=='formalization-review-1':
            self.set_snapshot(value['snapshot'],path=str(path),notes=value.get('notes',()))
        else:
            if 'state' not in value and 'commit_receipt' not in value:raise ValueError('Это не снимок формализации')
            self.set_snapshot(value,path=str(path))

    def open_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Открыть разбор','','JSON (*.json)')
        if path:
            try:self.load_path(path)
            except (OSError,ValueError,KeyError,TypeError) as exc:QMessageBox.warning(self,'Разбор',str(exc))

    def export(self):
        if not self.inspection:return
        path,_=QFileDialog.getSaveFileName(self,'Сохранить проверку','formalization-review.json','JSON (*.json)')
        if not path:return
        value={'schema':'formalization-review-1','semantic_correctness':'NOT_AUTOMATICALLY_EVALUATED',
            'source_sha256':self.inspection.source_sha256,'origin_artifact':self.path,
            'snapshot':self.inspection.snapshot,'notes':self.notes}
        try:
            with Path(path).open('w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
            self.notes_status.setText('Проверка сохранена: '+path)
        except OSError as exc:QMessageBox.warning(self,'Экспорт',str(exc))

    def export_readable(self):
        if not self.inspection:return
        path,_=QFileDialog.getSaveFileName(self,'Сохранить читаемый отчёт','formalization-review.html','HTML (*.html)')
        if not path:return
        try:
            Path(path).write_text(self.readable.report(self.notes),encoding='utf-8')
            self.notes_status.setText('Читаемый отчёт сохранён: '+path)
        except OSError as exc:QMessageBox.warning(self,'Отчёт',str(exc))

    def reset_page(self,*_):self.offset=0;self.render()
    def move(self,delta):self.offset=max(0,self.offset+delta);self.render()
    def render(self):
        if not self.inspection:return
        entries,count=self.inspection.page(self.category.currentData(),self.search.text(),self.offset)
        if not entries and self.offset:self.offset=max(0,((count-1)//150)*150);entries,count=self.inspection.page(self.category.currentData(),self.search.text(),self.offset)
        self.rows.clear()
        for e in entries:
            label=e.label if self.category.currentData() else e.category+' · '+e.label
            if e.category in {'Решения','Пробы'} and e.source_range:
                label='«'+self.readable.excerpt(e.source_range,50)+'»\n'+label.split(' · ')[0]
            status=STATUS.get(e.status,'Состояние записано' if e.status else '')
            row=QTreeWidgetItem([label+('\n'+status if status else '')]);row.setData(0,Qt.ItemDataRole.UserRole,e)
            row.setToolTip(0,e.label+('\n'+status if status else ''));self.rows.addTopLevelItem(row)
        self.page_label.setText(f'{self.offset+1 if count else 0}–{min(self.offset+150,count)} / {count}')
        if self.rows.topLevelItemCount():self.rows.setCurrentItem(self.rows.topLevelItem(0))

    def show_source(self,bounds):
        text=self.inspection.text;start,end=bounds if bounds and len(bounds)==2 else (0,0)
        start=max(0,min(start,len(text)));end=max(start,min(end,len(text)))
        left=max(0,start-2000) if len(text)>60000 else 0;right=min(len(text),max(start+12000,min(end+2000,left+60000))) if left or len(text)>60000 else len(text)
        chunk=text[left:right];self.source.setPlainText(chunk)
        self.source.setToolTip(f'Исходные смещения [{left}, {right}); выбранный фрагмент [{start}, {end})')
        cursor=self.source.textCursor();cursor.setPosition(len(text[left:start].encode('utf-16-le'))//2)
        cursor.setPosition(len(text[left:min(end,right)].encode('utf-16-le'))//2,QTextCursor.MoveMode.KeepAnchor)
        highlight=QTextEdit.ExtraSelection();highlight.cursor=cursor;highlight.format.setBackground(QColor('#476951'))
        self.source.setExtraSelections([highlight]);self.source.setTextCursor(cursor);self.source.ensureCursorVisible()

    def selected(self,row,previous=None):
        if row is None:return
        entry=row.data(0,Qt.ItemDataRole.UserRole)
        if entry is None:return
        self.current=entry;self.show_source(entry.source_range)
        self.detail.setHtml(document(self.readable.explain(entry)));self.technical.clear();self.show_technical();self.links.clear()
        for ref in self.inspection.links(entry):self.links.addItem(self.readable.title(self.inspection.by_ref[ref]),ref)
        if entry.category=='Формулы' and row.childCount()==0:self.formula_children(row,entry.record)

    def formula_children(self,parent,node,depth=0):
        if depth>=32:return
        for child in node.get('operands',()):
            ref=child.get('frame_ref');entry=self.inspection.by_ref.get(ref)
            label=entry.label if entry else self.readable.node_label(child)
            row=QTreeWidgetItem([str(label),'']);parent.addChild(row)
            if entry:row.setData(0,Qt.ItemDataRole.UserRole,entry)
            else:
                parent_entry=parent.data(0,Qt.ItemDataRole.UserRole)
                bounds=(child.get('scope_boundary') or {}).get('source_range')
                row.setData(0,Qt.ItemDataRole.UserRole,Entry('Подформула',str((parent_entry.ref if parent_entry else 'tree'))+'/'+str(parent.childCount()),str(label),'STRUCTURE ≠ FACT',child,bounds))
            self.formula_children(row,child,depth+1)
        parent.setExpanded(True)

    def show_technical(self,*_):
        if self.current and self.tabs.currentIndex()==1:
            self.technical.setPlainText(self.current.ref+'\n'+preview(self.current.record))

    def follow_link(self,url):
        if url.scheme()=='review':self.jump_to(unquote(url.toString()[len('review:'):]))

    def jump(self):self.jump_to(self.links.currentData())

    def jump_to(self,ref):
        if not ref or not self.inspection:return
        entry=self.inspection.by_ref.get(ref)
        if not entry:return
        self.category.blockSignals(True)
        self.category.setCurrentIndex(self.category.findData(entry.category))
        self.category.blockSignals(False);self.search.clear()
        entries=[e for e in self.inspection.entries if e.category==entry.category]
        self.offset=(next(i for i,e in enumerate(entries) if e.ref==ref)//150)*150
        self.render()
        for i in range(self.rows.topLevelItemCount()):
            row=self.rows.topLevelItem(i)
            if row.data(0,Qt.ItemDataRole.UserRole).ref==ref:self.rows.setCurrentItem(row);break

    def add_note(self):
        if not self.current:return
        try:self.notes.append(self.inspection.note(self.current,self.comment.text(),self.verdict.currentText()))
        except ValueError as exc:QMessageBox.warning(self,'Замечание',str(exc));return
        self.comment.clear();self.notes_status.setText(f'Замечаний: {len(self.notes)}. Экспортируйте для сохранения.')

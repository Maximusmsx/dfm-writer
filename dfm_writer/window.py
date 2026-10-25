from pathlib import Path
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon, QFontDatabase
from PyQt6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QLineEdit,QPushButton,QComboBox,QGroupBox,QFileDialog,QListWidget,
    QListWidgetItem,QCheckBox,QProgressBar,QPlainTextEdit,QMessageBox)
from .config import ConfigStore, application_dir
from .core import DfmDocument,discover_memos,prefixes,replacement_rules,assignment_colons
from .jobs import Worker


class MainWindow(QMainWindow):
    def __init__(self,store=None):
        super().__init__()
        # Offscreen Qt has no system font discovery; use the Windows font for verification too.
        if not QFontDatabase.families():
            import os
            font = Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'msyh.ttc'
            if font.exists():
                QFontDatabase.addApplicationFont(str(font))
        self.store = store or ConfigStore()
        self.current_profile = ''
        self.loading = True
        self.selected = set()
        self.memos = []
        self.worker = None
        self.setWindowTitle('数据直写DFM')
        self.resize(1000,980)
        self.setMinimumSize(820,940)
        icon = application_dir()/'assets'/'dfm.ico'
        if not icon.exists():
            import sys
            icon = Path(getattr(sys,'_MEIPASS',application_dir()))/'assets'/'dfm.ico'
        self.setWindowIcon(QIcon(str(icon)))
        self._build()
        self.loading = False
        self._refresh_profiles()
        last = self.store.data.get('last_profile','')
        names = self.store.data['profiles']
        if names:
            self.load_profile(last if last in names else next(iter(names)))
        else:
            self.combo.setEditText('默认配置')
            self.save_profile()

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22,18,22,18)
        layout.setSpacing(10)
        title = QLabel('数据直写 DFM')
        title.setFont(QFont('Microsoft YaHei UI',19,QFont.Weight.Bold))
        title.setStyleSheet('font-size:22px;font-weight:700;')
        layout.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel('配置'))
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.setMinimumWidth(240)
        self.combo.activated.connect(lambda i:self.load_profile(self.combo.itemText(i)))
        self.combo.lineEdit().returnPressed.connect(self._profile_entered)
        top.addWidget(self.combo,1)
        self.save_button = QPushButton('保存当前配置')
        self.save_button.setObjectName('save')
        self.save_button.clicked.connect(self.save_profile)
        top.addWidget(self.save_button)
        self.delete_button = QPushButton('删除当前配置')
        self.delete_button.setObjectName('delete')
        self.delete_button.clicked.connect(self.delete_profile)
        top.addWidget(self.delete_button)
        layout.addLayout(top)

        db = QGroupBox('1. 数据库连接配置')
        grid = QGridLayout(db)
        self.user = QLineEdit()
        self.user.setPlaceholderText('用户名')
        self.password = QLineEdit()
        self.password.setPlaceholderText('密码')
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.dsn = QLineEdit()
        self.dsn.setPlaceholderText('主机:端口/服务名，例如 127.0.0.1:1521/orcl')
        grid.addWidget(self.user,0,0)
        grid.addWidget(self.password,0,1)
        grid.addWidget(self.dsn,1,0,1,2)
        self.connect_button = QPushButton('连接 / 测试数据库')
        self.connect_button.clicked.connect(lambda:self.start_job(True))
        self.status = QLabel('● 未连接')
        self.status.setStyleSheet('color:#64748b;')
        grid.addWidget(self.connect_button,2,0)
        grid.addWidget(self.status,2,1)
        layout.addWidget(db)
        for field in (self.user,self.password,self.dsn):
            field.textChanged.connect(self._credentials_changed)
            field.editingFinished.connect(self.autosave)

        file_group = QGroupBox('2. DFM 文件选择')
        file_layout = QVBoxLayout(file_group)
        row = QHBoxLayout()
        self.file = QLineEdit()
        self.file.setPlaceholderText('输入或选择要修改的 .dfm 文件')
        self.file.editingFinished.connect(self.scan_file)
        row.addWidget(self.file,1)
        self.browse = QPushButton('浏览…')
        self.browse.clicked.connect(self.browse_file)
        row.addWidget(self.browse)
        self.refresh = QPushButton('重新读取')
        self.refresh.clicked.connect(self.scan_file)
        row.addWidget(self.refresh)
        file_layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel('目标 DFM'))
        self.target = QComboBox()
        self.target.addItem('Delphi 7（默认）','7')
        self.target.addItem('Delphi 5','5')
        self.target.currentIndexChanged.connect(self._target_changed)
        row.addWidget(self.target)
        self.target_hint = QLabel('Unicode 数字转义 · 无 BOM')
        self.target_hint.setStyleSheet('color:#64748b;font-size:12px;')
        row.addWidget(self.target_hint,1)
        file_layout.addLayout(row)
        layout.addWidget(file_group)

        component_group = QGroupBox('3. 对象选择')
        component_group.setMinimumHeight(270)
        objects_layout = QVBoxLayout(component_group)
        row = QHBoxLayout()
        row.addWidget(QLabel('组件前缀'))
        self.prefix = QLineEdit('Pack,Func')
        self.prefix.setPlaceholderText('COMPONENT_PREFIX，多个前缀用英文逗号分隔')
        self.prefix.editingFinished.connect(self.scan_file)
        row.addWidget(self.prefix,1)
        self.only_checked = QCheckBox('仅显示已勾选对象')
        self.only_checked.toggled.connect(self._filter_changed)
        row.addWidget(self.only_checked)
        objects_layout.addLayout(row)
        row = QHBoxLayout()
        self.select_all = QPushButton('全选显示对象')
        self.select_none = QPushButton('取消显示对象勾选')
        self.select_all.clicked.connect(lambda:self.select_visible(True))
        self.select_none.clicked.connect(lambda:self.select_visible(False))
        row.addWidget(self.select_all)
        row.addWidget(self.select_none)
        row.addStretch()
        self.count = QLabel('0 个对象，已勾选 0 个')
        row.addWidget(self.count)
        objects_layout.addLayout(row)
        self.objects = QListWidget()
        self.objects.setViewMode(QListWidget.ViewMode.IconMode)
        self.objects.setFlow(QListWidget.Flow.LeftToRight)
        self.objects.setWrapping(True)
        self.objects.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.objects.setMovement(QListWidget.Movement.Static)
        from PyQt6.QtCore import QSize
        self.objects.setGridSize(QSize(430,32))
        self.objects.setMinimumHeight(160)
        self.objects.itemChanged.connect(self._item_changed)
        objects_layout.addWidget(self.objects)
        layout.addWidget(component_group,2)

        rule_group = QGroupBox('4. SQL 生成选项')
        box = QVBoxLayout(rule_group)
        row = QHBoxLayout()
        row.addWidget(QLabel('PL/SQL 赋值符'))
        self.colon_mode = QComboBox()
        self.colon_mode.setObjectName('colonMode')
        self.colon_mode.setMinimumWidth(290)
        self.colon_mode.addItem('单冒号 :=（标准 PL/SQL）','1')
        self.colon_mode.addItem('双冒号 ::=（BDE TQuery 兼容）','2')
        self.colon_mode.currentIndexChanged.connect(self._colon_mode_changed)
        row.addWidget(self.colon_mode)
        colon_hint = QLabel('只转换赋值符；:参数名、字符串和注释保持不变。')
        colon_hint.setStyleSheet('color:#64748b;font-size:12px;')
        row.addWidget(colon_hint,1)
        box.addLayout(row)
        self.rules = QLineEdit()
        self.rules.setPlaceholderText('REPALCE_PATTEN，例如 xxx->yyy|$|aaa->bbb')
        self.rules.editingFinished.connect(self.autosave)
        box.addWidget(self.rules)
        hint = QLabel('全局替换规则：查找内容->替换内容；多条用 |$| 分隔，按从左到右依次替换。留空则不替换。')
        hint.setStyleSheet('color:#64748b;font-size:12px;')
        box.addWidget(hint)
        layout.addWidget(rule_group)

        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0,100)
        self.progress.setValue(0)
        self.progress.setFormat('%p%')
        row.addWidget(self.progress,1)
        self.generate_button = QPushButton('开始生成')
        self.generate_button.setObjectName('generate')
        self.generate_button.setMinimumSize(170,44)
        self.generate_button.clicked.connect(lambda:self.start_job(False))
        row.addWidget(self.generate_button)
        layout.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setMaximumHeight(125)
        self.log.setPlaceholderText('运行日志；生成前自动备份原 DFM。')
        layout.addWidget(self.log)
        self.statusBar().showMessage('就绪 · Oracle Client 19.32 内嵌运行')
        self.setStyleSheet('''
            QMainWindow {background:#f4f6f9;}
            QWidget {font-family:"Microsoft YaHei UI";font-size:13px;color:#18283b;}
            QGroupBox {background:white;border:1px solid #dbe2ea;border-radius:7px;margin-top:11px;padding:14px 10px 8px;font-weight:600;}
            QGroupBox::title {subcontrol-origin:margin;left:12px;padding:0 5px;}
            QLineEdit,QComboBox,QListWidget,QPlainTextEdit {background:white;border:1px solid #cbd5e1;border-radius:4px;padding:6px;}
            QLineEdit:focus,QComboBox:focus {border:1px solid #3271d4;}
            QPushButton {background:#edf2f8;border:1px solid #cad5e3;border-radius:4px;padding:6px 13px;}
            QPushButton:hover {background:#dfeafa;}
            QPushButton:disabled {color:#95a2b2;background:#edf0f4;}
            QPushButton#generate {background:#2563c5;color:white;border:0;font-size:17px;font-weight:600;}
            QPushButton#save {background:#e4f4e9;color:#237447;border-color:#b6d9c3;}
            QPushButton#delete {color:#b83a3a;}
            QProgressBar {border:1px solid #d4deeb;border-radius:4px;text-align:center;background:white;min-height:24px;}
            QProgressBar::chunk {background:#a7c8f8;border-radius:3px;}
            QListWidget::item {padding:3px;}
            QListWidget::item:selected {background:#e6effc;color:#18283b;}
        ''')

    def _refresh_profiles(self):
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(self.store.data['profiles'])
        self.combo.blockSignals(False)

    def collect(self):
        return {'user':self.user.text().strip(),'password':self.password.text(),
                'conn_str':self.dsn.text().strip(),'dfm_path':self.file.text().strip(),
                'COMPONENT_PREFIX':self.prefix.text(),'REPALCE_PATTEN':self.rules.text(),
                'ASSIGNMENT_COLONS':self.colon_mode.currentData(),
                'DELPHI_VERSION':self.target.currentData(),
                'only_checked':self.only_checked.isChecked(),'selected_objects':sorted(self.selected)}

    def _write_config(self):
        try:
            self.store.save()
            return True
        except Exception as error:
            self.log.appendPlainText('配置保存失败：'+str(error))
            self.statusBar().showMessage('配置保存失败：'+str(error))
            return False

    def autosave(self):
        if not self.loading and self.current_profile:
            self.store.data['profiles'][self.current_profile] = self.collect()
            self.store.data['last_profile'] = self.current_profile
            self._write_config()

    def save_profile(self):
        name = self.combo.currentText().strip()
        if not name:
            QMessageBox.warning(self,'配置名为空','请输入配置名称。')
            return
        self.store.data['profiles'][name] = self.collect()
        self.current_profile = name
        self.store.data['last_profile'] = name
        if self._write_config():
            self._refresh_profiles()
            self.combo.setCurrentText(name)
            self.log.appendPlainText(f'配置 [{name}] 已保存')

    def _profile_entered(self):
        name = self.combo.currentText().strip()
        if name in self.store.data['profiles']:
            self.load_profile(name)

    def load_profile(self,name):
        if name not in self.store.data['profiles']:
            return
        self.autosave()
        self.loading = True
        profile = self.store.data['profiles'][name]
        self.current_profile = name
        self.combo.setCurrentText(name)
        self.user.setText(profile.get('user',''))
        self.password.setText(profile.get('password',''))
        self.dsn.setText(profile.get('conn_str',''))
        self.file.setText(profile.get('dfm_path',''))
        self.target.setCurrentIndex(1 if profile.get('DELPHI_VERSION','7')=='5' else 0)
        self._target_changed()
        self.prefix.setText(profile.get('COMPONENT_PREFIX','Pack,Func'))
        self.rules.setText(profile.get('REPALCE_PATTEN',''))
        colon_mode = str(profile.get('ASSIGNMENT_COLONS',''))
        if colon_mode not in ('1','2'):
            legacy_double = any(rule.strip()==':=->::=' for rule in self.rules.text().split('|$|'))
            colon_mode = '2' if legacy_double else '1'
        self.colon_mode.setCurrentIndex(1 if colon_mode=='2' else 0)
        self.selected = set(profile.get('selected_objects',[]))
        self.only_checked.setChecked(profile.get('only_checked',False))
        self.progress.setValue(0)
        self.status.setText('● 未连接')
        self.loading = False
        self.scan_file()

    def delete_profile(self):
        name = self.combo.currentText().strip()
        if name not in self.store.data['profiles']:
            return
        del self.store.data['profiles'][name]
        self.current_profile = ''
        self._refresh_profiles()
        if self.store.data['profiles']:
            self.load_profile(next(iter(self.store.data['profiles'])))
        else:
            self.loading = True
            for field in (self.user,self.password,self.dsn,self.file,self.rules):
                field.clear()
            self.prefix.setText('Pack,Func')
            self.target.setCurrentIndex(0)
            self.colon_mode.setCurrentIndex(0)
            self.only_checked.setChecked(False)
            self.selected.clear()
            self.memos = []
            self.current_profile = ''
            self.combo.setEditText('默认配置')
            self.status.setText('● 未连接')
            self.progress.setValue(0)
            self.loading = False
            self.refresh_objects()
        self.store.data['last_profile'] = self.current_profile
        self._write_config()

    def _credentials_changed(self):
        self.status.setText('● 未连接')
        self.status.setStyleSheet('color:#64748b;')

    def _target_changed(self):
        self.target_hint.setText('中文 ANSI/GBK · 不生成 Unicode 数字转义 · 无 BOM' if self.target.currentData()=='5' else 'Unicode 数字转义 · 无 BOM')
        self.autosave()

    def _colon_mode_changed(self):
        self.autosave()

    def browse_file(self):
        path,_ = QFileDialog.getOpenFileName(self,'选择 DFM 文件',self.file.text(),'Delphi DFM 文件 (*.dfm)')
        if path:
            self.file.setText(path)
            self.scan_file()

    def scan_file(self):
        if self.loading:
            return
        self.memos = []
        path = self.file.text().strip()
        if path:
            try:
                document = DfmDocument(path)
                self.memos = discover_memos(document.text,self.prefix.text())
                self.statusBar().showMessage(f'已读取 {Path(path).name} · {len(self.memos)} 个匹配的文本组件')
            except Exception as error:
                self.log.appendPlainText('读取 DFM 失败：'+str(error))
                self.statusBar().showMessage('读取 DFM 失败：'+str(error))
        self.refresh_objects()
        self.autosave()

    def refresh_objects(self):
        self.objects.blockSignals(True)
        self.objects.clear()
        for memo in self.memos:
            checked = memo.name in self.selected
            if self.only_checked.isChecked() and not checked:
                continue
            item = QListWidgetItem(memo.name,self.objects)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.objects.blockSignals(False)
        self.count.setText(f'{len(self.memos)} 个对象，已勾选 {sum(m.name in self.selected for m in self.memos)} 个')

    def _item_changed(self,item):
        if item.checkState() == Qt.CheckState.Checked:
            self.selected.add(item.text())
        else:
            self.selected.discard(item.text())
        self.autosave()
        QTimer.singleShot(0,self.refresh_objects)

    def _filter_changed(self):
        if not self.loading:
            self.refresh_objects()
            self.autosave()

    def select_visible(self,checked):
        names = {self.objects.item(i).text() for i in range(self.objects.count())}
        if checked:
            self.selected.update(names)
        else:
            self.selected.difference_update(names)
        self.refresh_objects()
        self.autosave()

    def start_job(self,test_only):
        if self.worker is not None:
            return
        config = self.collect()
        config['selected_objects'] = [m.name for m in self.memos if m.name in self.selected]
        try:
            if not config['user'] or not config['password'] or not config['conn_str']:
                raise ValueError('请填写数据库用户名、密码和连接地址。')
            if not test_only:
                if not prefixes(config['COMPONENT_PREFIX']):
                    raise ValueError('请填写 COMPONENT_PREFIX。')
                replacement_rules(config['REPALCE_PATTEN'])
                assignment_colons(config['ASSIGNMENT_COLONS'])
                if not config['selected_objects']:
                    raise ValueError('请读取 DFM 并勾选至少一个对象。')
                DfmDocument(config['dfm_path'])
        except Exception as error:
            QMessageBox.warning(self,'参数不完整',str(error))
            return
        self.save_profile()
        self.progress.setValue(0)
        self.worker = Worker(config,test_only,self)
        self.worker.progress.connect(self.on_progress)
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.succeeded.connect(lambda result:self._succeeded(result,test_only))
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self._set_busy(True)
        self.statusBar().showMessage('正在测试数据库连接…' if test_only else '正在读取数据库并生成…')
        self.worker.start()

    def _set_busy(self,busy):
        for widget in (self.combo,self.save_button,self.delete_button,self.user,self.password,self.dsn,
                       self.connect_button,self.file,self.browse,self.refresh,self.target,self.prefix,self.objects,
                       self.only_checked,self.select_all,self.select_none,self.colon_mode,self.rules,
                       self.generate_button):
            widget.setEnabled(not busy)

    def on_progress(self,done,total,name):
        self.progress.setValue(round(done*100/total))
        self.statusBar().showMessage(f'{done}/{total} · {name}')

    def _succeeded(self,result,test_only):
        if test_only:
            self.status.setText('● 已连接 '+result)
            self.status.setStyleSheet('color:#237447;')
            self.log.appendPlainText('数据库连接测试成功：'+result)
            self.statusBar().showMessage('数据库连接测试成功')
        else:
            self.progress.setValue(100)
            self.log.appendPlainText(f"生成完成：{result['count']} 个对象\nDFM：{result['path']}\n原文件备份：{result['backup']}")
            self.statusBar().showMessage(f"生成完成 · {result['count']} 个对象 · 已备份原文件")
            self.scan_file()

    def _failed(self,message):
        self.progress.setValue(0)
        self.status.setText('● 操作失败，查看日志')
        self.log.appendPlainText('操作失败：'+message)
        self.statusBar().showMessage('操作失败；未提交的转换不会写入 DFM')
        QMessageBox.critical(self,'操作失败',message)

    def _finished(self):
        self._set_busy(False)
        self.worker.deleteLater()
        self.worker = None

    def closeEvent(self,event):
        if self.worker is not None:
            self.statusBar().showMessage('正在处理，请完成后关闭窗口。')
            event.ignore()
            return
        self.autosave()
        event.accept()

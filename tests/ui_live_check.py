"""Exercise the real Qt worker, progress signals and config save on a DFM copy."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PyQt6.QtWidgets import QApplication,QMessageBox
from dfm_writer.config import ConfigStore
from dfm_writer.window import MainWindow

app = QApplication([])
config_path,dfm_path,report_path = map(Path,sys.argv[1:4])
profile_name = sys.argv[4] if len(sys.argv) > 4 else 'lxd'
profiles = json.loads(config_path.read_text('utf-8'))['profiles']
profile = dict(profiles[profile_name])
original_hash = hashlib.sha256(dfm_path.read_bytes()).hexdigest()
errors = []
QMessageBox.critical = lambda parent,title,text:errors.append(text)
QMessageBox.warning = lambda parent,title,text:errors.append(text)
with tempfile.TemporaryDirectory(prefix='dfm_ui_live_') as directory:
    path = Path(directory)/'test.dfm'
    shutil.copy2(dfm_path,path)
    profile.update(dfm_path=str(path),COMPONENT_PREFIX='Pack,Func',REPALCE_PATTEN='',only_checked=True,
                   selected_objects=['PackXC_SERVICE_Spec','PackXC_SERVICE_Body','PackTAX_UNTAX_Spec',
                                     'PackTAX_UNTAX_Body','FuncCalcAddValueTax','FuncCalcTaxPrepare','FuncGetErrorMsg'])
    store = ConfigStore(Path(directory)/'config.json')
    store.data['profiles'] = {'live':profile}
    window = MainWindow(store)
    window.show()
    app.processEvents()
    window.start_job(False)
    deadline = time.monotonic()+90
    while window.worker is not None and time.monotonic()<deadline:
        app.processEvents()
        time.sleep(0.02)
    assert window.worker is None,'Qt worker timeout'
    assert not errors,errors
    assert window.progress.value() == 100
    assert '生成完成' in window.log.toPlainText()
    assert path.read_bytes() != dfm_path.read_bytes()
    assert list(path.parent.glob('*.bak'))
    window.grab().save(str(report_path.with_suffix('.png')))
    window.close()
    assert ConfigStore(store.path).data['profiles']['live']['selected_objects'] == sorted(profile['selected_objects'])
assert hashlib.sha256(dfm_path.read_bytes()).hexdigest() == original_hash
report_path.write_text(json.dumps({'status':'passed','qt_worker':'passed','progress':100,'objects':7,
                                 'config_saved':True,'backup_created':True,'original_unchanged':True},indent=2),encoding='utf-8')

from pathlib import Path
import os
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PyQt6.QtWidgets import QApplication
from dfm_writer.window import MainWindow
from dfm_writer.config import ConfigStore
import tempfile

app = QApplication([])
with tempfile.TemporaryDirectory() as directory:
    store = ConfigStore(Path(directory)/'config.json')
    store.data['profiles'] = {'示例配置':{
        'user':'xc','password':'demo','conn_str':'127.0.0.1:1521/orcl',
        'dfm_path':str(Path('evidence/live_generation/UfrmUpdate.test.dfm').resolve()),
        'COMPONENT_PREFIX':'Pack,Func','REPALCE_PATTEN':':=->::=|$|xxx->yyy',
        'only_checked':True,
        'selected_objects':['PackXC_SERVICE_Spec','PackXC_SERVICE_Body','PackTAX_UNTAX_Spec',
                            'PackTAX_UNTAX_Body','FuncCalcAddValueTax','FuncCalcTaxPrepare','FuncGetErrorMsg']}}
    window = MainWindow(store)
    window.show()
    window.on_progress(1,4,'FuncGetErrorMsg')
    window.log.appendPlainText('界面预览：仅显示当前 DFM 中存在且已勾选的 7 个对象。')
    app.processEvents()
    window.grab().save('evidence/ui_preview.png')
    window.close()

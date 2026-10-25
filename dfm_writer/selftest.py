"""Packaged runtime verification; never touches the user's DFM or configuration."""
import json
from pathlib import Path
import tempfile
import traceback


FIXTURE = '''object MainForm: TForm
  Caption = 'Untouched'
  object Panel: TPanel
    object FuncDemo: TMemo
      Left = 12
      Lines.Strings = (
        'OLD')
      TabOrder = 3
    end
    object PackDemo_Spec: TRichEdit
      Left = 7
    end
    object OtherMemo: TMemo
      Lines.Strings = (
        'KEEP')
    end
    object FuncLabel: TLabel
      Caption = 'KEEP'
    end
  end
end
'''


def check_core(directory):
    from .core import (DfmDocument,discover_memos,decode_lines,ddl_rows,replacement_rules,
        convert_assignment_colons)
    path = Path(directory)/'test.dfm'
    path.write_bytes(FIXTURE.replace('\n','\r\n').encode('ascii'))
    doc = DfmDocument(path)
    assert [m.name for m in discover_memos(doc.text,'Pack,Func')] == ['FuncDemo','PackDemo_Spec']
    rows = ddl_rows(["FUNCTION Demo RETURN VARCHAR2 IS\n","BEGIN\n","\tRETURN '中文'; -- a+b #39 "+'x'*140+'\n','END;\n'],'Demo','FUNCTION',replacement_rules('中文->替换|$|替换->成功'))
    rendered = doc.render('Pack,Func',{'FuncDemo':rows,'PackDemo_Spec':['PACKAGE Demo IS','END;']})
    text = rendered.decode('utf-8')
    memos = {m.name:m for m in discover_memos(text,'Pack,Func')}
    assert decode_lines(text,memos['FuncDemo']) == rows
    assert '成功' in rows[3]
    assert "P_TAXABST::= 'x'" in convert_assignment_colons("P_TAXABST:='x'; y:=:BIND;",'2')
    assert 'y::= :BIND' in convert_assignment_colons("P_TAXABST:='x'; y:=:BIND;",'2')
    assert convert_assignment_colons("x:=1; y:=:BIND;",'2') == 'x::= 1; y::= :BIND;'
    assert "      TabOrder = 3\r\n" in text
    assert "        'KEEP')\r\n" in text
    backup = doc.save(rendered)
    assert backup.read_bytes() == doc.raw
    assert path.read_bytes() == rendered
    formats = {}
    for version in ('7','5'):
        path.write_bytes(FIXTURE.replace('\n','\r\n').encode('ascii'))
        document = DfmDocument(path)
        data = document.render('Pack,Func',{'FuncDemo':rows},version)
        decoded = data.decode('gbk')
        memo = next(m for m in discover_memos(decoded,'Func') if m.name=='FuncDemo')
        assert decode_lines(decoded,memo,version) == rows
        formats[version] = 'passed'
    return {'core':'passed','backup':'passed','object_count':2,'legacy_formats':formats}


def check_live(config_path,dfm_path,profile_name='lxd'):
    import hashlib
    import shutil
    from . import database
    from .core import DfmDocument,discover_memos,decode_lines,object_mapping,ddl_rows
    from .jobs import generate
    profiles = json.loads(Path(config_path).read_text('utf-8'))['profiles']
    if profile_name not in profiles:
        raise ValueError(f'打包在线校验缺少配置：{profile_name}')
    base = dict(profiles[profile_name])
    original = Path(dfm_path)
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    names = ['PackXC_SERVICE_Spec','PackXC_SERVICE_Body','PackTAX_UNTAX_Spec','PackTAX_UNTAX_Body',
             'FuncCalcAddValueTax','FuncCalcTaxPrepare','FuncGetErrorMsg']
    targets = {}
    for version in ('7','5'):
        with tempfile.TemporaryDirectory(prefix='dfm_live_') as directory:
            path = Path(directory)/'test.dfm'
            if version=='7':
                shutil.copy2(original,path)
            else:
                # A D5 file must start with D5-compatible properties outside the target memos.
                form = 'object CompatibilityForm: TForm\r\n'
                form += ''.join(f'  object {name}: TMemo\r\n    WordWrap = False\r\n  end\r\n' for name in names)
                path.write_bytes((form+'end\r\n').encode('ascii'))
            config = dict(base)
            config.update(dfm_path=str(path),COMPONENT_PREFIX='Pack,Func',REPALCE_PATTEN='',selected_objects=names,DELPHI_VERSION=version)
            progress = []
            result = generate(config,lambda done,total,name:progress.append(round(done*100/total)))
            doc = DfmDocument(path)
            memos = {memo.name:memo for memo in discover_memos(doc.text,'Pack,Func')}
            with database.connect(config) as connection:
                target = database.identity(connection)
                for memo in names:
                    name,kind = object_mapping(memo,'Pack,Func')
                    kind,rows = database.read_source(connection,name,kind)
                    assert decode_lines(doc.text,memos[memo],version) == ddl_rows(rows,name,kind,[])
            assert result['count'] == len(names)
            assert progress == [14,29,43,57,71,86,100]
            targets[version] = {'status':'passed','objects':len(names),'progress':progress}
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    return {'identity':target,'targets':targets,'original_unchanged':True,'status':'passed'}


def run(report_path,live_config=None,live_dfm=None,live_profile='lxd'):
    report = {}
    try:
        import oracledb
        from PyQt6.QtCore import PYQT_VERSION_STR
        from PyQt6.QtWidgets import QApplication
        from .oracle_runtime import init_thick_mode
        from .config import ConfigStore
        from .window import MainWindow
        with tempfile.TemporaryDirectory(prefix='dfm_selftest_') as directory:
            report.update(check_core(directory))
            app = QApplication.instance() or QApplication([])
            window = MainWindow(ConfigStore(Path(directory)/'config.json'))
            window.show()
            app.processEvents()
            assert window.colon_mode.currentData() in ('1','2')
            screenshot = str(Path(report_path).with_suffix('.png'))
            window.grab().save(screenshot)
            window.close()
            report['ui'] = 'passed'
        ok,message = init_thick_mode()
        if not ok:
            raise RuntimeError(message)
        if live_config and live_dfm:
            report['live'] = check_live(live_config,live_dfm,live_profile)
        report.update(oracle_client='.'.join(map(str,oracledb.clientversion())),pyqt=PYQT_VERSION_STR,
                      driver=oracledb.__version__,status='passed')
        code = 0
    except Exception:
        report.update(status='failed',error=traceback.format_exc())
        code = 1
    Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return code

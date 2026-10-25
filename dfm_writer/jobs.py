from PyQt6.QtCore import QThread, pyqtSignal
from .core import (DfmDocument,discover_memos,object_mapping,replacement_rules,ddl_rows,
    delphi_version,assignment_colons)
from . import database


def generate(config,progress=lambda done,total,name:None,log=lambda text:None):
    document = DfmDocument(config['dfm_path'])
    target = delphi_version(config.get('DELPHI_VERSION','7'))
    colon_mode = config.get('ASSIGNMENT_COLONS')
    if colon_mode is not None:
        colon_mode = assignment_colons(colon_mode)
    selected = set(config['selected_objects'])
    memos = [m for m in discover_memos(document.text,config['COMPONENT_PREFIX']) if m.name in selected]
    if len(memos) != len(selected) or not memos:
        raise ValueError('勾选对象为空或已不在 DFM 中，请重新读取对象列表')
    rules = replacement_rules(config.get('REPALCE_PATTEN',''))
    values = {}
    log(f'目标格式：Delphi {target}'+(' · 中文 ANSI/GBK' if target=='5' else ' · Unicode 数字转义'))
    if colon_mode is not None:
        log('PL/SQL 赋值符：'+('单冒号 :=（标准）' if colon_mode=='1' else '双冒号 ::=（BDE TQuery 兼容）'))
    with database.connect(config) as connection:
        log('数据库连接成功：'+database.identity(connection))
        for i,memo in enumerate(memos,1):
            name,kind = object_mapping(memo.name,config['COMPONENT_PREFIX'])
            kind,rows = database.read_source(connection,name,kind)
            values[memo.name] = ddl_rows(rows,name,kind,rules,colon_mode)
            log(f'已转换 {memo.name} ← {name} ({kind})，{len(rows)} 行')
            if i<len(memos):
                progress(i,len(memos),memo.name)
    content = document.render(config['COMPONENT_PREFIX'],values,target)
    backup = document.save(content)
    progress(len(memos),len(memos),memos[-1].name)
    return {'count':len(memos),'path':str(document.path),'backup':str(backup)}


class Worker(QThread):
    progress = pyqtSignal(int,int,str)
    log = pyqtSignal(str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self,config,test_only=False,parent=None):
        super().__init__(parent)
        self.config,self.test_only = config,test_only

    def run(self):
        try:
            if self.test_only:
                with database.connect(self.config) as connection:
                    result = database.identity(connection)
            else:
                result = generate(self.config,self.progress.emit,self.log.emit)
            self.succeeded.emit(result)
        except Exception as error:
            self.failed.emit(str(error))

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dfm_writer.core import (DfmDocument,discover_memos,object_mapping,replacement_rules,
    replace_source,encode_fragment,decode_expression,ddl_rows,decode_lines,
    assignment_colons,convert_assignment_colons)
from dfm_writer.selftest import FIXTURE,check_core
from dfm_writer.config import ConfigStore


class ConversionTests(unittest.TestCase):
    def test_complete_roundtrip_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(check_core(directory)['core'],'passed')

    def test_character_encoding(self):
        self.assertEqual(encode_fragment("  RETURN '中文';"),"'  RETURN '#39#20013#25991#39';'")
        for value in ['', '  ', '\t', "'", "''", '#39', 'a+b', r'c:\name', '“中文”', 'a'*256, '😀']:
            self.assertEqual(decode_expression(encode_fragment(value)),value)

    def test_mapping(self):
        self.assertEqual(object_mapping('PackXC_SERVICE_Body','Pack,Func'),('XC_SERVICE','PACKAGE BODY'))
        self.assertEqual(object_mapping('PackXC_SERVICE_Spec','Pack,Func'),('XC_SERVICE','PACKAGE'))
        self.assertEqual(object_mapping('FuncGetErrorMsg','Pack,Func'),('GetErrorMsg',None))
        self.assertEqual(object_mapping('FunctionFoo','Func,Function'),('Foo',None))
        with self.assertRaises(ValueError):
            object_mapping('Other','Pack,Func')

    def test_replacements_order_and_validation(self):
        rules = replacement_rules(':=->::=|$|xxx->yyy|$|yyy->zzz')
        self.assertEqual(replace_source('x:=xxx',rules),'x::=zzz')
        self.assertEqual(replace_source('abc',replacement_rules('b->')),'ac')
        for bad in ['->x','abc',':=->::=|$|']:
            with self.assertRaises(ValueError):
                replacement_rules(bad)

    def test_assignment_colons_only_touch_assignment_operators(self):
        source = ("P_TAXABST:= '发放金额小于起征点'; amount := :P_AMOUNT;\n"
                  "33333333333333\n"
                  "-- :- := comment\n/* :- := block */\n"
                  "text := q'[It''s := literal]'; SELECT ':=' FROM dual;")
        double = convert_assignment_colons(source,'2')
        self.assertIn("P_TAXABST::= '发放金额小于起征点'",double)
        self.assertIn('amount ::= :P_AMOUNT',double)
        self.assertIn('V_CalcAmt::= CASE',convert_assignment_colons('V_CalcAmt:=CASE','2'))
        self.assertIn('-- :- := comment',double)
        self.assertIn('/* :- := block */',double)
        self.assertIn("q'[It''s := literal]'",double)
        self.assertIn("SELECT ':=' FROM dual",double)
        self.assertIn('33333333333333',double)
        self.assertEqual(convert_assignment_colons(double,'1'),source)
        self.assertEqual(convert_assignment_colons(double,'2'),double)
        self.assertEqual(assignment_colons('::='),'2')
        with self.assertRaises(ValueError):
            assignment_colons('3')

    def test_headers_owner_and_whitespace(self):
        rows = ddl_rows(['FUNCTION "XC"."Demo" RETURN NUMBER\n','  \n','END;  \n'],'Demo','FUNCTION',[])
        self.assertEqual(rows[1],'CREATE OR REPLACE FUNCTION "Demo" RETURN NUMBER')
        self.assertEqual(rows[2:],[ '  ','END;  '])
        self.assertEqual(ddl_rows(['PACKAGE XC_SERVICE AS\n','END;\n'],'XC_SERVICE','PACKAGE',[])[0],'/*包PACKAGE XC_SERVICE*/')
        converted = ddl_rows(['PROCEDURE Demo(P IN NUMBER) IS\n','BEGIN\n','  x:=P; y:=:BIND; END;\n'],
                             'Demo','PROCEDURE',[],'2')
        self.assertEqual(converted[2:],['BEGIN','  x::= P; y::= :BIND; END;'])

    def test_surgical_edit_and_all_encodings(self):
        for encoding,bom in [('gbk',False)]:
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'a.dfm'
                fixture = FIXTURE.replace("Caption = 'Untouched'","Caption = '保留中文'").replace('\n','\r\n')
                path.write_bytes(fixture.encode(encoding))
                doc = DfmDocument(path)
                old = discover_memos(doc.text,'Func')[0]
                values = ['', '  ', "  RETURN '中文';",'x'*130,'\t#39 +']
                result = doc.render('Func',{'FuncDemo':values})
                newtext = result.decode(doc.encoding)
                new = discover_memos(newtext,'Func')[0]
                self.assertEqual(doc.text[:old.property_start],newtext[:new.property_start])
                self.assertEqual(doc.text[old.property_end:],newtext[new.property_end:])
                self.assertEqual(decode_lines(newtext,new),values)
                self.assertEqual(result.startswith(b'\xef\xbb\xbf'),bom)

    def test_file_changed_and_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'a.dfm'
            path.write_text(FIXTURE,encoding='ascii')
            doc = DfmDocument(path)
            path.write_text('externally changed',encoding='ascii')
            with self.assertRaises(ValueError):
                doc.save(b'bad')
            self.assertEqual(path.read_text(),'externally changed')
            path.write_bytes(b'TPF0\0')
            with self.assertRaises(ValueError):
                DfmDocument(path)
            for prefix in (b'\xef\xbb\xbf',b'\xff\xfe',b'\xfe\xff'):
                path.write_bytes(prefix+FIXTURE.encode('ascii'))
                with self.assertRaises(ValueError):
                    DfmDocument(path)
            with self.assertRaises(ValueError):
                DfmDocument(Path(directory)/'a.txt')
            with self.assertRaises(ValueError):
                discover_memos('object a: TMemo\n','Func')

    def test_original_seven_snapshots(self):
        root = Path(__file__).resolve().parent.parent
        evidence = root/'evidence'
        sample = os.environ.get('DFM_SAMPLE','')
        source_file = Path(sample) if sample else None
        if source_file is None or not source_file.exists() or not any(evidence.glob('*.memo.sql')):
            self.skipTest('需要 DFM_SAMPLE 和 evidence/*.memo.sql 才能运行真实样本测试')
        doc = DfmDocument(source_file)
        memos = {m.name:m for m in discover_memos(doc.text,'Pack,Func')}
        values = {}
        for path in evidence.glob('*.memo.sql'):
            name = path.name[:-len('.memo.sql')]
            rows = path.read_text('utf-8').splitlines()
            self.assertEqual(decode_lines(doc.text,memos[name]),rows,name)
            values[name] = rows
        self.assertEqual(len(values),7)
        newtext = doc.render('Pack,Func',values).decode(doc.encoding)
        newmemos = {m.name:m for m in discover_memos(newtext,'Pack,Func')}
        for name,rows in values.items():
            self.assertEqual(decode_lines(newtext,newmemos[name]),rows)


class ConfigAndUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_profile_switch_filter_and_persistence(self):
        from dfm_writer.window import MainWindow
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.dfm'
            path.write_text(FIXTURE,encoding='ascii')
            store = ConfigStore(Path(directory)/'config.json')
            store.data['profiles'] = {
                'A':{'user':'userA','password':'a','conn_str':'hostA/service','dfm_path':str(path),'DELPHI_VERSION':'5',
                     'COMPONENT_PREFIX':'Pack,Func','REPALCE_PATTEN':':=->::=',
                     'ASSIGNMENT_COLONS':'2',
                     'selected_objects':['FuncDemo','MissingMemo'],'only_checked':True},
                'B':{'user':'userB','password':'b','conn_str':'hostB/service','dfm_path':str(path),
                     'COMPONENT_PREFIX':'Pack','REPALCE_PATTEN':'x->y','ASSIGNMENT_COLONS':'1',
                     'selected_objects':['PackDemo_Spec'],'only_checked':False}}
            window = MainWindow(store)
            self.assertEqual(window.objects.count(),1)
            self.assertEqual(window.objects.item(0).text(),'FuncDemo')
            self.assertEqual(window.target.currentData(),'5')
            self.assertEqual(window.colon_mode.currentData(),'2')
            window.rules.setText('a->b|$|b->c')
            window.colon_mode.setCurrentIndex(0)
            window.load_profile('B')
            self.assertEqual(window.user.text(),'userB')
            self.assertEqual(window.target.currentData(),'7')
            self.assertEqual(window.prefix.text(),'Pack')
            self.assertEqual(window.colon_mode.currentData(),'1')
            self.assertFalse(window.only_checked.isChecked())
            self.assertEqual(window.objects.count(),1)
            window.load_profile('A')
            self.assertEqual(window.rules.text(),'a->b|$|b->c')
            self.assertEqual(window.target.currentData(),'5')
            self.assertEqual(window.colon_mode.currentData(),'1')
            window.only_checked.setChecked(False)
            self.assertEqual(window.objects.count(),2)
            window.select_visible(True)
            window.only_checked.setChecked(True)
            self.assertEqual(window.objects.count(),2)
            window.on_progress(1,4,'FuncDemo')
            self.assertEqual(window.progress.value(),25)
            window.close()
            saved = ConfigStore(store.path)
            self.assertIn('MissingMemo',saved.data['profiles']['A']['selected_objects'])
            self.assertEqual(saved.data['profiles']['A']['ASSIGNMENT_COLONS'],'1')
            self.assertEqual(saved.data['last_profile'],'A')

    def test_generate_progress_and_failure_atomicity(self):
        from dfm_writer.jobs import generate
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.dfm'
            original = FIXTURE.encode('ascii')
            path.write_bytes(original)
            config = {'user':'x','password':'y','conn_str':'z','dfm_path':str(path),'COMPONENT_PREFIX':'Pack,Func',
                      'REPALCE_PATTEN':'','ASSIGNMENT_COLONS':'2',
                      'selected_objects':['FuncDemo','PackDemo_Spec']}
            progress = []
            with patch('dfm_writer.jobs.database.connect',return_value=nullcontext(object())), \
                 patch('dfm_writer.jobs.database.identity',return_value='TEST@DB'), \
                 patch('dfm_writer.jobs.database.read_source',side_effect=[('FUNCTION',['FUNCTION Demo RETURN NUMBER IS\n','BEGIN RETURN 1; END;\n']),ValueError('missing body')]):
                with self.assertRaises(ValueError):
                    generate(config,lambda *args:progress.append(args))
            self.assertEqual(path.read_bytes(),original)
            self.assertFalse(list(path.parent.glob('*.bak')))
            self.assertEqual(progress[0][0:2],(1,2))
            progress.clear()
            with patch('dfm_writer.jobs.database.connect',return_value=nullcontext(object())), \
                 patch('dfm_writer.jobs.database.identity',return_value='TEST@DB'), \
                 patch('dfm_writer.jobs.database.read_source',side_effect=[('FUNCTION',['FUNCTION Demo RETURN NUMBER IS\n','BEGIN x:=1; RETURN x; END;\n']),('PACKAGE',['PACKAGE Demo IS\n','END;\n'])]):
                result = generate(config,lambda *args:progress.append(args))
            self.assertEqual([p[0] for p in progress],[1,2])
            self.assertEqual(Path(result['backup']).read_bytes(),original)
            doc = DfmDocument(path)
            self.assertIn('::=',decode_lines(doc.text,discover_memos(doc.text,'Func')[0])[2])


if __name__ == '__main__':
    unittest.main()

"""Create native-loader fixtures and compare with an independent byte parser."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from dfm_writer.core import DfmDocument,discover_memos
from legacy_dfm_reader import read_string_list

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT/'evidence'/'legacy'


def main():
    OUT.mkdir(exist_ok=True)
    rows = ['CREATE OR REPLACE FUNCTION Demo RETURN VARCHAR2 IS',
            '/*中文、全角标点与单引号*/', 'BEGIN', "  RETURN '中文';", "  RETURN '';",
            '\t-- Tab retained', '  ', '-- literal #39 and SQL + stay literal',
            'x'*65, 'a'*63+'中'+'b'*70, '中'*65, '  -- trailing spaces  ', 'END;']
    fixture = 'object CompatibilityForm: TForm\r\n  object FuncDemo: TMemo\r\n    WordWrap = False\r\n  end\r\nend\r\n'
    report = {}
    for version in ('7','5'):
        path = OUT/f'Delphi{version}.dfm'
        path.write_bytes(fixture.encode('ascii'))
        document = DfmDocument(path)
        rendered = document.render('Func',{'FuncDemo':rows},version)
        path.write_bytes(rendered)
        text = rendered.decode('gbk')
        memo = discover_memos(text,'Func')[0]
        assert read_string_list(text[memo.property_start:memo.property_end].encode('gbk'),version) == rows
        (OUT/f'Delphi{version}.expected.gbk.txt').write_bytes(('\r\n'.join(rows)+'\r\n').encode('gbk'))
        report[version] = {'status':'passed','rows':len(rows),'bytes':len(rendered),'bom':False,
                           'generated_text':'ASCII Unicode escapes' if version=='7' else 'ANSI GBK quoted text'}
    (OUT/'syntax_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()

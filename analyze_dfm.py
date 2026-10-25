import collections
import difflib
import hashlib
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get('DFM_SAMPLE', ''))
MAPPING = {
    'PackXC_SERVICE_Spec': ('XC_SERVICE', 'PACKAGE'),
    'PackXC_SERVICE_Body': ('XC_SERVICE', 'PACKAGE BODY'),
    'PackTAX_UNTAX_Spec': ('TAX_UNTAX', 'PACKAGE'),
    'PackTAX_UNTAX_Body': ('TAX_UNTAX', 'PACKAGE BODY'),
    'FuncCalcAddValueTax': ('CALCADDVALUETAX', 'FUNCTION'),
    'FuncCalcTaxPrepare': ('CALCTAXPREPARE', 'FUNCTION'),
    'FuncGetErrorMsg': ('GETERRORMSG', 'FUNCTION'),
}

def decode_expression(expr):
    out = []
    pos = 0
    for m in re.finditer(r"'((?:[^']|'')*)'|#(\d+)|\s+|\+", expr):
        assert m.start() == pos, (pos, expr)
        pos = m.end()
        if m.group(1) is not None:
            out.append(m.group(1).replace("''", "'"))
        elif m.group(2) is not None:
            out.append(chr(int(m.group(2))))
    assert pos == len(expr), expr[pos:]
    return ''.join(out)

def encode_fragment(text):
    parts, ascii_run = [], []
    def flush():
        if ascii_run:
            parts.append("'"+''.join(ascii_run)+"'")
            ascii_run[:] = []
    for ch in text:
        if ' ' <= ch <= '~' and ch != "'":
            ascii_run.append(ch)
        else:
            flush()
            parts.append('#'+str(ord(ch)))
    flush()
    return ''.join(parts) or "''"

def encode_line(text):
    return ' +\n'.join(encode_fragment(text[i:i+64]) for i in range(0,len(text),64)) if text else "''"

def main():
    if not SOURCE.is_file():
        raise SystemExit('用法：python analyze_dfm.py <文本 DFM 路径>（或设置环境变量 DFM_SAMPLE）')
    if not (ROOT / 'evidence/db_source_hex.json').is_file():
        raise SystemExit('缺少本地验证材料 evidence/db_source_hex.json，无法比对在线源码')
    raw = SOURCE.read_bytes()
    dfm = raw.decode('ascii')
    src = collections.defaultdict(list)
    for chunk in json.loads((ROOT / 'evidence/db_source_hex.json').read_text('utf-8')):
        for row in chunk.splitlines()[1:]:
            name, typ, lineno, hextext = row.split(',', 3)
            src[name, typ].append((int(lineno), bytes.fromhex(hextext).decode('gbk')))
    summary = {'file_bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
               'ascii_only': True, 'crlf': raw.count(b'\r\n'), 'bare_lf': raw.count(b'\n')-raw.count(b'\r\n'), 'objects': {}}
    for memo, key in MAPPING.items():
        obj = re.search(r'^  object '+memo+r': TMemo\r?\n(.*?)^  end\s*$', dfm, re.M | re.S).group(1)
        prop = re.search(r'    Lines.Strings = \(\r?\n(.*?)\)\r?\n', obj, re.S)
        assert prop, memo
        rows, physical, pending, locations, exprs = [], [], '', [], []
        startline = dfm[:dfm.index(prop.group(1), dfm.index('  object '+memo+': TMemo'))].count('\n')+1
        for i, line in enumerate(prop.group(1).splitlines()):
            s = line.strip()
            if not s:
                continue
            physical.append(s)
            pending += s
            if s.endswith('+'):
                continue
            rows.append(decode_expression(pending))
            exprs.append(pending)
            locations.append(startline+i)
            pending = ''
        assert not pending
        dbrows = src[key]
        assert [i for i, s in dbrows] == list(range(1, len(dbrows)+1))
        # Oracle SOURCE rows are kept separately; remove only the source row terminator.
        db = [s[:-1] if s.endswith('\n') else s for i, s in dbrows]
        db = [s[:-1] if s.endswith('\r') else s for s in db]
        for s in rows + db + ["SELECT '中文', '''', 'a+b', '#39', '\\x' FROM dual;", '\t', '', '  ']:
            assert decode_expression(encode_line(s)) == s
        # Compare lexemes rather than formatting whitespace outside quoted literals.
        lex = lambda s: re.findall(r"'(?:[^']|'')*'|#\d+|\+",s)
        canonical_mismatches = [(i+1,locations[i],rows[i],exprs[i],encode_line(rows[i])) for i in range(len(rows)) if lex(exprs[i]) != lex(encode_line(rows[i]))]
        stem = ROOT / 'evidence' / memo
        stem.with_suffix('.memo.sql').write_text('\n'.join(rows)+'\n', encoding='utf-8')
        stem.with_suffix('.db.sql').write_text('\n'.join(db)+'\n', encoding='utf-8')
        diff = list(difflib.unified_diff(db, rows, fromfile=key[0]+' '+key[1]+' USER_SOURCE', tofile=memo, lineterm=''))
        stem.with_suffix('.diff.txt').write_text('\n'.join(diff)+'\n', encoding='utf-8')
        clean = lambda ss: [s.strip() for s in ss if s.strip()]
        matcher = difflib.SequenceMatcher(None, clean(db)[1:], clean(rows)[2:], autojunk=False)
        summary['objects'][memo] = {
            'db_lines': len(db), 'memo_lines': len(rows), 'physical_nonblank': len(physical),
            'plus_count': sum(s.endswith('+') for s in physical),
            'max_physical_length': max(map(len,physical)),
            'max_decoded_fragment': max(len(decode_expression(s)) for s in physical),
            'max_sql_line': max(map(len,rows)),
            'first_db': db[:3], 'first_memo': rows[:3], 'last_db': db[-4:], 'last_memo': rows[-4:],
            'memo_blank': sum(not s for s in rows), 'db_blank': sum(not s for s in db),
            'memo_trailing_ws': sum(s != s.rstrip() for s in rows), 'db_trailing_ws': sum(s != s.rstrip() for s in db),
            'tab_memo': sum(s.count('\t') for s in rows), 'tab_db': sum(s.count('\t') for s in db),
            'hash9_count': sum(s.count('#9') for s in physical),
            'quote39_count': sum(s.count('#39') for s in physical),
            'doubled_quote_tokens': sum("''" in s for s in physical),
            'embedded_doubled_quotes': [s for s in physical if any("''" in m.group(1) for m in re.finditer(r"'((?:[^']|'')*)'",s))][:5],
            'numeric_codes': sorted(set(int(x) for s in physical for x in re.findall(r'#(\d+)',s))),
            'over64_fragments': [s for s in physical if len(decode_expression(s))>64][:5],
            'continuation_lengths': dict(collections.Counter(len(decode_expression(s)) for s in physical if s.endswith('+'))),
            'placeholders': {x: sum(s.count(x) for s in rows) for x in ('@@@@','#YEAR#','#USER#','#NOWYEAR#','#TAX_CENTER#')},
            'normalized_body_ratio': matcher.ratio(),
            'normalized_changes': [(tag,i,j,k,l,clean(db)[1:][i:j],clean(rows)[2:][k:l]) for tag,i,j,k,l in matcher.get_opcodes() if tag != 'equal'],
            'diff_lines': len(diff), 'start_dfm_line': startline,
            'canonical_mismatches': canonical_mismatches,
        }
    (ROOT/'evidence/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:{x:v[x] for x in ('db_lines','memo_lines','plus_count','canonical_mismatches')} for k,v in summary['objects'].items()},ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()

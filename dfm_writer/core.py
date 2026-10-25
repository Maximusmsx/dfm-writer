"""Text DFM discovery and surgical Lines.Strings serialization (no database writes)."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import re
import tempfile


@dataclass
class Memo:
    name: str
    start: int
    end: int
    indent: str
    property_start: int | None = None
    property_end: int | None = None


TEXT_COMPONENT_KINDS = {'tmemo','trichedit'}


def prefixes(value):
    return sorted(set(p.strip() for p in value.split(',') if p.strip()), key=lambda p: (-len(p), p.lower()))


def replacement_rules(value):
    rules = []
    if not value.strip():
        return rules
    for rule in value.split('|$|'):
        if '->' not in rule:
            raise ValueError(f'替换规则缺少 ->：{rule}')
        old, new = rule.split('->', 1)
        if not old:
            raise ValueError('替换规则的查找内容不能为空')
        rules.append((old, new))
    return rules


def replace_source(text, rules):
    for old, new in rules:
        text = text.replace(old, new)
    return text


def assignment_colons(value):
    """Normalize the UI/config assignment-colon mode to 1 or 2."""
    value = str(value).strip().lower()
    modes = {'1':'1','single':'1','one':'1',':=':'1',
             '2':'2','double':'2','two':'2','::=':'2'}
    if value not in modes:
        raise ValueError('PL/SQL 赋值符只能是单冒号 := 或双冒号 ::=')
    return modes[value]


def _q_quote_end(text, pos):
    """Return the end offset of an Oracle q-quoted literal, or None."""
    lower = text[pos:pos+3].lower()
    if lower.startswith("q'") and pos+2 <= len(text):
        content = pos+2
    elif lower == "nq'":
        content = pos+3
    else:
        return None
    if content >= len(text):
        return len(text)
    closing = {'[':']','{':'}','(':')','<':'>'}.get(text[content],text[content])
    marker = closing+"'"
    end = text.find(marker,content+1)
    return len(text) if end < 0 else end+len(marker)


def convert_assignment_colons(text, mode):
    """Convert PL/SQL assignment operators while preserving binds and literals.

    Only the assignment token := (or its BDE-safe spelling ::=) is changed.
    Colons followed by a bind name are left untouched. Strings, quoted
    identifiers and comments are copied verbatim.
    """
    double_colon_mode = assignment_colons(mode)=='2'
    target = ':=' if not double_colon_mode else '::='
    result, i, size = [], 0, len(text)
    while i < size:
        q_end = _q_quote_end(text,i)
        if q_end is not None:
            result.append(text[i:q_end])
            i = q_end
            continue
        if text.startswith('--',i):
            end = text.find('\n',i)
            end = size if end < 0 else end
            result.append(text[i:end])
            i = end
            continue
        if text.startswith('/*',i):
            end = text.find('*/',i+2)
            end = size if end < 0 else end+2
            result.append(text[i:end])
            i = end
            continue
        char = text[i]
        if char in ("'",'"'):
            start, quote = i, char
            i += 1
            while i < size:
                if text[i] == quote:
                    if i+1 < size and text[i+1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            result.append(text[start:i])
            continue
        if text.startswith('::=',i):
            result.append(target)
            i += 3
            if double_colon_mode and i < size and not text[i].isspace():
                result.append(' ')
            continue
        if text.startswith(':=',i):
            result.append(target)
            i += 2
            if double_colon_mode and i < size and not text[i].isspace():
                result.append(' ')
            continue
        result.append(char)
        i += 1
    return ''.join(result)


def object_mapping(name, component_prefix):
    for prefix in prefixes(component_prefix):
        if name.lower().startswith(prefix.lower()):
            obj = name[len(prefix):]
            if obj.lower().endswith('_spec'):
                return obj[:-5], 'PACKAGE'
            if obj.lower().endswith('_body'):
                return obj[:-5], 'PACKAGE BODY'
            if obj:
                return obj, None  # Query USER_SOURCE to resolve FUNCTION/PROCEDURE/etc.
    raise ValueError(f'对象 {name} 没有匹配的组件前缀或数据库对象名')


def _list_end(text, pos):
    """Find the list closing parenthesis, ignoring quoted text and nested parentheses."""
    depth, quoted = 1, False
    while pos < len(text):
        ch = text[pos]
        if ch == "'":
            if quoted and pos + 1 < len(text) and text[pos+1] == "'":
                pos += 2
                continue
            quoted = not quoted
        elif not quoted:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if not depth:
                    return pos + 1
        pos += 1
    raise ValueError('DFM 的 Lines.Strings 列表未闭合')


def discover_memos(text, component_prefix):
    stack, result = [], []
    pattern = re.compile(r'(?m)^(?P<indent>[ \t]*)(?:(?:object|inherited|inline)\s+(?P<name>\w+)\s*:\s*(?P<kind>\w+)[^\r\n]*|(?P<end>end)[ \t]*)\r?$', re.I)
    for match in pattern.finditer(text):
        indent = match['indent']
        if match['name']:
            stack.append((match, match.end()))
        elif stack and stack[-1][0]['indent'] == indent:
            opening, _ = stack.pop()
            name = opening['name']
            if (opening['kind'].lower() not in TEXT_COMPONENT_KINDS or
                    not any(name.lower().startswith(p.lower()) for p in prefixes(component_prefix))):
                continue
            memo = Memo(name, opening.start(), match.start(), opening['indent'] + '  ')
            # These text controls have no child component properties; constrain to their indentation.
            prop = re.search(r'(?m)^'+re.escape(memo.indent)+r'Lines\.Strings\s*=\s*\(', text[opening.end():match.start()], re.I)
            if prop:
                memo.property_start = opening.end() + prop.start()
                memo.property_end = _list_end(text, opening.end() + prop.end())
                if memo.property_end > memo.end:
                    raise ValueError(f'{name} 的 Lines.Strings 超出组件边界')
            result.append(memo)
    if stack:
        raise ValueError('DFM 组件结构未闭合，请选择文本格式的 DFM')
    names = [m.name.lower() for m in result]
    if len(set(names)) != len(names):
        raise ValueError('DFM 中有重复的目标组件名称')
    return sorted(result, key=lambda m: m.start)


def delphi_version(value='7'):
    value = str(value)
    if value not in ('7','5'):
        raise ValueError('目标 Delphi 版本只能是 7 或 5')
    return value


def encode_fragment(value, target='7'):
    target = delphi_version(target)
    if target == '5':
        # D5's text reader consumes ANSI bytes, not Unicode #nnnn characters.
        value.encode('gbk',errors='strict')
    parts, run = [], []
    def flush():
        if run:
            parts.append("'" + ''.join(run) + "'")
            run.clear()
    for char in value:
        if char != "'" and ((' ' <= char <= '~') or (target == '5' and ord(char)>=128)):
            run.append(char)
        else:
            flush()
            # Numeric DFM characters represent UTF-16 units; current GBK source is BMP.
            units = char.encode('utf-16-le', errors='surrogatepass')
            parts.extend('#' + str(int.from_bytes(units[i:i+2], 'little')) for i in range(0,len(units),2))
    flush()
    return ''.join(parts) or "''"


def decode_expression(expr, target='7'):
    target = delphi_version(target)
    parts, ansi_parts, pos = [], [], 0
    for match in re.finditer(r"'((?:[^']|'')*)'|#(\d+)|\s+|\+", expr):
        if match.start() != pos:
            raise ValueError(f'DFM 字符串语法错误：{expr[pos:pos+40]}')
        pos = match.end()
        if match[1] is not None:
            value = match[1].replace("''", "'")
            parts.append(value)
            if target == '5':
                ansi_parts.append(value.encode('gbk'))
        elif match[2] is not None:
            code = int(match[2])
            if code > (255 if target == '5' else 65535):
                raise ValueError(f'Delphi {target} 数字字符转义越界：#{code}')
            parts.append(chr(code))
            if target == '5':
                ansi_parts.append(bytes([code]))
    if pos != len(expr):
        raise ValueError('DFM 字符串包含未识别的内容')
    if target == '5':
        return b''.join(ansi_parts).decode('gbk')
    return ''.join(parts).encode('utf-16-le', errors='surrogatepass').decode('utf-16-le')


def decode_lines(text, memo, target='7'):
    if memo.property_start is None:
        return []
    value = text[memo.property_start:memo.property_end]
    value = value[value.index('(')+1:-1]
    rows, pending = [], ''
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        pending += line
        if not line.endswith('+'):
            rows.append(decode_expression(pending,target))
            pending = ''
    if pending:
        raise ValueError('DFM 续行不完整')
    return rows


def line_chunks(row,target='7'):
    target = delphi_version(target)
    if target == '7':
        # Count UTF-16 code units, keeping a surrogate pair in the same fragment.
        length = lambda ch: len(ch.encode('utf-16-le'))//2
    else:
        length = lambda ch: len(ch.encode('gbk',errors='strict'))
    chunks,run,size = [],[],0
    for ch in row:
        width = length(ch)
        if size+width>64:
            chunks.append(''.join(run))
            run,size = [],0
        run.append(ch)
        size += width
    return chunks+[''.join(run)]


def serialize_lines(rows, indent, newline, target='7'):
    target = delphi_version(target)
    lines = [indent + 'Lines.Strings = (']
    for row in rows:
        chunks = line_chunks(row,target)
        if len(chunks) > 1:
            lines.append(indent + '  ')
        for i, chunk in enumerate(chunks):
            lines.append(indent + ('    ' if len(chunks)>1 else '  ') + encode_fragment(chunk,target) + (' +' if i<len(chunks)-1 else ''))
    if rows:
        lines[-1] += ')'
    else:
        lines[0] += ')'
    return newline.join(lines)


HEADERS = {
    ('XC_SERVICE', 'PACKAGE'): '/*包PACKAGE XC_SERVICE*/',
    ('XC_SERVICE', 'PACKAGE BODY'): '/*包XC_SERVICE BODY*/',
    ('TAX_UNTAX', 'PACKAGE'): '/*包PACKAGE TAX_UNTAX*/',
    ('TAX_UNTAX', 'PACKAGE BODY'): '/*包PACKAGE BODY TAX_UNTAX*/',
    ('CALCADDVALUETAX', 'FUNCTION'): '/*CalcAddValueTax函数源码：*/',
    ('CALCTAXPREPARE', 'FUNCTION'): '/* CalcTaxPrepare函数源码*/',
    ('GETERRORMSG', 'FUNCTION'): '/*GetErrorMsg函数源码：*/',
}


def ddl_rows(source_rows, name, kind, rules, colon_mode=None):
    if not source_rows:
        raise ValueError(f'数据库对象无源码：{name} ({kind})')
    rows = []
    for row in source_rows:
        row = row or ''
        if row.endswith('\n'):
            row = row[:-1]
        if row.endswith('\r'):
            row = row[:-1]
        rows.append(row)
    # USER_SOURCE gives an unqualified declaration; never use owner-qualified GET_DDL.
    rows[0] = 'CREATE OR REPLACE ' + re.sub(
        r'^(\s*(?:PACKAGE\s+BODY|PACKAGE|FUNCTION|PROCEDURE|TRIGGER|TYPE\s+BODY|TYPE)\s+)(?:"[^"]+"|[A-Za-z_][\w$#]*)\s*\.\s*',
        r'\1',rows[0],count=1,flags=re.I)
    header = HEADERS.get((name.upper(),kind))
    if header is None:
        if kind.startswith('PACKAGE'):
            header = f'/*包{kind} {name}*/'
        else:
            label = {'FUNCTION':'函数','PROCEDURE':'存储过程','TRIGGER':'触发器'}.get(kind,'')
            header = f'/*{name}{label}源码：*/'
    # Replacement runs on database DDL before the project-only description is added.
    text = replace_source('\n'.join(rows),rules)
    if colon_mode is not None:
        text = convert_assignment_colons(text,colon_mode)
    return [header] + text.replace('\r\n','\n').replace('\r','\n').split('\n')


def validate_numeric_escapes(text,target='7'):
    """Check unquoted numeric character tokens in the entire result, not literal '#39'."""
    limit = 255 if delphi_version(target)=='5' else 65535
    for match in re.finditer(r"'(?:[^']|'')*'|#(\d+)",text):
        if match[1] and int(match[1])>limit:
            line = text.count('\n',0,match.start())+1
            raise ValueError(f'Delphi {target} 不支持第 {line} 行的字符转义 #{match[1]}。'
                             '请使用该 Delphi 版本的原生 DFM；本工具只更新选中的文本组件，不迁移整个窗体的其他属性。')


class DfmDocument:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.suffix.lower() != '.dfm':
            raise ValueError('只能选择 .dfm 文件')
        self.raw = self.path.read_bytes()
        if self.raw.startswith(b'TPF0'):
            raise ValueError('请选择文本格式的 DFM（Delphi 中 View as Text 后保存）')
        if self.raw.startswith((b'\xef\xbb\xbf',b'\xff\xfe',b'\xfe\xff')):
            raise ValueError('Delphi 7/5 目标文件必须是无 BOM 的 ANSI/GBK 文本 DFM，不能是 UTF-8/UTF-16 BOM 文件')
        self.encoding = 'gbk'
        self.text = self.raw.decode(self.encoding)
        if self.text.encode(self.encoding) != self.raw:
            raise ValueError('文件编码无法无损还原')
        self.newline = '\r\n' if '\r\n' in self.text else '\n'

    def render(self, component_prefix, values, target='7'):
        target = delphi_version(target)
        memos = {m.name:m for m in discover_memos(self.text,component_prefix)}
        edits = []
        for name, rows in values.items():
            if name not in memos:
                raise ValueError(f'DFM 中不存在符合前缀的文本组件（TMemo/TRichEdit）：{name}')
            memo = memos[name]
            replacement = serialize_lines(rows,memo.indent,self.newline,target)
            if memo.property_start is None:
                edits.append((memo.end,memo.end,replacement+self.newline))
            else:
                edits.append((memo.property_start,memo.property_end,replacement))
        result = self.text
        for start,end,replacement in sorted(edits,reverse=True):
            result = result[:start]+replacement+result[end:]
        new_memos = {m.name:m for m in discover_memos(result,component_prefix)}
        for name, rows in values.items():
            if decode_lines(result,new_memos[name],target) != rows:
                raise ValueError(f'{name} 写入后校验失败')
        validate_numeric_escapes(result,target)
        return result.encode(self.encoding)

    def save(self, content):
        if self.path.read_bytes() != self.raw:
            raise ValueError('生成期间 DFM 被其他程序修改，请重新读取后生成')
        backup = self.path.with_name(self.path.name+'.'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.bak')
        with backup.open('xb') as stream:
            stream.write(self.raw)
        descriptor, temp = tempfile.mkstemp(prefix=self.path.name+'.',suffix='.tmp',dir=self.path.parent)
        try:
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.read_bytes() != self.raw:
                raise ValueError('写入前检测到 DFM 已变化，已停止替换')
            os.replace(temp,self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return backup

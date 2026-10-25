from pathlib import Path
import tempfile
import unittest
from dfm_writer.core import (encode_fragment,decode_expression,serialize_lines,line_chunks,
    DfmDocument,discover_memos,decode_lines,validate_numeric_escapes)
from legacy_dfm_reader import read_string_list


class LegacyCompatibilityTests(unittest.TestCase):
    def test_known_legacy_vectors(self):
        self.assertEqual(encode_fragment("  RETURN '中文';",'7'),"'  RETURN '#39#20013#25991#39';'")
        self.assertEqual(encode_fragment("  RETURN '中文';",'5'),"'  RETURN '#39'中文'#39';'")
        self.assertEqual(encode_fragment('中文','5').encode('gbk'),b"'\xd6\xd0\xce\xc4'")
        self.assertEqual(decode_expression('#214#208#206#196','5'),'中文')
        with self.assertRaises(ValueError):
            decode_expression('#20013','5')

    def test_independent_grammar_and_bytes(self):
        values = ['', '  ', '\t', "RETURN '';", "RETURN '中文';", 'a'*64,'a'*65,
                  '中'*64, 'a'*63+'中'+'b'*70, "'#39'+x",'--汉字“引号”¤', ' trailing  ']
        for version in ('7','5'):
            with self.subTest(version=version):
                encoded = serialize_lines(values,'    ','\r\n',version).encode('gbk')
                self.assertEqual(read_string_list(encoded,version),values)
                validate_numeric_escapes(encoded.decode('gbk'),version)
                if version=='7':
                    self.assertTrue(encoded.isascii())
                else:
                    self.assertIn('中文'.encode('gbk'),encoded)
                for value in values:
                    chunks = line_chunks(value,version)
                    self.assertEqual(''.join(chunks),value)
                    self.assertTrue(all(len(c.encode('gbk'))<=64 if version=='5' else len(c.encode('utf-16-le'))<=128 for c in chunks))

    def test_delphi5_fails_without_replacing_unrepresentable_characters(self):
        with self.assertRaises(UnicodeEncodeError):
            encode_fragment('emoji 😀','5')

    def test_delphi5_checks_unselected_properties(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.dfm'
            path.write_bytes(b"object Form1: TForm\r\n  Caption = #20013\r\n  object FuncDemo: TMemo\r\n  end\r\nend\r\n")
            doc = DfmDocument(path)
            with self.assertRaises(ValueError):
                doc.render('Func',{'FuncDemo':['中文']},'5')
            self.assertEqual(path.read_bytes(),doc.raw)

    def test_delphi5_complete_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.dfm'
            original = "object Form1: TForm\r\n  Caption = '保留'\r\n  object FuncDemo: TMemo\r\n  end\r\nend\r\n".encode('gbk')
            path.write_bytes(original)
            doc = DfmDocument(path)
            rows = ['中文',"RETURN '';",'中'*100,'\t  ']
            result = doc.render('Func',{'FuncDemo':rows},'5')
            self.assertFalse(result.startswith(b'\xef\xbb\xbf'))
            text = result.decode('gbk')
            memo = discover_memos(text,'Func')[0]
            self.assertEqual(decode_lines(text,memo,'5'),rows)
            value = text[memo.property_start:memo.property_end].encode('gbk')
            self.assertEqual(read_string_list(value,'5'),rows)
            self.assertIn("Caption = '保留'".encode('gbk'),result)

    def test_invalid_legacy_syntax_is_rejected(self):
        for value,version in [(b"Lines.Strings = (#20013)",'5'),
                              (b"Lines.Strings = ('abc' +)",'7'),
                              (b"Lines.Strings = ('unclosed)",'5'),
                              (b"Lines.Strings = (#65536)",'7')]:
            with self.assertRaises(ValueError):
                read_string_list(value,version)


if __name__ == '__main__':
    unittest.main()

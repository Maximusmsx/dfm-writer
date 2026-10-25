"""Independent byte-level reader for the Delphi 5/7 string-list subset we emit.

This deliberately does not import the application's encoder or decoder.
It is a syntax/byte oracle, not a substitute for running Borland's loader.
"""


def read_string_list(data,version):
    if data.startswith((b'\xef\xbb\xbf',b'\xff\xfe',b'\xfe\xff')):
        raise ValueError('Legacy DFM must not have a Unicode BOM')
    pos = data.index(b'(')+1
    length = len(data)
    whitespace = b' \r\n\t'

    def skip():
        nonlocal pos
        while pos<length and data[pos] in whitespace:
            pos += 1

    result = []
    while True:
        skip()
        if pos>=length:
            raise ValueError('unclosed list')
        if data[pos] == 41:
            pos += 1
            skip()
            if pos != length:
                raise ValueError('trailing tokens')
            return result
        raw_parts,wide_parts = [],[]
        while True:
            if data[pos] == 39:
                pos += 1
                buf = bytearray()
                while True:
                    if pos>=length or data[pos] in b'\r\n':
                        raise ValueError('unclosed quoted fragment')
                    value = data[pos]
                    pos += 1
                    if value == 39:
                        if pos<length and data[pos] == 39:
                            pos += 1
                            buf.append(39)
                        else:
                            break
                    else:
                        buf.append(value)
                raw_parts.append(bytes(buf))
                if version == '7':
                    wide_parts.append(bytes(buf).decode('gbk'))
            elif data[pos] == 35:
                pos += 1
                start = pos
                while pos<length and 48<=data[pos]<=57:
                    pos += 1
                if start == pos:
                    raise ValueError('numeric escape has no digits')
                number = int(data[start:pos])
                if number>(255 if version=='5' else 65535):
                    raise ValueError('character number out of range')
                if version == '5':
                    raw_parts.append(bytes([number]))
                else:
                    wide_parts.append(chr(number))
            else:
                raise ValueError('expected quoted fragment or numeric character')
            if pos<length and data[pos] in (35,39):
                continue
            skip()
            if pos<length and data[pos] == 43:
                pos += 1
                skip()
                if pos>=length or data[pos] not in (35,39):
                    raise ValueError('continuation has no string')
                continue
            if version == '5':
                result.append(b''.join(raw_parts).decode('gbk'))
            else:
                result.append(''.join(wide_parts).encode('utf-16-le',errors='surrogatepass').decode('utf-16-le'))
            break

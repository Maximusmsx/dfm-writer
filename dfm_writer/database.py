import oracledb
from .oracle_runtime import init_thick_mode


def connect(config):
    ok, message = init_thick_mode()
    if not ok:
        raise RuntimeError('无法加载内嵌 Oracle Client 19：'+message)
    connection = oracledb.connect(user=config['user'].strip(),password=config['password'],dsn=config['conn_str'].strip())
    connection.call_timeout = 60000
    return connection


def identity(connection):
    with connection.cursor() as cursor:
        cursor.execute("select user, sys_context('USERENV','DB_NAME') from dual")
        user, database = cursor.fetchone()
    return f'{user}@{database}'


def read_source(connection, name, kind):
    with connection.cursor() as cursor:
        if kind is None:
            cursor.execute('select distinct type from user_source where name=:name',name=name.upper())
            kinds = [row[0] for row in cursor]
            if len(kinds) != 1:
                raise ValueError(f'{name} 对象类型无法唯一确定：'+(', '.join(kinds) or '当前用户下没有可读取源码的对象'))
            kind = kinds[0]
        cursor.execute('select line,text from user_source where name=:name and type=:kind order by line',name=name.upper(),kind=kind)
        rows = cursor.fetchall()
    if not rows:
        raise ValueError(f'当前用户下未找到源码：{name} ({kind})')
    if [row[0] for row in rows] != list(range(1,len(rows)+1)):
        raise ValueError(f'{name} 源码行号不连续')
    return kind,[row[1] for row in rows]

import oracledb
import os
import shutil
import sys
import glob
import datetime
import decimal
import hashlib
import tempfile

# ── Thick 模式（读取 tnsnames.ora / TNS 别名）──────────────────
_thick_initialized = False


def _is_64bit_oci(path):
    """检查 oci.dll 是否为 64-bit (x86_64)，避免加载 32-bit dll 导致崩溃。"""
    if not os.path.exists(path):
        return False
    try:
        with open(path, "rb") as f:
            dos = f.read(0x40)
            if len(dos) < 0x40:
                return False
            pe_offset = int.from_bytes(dos[0x3C:0x40], "little")
            f.seek(pe_offset + 4)
            machine = int.from_bytes(f.read(2), "little")
        return machine == 0x8664   # x86_64
    except Exception:
        return False


def _find_oracle_client():
    r"""搜索第一个包含 64-bit oci.dll 的目录，跳过所有 32-bit 的 dll。

    优先级：
      1. exe 同目录下的 oracle_client\ 文件夹（便携部署）
      2. ORACLE_HOME 环境变量
      3. C:/D: 盘下的 oracle/instantclient_* 或 oracle/ora* 目录
      4. 常见第三方工具（Navicat、DataGrip 等）附带的 Instant Client
      5. PATH 中的目录
    """
    candidates = []

    # 0. 内嵌在 exe 中的 oracle_client（PyInstaller --add-data 解压到 _MEIPASS）
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "oracle_client"))

    # 1. exe/脚本 旁边的 oracle_client\ 目录（便于分发时手动放置）
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(exe_dir, "oracle_client"))

    # 2. ORACLE_HOME 环境变量
    oracle_home = os.environ.get("ORACLE_HOME", "")
    if oracle_home:
        candidates.append(os.path.join(oracle_home, "bin"))
        candidates.append(oracle_home)

    # 3. 常见 Oracle Instant Client 目录（最新版优先）
    for root in ["C:\\oracle", "D:\\oracle", "C:\\instantclient", "D:\\instantclient"]:
        try:
            # 匹配 instantclient_xx_x  和  oraXX  两种命名
            for p in sorted(
                glob.glob(os.path.join(root, "instantclient_*")) +
                glob.glob(os.path.join(root, "ora*")),
                reverse=True
            ):
                candidates.append(p)
                candidates.append(os.path.join(p, "bin"))
        except Exception:
            pass

    # 4. 常见第三方工具自带的 Instant Client
    for pattern in [
        r"C:\Program Files\PremiumSoft\Navicat*\instantclient*",
        r"C:\Program Files\JetBrains\*\jbr\bin",
        r"C:\Program Files\*\instantclient*",
    ]:
        try:
            for p in glob.glob(pattern):
                candidates.append(p)
        except Exception:
            pass

    # 5. PATH 中的每个目录
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d:
            candidates.append(d)

    for d in candidates:
        if _is_64bit_oci(os.path.join(d, "oci.dll")):
            return d

    return None


def init_thick_mode():
    """初始化 oracledb Thick 模式（连接 Oracle 11g 所必需）。"""
    global _thick_initialized
    if _thick_initialized:
        return True, ""
    lib_dir = _find_oracle_client()
    if lib_dir is None:
        return False, (
            "未找到 64-bit Oracle 客户端库 (oci.dll)。\n\n"
            "解决方法：\n"
            "① 从 Oracle 官网下载 Windows x64 Instant Client Basic：\n"
            "   https://www.oracle.com/database/technologies/instant-client/winx64-64-downloads.html\n"
            "② 解压后将 19c 客户端文件夹（如 instantclient_19_32）放到 C:\\oracle\\ 下，\n"
            "   或直接放在本程序 exe 同目录的 oracle_client\\ 文件夹中\n"
            "③ 重新启动本程序后再连接"
        )
    try:
        oracledb.init_oracle_client(lib_dir=lib_dir)
        _thick_initialized = True
        return True, ""
    except Exception as e:
        if 'DPI-1047' not in str(e) or str(lib_dir).isascii():
            return False, str(e)
        # OCI 19 can reject a Unicode Windows path. Reuse an ASCII cache of the same DLLs.
        try:
            dlls = sorted(glob.glob(os.path.join(lib_dir, '*.dll')))
            stamp = '|'.join(os.path.basename(p)+':'+str(os.stat(p).st_size)+':'+str(os.stat(p).st_mtime_ns) for p in dlls)
            cache = os.path.join(tempfile.gettempdir(), 'dfm_oracle19_'+hashlib.sha256(stamp.encode()).hexdigest()[:12])
            os.makedirs(cache,exist_ok=True)
            for source in dlls:
                destination = os.path.join(cache,os.path.basename(source))
                if not os.path.exists(destination) or os.path.getsize(destination) != os.path.getsize(source):
                    fd,temporary = tempfile.mkstemp(dir=cache,suffix='.dll')
                    os.close(fd)
                    try:
                        shutil.copy2(source,temporary)
                        os.replace(temporary,destination)
                    finally:
                        if os.path.exists(temporary):
                            os.unlink(temporary)
            if not cache.isascii():
                import ctypes
                buffer = ctypes.create_unicode_buffer(32768)
                if ctypes.windll.kernel32.GetShortPathNameW(cache,buffer,len(buffer)):
                    cache = buffer.value
            oracledb.init_oracle_client(lib_dir=cache)
            _thick_initialized = True
            return True, ''
        except Exception as fallback_error:
            return False, str(fallback_error)


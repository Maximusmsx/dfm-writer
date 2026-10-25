"""Build a Windows x64 single-file EXE, including Oracle Client 19 Basic."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
CLIENT_FILES = ('oci.dll','oraociei19.dll','orannzsbb19.dll','oraons.dll','BASIC_LICENSE','BASIC_README',
                'msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','concrt140.dll')


def main():
    import PyInstaller.__main__
    for name in CLIENT_FILES:
        if not (ROOT/'oracle_client'/name).exists():
            raise FileNotFoundError(f'内嵌运行文件缺失：oracle_client/{name}')
    args = [str(ROOT/'main.py'),'--onefile','--windowed','--clean','--noconfirm',
            '--name=数据直写DFM','--icon='+str(ROOT/'assets/dfm.ico'),
            '--distpath='+str(ROOT/'dist'),'--workpath='+str(ROOT/'build'),
            '--specpath='+str(ROOT),'--collect-all=oracledb','--collect-all=cryptography',
            '--hidden-import=cffi','--hidden-import=uuid',
            '--exclude-module=PyQt6.QtWebEngineCore','--exclude-module=PyQt6.QtWebEngineWidgets',
            '--exclude-module=PyQt6.QtQml','--exclude-module=PyQt6.QtQuick',
            '--add-data='+str(ROOT/'assets')+os.pathsep+'assets']
    for name in CLIENT_FILES:
        args.append('--add-data='+str(ROOT/'oracle_client'/name)+os.pathsep+'oracle_client')
    PyInstaller.__main__.run(args)


if __name__ == '__main__':
    main()

import json
import os
from pathlib import Path
import sys
import tempfile


def application_dir():
    return Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent


class ConfigStore:
    def __init__(self,path=None):
        self.path = Path(path) if path else application_dir()/'config.json'
        self.data = {'profiles':{},'last_profile':''}
        if self.path.exists():
            value = json.loads(self.path.read_text('utf-8'))
            if not isinstance(value,dict) or not isinstance(value.get('profiles'),dict):
                raise ValueError('配置文件格式错误，请检查 config.json')
            for name, profile in value['profiles'].items():
                if not isinstance(name,str) or not isinstance(profile,dict):
                    raise ValueError('配置条目格式错误')
            self.data = value

    def save(self):
        descriptor,temp = tempfile.mkstemp(prefix='config.',suffix='.tmp',dir=self.path.parent)
        try:
            with os.fdopen(descriptor,'w',encoding='utf-8',newline='\n') as stream:
                json.dump(self.data,stream,ensure_ascii=False,indent=2)
            os.replace(temp,self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

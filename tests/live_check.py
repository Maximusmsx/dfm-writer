"""Read-only live check using an existing backup-tool profile; writes only a copied fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from dfm_writer import database
from dfm_writer.core import DfmDocument,discover_memos,decode_lines,object_mapping,ddl_rows
from dfm_writer.jobs import generate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config')
    parser.add_argument('dfm')
    parser.add_argument('output')
    parser.add_argument('--profile', default='lxd', help='config.json 中的配置名称')
    args = parser.parse_args()
    raw = json.loads(Path(args.config).read_text('utf-8'))
    profiles = [(k,v) for k,v in raw['profiles'].items() if k == args.profile]
    if len(profiles) != 1:
        raise ValueError(f'需要唯一配置：{args.profile}')
    profile_name,config = profiles[0]
    config = dict(config)
    original = Path(args.dfm)
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    destination = Path(args.output)
    destination.mkdir(parents=True,exist_ok=True)
    copy = destination/'UfrmUpdate.test.dfm'
    shutil.copy2(original,copy)
    selected = ['PackXC_SERVICE_Spec','PackXC_SERVICE_Body','PackTAX_UNTAX_Spec','PackTAX_UNTAX_Body',
                'FuncCalcAddValueTax','FuncCalcTaxPrepare','FuncGetErrorMsg']
    config.update(dfm_path=str(copy),COMPONENT_PREFIX='Pack,Func',REPALCE_PATTEN='',selected_objects=selected)
    progress = []
    result = generate(config,lambda done,total,name:progress.append(round(done*100/total)))
    doc = DfmDocument(copy)
    memos = {m.name:m for m in discover_memos(doc.text,'Pack,Func')}
    verified = []
    with database.connect(config) as conn:
        db_identity = database.identity(conn)
        for memo in selected:
            name,kind = object_mapping(memo,'Pack,Func')
            kind,rows = database.read_source(conn,name,kind)
            assert decode_lines(doc.text,memos[memo]) == ddl_rows(rows,name,kind,[])
            verified.append({'memo':memo,'source_lines':len(rows)})
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    assert progress == [14,29,43,57,71,86,100]
    report = {'status':'passed','profile':profile_name,'identity':db_identity,'verified':verified,
              'progress':progress,'original_unchanged':True,'result':result}
    (destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()

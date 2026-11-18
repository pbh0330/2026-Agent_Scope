"""Prepare a new local publication stage; never uploads or modifies old manifests."""
from pathlib import Path
import collections
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'.qa-publish/review-20261119'
STAGE = OUT/'stage-upload'


def main():
    STAGE.mkdir(parents=True, exist_ok=True)
    errors, files, edits = [], [], []
    for p in (ROOT/'QA').rglob('*'):
        if not p.is_file() or any(x in p.parts for x in ('__pycache__','work')): continue
        if '.local.' in p.name or (p.suffix not in ('.md','.json','.py','.cjs','.png','.xml','.patch') and p.name not in ('schema-check.txt','.gitattributes')): continue
        if p.suffix == '.xml' and not p.name.endswith('.public.xml'): continue
        dest = STAGE/p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix == '.png': shutil.copyfile(p, dest); continue
        text = p.read_text(encoding='utf-8-sig')
        if p.suffix == '.json':
            obj = json.loads(text)
            def clean(v):
                if isinstance(v,dict): return {k:clean(x) for k,x in v.items()}
                if isinstance(v,list): return [clean(x) for x in v]
                if isinstance(v,str): return re.sub(r'(?i)[A-Z]:[/\\]+Users[/\\]+[^\r\n"<>]*','<LOCAL_PATH>',v)
                return v
            safe = clean(obj)
            if safe != obj:
                edits.append(p.relative_to(ROOT).as_posix())
                text = json.dumps(safe,ensure_ascii=False,indent=2)+'\n'
        if p.suffix == '.md':
            # Bundle the actual local schema revision referenced by QA, rather than
            # redirecting a local draft to a different remote commit.
            schema_path = STAGE/'QA/reference/schema-design-draft-v0.7.7.md'
            schema_path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/'2026-agent-scope-pr/docs/schema-design-draft.md',schema_path)
            text = text.replace('../2026-agent-scope-pr/docs/schema-design-draft.md','reference/schema-design-draft-v0.7.7.md')
        if p.suffix == '.xml':
            text = re.sub(r'(?i)[A-Z]:[/\\]+Users[^\r\n<>"\']*','&lt;LOCAL_PATH&gt;',text)
            text = re.sub(r'gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}', 'FIXTURE_CREDENTIAL',text)
            text = text.replace('-----BEGIN '+'PRIVATE KEY-----','FIXTURE_PRIVATE_KEY_HEADER')
            ET.fromstring(text)
        dest.write_text(text,encoding='utf-8')
    form=ROOT/'.github/ISSUE_TEMPLATE/qa-defect.yml'
    if form.exists():
        d=STAGE/form.relative_to(ROOT);d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(form,d)
    examples=ROOT/'2026-agent-scope-pr/docs/examples/p0'
    for p in examples.glob('*'):
        if p.is_file() and p.suffix in ('.md','.json','.py'):
            d=STAGE/'QA/reference/examples/p0'/p.name;d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,d)
    for p in STAGE.rglob('*'):
        if not p.is_file(): continue
        data=p.read_bytes();relative=p.relative_to(STAGE).as_posix()
        files.append({'path':relative,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        if p.suffix == '.png': continue
        text=data.decode('utf-8-sig')
        for name,pattern in {
            'credential_pattern':r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            'personal_path':r'(?i)C:[/\\]+Users[/\\]+(?:ajou|CodexSandboxOffline)|DESKTOP-'+'RC5S1DE',
        }.items():
            if re.search(pattern,text): errors.append({'path':relative,'check':name})
        if p.suffix=='.json': json.loads(text)
        if p.suffix=='.md':
            for t in re.findall(r'\]\(([^)]+)\)',text):
                if '://' in t or t.startswith('#'): continue
                if not (p.parent/t.split('#')[0]).exists(): errors.append({'path':relative,'missing_link':t})
    report={'files':len(files),'bytes':sum(x['bytes'] for x in files),'path_sanitized_files':edits,
            'errors':errors,'screenshots':'Copied existing QA captures; automated credential patterns cannot inspect image pixels.',
            'excluded':'work, local logs/XML/executables, trace JSONL, caches, dependencies, source ZIPs',
            'publication':'local stage only; no GitHub update'}
    (OUT/'manifest.json').write_text(json.dumps(files,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'files':len(files),'errors':errors},ensure_ascii=True))
    if errors: raise SystemExit(1)


if __name__=='__main__': main()

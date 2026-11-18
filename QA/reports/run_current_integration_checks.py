"""Check the published dashboard snapshot with the pinned usage API (local only)."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'QA/evidence/RUN-20261118-LINK-01'
DASH = ROOT / '.parts-snapshots-20261118-check/2026-Agent_Scope-8f56930af9f2b9b8491b0df6c26ba6c4a4dc8cc5/dashboard'


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([sys.executable, str(DASH/'pipeline/check_schema.py'), str(DASH/'public/data')],
                          capture_output=True, encoding='utf-8', env={**os.environ, 'PYTHONUTF8':'1'})
    (OUT/'schema-check.txt').write_text(proc.stdout+proc.stderr, encoding='utf-8')
    assert proc.returncode == 0
    snap = DASH/'public/data/snapshots/P2/snapshot.json'
    inventory = json.loads(snap.read_text(encoding='utf-8'))
    dump(OUT/'P2.snapshot.json', inventory)
    spec = importlib.util.spec_from_file_location('usage_check', Path(__file__).with_name('run_usage_link_validation.py'))
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    previous.OUT = OUT/'pc'; previous.SNAPSHOT = snap
    previous.main()
    # Controlled positive mapping: change only the MCP exposed name in a copy
    # of the PC fixture. Never represent these calls as real testbed telemetry.
    trace = previous.SOURCE/'testdata/pc-1029.traces.jsonl'
    text = trace.read_text(encoding='utf-8')
    assert 'fs__read_text_file' in text
    controlled = OUT/'controlled.traces.jsonl'
    controlled.write_text(text.replace('fs__read_text_file', 'fs-workspace__read_text_file'), encoding='utf-8')
    cmd = [str(previous.OUT/'agentscope-usage-api.local.exe'), '--env', inventory['environment_id'],
           '--profile', inventory['profile_id'], '--input', str(controlled), '--inventory', str(snap),
           '--reference-pricing=false', '--addr', '127.0.0.1:18088']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    log = (OUT/'controlled-server.local.log').open('wb')
    process = subprocess.Popen(cmd, stdout=log, stderr=log)
    try:
        for _ in range(100):
            try:
                with opener.open('http://127.0.0.1:18088/api/v1/usage/health', timeout=2) as r:
                    json.load(r)
                break
            except OSError:
                if process.poll() is not None: raise RuntimeError('controlled API exited')
                time.sleep(.1)
        else: raise RuntimeError('controlled API timeout')
        responses = {}
        for name, path in {'summary':'summary', 'records':'records?limit=500', 'assets':'by-asset?group=asset'}.items():
            with opener.open('http://127.0.0.1:18088/api/v1/usage/'+path) as r:
                responses[name] = json.load(r)
            dump(OUT/f'controlled-{name}.json', responses[name])
        expected = next(a['asset_id'] for a in inventory['assets'] if a.get('project',{}).get('canonical_key') == 'fs-workspace/tool/read_text_file')
        matched = [r for r in responses['records']['items'] if r.get('mapping_status') == 'matched']
        checks = [
            {'check':'controlled_positive_mapping', 'pass':bool(matched) and all(r['asset_id']==expected for r in matched)},
            {'check':'all_calls_preserved', 'pass':responses['summary']['calls']==16},
            {'check':'matched_and_unmatched_partition', 'pass':sum(responses['summary']['by_mapping'].values())==16},
        ]
        dump(OUT/'controlled-checks.json', checks)
        dump(OUT/'execution.json', {'dashboard_commit':'8f56930af9f2b9b8491b0df6c26ba6c4a4dc8cc5',
             'token_commit':'6e4cf5c0cf7116821d48fd3231c7cb2a6595a4ae', 'snapshot_id':inventory['snapshot_id'],
             'controlled_input':'PC fixture copy; MCP exposed name replaced; NOT testbed telemetry',
             'expected_asset_id':expected, 'matched_calls':len(matched),
             'checks_passed':sum(c['pass'] for c in checks), 'checks_failed':sum(not c['pass'] for c in checks)})
        print(json.dumps({'controlled_checks':checks, 'matched_calls':len(matched)}))
        assert all(c['pass'] for c in checks)
        cli = OUT/'agentscope-usage.local.exe'
        env = {**os.environ, 'GOCACHE':str(ROOT/'.tools/go-cache'), 'GOPATH':str(ROOT/'.tools/go-path'),
               'GOTOOLCHAIN':'local', 'GOPROXY':'off'}
        subprocess.run([str(ROOT/'.tools/go-runtime/go/bin/go.exe'), 'build', '-o', str(cli), './cmd/agentscope-usage'],
                       cwd=previous.SOURCE.parent/'usagereport', env=env, check=True, capture_output=True)
        subprocess.run([str(cli), '--env', inventory['environment_id'], '--profile', inventory['profile_id'],
                        '--inventory', str(snap), '--input', str(controlled), '--reference-pricing=false',
                        '--out', str(OUT/'controlled.usage.json')], check=True, capture_output=True)
        records = json.loads((OUT/'controlled.usage.json').read_text(encoding='utf-8'))['records']
        by_id = {r['usage_id']:r for r in responses['records']['items']}
        file_checks = [
            {'check':'same_record_ids','pass':{r['usage_id'] for r in records}==set(by_id)},
            {'check':'file_api_fields','pass':all(r['asset_ref']==by_id[r['usage_id']]['asset_id']
                and r['approx_input_tokens']==by_id[r['usage_id']]['tokens']
                and r['mapping_status']==by_id[r['usage_id']]['mapping_status'] for r in records)},
            {'check':'total_tokens','pass':sum(r['approx_input_tokens'] or 0 for r in records)==15769}]
        dump(OUT/'file-api-checks.json',file_checks)
        assert all(c['pass'] for c in file_checks)
    finally:
        process.terminate(); process.wait(timeout=10); log.close()


if __name__ == '__main__': main()

"""Run the pinned usage API against saved PC traces and the saved P2 inventory."""
from pathlib import Path
import json
import os
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'QA/evidence/RUN-20261117-USAGE-01'
SOURCE = ROOT / '.parts-snapshots-20261116/token/token-collector/backend/usageapi'
SNAPSHOT = ROOT / 'QA/evidence/RUN-20261116-INTEGRATION-01/data/snapshots/P2/snapshot.json'


def dump(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'GOCACHE': str(ROOT / '.tools/go-cache'),
           'GOPATH': str(ROOT / '.tools/go-path'), 'GOTOOLCHAIN': 'local', 'GOPROXY': 'off'}
    binary = OUT / 'agentscope-usage-api.local.exe'
    go = ROOT / '.tools/go-runtime/go/bin/go.exe'
    build = subprocess.run([str(go), 'build', '-o', str(binary), './cmd/agentscope-usage-api'],
                           cwd=SOURCE, env=env, capture_output=True, timeout=240)
    (OUT / 'build.local.log').write_bytes(build.stdout + build.stderr)
    if build.returncode:
        raise RuntimeError('Go build failed; see build.local.log')
    inventory = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    common = [str(binary), '--profile', inventory['profile_id'], '--input',
              str(SOURCE / 'testdata/pc-1029.traces.jsonl'), '--inventory', str(SNAPSHOT),
              '--reference-pricing=false', '--addr', '127.0.0.1:18088']
    mismatch = subprocess.run(common + ['--env', 'validation-wrong-environment'],
                              capture_output=True, timeout=20)
    (OUT / 'context-mismatch.local.log').write_bytes(mismatch.stdout + mismatch.stderr)
    responses = {}
    checks = [{'name': 'environment_mismatch_rejected', 'pass': mismatch.returncode != 0}]
    log = (OUT / 'server.local.log').open('wb')
    process = subprocess.Popen(common + ['--env', inventory['environment_id']], stdout=log, stderr=log)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for attempt in range(100):
            try:
                with opener.open('http://127.0.0.1:18088/api/v1/usage/health', timeout=2) as response:
                    health = json.load(response)
                break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError('API exited before becoming ready')
                time.sleep(0.1)
        else:
            raise RuntimeError('API readiness timeout')
        paths = {'health': 'health', 'summary': 'summary', 'by-asset.asset': 'by-asset?group=asset',
                 'by-asset.server': 'by-asset?group=server', 'by-asset.pattern': 'by-asset?group=pattern',
                 'records': 'records?limit=500', 'timeseries': 'timeseries', 'brake-events': 'brake-events?limit=500'}
        for name, path in paths.items():
            with opener.open('http://127.0.0.1:18088/api/v1/usage/' + path, timeout=10) as response:
                responses[name] = json.load(response)
            dump(name + '.json', responses[name])
            checks.append({'name': name + '_http_json', 'pass': True})
        checks += [
            {'name': 'health_snapshot_matches', 'pass': responses['health']['inventory_snapshot_id'] == inventory['snapshot_id']},
            {'name': 'summary_snapshot_matches', 'pass': responses['summary']['data_quality']['inventory_snapshot_id'] == inventory['snapshot_id']},
            {'name': 'records_count_matches', 'pass': responses['records']['total'] == responses['summary']['calls'] == 16},
            {'name': 'pc_calls_remain_unmatched', 'pass': responses['summary']['by_mapping'] == {'matched': 0, 'ambiguous': 0, 'unmatched': 16}},
            {'name': 'unmatched_records_have_no_asset', 'pass': all(r['asset_id'] is None for r in responses['records']['items'])},
        ]
        dump('checks.json', checks)
        summary = {'source_commit': '6e4cf5c0cf7116821d48fd3231c7cb2a6595a4ae',
                   'inventory_snapshot_id': inventory['snapshot_id'],
                   'input_kind': 'saved PC traces; not testbed calls',
                   'reference_pricing': False,
                   'passed': sum(c['pass'] for c in checks), 'failed': sum(not c['pass'] for c in checks),
                   'calls': responses['summary']['calls'], 'mapping': responses['summary']['by_mapping'],
                   'limitations': ['No testbed telemetry available; successful tool-to-asset mapping remains unverified.',
                                   'No browser UI, VM, live reload, or token-count plugin execution.']}
        dump('execution-summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False))
        if summary['failed']:
            raise RuntimeError('Validation check failed')
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()


if __name__ == '__main__':
    main()

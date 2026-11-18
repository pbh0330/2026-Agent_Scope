"""Re-run the pinned saved-input pipeline and independently check its outputs.

Run from workspace root with the existing QA Python environment. No VM/network IO.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'QA/evidence/RUN-20261117-SAVED-01'
PARTS = ROOT / '.parts-snapshots-20261116'
PROFILES = ['P0', 'P1', 'P2', 'S1', 'S1-T5', 'S2', 'S3', 'S4', 'S5-T1', 'S5-T2', 'S5-T3']
TIME_FIELDS = {'generated_at', 'started_at', 'finished_at', 'observed_at', 'collected_at',
               'evaluated_at', 'detected_at', 'snapshot_id', 'report_id'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items() if k not in TIME_FIELDS}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    if isinstance(value, str):
        return re.sub(r'2026\d{4}T\d{6}Z', '<RUN_TIME>', value)
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    executions = []
    for n in ([] if '--checks-only' in sys.argv else range(1, 4)):
        dest = OUT / f'run-{n}'
        cmd = [sys.executable, str(PARTS / 'dashboard/dashboard/pipeline/build_data.py'),
               '--scanner', str(ROOT / '.pr5-current/asset-scanner'),
               '--testbed', str(PARTS / 'testbed-vm/testbed'),
               '--scenarios', str(PARTS / 'scenario/docs/threat-scenarios'),
               '--out', str(dest / 'data'), '--work', str(dest / 'work')]
        start = time.perf_counter()
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding='utf-8',
                              env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'})
        # Local logs are not publication artifacts.
        (OUT / f'run-{n}.local.log').write_text(proc.stdout + proc.stderr, encoding='utf-8')
        executions.append({'run': n, 'exit_code': proc.returncode,
                           'elapsed_seconds': round(time.perf_counter() - start, 3)})
        if proc.returncode:
            dump(OUT / 'execution.json', executions)
            raise SystemExit(f'Pipeline failed in run {n}; see local log')
        print(f'run {n}: exit 0', flush=True)
    if executions:
        dump(OUT / 'execution.json', {'runs': executions, 'excluded_time_fields': sorted(TIME_FIELDS),
                                 'scope': 'saved inputs only; no VM recollection, browser or usage API',
                                 'pinned_versions': load(PARTS / 'versions.json'),
                                 'scanner_commit': '0b2ff6bb2dd2f87e95550223008050e960cd07af',
                                 'testbed_vm_commit': '444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb'})
    checks = []

    def check(profile, name, passed, details=None):
        checks.append({'profile': profile, 'check': name, 'pass': bool(passed), 'details': details})

    for profile in PROFILES:
        snapshots = [load(OUT / f'run-{n}/data/snapshots/{profile}/snapshot.json') for n in range(1, 4)]
        detections = [load(OUT / f'run-{n}/data/snapshots/{profile}/detections.json') for n in range(1, 4)]
        s, d = snapshots[0], detections[0]
        assets = {a['asset_id']: a for a in s['assets']}
        keyed = {a.get('project', {}).get('canonical_key'): a for a in s['assets']}
        rels = {r['relation_id']: r for r in s['relations']}
        evidence = {e['evidence_id'] for e in s['evidence']}
        collections = {c['collection_id'] for c in s['collection_results']}
        for name, values in [('snapshot', snapshots), ('detections', detections)]:
            hashes = [digest(normalized(v)) for v in values]
            check(profile, f'three_run_{name}_equality', len(set(hashes)) == 1, hashes)
        check(profile, 'unique_asset_ids', len(assets) == len(s['assets']))
        check(profile, 'unique_canonical_keys', len(keyed) == len(assets))
        check(profile, 'unique_relation_ids', len(rels) == len(s['relations']))
        duplicate_tools = {}
        for a in s['assets']:
            if a['asset_type'] == 'tool':
                duplicate_tools.setdefault(a['name'], []).append(a)
        groups = [rows for rows in duplicate_tools.values() if len(rows) > 1]
        check(profile, 'same_name_tools_keep_distinct_ids_and_owners',
              all(len({a['asset_id'] for a in rows}) == len(rows)
                  and len({a.get('owner_ref') for a in rows}) == len(rows) for rows in groups),
              {'duplicate_names': [rows[0]['name'] for rows in groups]})
        bad = []

        def refs(obj, path=''):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    loc = f'{path}/{k}'
                    if k == 'evidence_refs' and isinstance(v, list):
                        bad.extend({'path': loc, 'missing': x} for x in v if x not in evidence)
                    if k == 'collection_ref' and v and v not in collections:
                        bad.append({'path': loc, 'missing': v})
                    refs(v, loc)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    refs(v, f'{path}/{i}')
        refs(s)
        refs(d)
        check(profile, 'evidence_and_collection_references', not bad, bad)
        bad = []
        for r in s['relations']:
            source, target = r.get('source_asset_ref'), r.get('target', {})
            if source not in assets or (target.get('kind') == 'asset' and target.get('asset_ref') not in assets):
                bad.append(r['relation_id'])
        for a in s['assets']:
            owner = a.get('owner_ref')
            if owner and owner not in assets:
                bad.append(a['asset_id'])
        check(profile, 'asset_and_relation_references', not bad, bad)
        bad = []
        for group in ['alerts', 'evaluations']:
            for row in d.get(group, []):
                bad.extend(x for x in row.get('asset_ids', []) if x not in assets)
                bad.extend(x for x in row.get('relation_ids', []) if x not in rels)
        check(profile, 'detection_target_references', not bad, bad)
        runtime = [(a['asset_id'], st['state']) for a in s['assets']
                   for st in a.get('project', {}).get('state_assessments', [])
                   if st['state'] in ('CALLABLE', 'USED') and st.get('value') is not None]
        check(profile, 'no_static_runtime_assertion', not runtime, runtime)
        gt = load(ROOT / f'QA/evidence/GT-20261116-444f558/full/{profile}.json')
        mapping = {a['asset_key']: keyed.get(a['asset_key'], {}).get('asset_id') for a in gt['assets']}
        check(profile, 'source_asset_mapping', all(mapping.values()), {'source': len(mapping), 'matched': sum(bool(v) for v in mapping.values())})
        bad = []
        exposure_count = 0
        for a in gt['assets']:
            actual = keyed.get(a['asset_key'])
            attrs = a.get('attributes', {})
            if actual and 'exposed_to_agent' in attrs:
                states = [st for st in actual.get('project', {}).get('state_assessments', []) if st['state'] == 'EXPOSED']
                exposure_count += 1
                if len(states) != 1 or states[0].get('value') is not attrs['exposed_to_agent']:
                    bad.append(a['asset_key'])
        stale_keys = {'inventory-remote/tool/inventory_list_hosts', 'inventory-remote/tool/inventory_get_host'}
        if profile in {'S1-T5', 'S5-T1', 'S5-T2', 'S5-T3'} and set(bad) == stale_keys:
            checks.append({'profile': profile, 'check': 'source_exposure_stale_difference', 'pass': None,
                           'details': {'compared': exposure_count, 'source_true_output_null': bad,
                                       'reason': 'changed server: P2 advertised capture reused, exposure not remeasured'}})
            nulls = [st.get('value') is None for key in stale_keys
                     for st in keyed[key]['project']['state_assessments'] if st['state'] == 'EXPOSED']
            check(profile, 'stale_exposure_is_unknown', len(nulls) == 2 and all(nulls))
        else:
            check(profile, 'source_exposure_true_false_null', not bad, {'compared': exposure_count, 'differences': bad})
        advertised = [r for r in gt['relations'] if r['type'] == 'ADVERTISES']
        missing = []
        for r in advertised:
            src, dst = mapping.get(r['source']), mapping.get(r['target'])
            matches = [x for x in s['relations'] if x['relation_type'] == 'ADVERTISES'
                       and x['source_asset_ref'] == src and x['target'].get('asset_ref') == dst]
            if len(matches) != 1 or assets.get(dst, {}).get('owner_ref') != src:
                missing.append({'source': r['source'], 'target': r['target']})
        check(profile, 'source_advertises_and_owner', not missing, {'compared': len(advertised), 'differences': missing})
        for expected in gt.get('expected_alerts', []):
            matches = [a for a in d['alerts'] if a['rule_id'] == expected['condition_id']
                       and mapping.get(expected['target']) in a.get('asset_ids', [])]
            if expected.get('required', True):
                check(profile, 'required_alert:' + expected['condition_id'] + ':' + expected['target'], bool(matches),
                      {'alert_ids': [a['alert_id'] for a in matches],
                       'expected_severity': expected.get('severity'), 'actual_severities': [a['severity'] for a in matches]})
            else:
                checks.append({'profile': profile, 'check': 'optional_alert:' + expected['condition_id'] + ':' + expected['target'],
                               'pass': None, 'details': {'present': bool(matches), 'excluded_from_required_denominator': True}})
        for expected in gt.get('expected_unknown', []):
            target = mapping.get(expected['target'])
            evaluations = [e for e in d['evaluations'] if e['rule_id'] == expected['condition_id'] and target in e.get('asset_ids', [])]
            alerts = [a['alert_id'] for a in d['alerts'] if a['scenario_id'] == expected['scenario'] and target in a.get('asset_ids', [])]
            check(profile, 'unknown:' + expected['condition_id'], bool(evaluations) and all(e['result'] == 'unknown' for e in evaluations) and not alerts,
                  {'evaluation_ids': [e['evaluation_id'] for e in evaluations], 'forbidden_alerts': alerts})
        no_alert = gt.get('expected_no_alert', {})
        scenarios = no_alert.get('scenario', [])
        if isinstance(scenarios, str):
            scenarios = [scenarios]
        for key in no_alert.get('targets', []):
            # A no-alert scope can also contain a specifically expected positive rule
            # (e.g. S5-T2 C2). Only that exact target/rule is exempted.
            allowed = {e['condition_id'] for e in gt.get('expected_alerts', []) if e['target'] == key}
            def expected_positive(a):
                return any(e['condition_id'] == a['rule_id'] and mapping.get(e['target']) in a.get('asset_ids', [])
                           for e in gt.get('expected_alerts', []))
            forbidden = [a['alert_id'] for a in d['alerts'] if a['scenario_id'] in scenarios
                         and mapping.get(key) in a.get('asset_ids', []) and not expected_positive(a)]
            check(profile, 'no_forbidden_alert:' + key, bool(mapping.get(key)) and not forbidden,
                  {'scenarios': scenarios, 'allowed_rules': sorted(allowed), 'forbidden_alerts': forbidden,
                   'scope': 'exclude exact expected positive rule/primary target matches; server can be a related asset'})
    dump(OUT / 'checks.json', checks)
    summary = {'checks': len(checks), 'passed': sum(c['pass'] is True for c in checks),
               'failed': sum(c['pass'] is False for c in checks), 'non_verdict_observations': sum(c['pass'] is None for c in checks)}
    dump(OUT / 'summary.json', summary)
    print(json.dumps(summary))
    if summary['failed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

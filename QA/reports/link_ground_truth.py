"""Rebuild the pinned ground-truth index and link saved integration evidence."""
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.parts-snapshots-20261116/testbed-vm/testbed/ground-truth'
DATA = ROOT / 'QA/evidence/RUN-20261116-INTEGRATION-01/data'
OUT = ROOT / 'QA/evidence/GT-20261116-444f558'
COMMIT = '444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb'
PROFILES = ['P0', 'P1', 'P2', 'S1', 'S1-T5', 'S2', 'S3', 'S4', 'S5-T1', 'S5-T2', 'S5-T3']

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def relkey(r):
    return r['type'], r['source'], r['target']

def full(d, base):
    if 'assets' in d:
        return copy.deepcopy(d)
    assets = {a['asset_key']: copy.deepcopy(a) for a in base['assets']}
    for k in d['removed_assets']:
        del assets[k]
    for a in d['changed_assets']:
        attrs = assets[a['asset_key']].setdefault('attributes', {})
        for key, change in a['changes'].items():
            assert attrs.get(key) == change['before'], (d['profile'], a['asset_key'], key)
            attrs[key] = copy.deepcopy(change['after'])
    for a in d['added_assets']:
        assert a['asset_key'] not in assets
        assets[a['asset_key']] = copy.deepcopy(a)
    removed = {relkey(r) for r in d['removed_relations']}
    assert removed <= {relkey(r) for r in base['relations']}
    relations = [copy.deepcopy(r) for r in base['relations'] if relkey(r) not in removed]
    relations.extend(copy.deepcopy(d['added_relations']))
    return dict(d, assets=list(assets.values()), relations=relations, materialized_from='P2.json')

def main():
    sources = {p: read(SOURCE / (p + '.json')) for p in PROFILES}
    manifest = read(DATA / 'manifest.json')
    entries = {e['key']: e for e in manifest['snapshots']}
    rows = []
    for p, d in sources.items():
        f = full(d, sources['P2'])
        ids = [a['asset_key'] for a in f['assets']]
        counts = dict(Counter(a['asset_type'] for a in f['assets']))
        assert len(ids) == len(set(ids))
        assert counts == d['summary']['asset_counts']
        assert len(f['relations']) == d['summary']['relation_count']
        assert all(r['source'] in ids and r['target'] in ids for r in f['relations'])
        raw = (SOURCE / (p + '.json')).read_bytes()
        write(OUT / 'source' / (p + '.json'), d)
        write(OUT / 'full' / (p + '.json'), f)
        entry = entries[p]
        snapshot = read(DATA / entry['files']['snapshot'])
        bykey = {}
        for a in snapshot['assets']:
            k = a.get('project', {}).get('canonical_key')
            if k:
                bykey.setdefault(k, []).append(a['asset_id'])
        mappings = [{'asset_key': k, 'asset_ids': bykey.get(k, []),
                     'status': 'matched' if len(bykey.get(k, [])) == 1 else
                     'ambiguous' if bykey.get(k) else 'unmatched'} for k in ids]
        expected_path = entry['files'].get('expected')
        expected = read(DATA / expected_path) if expected_path else {}
        condition_links = []
        for a in d.get('expected_alerts', []) + d.get('expected_unknown', []):
            matches = [c for c in expected.get('checks', []) if
                       c.get('condition_id') == a['condition_id'] and c.get('target') == a['target']
                       and c.get('scenario_id') == a['scenario']]
            condition_links.append({'condition_id': a['condition_id'], 'target': a['target'],
                                    'scenario_id': a['scenario'], 'required': a.get('required'),
                                    'checks': matches})
        link = {'profile': p, 'snapshot_id': snapshot['snapshot_id'], 'id_mappings': mappings,
                'additional_output_assets': [a['asset_id'] for a in snapshot['assets']
                                             if a.get('project', {}).get('canonical_key') not in ids],
                'condition_links': condition_links,
                'saved_expected_checks': expected.get('checks', [])}
        write(OUT / 'links' / (p + '.json'), link)
        rows.append({'profile': p, 'source_sha256': hashlib.sha256(raw).hexdigest(),
                     'source_assets': len(ids), 'source_relations': len(f['relations']),
                     'asset_counts': counts,
                     'required_alerts': sum(a['required'] for a in d.get('expected_alerts', [])),
                     'optional_alerts': sum(not a['required'] for a in d.get('expected_alerts', [])),
                     'unknown_conditions': len(d.get('expected_unknown', [])),
                     'output_assets': len(snapshot['assets']), 'output_relations': len(snapshot['relations']),
                     'mapping_counts': dict(Counter(m['status'] for m in mappings)),
                     'saved_expected_counts': dict(Counter(c['result'] for c in expected.get('checks', []))),
                     'snapshot_file': entry['files']['snapshot'], 'expected_file': expected_path,
                     'unlinked_conditions': sum(not c['checks'] for c in condition_links)})
    write(OUT / 'index.json', {'ground_truth_id': 'GT-20261116-444f558', 'source_commit': COMMIT,
          'scope': 'testbed-added assets; stock excluded; source counts fixed to commit',
          'execution_id': 'RUN-20261116-INTEGRATION-01', 'profiles': rows,
          'limitations': ['canonical-key mappings only; not full attribute/relation equivalence',
                         'saved evidence only; no live VM query; no final 0.7 contract acceptance']})
    print(json.dumps(rows, ensure_ascii=True))

if __name__ == '__main__':
    main()

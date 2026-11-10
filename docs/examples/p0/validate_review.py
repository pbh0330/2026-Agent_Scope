"""Checks for the P0 review fixture; not a complete JSON Schema validator."""
import json
from collections import Counter
from pathlib import Path


def check(condition, message):
    if not condition:
        raise ValueError(message)


def validate():
    data = json.loads(Path(__file__).with_name('P0.inventory.review.json').read_text(encoding='utf-8'))
    for key in ('schema_version', 'snapshot_id', 'environment_id', 'profile_id',
                'context', 'basis', 'environment', 'producer', 'generated_at',
                'scan', 'assets', 'relations', 'evidence', 'collection_results'):
        check(key in data, f'Missing field: {key}')
    groups = [('assets', 'asset_id'), ('relations', 'relation_id'),
              ('evidence', 'evidence_id'), ('collection_results', 'collection_id')]
    indexes = {}
    for group, field in groups:
        rows = data[group]
        ids = [row[field] for row in rows]
        check(len(ids) == len(set(ids)), f'Duplicate IDs in {group}')
        indexes[group] = dict(zip(ids, rows))
    assets, evidence = indexes['assets'], indexes['evidence']
    check(data['scan']['status'] == 'partial', 'Review must retain coverage gaps')
    check(assets[data['context']['gateway_ref']]['asset_type'] == 'gateway', 'Gateway context')
    check(data['scan']['started_at'] <= data['scan']['finished_at'] <= data['generated_at'], 'Time order')
    for row in data['assets'] + data['relations']:
        check(bool(row['evidence_refs']), 'Missing evidence')
        check(all(ref in evidence for ref in row['evidence_refs']), 'Dangling evidence')
    for asset in data['assets']:
        check(asset['context']['profile_id'] == data['profile_id'], 'Profile mismatch')
        if 'owner_ref' in asset:
            check(asset['owner_ref'] in assets, 'Dangling owner')
        for state in asset['project']['state_assessments']:
            check(all(ref in evidence for ref in state['evidence_refs']), 'State evidence')
            check(state['value'] is not None or bool(state.get('reason')), 'Unknown reason')
        if asset['asset_type'] == 'tool':
            check(assets[asset['owner_ref']]['asset_type'] == 'mcp_server', 'Tool owner type')
            check(asset['mcp']['protocol_version'] == '2025-11-25', 'Preserve negotiated version')
            check(isinstance(asset['mcp']['definition']['inputSchema'], dict), 'Tool definition')
        if asset['asset_type'] == 'permission_auth':
            check(all(ref in assets for ref in asset['project']['permission_auth']['target_refs']), 'Policy targets')
    expected_types = {'DECLARES': ('gateway', 'mcp_server'),
                      'PAIRED_WITH': ('gateway', 'node'),
                      'ADVERTISES': ('mcp_server', 'tool')}
    for relation in data['relations']:
        source = assets[relation['source_asset_ref']]
        target = assets[relation['target']['asset_ref']]
        check((source['asset_type'], target['asset_type']) == expected_types[relation['relation_type']], 'Relation direction/type')
    for item in data['evidence']:
        check(item['collection_ref'] in indexes['collection_results'], 'Evidence collection')
    for item in data['collection_results']:
        check(item['target_ref'] is None or item['target_ref'] in assets, 'Collection target')
    counts = Counter(asset['asset_type'] for asset in data['assets'])
    check(counts == {'gateway': 1, 'node': 1, 'mcp_server': 1, 'tool': 14, 'permission_auth': 1}, 'Asset counts')
    check(Counter(r['relation_type'] for r in data['relations']) == {'PAIRED_WITH': 1, 'DECLARES': 1, 'ADVERTISES': 14}, 'Relation counts')
    print('PASS: 18 assets, 16 relations; IDs, references, ownership and fixture invariants')


if __name__ == '__main__':
    validate()

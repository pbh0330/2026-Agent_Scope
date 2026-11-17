"""공통 스키마 0.7.0-draft(스키마 문서 v0.7.7의 2~7·13절) 기준으로 public/data 출력을 점검한다.

사용: python pipeline/check_schema.py public/data
문서의 필수 필드·자료형·열거값·참조 규칙을 옮긴 검사이며, 공식 JSON Schema가 확정되면 그것으로 바꾼다.
scope 후보 목록에 없는 수집 작업 이름은 오류가 아니라 '협의 필요'로 따로 센다.
"""
import json, sys, glob, os, re, collections
root = sys.argv[1]
TYPES = {'gateway','node','mcp_server','tool','resource_prompt','skill','plugin','permission_auth'}
STATES = {'DECLARED','DISCOVERED','EXPOSED','POTENTIALLY_CALLABLE','CALLABLE','USED'}
SUBJ = {'EXPOSED','POTENTIALLY_CALLABLE','CALLABLE','USED'}
RES = {'detected','not_detected','unknown','not_applicable','not_evaluated','error'}
SEV = {'info','low','medium','high','critical'}; CONF = {'high','medium','low'}
ISO = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)$')
errs = collections.Counter(); ex = {}; NOTE = collections.Counter()
def E(code, where): errs[code]+=1; ex.setdefault(code, where)
def req(o, keys, code, where):
    for k in keys:
        if k not in o: E(f'{code}.missing:{k}', where)
for d in sorted(glob.glob(os.path.join(root,'snapshots','*'))):
    key=os.path.basename(d)
    s=json.load(open(os.path.join(d,'snapshot.json')))
    req(s,['schema_version','snapshot_id','environment_id','profile_id','context','basis','environment','producer','generated_at','scan','assets','relations','evidence','collection_results'],'snap',key)
    if s.get('schema_version')!='0.7.0-draft': E('snap.version='+str(s.get('schema_version')),key)
    if s.get('basis',{}).get('mcp_spec_version')!='2026-07-28': E('snap.basis.mcp_spec_version',key)
    env=s.get('environment',{})
    for k in ('openclaw_version','openclaw_commit'):
        if k not in env: E('snap.environment.missing:'+k,key)
    if (env.get('openclaw_version') is None or env.get('openclaw_commit') is None) and not env.get('version_note'): E('snap.environment.version_note',key)
    sc=s.get('scan',{})
    if sc.get('status') not in ('success','partial','failed'): E('snap.scan.status='+str(sc.get('status')),key)
    for t in ('started_at','finished_at'):
        if not ISO.match(str(sc.get(t,''))): E('snap.scan.'+t,key)
    if not ISO.match(str(s.get('generated_at',''))): E('snap.generated_at',key)
    if sc.get('started_at') and sc.get('finished_at') and s.get('generated_at') and not (sc['started_at']<=sc['finished_at']<=s['generated_at']): E('snap.scan.order',key)
    ids={a['asset_id']:a for a in s['assets']}
    if len(ids)!=len(s['assets']): E('asset.dup_id',key)
    evids={e['evidence_id'] for e in s['evidence']}
    cols={c['collection_id'] for c in s['collection_results']}
    gw=s.get('context',{}).get('gateway_ref')
    if gw and ids.get(gw,{}).get('asset_type')!='gateway': E('snap.context.gateway_ref',key)
    for a in s['assets']:
        w=f"{key}:{a.get('asset_id')}:{a.get('asset_type')}"
        req(a,['asset_id','asset_type','name','context','evidence_refs','project'],'asset',w)
        t=a.get('asset_type')
        if t not in TYPES: E('asset.type',w)
        if t=='resource_prompt' and a.get('asset_subtype') not in ('resource','resource_template','prompt'): E('asset.subtype.rp='+str(a.get('asset_subtype')),w)
        if t=='permission_auth' and a.get('asset_subtype') not in ('permission','authentication'): E('asset.subtype.pa='+str(a.get('asset_subtype')),w)
        if t in ('tool','resource_prompt'):
            o=a.get('owner_ref')
            if ids.get(o,{}).get('asset_type')!='mcp_server': E('asset.owner_ref.child',w)
            if not (a.get('mcp') or {}).get('definition'): E('asset.mcp.definition',w)
        if t=='mcp_server' and a.get('owner_ref') and ids.get(a['owner_ref'],{}).get('asset_type') not in ('gateway','node','plugin'): E('asset.owner_ref.server',w)
        if a.get('mcp') is not None:
            m=a['mcp']
            if 'protocol_version' not in m: E('asset.mcp.protocol_version.missing',w)
            elif m['protocol_version'] is None and not m.get('version_note'): E('asset.mcp.version_note',w)
            dfn=m.get('definition') or {}
            if t=='tool' and dfn and ('name' not in dfn or 'inputSchema' not in dfn): E('asset.mcp.tool.official',w)
        ctx=a.get('context',{})
        if ctx.get('profile_id')!=s.get('profile_id'): E('asset.context.profile_id',w)
        if ctx.get('gateway_ref') and ids.get(ctx['gateway_ref'],{}).get('asset_type')!='gateway': E('asset.context.gateway_ref',w)
        if not a.get('evidence_refs'): E('asset.evidence_refs.empty',w)
        for r in a.get('evidence_refs',[]):
            if r not in evids: E('asset.evidence_refs.dangling',w)
        p=a.get('product')
        if p is not None:
            for k in ('name','source_ref','config_path'):
                if k not in p: E('asset.product.missing:'+k,w)
            if p.get('name')!='openclaw': E('asset.product.name='+str(p.get('name')),w)
        sa=(a.get('project') or {}).get('state_assessments')
        if sa is None: E('asset.project.state_assessments.missing',w); continue
        for x in sa:
            if x.get('state') not in STATES: E('state.enum',w)
            v=x.get('value','__')
            if v not in (True,False,None): E('state.value',w)
            if v in (True,False) and not x.get('evidence_refs'): E('state.evidence_refs',w)
            if v is None and not x.get('reason'): E('state.reason',w)
            if x.get('state') in SUBJ and v in (True,False) and not x.get('subject_ref'): E('state.subject_ref:'+x['state'],w)
            if x.get('state') in ('CALLABLE','USED') and v in (True,False): E('state.static_callable',w)
            if x.get('policy_ref') and ids.get(x['policy_ref'],{}).get('asset_type')!='permission_auth': E('state.policy_ref',w)
            for r in x.get('evidence_refs',[]) or []:
                if r not in evids: E('state.evidence_dangling',w)
    rids=set()
    for r in s['relations']:
        w=f"{key}:{r.get('relation_id')}"
        req(r,['relation_id','relation_type','source_asset_ref','target','evidence_refs','confidence'],'rel',w)
        if r['relation_id'] in rids: E('rel.dup',w)
        rids.add(r['relation_id'])
        if r.get('source_asset_ref') not in ids: E('rel.source',w)
        tg=r.get('target',{})
        if tg.get('kind')=='asset' and tg.get('asset_ref') not in ids: E('rel.target',w)
        if r.get('confidence') not in ('confirmed','high','medium','low'): E('rel.confidence',w)
        if not r.get('evidence_refs'): E('rel.evidence.empty',w)
        for e in r.get('evidence_refs',[]):
            if e not in evids: E('rel.evidence.dangling',w)
    seen=set()
    for e in s['evidence']:
        w=f"{key}:{e.get('evidence_id')}"
        req(e,['evidence_id','evidence_type','source_ref','observed_at','collection_ref','redaction_status'],'ev',w)
        if e['evidence_id'] in seen: E('ev.dup',w)
        seen.add(e['evidence_id'])
        if e.get('evidence_type') not in ('config','manifest','protocol','schema','description','manual'): E('ev.type='+str(e.get('evidence_type')),w)
        if e.get('redaction_status') not in ('not_needed','redacted'): E('ev.redaction='+str(e.get('redaction_status')),w)
        if e.get('redaction_status')=='redacted' and not e.get('redacted_fields'): E('ev.redacted_fields',w)
        if e.get('collection_ref') not in cols: E('ev.collection_ref.dangling',w)
        if not ISO.match(str(e.get('observed_at',''))): E('ev.observed_at',w)
    for c in s['collection_results']:
        w=f"{key}:{c.get('collection_id')}"
        req(c,['collection_id','source_ref','scope','collected_at','target_ref','mode','status'],'col',w)
        if c.get('mode') not in ('local_file','online_catalog','imported_catalog'): E('col.mode='+str(c.get('mode')),w)
        if c.get('status') not in ('success','partial','failed','not_attempted'): E('col.status='+str(c.get('status')),w)
        if c.get('scope') not in ('gateway_config','node_config','skill_files','plugin_manifest','server_discovery','tools_list','resources_list','prompts_list','resource_templates_list'): NOTE['col.scope(후보 목록 밖)='+str(c.get('scope'))]+=1
        if c.get('target_ref') is not None and c['target_ref'] not in ids: E('col.target_ref.dangling',w)
        if c.get('target_ref') is None and not c.get('reason'): E('col.target_null.reason',w)
        if c.get('status')!='success' and not c.get('reason'): E('col.reason',w)
        if c.get('scope') in ('server_discovery','tools_list','resources_list','prompts_list','resource_templates_list'):
            if 'protocol_version' not in c: E('col.protocol_version',w)
            if 'auth_context_ref' not in c: E('col.auth_context_ref',w)
    # 상위 scan.status 일관성
    st=[c.get('status') for c in s['collection_results']]
    exp='success' if all(x=='success' for x in st) else ('failed' if not any(x in('success','partial') for x in st) else 'partial')
    if st and sc.get('status')!=exp: E(f'snap.scan.status_rollup({sc.get("status")}!={exp})',key)
    # detections
    dp=os.path.join(d,'detections.json')
    if os.path.exists(dp):
        r=json.load(open(dp))
        req(r,['schema_version','report_id','environment_id','profile_id','snapshot_id','generated_at','producer','ruleset','evaluations','alerts'],'det',key)
        if r.get('schema_version')!='0.7.0-draft': E('det.version',key)
        for k in ('environment_id','profile_id','snapshot_id'):
            if r.get(k)!=s.get(k): E('det.match:'+k,key)
        evs={}
        for v in r['evaluations']:
            w=f"{key}:{v.get('evaluation_id')}"
            req(v,['evaluation_id','scenario_id','rule_id','rule_version','asset_ids','relation_ids','evidence_refs','policy_refs','result','reason','evaluated_at'],'eval',w)
            if v['evaluation_id'] in evs: E('eval.dup',w)
            evs[v['evaluation_id']]=v
            if v.get('result') not in RES: E('eval.result',w)
            if v.get('result') in ('detected','not_detected') and not v.get('evidence_refs'): E('eval.evidence_empty:'+v['rule_id'],w)
            for x in v.get('asset_ids',[]):
                if x not in ids: E('eval.asset_dangling',w)
            for x in v.get('relation_ids',[]):
                if x not in rids: E('eval.rel_dangling',w)
            for x in v.get('evidence_refs',[]):
                if x not in evids: E('eval.ev_dangling',w)
            for p in v.get('policy_refs',[]) or []:
                if not isinstance(p,dict) or not all(k in p for k in ('id','version','source_ref')): E('eval.policy_refs.shape',w)
        ak=set()
        for a in r['alerts']:
            w=f"{key}:{a.get('alert_id')}"
            req(a,['alert_id','evaluation_id','finding_key','scenario_id','rule_id','rule_version','severity','confidence','message','asset_ids','relation_ids','evidence_refs','detected_at'],'alert',w)
            if a['alert_id'] in ak: E('alert.dup',w)
            ak.add(a['alert_id'])
            v=evs.get(a.get('evaluation_id'))
            if not v: E('alert.evaluation_dangling',w)
            elif v.get('result')!='detected' or v.get('rule_id')!=a.get('rule_id'): E('alert.evaluation_mismatch',w)
            if a.get('severity') not in SEV: E('alert.severity='+str(a.get('severity')),w)
            if a.get('confidence') not in CONF: E('alert.confidence',w)
            if not a.get('asset_ids') or not a.get('evidence_refs'): E('alert.refs_empty',w)
for k,n in sorted(errs.items()): print(f'오류 {n:5d}  {k}   예: {ex[k]}')
for k,n in sorted(NOTE.items()): print(f'협의 {n:5d}  {k}')
print('오류 합계', sum(errs.values()))
sys.exit(1 if errs else 0)

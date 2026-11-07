"""자산·관계 ID 생성 — asset-id-rules-proposal의 후보 B(Canonical Key + Hash).

canonical key는 테스트베드 정답 목록의 asset_key 형식을 그대로 쓴다.
  - 호스트 소속:  <host>/<type>/<name>        예) tb-gw/mcp_server/fs-workspace
  - 서버 소속:    <server>/<type>/<name|uri>  예) fs-workspace/tool/read_file
ID = <접두사>_<sha256(environment_id + "\\n" + canonical_key) 앞 16자리>

수집 시각·제품 버전은 ID에 넣지 않는다(스키마 3절). 같은 환경에서 다시 수집해도 ID가 유지된다.
최종 규칙은 팀 합의 후 이 파일만 바꾸면 된다.
"""

import hashlib

PREFIX = {
    "gateway": "gw",
    "node": "node",
    "mcp_server": "srv",
    "tool": "tool",
    "resource_prompt": "rp",
    "skill": "skill",
    "plugin": "plg",
    "permission_auth": "pa",
}


def digest(*parts: str, length: int = 16) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:length]


def asset_id(environment_id: str, asset_type: str, canonical_key: str) -> str:
    return f"{PREFIX[asset_type]}_{digest(environment_id, canonical_key)}"


def relation_id(environment_id: str, relation_type: str, source: str, target: str) -> str:
    return f"rel_{digest(environment_id, relation_type, source, target)}"

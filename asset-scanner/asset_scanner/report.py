"""수집 결과를 스캐너 내부 협의용 초안 JSON으로 정리한다.

이 형식은 팀 공통 스키마(InventorySnapshot 등)가 아니다. 공통 형식이 합의되면
원천 필드(`declared`, `declaration_path`, `source_path`)를 그대로 옮겨 변환하는 것을 전제로 한다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import __version__

FORMAT_NAME = "agent-scope.scanner.openclaw-mcp-config"
FORMAT_VERSION = "0.1.0-draft"

# 설정 읽기만으로는 확인할 수 없어 이번 단계에서 채우지 않는 항목.
NOT_VERIFIED = [
    "connection",          # 실제 연결·기동 여부
    "tools",               # 도구 목록 (tools/list)
    "resources_prompts",
    "capabilities",
    "protocol_version",
    "exposure",            # Agent 노출 여부
    "callability",         # 호출 가능 여부
]


def build_report(collected: dict) -> dict:
    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "format_status": (
            "스캐너 내부 협의용 초안입니다. 팀 공통 스키마가 아니며, 필드명과 구조는 협의 후 변경될 수 있습니다. "
            "전역 자산 ID는 정하지 않았으며 registration_key와 declaration_path로 항목을 구분합니다."
        ),
        "producer": {"name": "agent-scope-asset-scanner", "version": __version__},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": {
            "source_path": collected["source_path"],
            "source_path_redacted": collected["source_path_redacted"],
            "source_kind": "openclaw_config_file",
            "evidence_type": "config",
            "registry_path": "mcp.servers",
        },
        "scope": {
            "method": "설정 파일 정적 읽기",
            "values_resolved": False,
            "not_verified": NOT_VERIFIED,
            "note": "servers[]는 설정에 선언된 사실만 담습니다. 연결·도구·노출·호출 가능 상태는 확인하지 않았습니다.",
        },
        "collection": collected["collection"],
        "servers": collected["servers"],
    }

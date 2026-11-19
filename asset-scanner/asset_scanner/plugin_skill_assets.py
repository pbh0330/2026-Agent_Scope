"""OpenClaw Plugin·Skill 자체 정보를 명시적으로 지정한 파일에서 수집한다 (자산 수집 확대 ①, 내부 개발용 초안).

    python -m asset_scanner.plugin_skill_assets [--plugin-dir DIR]... [--skills-dir DIR]... \
        [--config FILE] [--plugins-list-json FILE] [--skills-list-json FILE] --output OUT

읽기 전용이다. 플러그인 코드를 import·실행하지 않고, 서버에 접속하지 않으며, 설치·활성화·`openclaw` 실행을 하지 않는다.
입력은 모두 호출자가 지정한 경로뿐이고 홈 디렉터리 등을 자동 탐색하지 않는다.

값의 출처를 세 가지로 구분해 서로 다른 필드에 둔다.
- 정적 파일에서 관측한 값: `openclaw.plugin.json`, `package.json`, `SKILL.md` frontmatter (`observed_from`, `manifest`, `package`, `frontmatter`)
- 설정에 선언된 활성화 값: `--config`의 `plugins.*`·`skills.*` (`declared_activation`). 선언일 뿐 실제 로딩·활성 상태가 아니다.
- 저장된 명령 출력의 런타임 관측값: `openclaw plugins list --json`·`openclaw skills list --json` 출력 파일 (`runtime_observation`).
  실행 시점은 알 수 없고(파일 수정 시각만 기록) 출력 안의 값을 그대로 옮길 뿐 이 모듈이 확인한 것이 아니다.
- 직접 조회한 런타임 관측값: `--openclaw-bin`으로 지정한 실행 파일에 허용 목록의 읽기 조회(`openclaw_direct`)를 실행한 결과. 같은 파서를 거치며
  `observation.source_kind`가 `direct_query`이고 명령·설치 버전·조회 범위·관측 시각(`scanner_clock_at_query`)을 함께 기록한다. 값은 OpenClaw가 돌려준
  것이며 이 모듈이 확인한 것이 아니다. `skills list`는 기본 거부(Gateway RPC·장치 신원 생성 가능)이고 명시적 동의가 있어야 실행한다.

연결 규칙(보수적): 같은 `id`·이름만으로 합치지 않는다. 플러그인은 `id`와 루트 경로가 모두 맞을 때만, 스킬은 `SKILL.md` 경로가
같을 때만 런타임 관측과 연결한다. 맞지 않으면 각각 별개 항목으로 남기고 후보로만 표시한다.
근거 문서: docs/asset-collection.md (OpenClaw 2026.9.6 패키지 문서·코드).
종료 코드: 0 완전, 1 부분, 2 인자 오류, 3 실패(읽은 항목 없음), 4 저장 실패.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

import json5

from . import __version__
from .cli import _make_console_output_safe, _same_file
from .skill_frontmatter import parse_frontmatter_lines
from .collector import (CollectionFailure, _find_duplicate_keys, collect_plugin_manifest, dotted_path, parse_config,
                        read_config, _type_name)
from .openclaw_direct import (DirectResult, add_direct_arguments, config_from_args, run_queries, validate_config)
from .output import OutputError, normalize_for_output, write_json_atomic
from .redaction import REDACTED, Redactor, classify_secret_ref, looks_like_secret_value
from .tools_catalog import _sanitize, _safe_short, _text, _seg, _short

FORMAT_NAME = "agent-scope.scanner.openclaw-plugin-skill-assets"
FORMAT_VERSION = "0.1.0-draft"
MANIFEST_NAME = "openclaw.plugin.json"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_FRONTMATTER_BYTES = 64 * 1024
MAX_SKILLS_PER_DIR = 500
MAX_NAMES = 200
EXIT_BY_STATUS = {"complete": 0, "partial": 1, "failed": 3}
EXIT_OUTPUT_ERROR = 4

NOT_VERIFIED = [
    "plugin_code_loaded",        # 플러그인 코드를 import·실행하지 않았다
    "runtime_activation",        # 설정 선언·저장된 출력 외에는 실제 로딩·활성 상태를 모른다
    "install_provenance",        # 설치 기록의 신뢰성·현재 파일과의 일치는 검증하지 않음
    "tools_hooks_registered",    # 등록된 Tool·훅은 저장된 출력에 적힌 이름만 옮겼다
    "skill_eligibility",         # 의존 바이너리·환경변수 충족 여부를 확인하지 않았다
    "live_server_query",
    "team_testbed",
    "common_asset_id",           # 팀 공통 ID 미확정
]

_MANIFEST_STR = ("id", "name", "description", "version")
_MANIFEST_STR_LIST = ("requiresPlugins", "legacyPluginIds", "channels", "providers", "skills", "enabledByDefaultOnPlatforms")
_SKILL_FM_STR = ("name", "description", "homepage", "command-dispatch", "command-tool", "command-arg-mode")
_SKILL_FM_BOOL = ("user-invocable", "disable-model-invocation")


def _issue(severity: str, code: str, message: str, **where: Any) -> dict:
    item = {"severity": severity, "code": code, "message": message}
    item.update({k: v for k, v in where.items() if v is not None})
    return item


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_path(p: Path) -> tuple[str, bool]:
    """결과에 쓰는 경로. 토큰처럼 보이는 조각만 가린다."""
    try:
        parts = p.resolve().parts
    except OSError:
        parts = p.parts
    masked = [REDACTED if looks_like_secret_value(x) else x for x in parts]
    return str(Path(*masked)), masked != list(parts)


def _identity(raw: Any, shown: Any) -> dict:
    """원본 식별값 기록. 가려졌거나 바뀐 값은 원본 식별값이 아니다."""
    if raw is None:
        return {"original_value": None, "status": "missing"}
    if not isinstance(raw, str) or raw == "":
        return {"original_value": None, "status": "invalid_type"}
    if shown != raw:
        return {"original_value": None, "status": "withheld_by_redaction"}
    return {"original_value": raw, "status": "as_reported"}


def _read_text_limited(path: Path, limit: int) -> tuple[str | None, dict | None]:
    try:
        original = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(original.st_mode) or original.st_nlink > 1:
            return None, _issue("error", "file_not_found", "파일이 없거나 링크·비일반 파일입니다.")
        if path.stat().st_size > limit * 64:
            return None, _issue("error", "file_too_large", "파일이 너무 커서 읽지 않았습니다.")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(fd, "rb") as f:
            opened = os.fstat(f.fileno())
            if (original.st_dev, original.st_ino) != (opened.st_dev, opened.st_ino):
                return None, _issue("error", "read_failed", "읽는 중 파일이 바뀌었습니다.")
            data = f.read(limit)
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, _issue("error", "not_utf8", "UTF-8 텍스트가 아닙니다.")
    except OSError as exc:
        return None, _issue("error", "read_failed", f"파일을 읽지 못했습니다 ({type(exc).__name__}).")


# ---- SKILL.md frontmatter ------------------------------------------------------------

def parse_frontmatter_ex(text: str) -> tuple[dict | None, dict, str | None]:
    """`---`로 둘러싸인 frontmatter를 `skill_frontmatter`의 한도 있는 YAML 1.2 핵심 자료형 해석기로 읽는다.

    반환: (값, 부가 정보{unparsed, duplicate_keys, limit_hits, alias_keys}, 문제 코드). 임의 객체를 생성하지 않으며 별칭 확장에 한도를 둔다.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, {}, "frontmatter_missing"
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None, {}, "frontmatter_unterminated"
    res = parse_frontmatter_lines(lines[1:end])
    return res["value"], res, None


def parse_frontmatter(text: str) -> tuple[dict | None, list[str], str | None]:
    """기존 시그니처 유지: (값, 해석하지 못한 키, 문제 코드)."""
    value, extra, problem = parse_frontmatter_ex(text)
    return value, list(extra.get("unparsed", [])), problem


MAX_INSTALL_SPECS = 20
_INSTALL_KINDS = ("brew", "node", "go", "uv", "download")
_INSTALL_KNOWN = {"id", "kind", "formula", "bins", "label", "os", "url", "sha256", "archive", "extract", "stripComponents", "targetDir"}


_HEX64_RE = re.compile(r"[0-9a-fA-F]{64}")


def _sha256_state(v: Any) -> str:
    """`valid_format`(64자리 16진 문자열) | `empty` | `invalid_format`(문자열이지만 모양이 다름) | `null` | `invalid_type`(숫자·불리언·목록·객체)."""
    if v is None:
        return "null"
    if isinstance(v, str):
        return "empty" if v == "" else ("valid_format" if _HEX64_RE.fullmatch(v) else "invalid_format")
    return "invalid_type"


def _install_spec(spec: Any) -> dict:
    """`metadata.openclaw.install[]` 한 항목에서 문서(`docs/tools/skills.md` Installer specs)에 있는 키만 옮긴다.

    다운로드·설치·검증은 하지 않는다. `sha256` 값(산출물 다이제스트)은 저장하지 않고 선언 여부만 남기며 검증 결과를 만들지 않는다.
    """
    if not isinstance(spec, dict):
        return {"value_kind": "invalid_type", "type": _type_name(spec)}
    out: dict[str, Any] = {}
    for k in ("id", "kind", "formula", "label", "archive", "targetDir", "url"):
        if isinstance(spec.get(k), str):
            out[k] = spec[k]
    if "kind" in out:
        out["kind_documented"] = out["kind"] in _INSTALL_KINDS
    for k in ("bins", "os"):
        if isinstance(spec.get(k), list):
            out[k] = [x for x in spec[k] if isinstance(x, str)][:MAX_NAMES]
    if isinstance(spec.get("extract"), bool):
        out["extract"] = spec["extract"]
    sc = spec.get("stripComponents")
    if isinstance(sc, int) and not isinstance(sc, bool):
        out["stripComponents"] = sc
    if out.get("kind") == "download" or "sha256" in spec:
        # 선언 여부(키 존재)와 값의 유효성을 분리한다. 숫자·null·잘못된 형식도 "선언은 했다"로 기록하고 문제는 sha256_state로 남긴다.
        # 값은 저장하지 않으며 숫자를 문자열로 바꿔 유효한 해시로 인정하지 않는다(형식 유효성은 검증이 아니라 모양 검사다).
        out["sha256_declared"] = "sha256" in spec
        out["sha256_state"] = _sha256_state(spec["sha256"]) if "sha256" in spec else "absent"
    out["other_keys"] = sorted(_seg(k) for k in spec if k not in _INSTALL_KNOWN)
    return out


MAX_ORIGIN_BYTES = 64 * 1024


def _read_install_origin(skill_dir: Path, red: Redactor, issues: list[dict]) -> dict | None:
    """`<skill 폴더>/.clawhub/origin.json`(ClawHub 설치 기록)을 읽는다. 없으면 None(원천 미제공: 로컬·Git 설치 등).

    필드는 고정 패키지(2026.9.6)의 `normalizeClawHubSkillOrigin`이 요구하는 것만 해석한다. 기록된 값을 옮길 뿐 검증하지 않으며
    레지스트리에 접속하지 않는다.
    """
    f = skill_dir / ".clawhub" / "origin.json"
    try:
        if not f.is_file():
            return None
        if f.stat().st_size > MAX_ORIGIN_BYTES:
            raise ValueError("too_large")
        raw = json5.loads(f.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        raw = None
    base: dict[str, Any] = {"source": "clawhub_origin_json", "file": ".clawhub/origin.json", "verified_by_scanner": False, "verification": "not_performed",
                            "basis": "OpenClaw 2026.9.6 docs/tools/skills.md, normalizeClawHubSkillOrigin"}
    ok = (isinstance(raw, dict) and raw.get("version") == 1 and all(isinstance(raw.get(k), str) and raw.get(k) for k in ("registry", "slug", "installedVersion"))
          and isinstance(raw.get("installedAt"), (int, float)) and not isinstance(raw.get("installedAt"), bool))
    if not ok:
        issues.append(_issue("warning", "skill_origin_malformed", "설치 기록(.clawhub/origin.json)이 예상 형식(version 1, registry, slug, installedVersion, installedAt)이 아닙니다. 값을 읽지 않았습니다."))
        return {**base, "status": "malformed"}
    rec = {**base, "status": "recorded", "version": 1, "installed_at_ms": raw["installedAt"]}
    for src, dst in (("registry", "registry"), ("slug", "slug"), ("installedVersion", "installed_version"), ("sourceUrl", "source_url"),
                     ("ownerHandle", "owner_handle"), ("requestedReference", "requested_reference"), ("trustState", "trust_state")):
        if isinstance(raw.get(src), str):
            rec[dst] = _sanitize(raw[src], f"install_origin.{dst}", red)
    rec["unknown_keys"] = sorted(_seg(k) for k in raw if k not in {"version", "registry", "slug", "installedVersion", "installedAt", "sourceUrl", "ownerHandle", "requestedReference", "trustState"})
    return rec


def _skill_metadata(fm_meta: Any) -> dict:
    """`metadata.openclaw`의 문서화된 필드 일부만 고른다. 나머지는 키 이름만 남긴다."""
    if not isinstance(fm_meta, dict):
        return {}
    oc = fm_meta.get("openclaw")
    if not isinstance(oc, dict):
        return {"openclaw_present": False}
    out: dict[str, Any] = {"openclaw_present": True}
    for k in ("skillKey", "primaryEnv", "homepage", "emoji"):
        if isinstance(oc.get(k), str):
            out[k] = oc[k]
    if isinstance(oc.get("always"), bool):
        out["always"] = oc["always"]
    if isinstance(oc.get("os"), list):
        out["os"] = [x for x in oc["os"] if isinstance(x, str)][:20]
    req = oc.get("requires")
    if isinstance(req, dict):
        out["requires"] = {k: [x for x in req[k] if isinstance(x, str)][:MAX_NAMES]
                           for k in ("bins", "anyBins", "env", "config") if isinstance(req.get(k), list)}
    if isinstance(oc.get("install"), list):
        out["install_spec_count"] = len(oc["install"])
        out["install_specs"] = [_install_spec(x) for x in oc["install"][:MAX_INSTALL_SPECS]]
    out["other_keys"] = sorted(_seg(k) for k in oc if k not in {"skillKey", "primaryEnv", "homepage", "emoji", "always", "os", "requires", "install"})
    return out


def read_skill(skill_md: Path, base_label: str) -> dict:
    """SKILL.md 하나에서 frontmatter와 파일 사실만 수집한다. 본문은 저장하지 않는다."""
    item: dict[str, Any] = {"kind": "skill"}
    spath, redacted = _safe_path(skill_md)
    item["observed_from"] = {"skill_file": spath, "evidence_type": "static_file", "source_path_redacted": redacted,
                             "provided_by": base_label}
    issues: list[dict] = []
    red = Redactor()
    text, err = _read_text_limited(skill_md, MAX_FRONTMATTER_BYTES)
    if err:
        item.update(collection_status="failed", outcome=err["code"], issues=[err], redactions=[], identity={"name": _identity(None, None)})
        return item
    try:
        size = skill_md.stat().st_size
    except OSError:
        size = None
    item["body_size_bytes"] = size   # 본문 내용은 서버·작성자가 제공한 비신뢰 데이터이므로 저장하지 않는다
    fm, extra, problem = parse_frontmatter_ex(text or "")
    unparsed = list(extra.get("unparsed", []))
    folder = skill_md.parent.name
    if fm is None:
        issues.append(_issue("error", problem or "frontmatter_missing", "frontmatter를 읽지 못했습니다."))
        item.update(collection_status="failed", outcome=problem, issues=issues, redactions=[], identity={"name": _identity(None, None)},
                    folder_name=_text(red, folder, "folder_name"))
        return item
    shown: dict[str, Any] = {}
    for k in _SKILL_FM_STR:
        if k in fm:
            if isinstance(fm[k], str):
                shown[k] = _sanitize(fm[k], k, red)
            else:
                issues.append(_issue("warning", "field_type_invalid", f"{k}가 문자열이 아닙니다.", field_path=k, actual=_type_name(fm[k])))
    for k in _SKILL_FM_BOOL:
        if k in fm:
            if isinstance(fm[k], bool):
                shown[k] = fm[k]
            else:
                issues.append(_issue("warning", "field_type_invalid", f"{k}가 불리언이 아닙니다.", field_path=k, actual=_type_name(fm[k])))
    meta = _skill_metadata(fm.get("metadata"))
    bad_digest = [(i, sp["sha256_state"]) for i, sp in enumerate(meta.get("install_specs") or [])
                  if isinstance(sp, dict) and sp.get("sha256_state") not in (None, "absent", "valid_format")]
    if bad_digest:
        issues.append(_issue("warning", "skill_install_sha256_invalid",
                             "설치 명세의 sha256이 선언돼 있지만 64자리 16진 문자열이 아닙니다(숫자로 해석되는 값은 따옴표가 필요할 수 있음). 값은 저장하지 않았고 유효한 해시로 인정하지 않았습니다.",
                             specs=[{"index": i, "state": st} for i, st in bad_digest]))
    meta_shown = _sanitize(meta, "metadata.openclaw", red) if meta else {}
    name_raw = fm.get("name") if isinstance(fm.get("name"), str) else None
    item["identity"] = {"name": _identity(name_raw, shown.get("name"))}
    for req in ("name", "description"):
        if req not in shown:
            issues.append(_issue("warning", "required_field_missing", f"문서가 필수로 정한 frontmatter {req}가 없습니다.", field_path=req))
    item["folder_name"] = _text(red, folder, "folder_name")
    item["name_matches_folder"] = (name_raw == folder) if name_raw is not None else None
    item["frontmatter_parser"] = extra.get("parser", "bounded_legacy_json5_fallback")
    item["frontmatter"] = shown
    item["metadata_openclaw"] = meta_shown
    origin_rec = _read_install_origin(skill_md.parent, red, issues)
    if origin_rec is not None:
        item["install_origin"] = origin_rec
    item["frontmatter_keys"] = sorted(_seg(k) for k in fm)
    if unparsed:
        item["frontmatter_unparsed_keys"] = [_seg(k) for k in unparsed]
        issues.append(_issue("warning", "frontmatter_value_not_parsed",
                             "안전하게 JSON 자료형으로 해석할 수 없는 YAML(사용자 정의 태그·순환 별칭·복합 키·구문 오류·한도 초과)은 값 없이 키 이름만 남깁니다.",
                             keys=[_seg(k) for k in unparsed]))
    if extra.get("alias_keys"):
        issues.append(_issue("warning", "frontmatter_alias_not_expanded", "앵커·별칭·태그는 확장하거나 실행하지 않았습니다.", keys=[_seg(k) for k in extra["alias_keys"]]))
    if extra.get("limit_hits"):
        issues.append(_issue("warning", "frontmatter_limit_exceeded", "중첩 깊이·노드 수·문자열 길이 한도를 넘어 해당 키를 읽지 않았습니다.",
                             hits=[{"key": _seg(h["key"]), "limit": h["what"]} for h in extra["limit_hits"]]))
    if extra.get("duplicate_keys"):
        issues.append(_issue("error", "duplicate_key", "frontmatter에 같은 키가 여러 번 선언되어 마지막 값만 읽었습니다.", keys=[_seg(k) for k in extra["duplicate_keys"]]))
    skill_key = meta.get("skillKey") if isinstance(meta.get("skillKey"), str) else name_raw
    item["config_key"] = {"value": skill_key if skill_key and not looks_like_secret_value(skill_key) else None,
                          "basis": "metadata.openclaw.skillKey" if isinstance(meta.get("skillKey"), str) else "name"}
    item["issues"] = issues
    item["redactions"] = red.redactions
    item["collection_status"] = "partial" if unparsed or extra.get("limit_hits") or any(i["severity"] == "error" for i in issues) else "complete"
    item["outcome"] = "skill_read"
    return item


def discover_skill_files(path: Path) -> tuple[list[Path], list[dict]]:
    """지정한 경로가 skill 폴더면 그 SKILL.md, 폴더들의 부모면 바로 아래 폴더의 SKILL.md를 모은다(깊이 1). 심볼릭 링크는 따르지 않는다."""
    notes: list[dict] = []
    if not path.is_dir():
        return [], [_issue("error", "dir_not_found", "디렉터리가 없습니다.")]
    direct = path / "SKILL.md"
    if direct.is_file() and not direct.is_symlink():
        return [direct], notes
    found: list[Path] = []
    try:
        children = sorted(c for c in path.iterdir())
    except OSError as exc:
        return [], [_issue("error", "dir_unreadable", f"디렉터리를 읽지 못했습니다 ({type(exc).__name__}).")]
    for c in children:
        if c.is_symlink():
            notes.append(_issue("warning", "symlink_not_followed", "심볼릭 링크는 따라가지 않았습니다."))
            continue
        f = c / "SKILL.md"
        if c.is_dir() and f.is_file() and not f.is_symlink():
            found.append(f)
        if len(found) >= MAX_SKILLS_PER_DIR:
            notes.append(_issue("error", "skill_limit_exceeded", f"디렉터리당 skill {MAX_SKILLS_PER_DIR}개 한도를 넘어 나머지를 읽지 않았습니다."))
            break
    return found, notes


# ---- Plugin ------------------------------------------------------------------------

def _within(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _str_list(value: Any, path: str, issues: list[dict], red: Redactor) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(x, str) for x in value):
        return [_sanitize(x, f"{path}[{i}]", red) for i, x in enumerate(value[:MAX_NAMES])]
    issues.append(_issue("warning", "field_type_invalid", f"{path}가 문자열 배열이 아닙니다.", field_path=path, actual=_type_name(value)))
    return None


def read_plugin(plugin_dir: Path, index: int) -> tuple[dict, list[dict]]:
    """플러그인 루트 디렉터리 하나를 읽는다. (항목, 이 플러그인이 선언한 skill 항목들)"""
    item: dict[str, Any] = {"kind": "plugin", "internal_ref": f"plugin-input[{index}]"}
    root_s, root_red = _safe_path(plugin_dir)
    item["root_dir"] = {"value": root_s, "provided_by": "operator_selected_directory", "path_redacted": root_red}
    issues: list[dict] = []
    red = Redactor()
    skills_out: list[dict] = []
    manifest_path = plugin_dir / MANIFEST_NAME
    if not plugin_dir.is_dir():
        item.update(collection_status="failed", outcome="plugin_dir_not_found", issues=[_issue("error", "plugin_dir_not_found", "디렉터리가 없습니다.")],
                    redactions=[], identity={"id": _identity(None, None), "name": _identity(None, None)})
        return item, skills_out
    try:
        text = read_config(manifest_path)
        root = parse_config(text)
    except CollectionFailure as fail:
        item.update(collection_status="failed", outcome=f"manifest_{fail.outcome}", issues=[_issue("error", f"manifest_{fail.reason['code']}", fail.reason["message"])],
                    redactions=[], identity={"id": _identity(None, None), "name": _identity(None, None)})
        return item, skills_out
    mpath, _ = _safe_path(manifest_path)
    item["observed_from"] = {"manifest": {"source_path": mpath, "evidence_type": "static_file"}, "package_json": None}
    if not isinstance(root, dict):
        item.update(collection_status="failed", outcome="manifest_not_object", issues=[_issue("error", "manifest_not_object", "매니페스트 최상위가 객체가 아닙니다.")],
                    redactions=[], identity={"id": _identity(None, None), "name": _identity(None, None)})
        return item, skills_out

    for dup in _find_duplicate_keys(root, ()):
        issues.append(_issue("error", "duplicate_key", "같은 키가 여러 번 선언되어 마지막 값만 읽었습니다.", field_path=dup))
    declared: dict[str, Any] = {}
    for key in _MANIFEST_STR:
        if key in root:
            if isinstance(root[key], str):
                declared[key] = _sanitize(root[key], key, red)
            else:
                issues.append(_issue("warning", "field_type_invalid", f"{key}가 문자열이 아닙니다.", field_path=key, actual=_type_name(root[key])))
    if "kind" in root:
        k = root["kind"]
        if isinstance(k, str) or (isinstance(k, list) and all(isinstance(x, str) for x in k)):
            declared["kind"] = _sanitize(k, "kind", red)
        else:
            issues.append(_issue("warning", "field_type_invalid", "kind가 문자열(배열)이 아닙니다.", field_path="kind", actual=_type_name(k)))
    if "enabledByDefault" in root:
        if root["enabledByDefault"] is True:
            declared["enabledByDefault"] = True
        else:
            issues.append(_issue("warning", "field_type_invalid", "문서는 enabledByDefault를 true만 허용합니다.", field_path="enabledByDefault"))
    for key in _MANIFEST_STR_LIST:
        if key in root:
            v = _str_list(root[key], key, issues, red)
            if v is not None:
                declared[key] = v
    # 문서화된 객체 필드는 키 이름과(문자열 목록인 경우) 목록만 옮긴다. 값 전체를 복사하거나 해석하지 않는다.
    if isinstance(root.get("activation"), dict):
        declared["activation_keys"] = [_seg(k) for k in root["activation"]][:30]
    if isinstance(root.get("contracts"), dict):
        contracts = {}
        for ck, cv in list(root["contracts"].items())[:30]:
            if isinstance(cv, list) and all(isinstance(x, str) for x in cv):
                contracts[_seg(ck)] = _sanitize(cv[:100], f"contracts.{ck}", red)
            else:
                contracts[_seg(ck)] = {"type": _type_name(cv)}
        declared["contracts"] = contracts
    item["manifest"] = {"declared": declared, "declared_keys": [_seg(k) for k in root],
                        "activation_note": "enabledByDefault는 번들 플러그인의 매니페스트 선언이며 실제 활성 상태가 아닙니다."}
    item["identity"] = {"id": _identity(root.get("id"), declared.get("id")), "name": _identity(root.get("name"), declared.get("name"))}
    if "id" not in root:
        issues.append(_issue("error", "required_field_missing", "문서가 필수로 정한 매니페스트 id가 없습니다.", field_path="id"))

    # package.json: 문서화된 공급 출처 힌트만 옮긴다. 무결성 값은 저장하지 않고 선언 여부만 남긴다.
    pkg_path = plugin_dir / "package.json"
    pkg_info: dict[str, Any] | None = None
    if pkg_path.is_file():
        ptxt, perr = _read_text_limited(pkg_path, MAX_FILE_BYTES)
        if perr:
            issues.append(_issue("warning", f"package_json_{perr['code']}", "package.json을 읽지 못했습니다."))
        else:
            try:
                pj = parse_config(ptxt)
            except CollectionFailure:
                pj = None
                issues.append(_issue("warning", "package_json_parse_error", "package.json 구문을 해석하지 못했습니다."))
            if isinstance(pj, dict):
                pkg_info = {}
                for k in ("name", "version"):
                    if isinstance(pj.get(k), str):
                        pkg_info[k] = _sanitize(pj[k], f"package.{k}", red)
                oc = pj.get("openclaw") if isinstance(pj.get("openclaw"), dict) else {}
                inst = oc.get("install") if isinstance(oc.get("install"), dict) else {}
                hints = {k: _sanitize(inst[k], f"package.openclaw.install.{k}", red) for k in ("clawhubSpec", "npmSpec", "localPath", "minHostVersion", "defaultChoice")
                         if isinstance(inst.get(k), str)}
                if hints:
                    pkg_info["install_hints"] = hints
                if "expectedIntegrity" in inst:
                    pkg_info["expected_integrity_declared"] = True   # 값(해시)은 저장하지 않는다
                comp = oc.get("compat") if isinstance(oc.get("compat"), dict) else {}
                if isinstance(comp.get("pluginApi"), str):
                    pkg_info["compat_plugin_api"] = _sanitize(comp["pluginApi"], "package.openclaw.compat.pluginApi", red)
                if isinstance(oc.get("extensions"), list):
                    pkg_info["extension_entry_count"] = len(oc["extensions"])
                # 실행 진입점: 문서가 정한 `openclaw.extensions` 등의 경로 문자열만 기록한다(읽거나 실행·import하지 않음).
                entry_points: dict[str, Any] = {}
                for ek in ("extensions", "runtimeExtensions"):
                    if isinstance(oc.get(ek), list):
                        entry_points[ek] = [_sanitize(x, f"package.openclaw.{ek}", red) for x in oc[ek][:50] if isinstance(x, str)]
                for ek in ("setupEntry", "runtimeSetupEntry"):
                    if isinstance(oc.get(ek), str):
                        entry_points[ek] = _sanitize(oc[ek], f"package.openclaw.{ek}", red)
                if entry_points:
                    escapes = [e for v in entry_points.values() for e in ([v] if isinstance(v, str) else v)
                               if e.startswith(("/", "\\")) or ".." in e.replace("\\", "/").split("/") or (len(e) > 1 and e[1] == ":")]
                    pkg_info["entry_points"] = {**entry_points, "executed_or_loaded_by_scanner": False,
                                                "outside_package_dir_declared": bool(escapes),
                                                "basis": "문서: 진입점은 플러그인 패키지 디렉터리 안이어야 함. 경로 문자열만 기록했고 파일 존재·내용은 확인하지 않음"}
                    if escapes:
                        issues.append(_issue("warning", "entry_point_outside_package", "진입점 경로가 패키지 디렉터리 밖을 가리키는 형태입니다. 읽지 않았습니다.", field_path="package.openclaw.extensions"))
                rpp = inst.get("requiredPlatformPackages")
                if isinstance(rpp, list):
                    pkg_info["required_platform_packages"] = [_sanitize(x, "package.openclaw.install.requiredPlatformPackages", red) for x in rpp[:50] if isinstance(x, str)]
                deps: dict[str, Any] = {}
                for dk in ("dependencies", "peerDependencies", "optionalDependencies"):
                    dv = pj.get(dk)
                    if isinstance(dv, dict):
                        deps[dk] = {"count": len(dv), "entries": [{"name": _sanitize(n, f"package.{dk}", red), "spec": _sanitize(v, f"package.{dk}.spec", red)}
                                                                 for n, v in list(dv.items())[:200] if isinstance(n, str) and isinstance(v, str)]}
                if deps:
                    pkg_info["dependencies"] = {**deps, "note": "package.json에 선언된 이름·버전 범위만 기록했습니다. 설치 여부·실제 해석된 버전·취약점은 확인하지 않았습니다."}
                hints: dict[str, Any] = {}
                au = pj.get("author")
                if isinstance(au, str):
                    nm = re.split(r"[<(]", au, 1)[0].strip()        # "이름 <이메일> (URL)"에서 이름만 (이메일·URL은 저장하지 않는다)
                    if nm:
                        hints["author_name"] = _sanitize(nm, "package.author", red)
                elif isinstance(au, dict) and isinstance(au.get("name"), str) and au["name"]:
                    hints["author_name"] = _sanitize(au["name"], "package.author.name", red)
                rp = pj.get("repository")
                rurl = rp if isinstance(rp, str) else (rp.get("url") if isinstance(rp, dict) else None)
                if isinstance(rurl, str) and rurl:
                    hints["repository"] = _sanitize(rurl, "package.repository", red)
                if isinstance(pj.get("homepage"), str) and pj["homepage"]:
                    hints["homepage"] = _sanitize(pj["homepage"], "package.homepage", red)
                if hints:
                    pkg_info["declared_provider_hints"] = hints
                if isinstance(pj.get("gitHead"), str) and pj["gitHead"]:
                    gh = pj["gitHead"]
                    pkg_info["git_head"] = {"value": gh if re.fullmatch(r"[0-9a-f]{40}", gh) else None,
                                            "format": "sha1_hex40" if re.fullmatch(r"[0-9a-f]{40}", gh) else "unrecognized", "verified_by_scanner": False}
                pkg_info["declared_keys"] = [_seg(k) for k in pj][:60]
                ppath, _ = _safe_path(pkg_path)
                item["observed_from"]["package_json"] = {"source_path": ppath, "evidence_type": "static_file"}
    item["package"] = pkg_info
    item["supply_source"] = {
        "basis": "package.json과 openclaw.plugin.json에 적힌 값. 설치 기록(플러그인 인덱스)은 읽지 않았으므로 설치 경로·출처는 확인하지 않았습니다.",
        "package_name": (pkg_info or {}).get("name"), "package_version": (pkg_info or {}).get("version"),
        "manifest_version": declared.get("version"), "install_hints": (pkg_info or {}).get("install_hints"),
        "declared_source_kinds": [kind for key, kind in (("npmSpec", "npm"), ("clawhubSpec", "clawhub"), ("localPath", "local_path"))
                                  if key in ((pkg_info or {}).get("install_hints") or {})],
        "integrity": {"expected_integrity_declared": bool((pkg_info or {}).get("expected_integrity_declared")),
                      "verification": "not_performed", "basis": "서명·무결성 검증은 신뢰 기준(허용 레지스트리·키)이 합의되지 않아 수행하지 않았습니다. 선언 여부만 기록합니다."},
    }

    # manifest에 선언된 MCP 서버: 기존 수집기를 그대로 쓴다. 같은 매니페스트 안의 선언이므로 연결 근거가 분명하다.
    if "mcpServers" in root:
        col = collect_plugin_manifest(manifest_path)
        item["mcp_servers"] = {
            "link_basis": "declared_in_same_manifest",
            "registry_path": col.get("registry_path"),
            "collection": {k: col["collection"].get(k) for k in ("status", "outcome", "server_count")},
            "records": col.get("servers", []),
            "note": "선언이 있다는 뜻이며 서버 실행·로딩·등록 성공을 뜻하지 않습니다.",
        }
        if col["collection"].get("status") != "complete":
            issues.append(_issue("warning", "mcp_servers_incomplete", "매니페스트의 mcpServers를 완전히 수집하지 못했습니다.", status=col["collection"].get("status")))
    else:
        item["mcp_servers"] = None

    # manifest.skills: 플러그인 루트 안의 상대 경로만 읽는다.
    declared_skills = []
    for i, rel in enumerate(declared.get("skills", []) if isinstance(declared.get("skills"), list) else []):
        raw_rel = root["skills"][i]
        entry: dict[str, Any] = {"declared_path": rel, "skills": []}
        # Manifest paths may use either platform's separators. Check Windows
        # drives/UNC paths even on POSIX, then resolve the relative path locally.
        relative = raw_rel.replace("\\", "/")
        target = plugin_dir / relative
        if PureWindowsPath(raw_rel).drive or Path(relative).is_absolute() or not _within(plugin_dir, target):
            entry["status"] = "outside_plugin_root_not_read"
            issues.append(_issue("error", "skills_path_outside_plugin_root", "skills 경로가 플러그인 루트 밖이라 읽지 않았습니다.", field_path=f"skills[{i}]"))
        else:
            files, notes = discover_skill_files(target)
            issues.extend(notes)
            entry["status"] = "read" if files else ("not_found" if not target.exists() else "no_skill_files")
            for f in files:
                sk = read_skill(f, "declared_by_plugin_manifest")
                sk["declared_by_plugin"] = {"plugin_ref": item["internal_ref"], "manifest_skills_index": i, "link_basis": "path_declared_in_manifest_within_plugin_root"}
                skills_out.append(sk)
        declared_skills.append(entry)   # entry["skills"]는 전역 번호가 정해진 뒤 collect_assets가 채운다
    item["skills_declared"] = declared_skills
    item["issues"] = issues
    item["redactions"] = red.redactions
    errors = [i for i in issues if i["severity"] == "error"]
    item["collection_status"] = "partial" if errors or any(i["code"] == "mcp_servers_incomplete" for i in issues) else "complete"
    item["outcome"] = "plugin_read"
    return item, skills_out


# ---- 설정에 선언된 활성화 값 -------------------------------------------------------------

def _bool_or_issue(node: dict, key: str, path: str, issues: list[dict]) -> bool | None:
    if key not in node:
        return None
    if isinstance(node[key], bool):
        return node[key]
    issues.append(_issue("warning", "field_type_invalid", f"{path}.{key}가 불리언이 아닙니다.", field_path=f"{path}.{key}", actual=_type_name(node[key])))
    return None


def _cred_kind(value: Any) -> dict:
    kind, detail = classify_secret_ref(value)
    if kind == "valid":
        return {"value_kind": "secret_ref", "ref": detail}
    if kind == "invalid":
        return {"value_kind": "invalid_secret_ref"}
    if isinstance(value, str):
        return {"value_kind": "literal_withheld"}   # 평문 값은 길이도 저장하지 않는다
    return {"value_kind": "non_string", "type": _type_name(value)}


def read_activation_settings(config_path: Path, resolve_includes: bool = False) -> dict:
    """`plugins.*`·`skills.*`에 선언된 활성화 설정을 읽는다. 선언일 뿐 실제 로딩·활성 상태가 아니다.

    `resolve_includes=True`이면 `$include`를 읽기 전용으로 펼치고(`config_includes.py`) 허용·차단·활성화 선언마다 원본 파일(최상위 설정 폴더 기준
    상대 경로)·include 사슬·논리 키 경로를 `*_origin(s)`에 기록한다. 기본값(False)은 기존 동작과 같다.
    """
    out: dict[str, Any] = {"source_path": _safe_path(config_path)[0], "evidence_type": "static_file", "plugins": None, "skills": None,
                           "issues": [], "status": "complete"}
    issues: list[dict] = out["issues"]
    try:
        root = parse_config(read_config(config_path))
    except CollectionFailure as fail:
        out.update(status="failed", outcome=fail.outcome)
        issues.append(_issue("error", fail.reason["code"], fail.reason["message"]))
        return out
    if not isinstance(root, dict):
        out.update(status="failed", outcome="root_not_object")
        issues.append(_issue("error", "root_not_object", "설정 최상위가 객체가 아닙니다."))
        return out
    ctx = None
    if resolve_includes:
        from .collector import _include_info
        from .config_includes import resolve_includes as _resolve   # 순환 import 방지
        ctx = _resolve(config_path, root)
        root = ctx.root
        out["includes"] = _include_info(ctx)
        for inc in ctx.issues:
            issues.append(_issue("error", inc["code"], inc["message"], field_path=inc.get("field_path"), source="include_resolution"))

    def origin(*ptr: Any) -> dict | None:
        """이 키 경로(논리 경로)의 원본 파일. 옵션을 쓰지 않았으면 None(필드를 더하지 않는다)."""
        if ctx is None:
            return None
        label, chain = ctx.origin_of(tuple(ptr))
        return {"file": label, "include_chain": list(chain), "config_path": dotted_path(tuple(ptr))}

    def put(rec: dict, key: str, value: dict | None) -> None:
        if value is not None:
            rec[key] = value

    for dup in _find_duplicate_keys(root, ()):
        issues.append(_issue("error", "duplicate_key", "같은 키가 여러 번 선언되어 마지막 값만 읽었습니다.", field_path=dup))
    red = Redactor()
    plugins = root.get("plugins")
    if isinstance(plugins, dict):
        p: dict[str, Any] = {"declared_keys": [_seg(k) for k in plugins]}
        e = _bool_or_issue(plugins, "enabled", "plugins", issues)
        if e is not None:
            p["enabled"] = e
            put(p, "enabled_origin", origin("plugins", "enabled"))
        for lk in ("allow", "deny"):
            if lk in plugins:
                v = _str_list(plugins[lk], f"plugins.{lk}", issues, red)
                if v is not None:
                    p[lk] = v
                    if ctx is not None and isinstance(plugins[lk], list) and len(plugins[lk]) == len(v):
                        p[f"{lk}_origins"] = [origin("plugins", lk, i) for i in range(len(v))]      # 원소별 출처(공식: 배열은 연결됨)
        entries: dict[str, dict] = {}
        ent = plugins.get("entries")
        if isinstance(ent, dict):
            for k, v in ent.items():
                rec: dict[str, Any] = {"entry_key": k}
                put(rec, "origin", origin("plugins", "entries", k))
                if isinstance(v, dict):
                    en = _bool_or_issue(v, "enabled", f"plugins.entries.{k}", issues)
                    if en is not None:
                        rec["enabled"] = en
                        put(rec, "enabled_origin", origin("plugins", "entries", k, "enabled"))
                    rec["other_keys"] = [_seg(x) for x in v if x != "enabled"][:40]
                else:
                    issues.append(_issue("warning", "field_type_invalid", "plugins.entries 항목이 객체가 아닙니다.", field_path=f"plugins.entries.{_seg(k)}"))
                entries[k] = rec
        elif ent is not None:
            issues.append(_issue("warning", "field_type_invalid", "plugins.entries가 객체가 아닙니다.", field_path="plugins.entries"))
        p["entries"] = entries
        out["plugins"] = p
    skills = root.get("skills")
    if isinstance(skills, dict):
        s: dict[str, Any] = {"declared_keys": [_seg(k) for k in skills]}
        if "allowBundled" in skills:
            v = _str_list(skills["allowBundled"], "skills.allowBundled", issues, red)
            if v is not None:
                s["allowBundled"] = v
                if ctx is not None and isinstance(skills["allowBundled"], list) and len(skills["allowBundled"]) == len(v):
                    s["allowBundled_origins"] = [origin("skills", "allowBundled", i) for i in range(len(v))]
        load = skills.get("load")
        if isinstance(load, dict) and "extraDirs" in load:
            v = _str_list(load["extraDirs"], "skills.load.extraDirs", issues, red)
            if v is not None:
                s["load_extraDirs"] = v
                if ctx is not None and isinstance(load["extraDirs"], list) and len(load["extraDirs"]) == len(v):
                    s["load_extraDirs_origins"] = [origin("skills", "load", "extraDirs", i) for i in range(len(v))]
        sentries: dict[str, dict] = {}
        ent = skills.get("entries")
        if isinstance(ent, dict):
            for k, v in ent.items():
                rec = {"entry_key": k}
                put(rec, "origin", origin("skills", "entries", k))
                if isinstance(v, dict):
                    en = _bool_or_issue(v, "enabled", f"skills.entries.{k}", issues)
                    if en is not None:
                        rec["enabled"] = en
                        put(rec, "enabled_origin", origin("skills", "entries", k, "enabled"))
                    if "apiKey" in v:
                        rec["apiKey"] = _cred_kind(v["apiKey"])
                        put(rec, "apiKey_origin", origin("skills", "entries", k, "apiKey"))
                    if isinstance(v.get("env"), dict):
                        rec["env_names"] = [_seg(x) for x in v["env"]][:MAX_NAMES]   # 값은 저장하지 않는다
                    if "config" in v:
                        rec["config_declared"] = True
                else:
                    issues.append(_issue("warning", "field_type_invalid", "skills.entries 항목이 객체가 아닙니다.", field_path=f"skills.entries.{_seg(k)}"))
                sentries[k] = rec
        elif ent is not None:
            issues.append(_issue("warning", "field_type_invalid", "skills.entries가 객체가 아닙니다.", field_path="skills.entries"))
        s["entries"] = sentries
        out["skills"] = s
    out["redactions"] = red.redactions
    if any(i["severity"] == "error" for i in issues):
        out["status"] = "partial"
    return out


def _declared_for_plugin(settings: dict | None, plugin_id: Any) -> dict | None:
    if not settings or not settings.get("plugins") or not isinstance(plugin_id, str):
        return None
    p = settings["plugins"]
    entry = p["entries"].get(plugin_id)
    out: dict[str, Any] = {
        "source": "config_declared", "link_basis": "plugins.entries.<id> == manifest id",
        "plugins_enabled_globally": p.get("enabled"),
        "entry_declared": entry is not None,
        "entry_enabled": (entry or {}).get("enabled"),
        "listed_in_allow": (plugin_id in p["allow"]) if "allow" in p else None,
        "listed_in_deny": (plugin_id in p["deny"]) if "deny" in p else None,
        "note": "설정에 적힌 값입니다. 실제 로딩·활성 여부는 이 값만으로 판단하지 않습니다(기본값·자동 활성화 규칙은 적용하지 않음).",
    }
    origins = {k: v for k, v in {
        "plugins_enabled": p.get("enabled_origin"),
        "entry": (entry or {}).get("origin"),
        "entry_enabled": (entry or {}).get("enabled_origin"),
        # 같은 id가 연결된 모든 원소(배열 연결로 중복될 수 있음)의 출처
        "allow": [o for x, o in zip(p.get("allow", []), p.get("allow_origins", [])) if x == plugin_id] or None,
        "deny": [o for x, o in zip(p.get("deny", []), p.get("deny_origins", [])) if x == plugin_id] or None,
    }.items() if v is not None}
    if origins:
        out["origins"] = origins
    return out


def _declared_for_skill(settings: dict | None, key: Any) -> dict | None:
    if not settings or not settings.get("skills") or not isinstance(key, str):
        return None
    s = settings["skills"]
    entry = s["entries"].get(key)
    return {"source": "config_declared", "link_basis": "skills.entries.<key> == metadata.openclaw.skillKey or name",
            "entry_declared": entry is not None, "entry_enabled": (entry or {}).get("enabled"),
            "apiKey": (entry or {}).get("apiKey"), "env_names": (entry or {}).get("env_names"),
            "listed_in_allowBundled": (key in s["allowBundled"]) if "allowBundled" in s else None,
            "note": "설정에 적힌 값입니다. 실제 적용 여부는 확인하지 않았습니다.",
            **({"origins": {k: v for k, v in {
                "entry": (entry or {}).get("origin"), "entry_enabled": (entry or {}).get("enabled_origin"),
                "apiKey": (entry or {}).get("apiKey_origin"),
                "allowBundled": [o for x, o in zip(s.get("allowBundled", []), s.get("allowBundled_origins", [])) if x == key] or None,
            }.items() if v is not None}} if any(k in s for k in ("allowBundled_origins",)) or (entry or {}).get("origin") else {})}


# ---- 저장된 명령 출력 --------------------------------------------------------------------

_PLUGIN_RUNTIME_STR = ("id", "name", "version", "packageName", "packageVersion", "builtWithOpenClawVersion", "description", "format",
                       "bundleFormat", "source", "rootDir", "origin", "activationSource", "activationReason", "status", "trust")
_PLUGIN_RUNTIME_BOOL = ("enabled", "explicitlyEnabled", "activated", "imported", "trustedOfficialInstall", "memorySlotSelected")
_PLUGIN_RUNTIME_NAMES = ("toolNames", "hookNames", "channelIds", "providerIds", "cliCommands", "services", "commands")
_SKILL_RUNTIME_STR = ("name", "description", "source", "filePath", "baseDir", "skillKey", "primaryEnv", "homepage")
_SKILL_RUNTIME_BOOL = ("bundled", "always", "disabled", "blockedByAllowlist", "blockedByAgentFilter", "eligible", "platformIncompatible",
                       "modelVisible", "userInvocable", "commandVisible")


def _load_json(path: Path) -> tuple[Any, dict | None]:
    text, err = _read_text_limited(path, MAX_FILE_BYTES)
    if err:
        return None, err
    try:
        return json.loads(text), None
    except (ValueError, RecursionError):
        return None, _issue("error", "invalid_json", "JSON이 아닙니다.")


def _observation(path: Path, command: str) -> dict:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except OSError:
        mtime = None
    return {"source_kind": "stored_command_output", "command": command, "file": _safe_path(path)[0],
            "file_modified_at": mtime, "observed_at": None,
            "observed_at_note": "출력 파일에는 실행 시각이 없습니다. file_modified_at은 저장된 파일의 수정 시각이며 관측 시각이 아닙니다.",
            "collected_at": _now(), "verified_by_scanner": False}


def _plugins_list_from(data: Any, observation: dict) -> dict:
    out: dict[str, Any] = {"observation": observation, "records": [], "issues": [], "status": "complete"}
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, list):
        out["status"] = "failed"
        out["issues"].append(_issue("error", "invalid_structure", "최상위 객체에 plugins 배열이 없습니다 (plugins list --json 출력이 아닐 수 있음)."))
        return out
    for i, rec in enumerate(plugins[:2000]):
        if not isinstance(rec, dict):
            out["issues"].append(_issue("warning", "record_not_object", "plugins 항목이 객체가 아닙니다.", index=i)); out["status"] = "partial"
            continue
        red = Redactor()
        shown: dict[str, Any] = {}
        for k in _PLUGIN_RUNTIME_STR:
            if isinstance(rec.get(k), str):
                shown[k] = _sanitize(rec[k], k, red)
        for k in _PLUGIN_RUNTIME_BOOL:
            if isinstance(rec.get(k), bool):
                shown[k] = rec[k]
        if isinstance(rec.get("kind"), (str, list)):
            shown["kind"] = _sanitize(rec["kind"], "kind", red)
        names = {}
        for k in _PLUGIN_RUNTIME_NAMES:
            if isinstance(rec.get(k), list):
                names[k] = [_sanitize(x, f"{k}[{j}]", red) for j, x in enumerate(rec[k][:MAX_NAMES]) if isinstance(x, str)]
        if isinstance(rec.get("error"), str):
            shown["error_present"] = True   # 오류 메시지 원문은 저장하지 않는다
        out["records"].append({"index": i, "observed": shown, "registered_names": names,
                               "identity": {"id": _identity(rec.get("id"), shown.get("id"))}, "redactions": red.redactions,
                               "raw_root_dir": rec.get("rootDir") if isinstance(rec.get("rootDir"), str) else None})
    if len(plugins) > 2000:
        out["issues"].append(_issue("error", "record_limit_exceeded", "플러그인 기록 2000개 한도를 넘어 나머지를 읽지 않았습니다.")); out["status"] = "partial"
    return out


def _failed_list(observation: dict, issue: dict) -> dict:
    return {"observation": observation, "records": [], "issues": [issue], "status": "failed"}


def _direct_failure_issue(result: DirectResult) -> dict:
    f = result.failure or {}
    extra = {k: v for k, v in f.items() if k not in ("code", "message")}
    return _issue("error", f"direct_{f.get('code', 'failed')}", f.get("message", "직접 조회에 실패했습니다."), **extra)


def read_plugins_list_json(path: Path) -> dict:
    data, err = _load_json(path)
    obs = _observation(path, "openclaw plugins list --json")
    if err:
        return _failed_list(obs, err)
    return _plugins_list_from(data, obs)


def read_plugin_inspect_json(path: Path) -> dict:
    """저장된 plugin inspect의 설치 원천. SQLite를 열거나 원문/해시/비밀값을 복사하지 않는다.

    원천: testbed/ground-truth/raw/P2/tb-gw.plugin-inspect.agentscope-asset-catalog.json
    (팀 444f558893315e6c3a02e0a29d3d1dfe5f5a7bdb), 공식 eb377ac의 zod-schema.installs.ts.
    installedAt/acceptedSurfaceAt을 last_updated 또는 modified로 대체하지 않는다.
    """
    from .tools_catalog import _read_capture
    data, err = _read_capture(path)
    obs = _observation(path, "openclaw plugins inspect <selected-id> --json (stored export)")
    if err:
        return _failed_list(obs, _issue("error", err["code"], err["message"]))
    if not isinstance(data, dict) or not isinstance(data.get("plugin"), dict):
        return _failed_list(obs, _issue("error", "inspect_structure_invalid", "plugin 객체를 찾지 못했습니다."))
    out = _plugins_list_from({"plugins": [data["plugin"]]}, obs)
    from .tools_catalog import _find_duplicates
    duplicates: list = []
    _find_duplicates(data, "", duplicates)
    for parent, keys in duplicates:
        for key in keys:
            out["issues"].append(_issue("error", "duplicate_key", "같은 키의 마지막 선언만 읽었습니다.", field_path=_safe_short(Redactor(), parent + "." + key, "diagnostic_field_path")))
        out["status"] = "partial"
    if not out["records"] or out["records"][0]["identity"]["id"]["status"] != "as_reported":
        out["issues"].append(_issue("error", "plugin_id_unavailable", "가려지지 않은 plugin id를 확인하지 못했습니다."))
        out["status"] = "partial"
    install = data.get("install")
    if install is None:
        out["install"] = {"status": "not_reported", "verified_by_scanner": False}
        return out
    if not isinstance(install, dict):
        out["install"] = {"status": "invalid_type", "verified_by_scanner": False}
        out["issues"].append(_issue("error", "install_type_invalid", "install이 객체가 아닙니다. 값은 저장하지 않았습니다."))
        out["status"] = "partial"
        return out
    red = Redactor()
    record: dict[str, Any] = {"status": "recorded", "verified_by_scanner": False, "declared": {}, "digest_metadata": {},
                              "time_semantics": "installedAt은 설치 기록 시각, acceptedSurfaceAt은 수락 시각입니다. last_updated·modified가 아닙니다."}
    strings = ("source", "spec", "sourcePath", "installPath", "version", "resolvedName", "resolvedVersion", "resolvedSpec", "resolvedAt", "installedAt",
               "clawhubUrl", "clawhubPackage", "clawhubFamily", "clawhubChannel", "clawhubTrustDisposition", "artifactKind", "artifactFormat",
               "gitUrl", "gitRef", "gitCommit", "acceptedSurfaceAt")
    for key in strings:
        if key not in install:
            continue
        if isinstance(install[key], str):
            record["declared"][key] = _sanitize(install[key], "install." + key, red)
        else:
            out["issues"].append(_issue("error", "field_type_invalid", "설치 기록의 문자열 필드 자료형이 다릅니다. 값은 저장하지 않았습니다.", field_path="install." + key))
            out["status"] = "partial"
    for key in ("integrity", "shasum", "npmIntegrity", "npmShasum", "clawpackSha256", "clawpackManifestSha256", "acceptedSurfaceHash", "acceptedSurfaceIntegrity"):
        if key in install:
            valid = isinstance(install[key], str) and bool(install[key].strip())
            record["digest_metadata"][key] = {"declared": True, "value_state": "nonempty_string" if valid else "invalid_type_or_empty", "verification": "not_performed"}
            if not valid:
                out["issues"].append(_issue("error", "digest_metadata_invalid", "무결성 선언의 자료형 또는 빈 값 문제입니다. 원문은 저장하지 않았습니다.", field_path="install." + key))
                out["status"] = "partial"
    if "acceptedSurface" in install:
        surface = install["acceptedSurface"]
        record["accepted_surface"] = {}
        if not isinstance(surface, dict):
            out["status"] = "partial"
            out["issues"].append(_issue("error", "accepted_surface_invalid", "acceptedSurface가 객체가 아닙니다."))
        else:
            for key in ("channels", "providers", "tools", "contracts", "hooks", "mcpServers", "cliCommands", "cliBackends", "skills", "dangerousConfigFlags"):
                if key in surface:
                    value = _str_list(surface[key], "install.acceptedSurface." + key, out["issues"], red)
                    if value is not None:
                        record["accepted_surface"][key] = value
                    else:
                        out["status"] = "partial"
    record["redactions"] = red.redactions
    out["install"] = record
    return out


def read_plugins_list_direct(result: DirectResult) -> dict:
    """`openclaw_direct`로 직접 조회한 `plugins list --json` 결과를 같은 파서로 읽는다."""
    if result.failure is not None:
        return _failed_list(result.observation, _direct_failure_issue(result))
    return _plugins_list_from(result.data, result.observation)


def _skills_list_from(data: Any, observation: dict) -> dict:
    out: dict[str, Any] = {"observation": observation, "records": [], "issues": [], "status": "complete"}
    skills = data.get("skills") if isinstance(data, dict) else (data if isinstance(data, list) else None)
    if not isinstance(skills, list):
        out["status"] = "failed"
        out["issues"].append(_issue("error", "invalid_structure", "skills 배열을 찾지 못했습니다 (skills list --json 출력이 아닐 수 있음)."))
        return out
    for i, rec in enumerate(skills[:2000]):
        if not isinstance(rec, dict):
            out["issues"].append(_issue("warning", "record_not_object", "skills 항목이 객체가 아닙니다.", index=i)); out["status"] = "partial"
            continue
        red = Redactor()
        shown = {k: _sanitize(rec[k], k, red) for k in _SKILL_RUNTIME_STR if isinstance(rec.get(k), str)}
        for k in _SKILL_RUNTIME_BOOL:
            if isinstance(rec.get(k), bool):
                shown[k] = rec[k]
        out["records"].append({"index": i, "observed": shown, "identity": {"name": _identity(rec.get("name"), shown.get("name"))},
                               "redactions": red.redactions, "raw_file_path": rec.get("filePath") if isinstance(rec.get("filePath"), str) else None})
    return out


def read_skills_list_json(path: Path) -> dict:
    data, err = _load_json(path)
    obs = _observation(path, "openclaw skills list --json")
    if err:
        return _failed_list(obs, err)
    return _skills_list_from(data, obs)


def read_skills_list_direct(result: DirectResult) -> dict:
    if result.failure is not None:
        return _failed_list(result.observation, _direct_failure_issue(result))
    return _skills_list_from(result.data, result.observation)


def _obs_note(observation: dict, what: str) -> str:
    if observation.get("source_kind") == "direct_query":
        return f"직접 조회한 {what} 출력의 값입니다. OpenClaw가 돌려준 값이며 스캐너가 확인한 것이 아닙니다."
    return f"저장된 {what} 출력의 값입니다. 스캐너가 확인한 것이 아닙니다."


def _norm(p: str | None) -> str | None:
    if not p:
        return None
    try:
        return os.path.normcase(os.path.normpath(p))
    except (OSError, ValueError):
        return None


# ---- 전체 -------------------------------------------------------------------------------

def collect_assets(plugin_dirs: list[Path], skills_dirs: list[Path], config: Path | None,
                   plugins_list: Path | dict | None, skills_list: Path | dict | None, resolve_includes: bool = False,
                   plugin_inspects: list[Path] | None = None) -> dict:
    settings = read_activation_settings(config, resolve_includes) if config else None
    plugin_items: list[dict] = []
    skill_items: list[dict] = []
    for i, d in enumerate(plugin_dirs):
        p, declared_skills = read_plugin(d, i)
        p["declared_activation"] = _declared_for_plugin(settings, (p.get("identity", {}).get("id", {}) or {}).get("original_value"))
        plugin_items.append(p)
        for s in declared_skills:
            skill_items.append(s)
    top_issues: list[dict] = []
    for d in skills_dirs:
        files, notes = discover_skill_files(d)
        top_issues.extend(notes)
        if not files and not notes:
            top_issues.append(_issue("warning", "no_skill_files", "지정한 디렉터리에서 SKILL.md를 찾지 못했습니다."))
        for f in files:
            skill_items.append(read_skill(f, "operator_selected_directory"))
    for n, s in enumerate(skill_items):
        s["internal_ref"] = f"skill-input[{n}]"
        key = (s.get("config_key") or {}).get("value")
        s["declared_activation"] = _declared_for_skill(settings, key)
        dp = s.get("declared_by_plugin")
        if dp:
            owner = next((p for p in plugin_items if p["internal_ref"] == dp["plugin_ref"]), None)
            if owner is not None:
                owner["skills_declared"][dp["manifest_skills_index"]]["skills"].append(s["internal_ref"])

    # 경로이면 저장된 출력 파일을 읽고, dict이면 직접 조회 등으로 이미 읽은 결과(read_*_direct)를 그대로 쓴다
    plist = plugins_list if isinstance(plugins_list, dict) else (read_plugins_list_json(plugins_list) if plugins_list else None)
    slist = skills_list if isinstance(skills_list, dict) else (read_skills_list_json(skills_list) if skills_list else None)
    matched_plugin_records: set[int] = set()
    if plist:
        for p in plugin_items:
            pid = ((p.get("identity") or {}).get("id") or {}).get("original_value")
            my_root = _norm(p["root_dir"]["value"]) if p.get("root_dir") else None
            same_id = [r for r in plist["records"] if ((r["identity"]["id"]).get("original_value") == pid and pid is not None)]
            linked = [r for r in same_id if r["raw_root_dir"] and _norm(str(Path(r["raw_root_dir"]).resolve())) == my_root]
            if len(linked) == 1:
                r = linked[0]
                matched_plugin_records.add(r["index"])
                p["runtime_observation"] = {"link_basis": "id_and_root_dir_match", "observation": plist["observation"], "observed": r["observed"],
                                            "registered_names": r["registered_names"],
                                            "note": _obs_note(plist["observation"], "plugins list --json")}
            else:
                p["runtime_observation"] = None
                if same_id:
                    p["runtime_candidates_not_linked"] = [{"record_index": r["index"], "reason": "id는 같지만 루트 경로가 다르거나 확인할 수 없어 연결하지 않았습니다"} for r in same_id]
    matched_skill_records: set[int] = set()
    if slist:
        for s in skill_items:
            my_file = _norm(((s.get("observed_from") or {}).get("skill_file")))
            hits = [r for r in slist["records"] if r["raw_file_path"] and _norm(str(Path(r["raw_file_path"]).resolve())) == my_file]
            if len(hits) == 1:
                matched_skill_records.add(hits[0]["index"])
                s["runtime_observation"] = {"link_basis": "skill_file_path_match", "observation": slist["observation"], "observed": hits[0]["observed"],
                                            "note": _obs_note(slist["observation"], "skills list --json")}
            else:
                s["runtime_observation"] = None
    unmatched_plugins = [{"kind": "plugin", "source": ("direct_plugins_list_only" if plist["observation"].get("source_kind") == "direct_query" else "stored_plugins_list_json_only"), "observation": plist["observation"], "observed": r["observed"],
                          "registered_names": r["registered_names"], "identity": r["identity"], "redactions": r["redactions"]}
                         for r in (plist["records"] if plist else []) if r["index"] not in matched_plugin_records]
    unmatched_skills = [{"kind": "skill", "source": ("direct_skills_list_only" if slist["observation"].get("source_kind") == "direct_query" else "stored_skills_list_json_only"), "observation": slist["observation"], "observed": r["observed"],
                         "identity": r["identity"], "redactions": r["redactions"]}
                        for r in (slist["records"] if slist else []) if r["index"] not in matched_skill_records]
    for lst in (plist, slist):
        if lst:
            for r in lst["records"]:
                r.pop("raw_root_dir", None); r.pop("raw_file_path", None)
    inspect_outputs = [read_plugin_inspect_json(p) for p in (plugin_inspects or [])]
    for p in plugin_items:
        p["installation_observations"] = []
        pid = p.get("identity", {}).get("id", {}).get("original_value")
        my_root = _norm(p.get("root_dir", {}).get("value"))
        if pid is None or p.get("root_dir", {}).get("path_redacted"):
            continue
        for n, inspected in enumerate(inspect_outputs):
            for record in inspected["records"]:
                same_id = record["identity"]["id"]["original_value"] == pid
                raw_root = record.get("raw_root_dir")
                if same_id and raw_root and _norm(str(Path(raw_root).resolve())) == my_root:
                    p["installation_observations"].append({"inspect_output_index": n, "link_basis": "id_and_root_dir_match",
                                                          "install": inspected.get("install"), "observation": inspected["observation"]})
    for inspected in inspect_outputs:
        for record in inspected["records"]:
            record.pop("raw_root_dir", None)
    return {"plugins": plugin_items, "skills": skill_items, "runtime_only": {"plugins": unmatched_plugins, "skills": unmatched_skills},
            "activation_settings": settings, "stored_outputs": {"plugins_list": plist and {k: plist[k] for k in ("observation", "status", "issues")},
                                                                "skills_list": slist and {k: slist[k] for k in ("observation", "status", "issues")}},
            "issues": top_issues, "plugin_inspect_outputs": inspect_outputs}


def summarize(collected: dict, inputs_given: bool) -> dict:
    items = collected["plugins"] + collected["skills"]
    stored = [v for v in (collected["stored_outputs"].get("plugins_list"), collected["stored_outputs"].get("skills_list")) if v]
    stored += collected.get("plugin_inspect_outputs", [])
    settings = collected["activation_settings"]
    statuses = [i["collection_status"] for i in items] + [s["status"] for s in stored] + ([settings["status"]] if settings else [])
    n_runtime = len(collected["runtime_only"]["plugins"]) + len(collected["runtime_only"]["skills"])
    if not inputs_given:
        status, outcome = "failed", "no_input"
    elif not items and not stored and not settings and not n_runtime:
        status, outcome = "failed", "nothing_read"
    elif statuses and all(s == "failed" for s in statuses) and not n_runtime:
        status, outcome = "failed", "all_inputs_failed"
    elif all(s == "complete" for s in statuses) and not any(i["severity"] == "error" for i in collected["issues"]):
        status, outcome = "complete", "assets_read"
    else:
        status, outcome = "partial", "some_inputs_incomplete"
    return {"status": status, "outcome": outcome, "plugin_count": len(collected["plugins"]), "skill_count": len(collected["skills"]),
            "runtime_only_plugin_count": len(collected["runtime_only"]["plugins"]), "runtime_only_skill_count": len(collected["runtime_only"]["skills"])}


def build_report(collected: dict, inputs_given: bool = True) -> dict:
    return {
        "format": FORMAT_NAME, "format_version": FORMAT_VERSION,
        "format_status": ("스캐너 내부 개발용 초안입니다. 팀 공통 스키마가 아니며 공통 ID는 정하지 않았습니다. "
                          "internal_ref는 이 파일 안에서만 쓰는 이름입니다."),
        "producer": {"name": "agent-scope-asset-scanner", "version": __version__},
        "generated_at": _now(),
        "basis": {"openclaw_version": "2026.9.6", "evidence": "패키지 문서·코드(정적 읽기). docs/asset-collection.md"},
        "scope": {
            "method": "명시적으로 지정한 플러그인/스킬 디렉터리, 설정 파일, 저장된 명령 출력 파일 읽기",
            "not_verified": NOT_VERIFIED,
            "value_origins": {
                "observed_from.static_file": "파일에서 관측한 값(manifest, package.json, SKILL.md frontmatter)",
                "declared_activation": "설정에 적힌 활성화 선언. 실제 로딩·활성 상태가 아님",
                "runtime_observation": "openclaw 명령 출력의 값. 저장된 출력(source_kind stored_command_output)이면 관측 시각 미상, 직접 조회(source_kind direct_query)면 명령·설치 버전·조회 범위·관측 시각을 기록. 어느 쪽도 스캐너가 확인한 값이 아님",
                "operator_selected": "어떤 경로를 읽을지 사용자가 지정한 사실. 경로의 종류(번들·관리형 등)는 판단하지 않음",
            },
        },
        "collection": summarize(collected, inputs_given),
        "plugins": collected["plugins"], "skills": collected["skills"], "runtime_only": collected["runtime_only"],
        "activation_settings": collected["activation_settings"], "stored_outputs": collected["stored_outputs"],
        "issues": collected["issues"], "plugin_inspect_outputs": collected.get("plugin_inspect_outputs", []),
    }


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m asset_scanner.plugin_skill_assets",
                                description="지정한 플러그인/스킬 디렉터리와 설정·저장된 명령 출력에서 Plugin·Skill 자체 정보를 수집합니다 (읽기 전용, 내부 개발용 초안).")
    p.add_argument("--plugin-dir", action="append", default=[], type=Path, help="openclaw.plugin.json이 있는 플러그인 루트 디렉터리 (여러 번 가능)")
    p.add_argument("--skills-dir", action="append", default=[], type=Path, help="SKILL.md가 있는 skill 폴더, 또는 그런 폴더들의 부모 디렉터리 (여러 번 가능)")
    p.add_argument("--config", type=Path, help="plugins.*·skills.* 활성화 선언을 읽을 OpenClaw 설정 파일(JSON5)")
    p.add_argument("--resolve-includes", action="store_true",
                   help="--config의 $include를 읽기 전용으로 펼칩니다(공식 병합 규칙, 설정 폴더·추가 허용 경계 안). 활성화·허용·차단 선언마다 원본 파일과 키 경로를 기록합니다. 생략하면 읽지 않습니다.")
    p.add_argument("--plugins-list-json", type=Path, help="저장해 둔 `openclaw plugins list --json` 출력 파일")
    p.add_argument("--plugin-inspect-json", action="append", default=[], type=Path, help="저장된 plugin inspect JSON (복수 설치는 id와 rootDir가 모두 맞을 때만 연결)")
    p.add_argument("--skills-list-json", type=Path, help="저장해 둔 `openclaw skills list --json` 출력 파일")
    p.add_argument("--openclaw-query", action="append", default=[], choices=("plugins", "skills"),
                   help="저장된 출력 대신 OpenClaw에 직접 조회 (--openclaw-bin 필요). skills는 기본 거부이며 --accept-skills-list-gateway-rpc가 있어야 합니다")
    add_direct_arguments(p)
    p.add_argument("--output", required=True, type=Path, help="결과 JSON 경로")
    return p


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    parser = _parser()
    args = parser.parse_args(argv)
    queries = list(dict.fromkeys(args.openclaw_query))
    if args.resolve_includes and not args.config:
        parser.error("--resolve-includes는 --config와 함께만 쓸 수 있습니다.")
    given = bool(args.plugin_dir or args.skills_dir or args.config or args.plugins_list_json or args.skills_list_json or args.plugin_inspect_json or queries)
    if not given:
        parser.error("입력이 없습니다. --plugin-dir, --skills-dir, --config, --plugins-list-json, --skills-list-json, --openclaw-query 중 하나 이상을 지정하세요.")
    if queries:
        if args.openclaw_bin is None:
            parser.error("--openclaw-query에는 --openclaw-bin(실행 파일 경로)이 필요합니다.")
        if ("plugins" in queries and args.plugins_list_json) or ("skills" in queries and args.skills_list_json):
            parser.error("같은 종류를 저장된 출력과 직접 조회로 동시에 지정할 수 없습니다 (출처가 섞이지 않게 하나만 고르세요).")
        problems = validate_config(config_from_args(args), queries)
        if problems:
            parser.error("; ".join(problems))
    plugins_src: Any = args.plugins_list_json
    skills_src: Any = args.skills_list_json
    if queries:
        results, _ver = run_queries(config_from_args(args), queries)
        if "plugins" in results:
            plugins_src = read_plugins_list_direct(results["plugins"])
        if "skills" in results:
            skills_src = read_skills_list_direct(results["skills"])
    for inp in [*args.plugin_dir, *args.skills_dir, *args.plugin_inspect_json, *(x for x in (args.config, args.plugins_list_json, args.skills_list_json) if x)]:
        if _same_file(inp, args.output):
            print("오류: --output이 입력과 같은 경로입니다. 입력을 덮어쓰지 않습니다.", file=sys.stderr)
            return EXIT_OUTPUT_ERROR
    report = build_report(collect_assets(args.plugin_dir, args.skills_dir, args.config, plugins_src, skills_src, args.resolve_includes, args.plugin_inspect_json), given)
    report, normalized = normalize_for_output(report)
    if normalized:
        report["collection"]["output_text_normalizations"] = normalized
    try:
        write_json_atomic(args.output, report)
    except OutputError as exc:
        print(f"오류: 결과 파일을 저장하지 못했습니다 ({exc.kind}). 기존 결과 파일은 바꾸지 않았습니다.", file=sys.stderr)
        return EXIT_OUTPUT_ERROR
    c = report["collection"]
    print("Plugin·Skill 자체 정보 수집 결과 (읽기 전용, 코드 실행·서버 접속 없음)")
    print(f"수집 상태: {c['status']} ({c['outcome']})")
    print(f"플러그인 {c['plugin_count']}개, 스킬 {c['skill_count']}개, 저장된 출력에만 있는 플러그인 {c['runtime_only_plugin_count']}개·스킬 {c['runtime_only_skill_count']}개")
    for p in report["plugins"]:
        print(f"  - plugin {json.dumps(_short((p.get('identity', {}).get('id') or {}).get('original_value') or '(id 미확인)'))}  [{p['collection_status']}]")
    for s in report["skills"]:
        print(f"  - skill  {json.dumps(_short((s.get('identity', {}).get('name') or {}).get('original_value') or '(name 미확인)'))}  [{s['collection_status']}]")
    print(f"결과 저장: {args.output}")
    return EXIT_BY_STATUS[c["status"]]


if __name__ == "__main__":
    sys.exit(main())

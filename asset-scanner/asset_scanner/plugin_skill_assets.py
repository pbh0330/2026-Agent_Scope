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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import json5

from . import __version__
from .cli import _make_console_output_safe, _same_file
from .collector import (CollectionFailure, _find_duplicate_keys, collect_plugin_manifest, dotted_path, parse_config,
                        read_config, _type_name)
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
    "install_provenance",        # 설치 기록(SQLite 플러그인 인덱스)은 읽지 않았다
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
        if not path.is_file():
            return None, _issue("error", "file_not_found", "파일이 없거나 일반 파일이 아닙니다.")
        if path.stat().st_size > limit * 64:
            return None, _issue("error", "file_too_large", "파일이 너무 커서 읽지 않았습니다.")
        with open(path, "rb") as f:
            data = f.read(limit)
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, _issue("error", "not_utf8", "UTF-8 텍스트가 아닙니다.")
    except OSError as exc:
        return None, _issue("error", "read_failed", f"파일을 읽지 못했습니다 ({type(exc).__name__}).")


# ---- SKILL.md frontmatter ------------------------------------------------------------

_KV_RE = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s+(.*))?$")


def _scalar(text: str) -> Any:
    t = text.strip()
    if t == "":
        return ""
    if t[0] in "\"'" and len(t) >= 2 and t[-1] == t[0]:
        return t[1:-1]
    low = t.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"[-+]?\d+", t):
        return int(t)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?", t):
        return float(t)
    if t[0] in "{[":
        try:
            return json5.loads(t)
        except ValueError:
            pass
        if t[0] == "[" and t[-1] == "]" and "{" not in t and "[" not in t[1:]:
            # YAML 흐름 목록 `[a, b]`: 따옴표 없는 문자열 항목도 허용한다
            inner = t[1:-1].strip()
            return [] if not inner else [_scalar(x) for x in inner.split(",")]
        return _Unparsed()
    return t


class _Unparsed(Exception):
    """YAML의 블록 스칼라·앵커·복잡한 구조처럼 이 단순 파서가 해석하지 않는 값의 표식."""


def _parse_block(lines: list[str]) -> Any:
    """들여쓰기로 표현한 중첩 매핑(`key:`/`key: 값`)과 목록(`- 값`)만 읽는다. 그 밖의 문법이면 _Unparsed를 던진다."""
    rows: list[tuple[int, str]] = []
    for ln in lines:
        if "\t" in ln[: len(ln) - len(ln.lstrip())]:
            raise _Unparsed()
        if ln.strip() == "" or ln.lstrip().startswith("#"):
            continue
        rows.append((len(ln) - len(ln.lstrip(" ")), ln.strip()))
    pos = 0

    def parse(indent: int) -> Any:
        nonlocal pos
        if pos >= len(rows):
            raise _Unparsed()
        if rows[pos][1].startswith("- "):
            seq = []
            while pos < len(rows) and rows[pos][0] == indent and rows[pos][1].startswith("- "):
                val = _scalar(rows[pos][1][2:])
                if isinstance(val, _Unparsed) or (isinstance(val, str) and _KV_RE.match(val)):
                    raise _Unparsed()
                seq.append(val)
                pos += 1
            return seq
        mapping: dict[str, Any] = {}
        while pos < len(rows) and rows[pos][0] == indent:
            m = _KV_RE.match(rows[pos][1])
            if not m or rows[pos][1].startswith("- ") or m.group(1) in mapping:
                raise _Unparsed()
            key, rest = m.group(1), m.group(2)
            pos += 1
            if rest is None or rest.strip() == "":
                if pos < len(rows) and rows[pos][0] > indent:
                    mapping[key] = parse(rows[pos][0])
                else:
                    mapping[key] = None
            else:
                if rest.strip() in (">", "|", ">-", "|-", "&", "*") or rest.strip()[0] in "&*!":
                    raise _Unparsed()
                v = _scalar(rest)
                if isinstance(v, _Unparsed):
                    raise _Unparsed()
                mapping[key] = v
        if pos < len(rows) and rows[pos][0] > indent:
            raise _Unparsed()
        return mapping

    result = parse(rows[0][0]) if rows else None
    if pos != len(rows):
        raise _Unparsed()
    return result


def parse_frontmatter(text: str) -> tuple[dict | None, list[str], str | None]:
    """`---`로 둘러싸인 frontmatter를 보수적으로 해석한다. (값, 해석하지 못한 키, 문제 코드)

    문서는 YAML을 먼저 쓰고 실패하면 한 줄 파서를 쓴다고 밝힌다. 여기서는 YAML 라이브러리 없이 한 줄 `key: value`와
    JSON5 한 줄 값, `metadata:` 아래 들여쓴 블록(JSON5로 재해석)만 읽고 나머지는 추정하지 않고 키 이름만 남긴다.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, [], "frontmatter_missing"
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None, [], "frontmatter_unterminated"
    out: dict[str, Any] = {}
    unparsed: list[str] = []
    current: str | None = None
    block: list[str] = []

    def flush() -> None:
        nonlocal block
        if current is None:
            block = []
            return
        if block:
            try:
                out[current] = _parse_block(block)
            except _Unparsed:
                if current == "metadata":
                    # 문서: 중첩 metadata는 JSON 문자열로 펴서 JSON5로 다시 읽는다. 들여쓴 블록이 JSON5 한 덩어리이면 그렇게도 읽는다.
                    try:
                        out[current] = json5.loads(" ".join(s.strip() for s in block))
                        block = []
                        return
                    except ValueError:
                        pass
                out.pop(current, None)
                unparsed.append(current)
        block = []

    for line in lines[1:end]:
        if line.strip() == "" or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":
            block.append(line)
            continue
        flush()
        m = _KV_RE.match(line)
        if not m:
            current = None
            continue
        current = m.group(1)
        rest = m.group(2)
        if rest is None or rest.strip() == "" or rest.strip() in (">", "|", ">-", "|-"):
            out[current] = None
            if rest and rest.strip() in (">", "|", ">-", "|-"):
                unparsed.append(current)
                current = None
            continue
        val = _scalar(rest)
        if isinstance(val, _Unparsed):
            unparsed.append(current)
            out.pop(current, None)
        else:
            out[current] = val
    flush()
    for k in unparsed:
        if k in out and out[k] is None:
            out.pop(k, None)
    return out, sorted(set(unparsed)), None


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
    fm, unparsed, problem = parse_frontmatter(text or "")
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
    meta_shown = _sanitize(meta, "metadata.openclaw", red) if meta else {}
    name_raw = fm.get("name") if isinstance(fm.get("name"), str) else None
    item["identity"] = {"name": _identity(name_raw, shown.get("name"))}
    for req in ("name", "description"):
        if req not in shown:
            issues.append(_issue("warning", "required_field_missing", f"문서가 필수로 정한 frontmatter {req}가 없습니다.", field_path=req))
    item["folder_name"] = _text(red, folder, "folder_name")
    item["name_matches_folder"] = (name_raw == folder) if name_raw is not None else None
    item["frontmatter"] = shown
    item["metadata_openclaw"] = meta_shown
    item["frontmatter_keys"] = sorted(_seg(k) for k in fm)
    if unparsed:
        item["frontmatter_unparsed_keys"] = [_seg(k) for k in unparsed]
        issues.append(_issue("warning", "frontmatter_value_not_parsed", "YAML 블록 스칼라·중첩 값은 이 단순 파서가 해석하지 않아 키 이름만 남깁니다.",
                             keys=[_seg(k) for k in unparsed]))
    skill_key = meta.get("skillKey") if isinstance(meta.get("skillKey"), str) else name_raw
    item["config_key"] = {"value": skill_key if skill_key and not looks_like_secret_value(skill_key) else None,
                          "basis": "metadata.openclaw.skillKey" if isinstance(meta.get("skillKey"), str) else "name"}
    item["issues"] = issues
    item["redactions"] = red.redactions
    item["collection_status"] = "partial" if any(i["severity"] == "error" for i in issues) else "complete"
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
                pkg_info["declared_keys"] = [_seg(k) for k in pj][:60]
                ppath, _ = _safe_path(pkg_path)
                item["observed_from"]["package_json"] = {"source_path": ppath, "evidence_type": "static_file"}
    item["package"] = pkg_info
    item["supply_source"] = {
        "basis": "package.json과 openclaw.plugin.json에 적힌 값. 설치 기록(플러그인 인덱스)은 읽지 않았으므로 설치 경로·출처는 확인하지 않았습니다.",
        "package_name": (pkg_info or {}).get("name"), "package_version": (pkg_info or {}).get("version"),
        "manifest_version": declared.get("version"), "install_hints": (pkg_info or {}).get("install_hints"),
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
        target = (plugin_dir / raw_rel)
        if os.path.isabs(raw_rel) or not _within(plugin_dir, target):
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


def read_activation_settings(config_path: Path) -> dict:
    """`plugins.*`·`skills.*`에 선언된 활성화 설정을 읽는다. 선언일 뿐 실제 로딩·활성 상태가 아니다."""
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
    for dup in _find_duplicate_keys(root, ()):
        issues.append(_issue("error", "duplicate_key", "같은 키가 여러 번 선언되어 마지막 값만 읽었습니다.", field_path=dup))
    red = Redactor()
    plugins = root.get("plugins")
    if isinstance(plugins, dict):
        p: dict[str, Any] = {"declared_keys": [_seg(k) for k in plugins]}
        e = _bool_or_issue(plugins, "enabled", "plugins", issues)
        if e is not None:
            p["enabled"] = e
        for lk in ("allow", "deny"):
            if lk in plugins:
                v = _str_list(plugins[lk], f"plugins.{lk}", issues, red)
                if v is not None:
                    p[lk] = v
        entries: dict[str, dict] = {}
        ent = plugins.get("entries")
        if isinstance(ent, dict):
            for k, v in ent.items():
                rec: dict[str, Any] = {"entry_key": k}
                if isinstance(v, dict):
                    en = _bool_or_issue(v, "enabled", f"plugins.entries.{k}", issues)
                    if en is not None:
                        rec["enabled"] = en
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
        load = skills.get("load")
        if isinstance(load, dict) and "extraDirs" in load:
            v = _str_list(load["extraDirs"], "skills.load.extraDirs", issues, red)
            if v is not None:
                s["load_extraDirs"] = v
        sentries: dict[str, dict] = {}
        ent = skills.get("entries")
        if isinstance(ent, dict):
            for k, v in ent.items():
                rec = {"entry_key": k}
                if isinstance(v, dict):
                    en = _bool_or_issue(v, "enabled", f"skills.entries.{k}", issues)
                    if en is not None:
                        rec["enabled"] = en
                    if "apiKey" in v:
                        rec["apiKey"] = _cred_kind(v["apiKey"])
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
            "note": "설정에 적힌 값입니다. 실제 적용 여부는 확인하지 않았습니다."}


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


def read_plugins_list_json(path: Path) -> dict:
    data, err = _load_json(path)
    out: dict[str, Any] = {"observation": _observation(path, "openclaw plugins list --json"), "records": [], "issues": [], "status": "complete"}
    if err:
        out["status"] = "failed"; out["issues"].append(err)
        return out
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


def read_skills_list_json(path: Path) -> dict:
    data, err = _load_json(path)
    out: dict[str, Any] = {"observation": _observation(path, "openclaw skills list --json"), "records": [], "issues": [], "status": "complete"}
    if err:
        out["status"] = "failed"; out["issues"].append(err)
        return out
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


def _norm(p: str | None) -> str | None:
    if not p:
        return None
    try:
        return os.path.normcase(os.path.normpath(p))
    except (OSError, ValueError):
        return None


# ---- 전체 -------------------------------------------------------------------------------

def collect_assets(plugin_dirs: list[Path], skills_dirs: list[Path], config: Path | None,
                   plugins_list: Path | None, skills_list: Path | None) -> dict:
    settings = read_activation_settings(config) if config else None
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

    plist = read_plugins_list_json(plugins_list) if plugins_list else None
    slist = read_skills_list_json(skills_list) if skills_list else None
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
                                            "note": "저장된 plugins list --json 출력의 값입니다. 스캐너가 확인한 것이 아닙니다."}
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
                                            "note": "저장된 skills list --json 출력의 값입니다. 스캐너가 확인한 것이 아닙니다."}
            else:
                s["runtime_observation"] = None
    unmatched_plugins = [{"kind": "plugin", "source": "stored_plugins_list_json_only", "observation": plist["observation"], "observed": r["observed"],
                          "registered_names": r["registered_names"], "identity": r["identity"], "redactions": r["redactions"]}
                         for r in (plist["records"] if plist else []) if r["index"] not in matched_plugin_records]
    unmatched_skills = [{"kind": "skill", "source": "stored_skills_list_json_only", "observation": slist["observation"], "observed": r["observed"],
                         "identity": r["identity"], "redactions": r["redactions"]}
                        for r in (slist["records"] if slist else []) if r["index"] not in matched_skill_records]
    for lst in (plist, slist):
        if lst:
            for r in lst["records"]:
                r.pop("raw_root_dir", None); r.pop("raw_file_path", None)
    return {"plugins": plugin_items, "skills": skill_items, "runtime_only": {"plugins": unmatched_plugins, "skills": unmatched_skills},
            "activation_settings": settings, "stored_outputs": {"plugins_list": plist and {k: plist[k] for k in ("observation", "status", "issues")},
                                                                "skills_list": slist and {k: slist[k] for k in ("observation", "status", "issues")}},
            "issues": top_issues}


def summarize(collected: dict, inputs_given: bool) -> dict:
    items = collected["plugins"] + collected["skills"]
    stored = [v for v in (collected["stored_outputs"].get("plugins_list"), collected["stored_outputs"].get("skills_list")) if v]
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
                "runtime_observation": "저장된 openclaw 명령 출력의 값. 스캐너가 확인한 것이 아니며 관측 시각 미상",
                "operator_selected": "어떤 경로를 읽을지 사용자가 지정한 사실. 경로의 종류(번들·관리형 등)는 판단하지 않음",
            },
        },
        "collection": summarize(collected, inputs_given),
        "plugins": collected["plugins"], "skills": collected["skills"], "runtime_only": collected["runtime_only"],
        "activation_settings": collected["activation_settings"], "stored_outputs": collected["stored_outputs"],
        "issues": collected["issues"],
    }


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m asset_scanner.plugin_skill_assets",
                                description="지정한 플러그인/스킬 디렉터리와 설정·저장된 명령 출력에서 Plugin·Skill 자체 정보를 수집합니다 (읽기 전용, 내부 개발용 초안).")
    p.add_argument("--plugin-dir", action="append", default=[], type=Path, help="openclaw.plugin.json이 있는 플러그인 루트 디렉터리 (여러 번 가능)")
    p.add_argument("--skills-dir", action="append", default=[], type=Path, help="SKILL.md가 있는 skill 폴더, 또는 그런 폴더들의 부모 디렉터리 (여러 번 가능)")
    p.add_argument("--config", type=Path, help="plugins.*·skills.* 활성화 선언을 읽을 OpenClaw 설정 파일(JSON5)")
    p.add_argument("--plugins-list-json", type=Path, help="저장해 둔 `openclaw plugins list --json` 출력 파일")
    p.add_argument("--skills-list-json", type=Path, help="저장해 둔 `openclaw skills list --json` 출력 파일")
    p.add_argument("--output", required=True, type=Path, help="결과 JSON 경로")
    return p


def main(argv: list[str] | None = None) -> int:
    _make_console_output_safe()
    args = _parser().parse_args(argv)
    given = bool(args.plugin_dir or args.skills_dir or args.config or args.plugins_list_json or args.skills_list_json)
    if not given:
        _parser().error("입력이 없습니다. --plugin-dir, --skills-dir, --config, --plugins-list-json, --skills-list-json 중 하나 이상을 지정하세요.")
    for inp in [*args.plugin_dir, *args.skills_dir, *(x for x in (args.config, args.plugins_list_json, args.skills_list_json) if x)]:
        if _same_file(inp, args.output):
            print("오류: --output이 입력과 같은 경로입니다. 입력을 덮어쓰지 않습니다.", file=sys.stderr)
            return EXIT_OUTPUT_ERROR
    report = build_report(collect_assets(args.plugin_dir, args.skills_dir, args.config, args.plugins_list_json, args.skills_list_json), given)
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

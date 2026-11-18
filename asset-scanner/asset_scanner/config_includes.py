"""OpenClaw 설정의 `$include`를 읽기 전용으로 펼친다 (선택 기능: `--resolve-includes`).

근거: openclaw/openclaw 고정 커밋 `eb377ac59e6c9fd6c7705028034812becf00271b`(OpenClaw 2026.9.6)의
`src/config/includes.ts`, `src/infra/deep-merge.ts`, `src/infra/prototype-keys.ts`, `src/infra/plain-object.ts`,
`src/config/includes.test.ts`를 직접 읽고 같은 동작으로 구현했다(사본: output/openclaw-includes-src/). 문서(docs/gateway/config-secrets-env.md)와도 일치한다.

병합 규칙(공식 `deepMerge = mergeDeep(arrays: "concat", undefinedValues: "replace")`)
- `$include` 문자열 하나: 포함한 객체를 그 파일의 내용으로 대체(형제 키가 없으면 내용 그대로).
- `$include` 문자열 배열: 빈 객체에서 시작해 순서대로 병합(뒤가 앞을 이김). **빈 배열은 `{}`**(오류 아님, 형제 키는 그대로 남음).
- 형제 키: 포함 내용과 **같은 병합**으로 뒤에 합침. 포함 내용이 객체가 아닌데 형제 키가 있으면 오류.
- 병합: 둘 다 배열이면 **연결**(순서·중복 원소 그대로, 중복 제거 없음). 둘 다 객체면 키별 재귀 병합(기존 키는 병합, 새 키는 복사).
  그 밖(자료형이 다르거나 스칼라)은 뒤의 값이 앞의 값을 대체한다(null 포함). 객체 병합에서 `__proto__`·`prototype`·`constructor` 키는 버린다.
- 중첩 include 최대 10단계, 경로 널 문자 금지·해석 전후 4096자 미만, 파일 2MB 이하, 일반 파일·하드링크 아님, 순환 금지.
- 경로는 포함한 파일 기준으로 해석하되 **최상위 설정 파일 폴더 또는 명시적으로 추가 허용한 경계 안**(해석 전·실제 경로 모두)이어야 한다.

스캐너가 더한 것(공식에 없음): 읽는 파일 수 상한 64개, 값마다 출처(파일·include 사슬) 추적, 비밀처럼 보이는 키의 자리표시자 충돌 표시.
`OPENCLAW_INCLUDE_ROOTS`는 플랫폼 구분자(POSIX `:`, Windows `;`)로 나눈 추가 경계입니다. 절대 경로(또는 `~` 경로)만 받습니다.
구현하지 않는 것(지원 한계): 설정 안의 환경변수·SecretRef 해석, 쓰기 연동.

공식은 오류가 나면 설정 로드를 중단한다. 이 모듈은 중단하지 않고 사유를 `issues`에 기록하며, 해석하지 못한 `$include` 선언을 결과에 남겨
수집기·조회 기능이 불완전함을 알 수 있게 한다. 정상적으로 해석된 배열 병합은 이슈로 만들지 않는다.
모든 읽기는 일반 파일 하나씩이며 원문 파일 경로는 결과에 넣지 않고 최상위 설정 폴더 기준 상대 경로(POSIX 표기)만 남긴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

from .collector import CollectionFailure, _Obj, dotted_path, parse_config, read_config
from .redaction import Redactor

MAX_DEPTH = 10
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_PATH_CHARS = 4096
MAX_FILES = 64
MAIN_LABEL = "(top-level config)"
BLOCKED_KEYS = frozenset({"__proto__", "prototype", "constructor"})
OFFICIAL_SOURCE = "openclaw/openclaw eb377ac59e6c9fd6c7705028034812becf00271b src/config/includes.ts, src/infra/deep-merge.ts"

Origin = tuple[str, tuple[str, ...]]
_MAIN: Origin = (MAIN_LABEL, ())


@dataclass
class _Prov:
    """값과 함께 병합되는 출처 트리. `kids`는 객체면 키→출처, 배열이면 원소 순서의 출처 목록, 스칼라면 None."""

    origin: Origin | None
    kids: Any = None


@dataclass
class IncludeContext:
    """펼친 결과와 근거. `origins`는 (JSON 경로 튜플) → (파일 라벨, include 사슬). 부모와 출처가 다른 위치만 기록한다."""

    root: Any
    edges: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    origins: dict[tuple, Origin] = field(default_factory=dict)
    files_read: int = 0

    def origin_of(self, pointer: tuple) -> Origin:
        for n in range(len(pointer), -1, -1):
            hit = self.origins.get(tuple(pointer[:n]))
            if hit:
                return hit
        return _MAIN

    def field_origin_overrides(self, pointer: tuple) -> list[dict]:
        base_label = self.origin_of(pointer)[0]
        out = []
        for ptr, (label, _chain) in sorted(self.origins.items(), key=lambda kv: [str(p) for p in kv[0]]):
            if len(ptr) > len(pointer) and tuple(ptr[:len(pointer)]) == tuple(pointer) and label != base_label:
                out.append({"field_path": dotted_path(ptr), "file": label})
        return out


def _issue(code: str, message: str, **detail: Any) -> dict:
    return {"severity": "error", "code": code, "message": message, **detail}


def _kind(v: Any) -> str:
    return "object" if isinstance(v, dict) else "array" if isinstance(v, list) else "scalar"


def _copy_attrs(dst: _Obj, src: Any) -> None:
    dst.duplicate_keys = list(getattr(src, "duplicate_keys", []))
    dst.masked_keys = list(getattr(src, "masked_keys", []))


class _Resolver:
    def __init__(self, config_path: Path, allowed_roots: list[Path] | None = None):
        self.config_real = config_path.resolve()
        self.config_dir = self.config_real.parent
        self.ctx = IncludeContext(root=None)
        self.red = Redactor()
        self.boundaries = [(self.config_dir, self.config_dir)]
        roots = allowed_roots
        if roots is None:
            roots = [Path(x.strip()) for x in os.environ.get("OPENCLAW_INCLUDE_ROOTS", "").split(os.pathsep) if x.strip()]
        if len(roots) > MAX_FILES:
            self.ctx.issues.append(_issue("include_root_limit_exceeded", "추가 경계가 64개를 넘어 나머지는 허용하지 않았습니다."))
        for n, root in enumerate(roots[:MAX_FILES]):
            try:
                lexical = Path(root).expanduser()
                if not lexical.is_absolute() or "\x00" in str(lexical) or len(str(lexical)) >= MAX_PATH_CHARS:
                    raise ValueError("invalid root")
                real = lexical.resolve()
                if not real.is_dir():
                    raise ValueError("root not directory")
                pair = (Path(os.path.abspath(lexical)), real)
                if pair not in self.boundaries:
                    self.boundaries.append(pair)
            except (OSError, ValueError, RuntimeError):
                self.ctx.issues.append(_issue("include_root_invalid", "추가 허용 경계는 존재하는 절대 디렉터리여야 합니다. 값은 기록하지 않았습니다.", root_index=n))
        if len(self.boundaries) > 1:
            self.ctx.notes.append({"code": "additional_include_roots", "count": len(self.boundaries) - 1,
                                   "source": "OPENCLAW_INCLUDE_ROOTS" if allowed_roots is None else "caller_allowed_roots"})

    # ---- 경로·읽기 ------------------------------------------------------------------------------
    def _label(self, p: Path) -> str:
        try:
            return p.relative_to(self.config_dir).as_posix()
        except ValueError:
            for n, (_, root) in enumerate(self.boundaries[1:]):
                try:
                    return f"include-root[{n}]/" + p.relative_to(root).as_posix()
                except ValueError:
                    continue
            return "(outside)"

    def _inside_any(self, p: Path, which: int) -> bool:
        for pair in self.boundaries:
            try:
                p.relative_to(pair[which])
                return True
            except ValueError:
                pass
        return False

    def _locate(self, target: str, including: Path, where: str) -> Path | None:
        shown = self.red.sanitize_string(target, where)
        if "\x00" in target:
            self.ctx.issues.append(_issue("include_path_invalid", "경로에 널 문자가 있어 읽지 않았습니다.", field_path=where))
            return None
        if len(target) >= MAX_PATH_CHARS:
            self.ctx.issues.append(_issue("include_path_too_long", "경로가 4096자 이상이라 읽지 않았습니다.", field_path=where))
            return None
        try:
            cand = Path(target)
            lexical = Path(os.path.abspath(cand if cand.is_absolute() else including.parent / cand))
            if not self._inside_any(lexical, 0):
                self.ctx.issues.append(_issue("include_path_outside_root", "허용한 경계 밖의 경로라 읽지 않았습니다.", field_path=where, target=shown))
                return None
            full = lexical.resolve()
        except (OSError, ValueError, RuntimeError):
            self.ctx.issues.append(_issue("include_path_invalid", "경로를 해석하지 못했습니다.", field_path=where, target=shown))
            return None
        if len(str(full)) >= MAX_PATH_CHARS:
            self.ctx.issues.append(_issue("include_path_too_long", "해석된 경로가 4096자 이상이라 읽지 않았습니다.", field_path=where))
            return None
        if not self._inside_any(full, 1):
            self.ctx.issues.append(_issue("include_path_outside_root", "실제 파일 경로가 허용한 경계를 벗어나 읽지 않았습니다.", field_path=where, target=shown))
            return None
        return full

    def _read(self, full: Path, where: str, shown: str) -> Any:
        if not full.exists():
            self.ctx.issues.append(_issue("include_file_not_found", "포함할 파일이 없습니다.", field_path=where, target=shown))
            return None
        if not full.is_file():
            self.ctx.issues.append(_issue("include_not_a_file", "포함할 경로가 일반 파일이 아닙니다.", field_path=where, target=shown))
            return None
        try:
            st = full.stat()
        except OSError:
            self.ctx.issues.append(_issue("include_read_failed", "포함할 파일을 읽지 못했습니다.", field_path=where, target=shown))
            return None
        if st.st_size > MAX_FILE_BYTES:
            self.ctx.issues.append(_issue("include_file_too_large", "포함할 파일이 2MB를 넘어 읽지 않았습니다.", field_path=where, target=shown, bytes=st.st_size))
            return None
        if getattr(st, "st_nlink", 1) > 1:
            self.ctx.issues.append(_issue("include_hardlink_rejected", "포함할 파일이 하드링크 별칭이라 읽지 않았습니다(공식 보안 검사: 일반 파일·크기·하드링크 아님).",
                                          field_path=where, target=shown))
            return None
        try:
            tree = parse_config(read_config(full))
        except CollectionFailure as fail:
            self.ctx.issues.append(_issue("include_parse_error", "포함한 파일을 해석하지 못했습니다.", field_path=where, target=shown,
                                          reason_code=fail.reason.get("code"), **{k: v for k, v in fail.reason.items() if k in ("line", "column")}))
            return None
        self.ctx.files_read += 1
        return tree

    # ---- 병합(공식 deep-merge.ts) ------------------------------------------------------------------
    def _note(self, code: str, ptr: tuple) -> None:
        entry = {"code": code, "field_path": dotted_path(ptr) if ptr else "(root)"}
        if entry not in self.ctx.notes:
            self.ctx.notes.append(entry)

    def _sanitize(self, v: Any, p: _Prov, ptr: tuple) -> tuple[Any, _Prov]:
        """공식 sanitizePlainObject: 객체의 금지 키를 (중첩 객체까지, 배열 안은 제외) 버린 복사본."""
        if not isinstance(v, dict):
            return v, p
        out = _Obj()
        _copy_attrs(out, v)
        kids: dict[str, _Prov] = {}
        for k, val in v.items():
            if k in BLOCKED_KEYS:
                self._note("blocked_key_dropped", ptr + (k,))
                continue
            sv, sp = self._sanitize(val, p.kids[k], ptr + (k,))
            out[k], kids[k] = sv, sp
        return out, _Prov(p.origin, kids)

    def _merge(self, bv: Any, bp: _Prov, ov: Any, op: _Prov, ptr: tuple) -> tuple[Any, _Prov]:
        if isinstance(bv, list) and isinstance(ov, list):
            return bv + ov, _Prov(bp.origin or op.origin, list(bp.kids) + list(op.kids))      # 연결: 순서·중복 보존
        if not (isinstance(bv, dict) and isinstance(ov, dict)):
            if bp.origin is not None and _kind(bv) != _kind(ov):
                self._note("type_conflict_later_value_wins", ptr)
            return ov, op                                                                       # 뒤의 값이 대체
        merged, mp = self._sanitize(bv, bp, ptr)
        kids: dict[str, _Prov] = mp.kids
        clash = set(merged.masked_keys) & set(getattr(ov, "masked_keys", []))
        if clash:
            self.ctx.issues.append(_issue("masked_key_collision", "서로 다른 파일에서 비밀처럼 보이는 키가 같은 자리표시자로 가려져 합쳐졌을 수 있습니다.",
                                          field_path=dotted_path(ptr) if ptr else "(root)"))
        for k in getattr(ov, "masked_keys", []):
            if k not in merged.masked_keys:
                merged.masked_keys.append(k)
        for k in getattr(ov, "duplicate_keys", []):
            if k not in merged.duplicate_keys:
                merged.duplicate_keys.append(k)
        for k, v in ov.items():
            if k in BLOCKED_KEYS:
                self._note("blocked_key_dropped", ptr + (k,))
                continue
            cur = merged.get(k)
            vp = op.kids[k]
            if isinstance(v, dict):
                if isinstance(cur, dict):
                    merged[k], kids[k] = self._merge(cur, kids[k], v, vp, ptr + (k,))
                else:
                    if k in merged and _kind(cur) != "object":
                        self._note("type_conflict_later_value_wins", ptr + (k,))
                    merged[k], kids[k] = self._sanitize(v, vp, ptr + (k,))
            elif isinstance(v, list) and isinstance(cur, list):
                merged[k], kids[k] = cur + v, _Prov(kids[k].origin or vp.origin, list(kids[k].kids) + list(vp.kids))
            else:
                if k in merged and _kind(cur) != _kind(v):
                    self._note("type_conflict_later_value_wins", ptr + (k,))
                merged[k], kids[k] = v, vp
        return merged, _Prov(bp.origin or op.origin, kids)

    # ---- 펼치기(공식 IncludeProcessor) ------------------------------------------------------------
    def expand(self, node: Any, file: Path, label: str, chain: tuple[str, ...], depth: int, ptr: tuple, stack: tuple[Path, ...]) -> tuple[Any, _Prov]:
        here: Origin = (label, chain)
        if isinstance(node, list):
            items = [self.expand(v, file, label, chain, depth, ptr + (i,), stack) for i, v in enumerate(node)]
            return [v for v, _ in items], _Prov(here, [p for _, p in items])
        if not isinstance(node, dict):
            return node, _Prov(here, None)
        siblings = {k: v for k, v in node.items() if k != "$include"}
        rest = _Obj()
        _copy_attrs(rest, node)
        rest_kids: dict[str, _Prov] = {}
        for k, v in siblings.items():
            rest[k], rest_kids[k] = self.expand(v, file, label, chain, depth, ptr + (k,), stack)
        rest_p = _Prov(here, rest_kids)
        if "$include" not in node:
            return rest, rest_p
        where = dotted_path(ptr) if ptr else "(root)"
        spec = node["$include"]
        targets = [spec] if isinstance(spec, str) else spec if isinstance(spec, list) and all(isinstance(t, str) for t in spec) else None
        if targets is None:
            self.ctx.issues.append(_issue("include_type_invalid", "$include는 문자열 또는 문자열 배열이어야 합니다.", field_path=where))
            return self._keep_directive(rest, rest_p, spec, here)
        if depth >= MAX_DEPTH:
            self.ctx.issues.append(_issue("include_depth_exceeded", "중첩 include가 10단계를 넘어 읽지 않았습니다.", field_path=where))
            return self._keep_directive(rest, rest_p, spec, here)
        merged: Any = _Obj()
        mp = _Prov(None, {})
        # 빈 배열은 공식 구현에서 reduce(deepMerge, {})의 초기값 {}가 그대로 결과다(오류 아님). 형제 키가 있으면 deepMerge({}, rest).
        have = not targets
        ok_all = True
        for t in targets:
            shown = self.red.sanitize_string(t, where)
            full = self._locate(t, file, where)
            if full is None:
                ok_all = False
                continue
            if full in stack or full == self.config_real or full == file.resolve():
                self.ctx.issues.append(_issue("include_circular", "순환 include라 읽지 않았습니다.", field_path=where, target=shown))
                ok_all = False
                continue
            if self.ctx.files_read >= MAX_FILES:
                self.ctx.issues.append(_issue("include_file_limit", f"읽은 include 파일이 {MAX_FILES}개를 넘어 더 읽지 않았습니다(스캐너 상한).", field_path=where, target=shown))
                ok_all = False
                continue
            tree = self._read(full, where, shown)
            if tree is None:
                ok_all = False
                continue
            flabel = self._label(full)
            new_chain = chain + (flabel,)
            self.ctx.edges.append({"declared_in": label, "field_path": where, "target": flabel, "depth": depth + 1})
            value, vp = self.expand(tree, full, flabel, new_chain, depth + 1, ptr, stack + (full, file.resolve()))
            merged, mp = self._merge(merged, mp, value, vp, ptr)
            have = True
        if not have:
            return self._keep_directive(rest, rest_p, spec, here)
        if not siblings:
            result, rp = merged, mp
        else:
            if not isinstance(merged, dict):
                self.ctx.issues.append(_issue("include_non_object_with_siblings", "형제 키가 있는데 include 내용이 객체가 아닙니다(공식 구현도 오류).", field_path=where))
                return merged, mp
            result, rp = self._merge(merged, mp, rest, rest_p, ptr)
        if not ok_all and isinstance(result, dict):
            result["$include"] = spec                     # 일부만 읽었으므로 선언을 남겨 불완전함을 알린다
            rp.kids["$include"] = _Prov(here, None)
        return result, rp

    @staticmethod
    def _keep_directive(rest: _Obj, rest_p: _Prov, spec: Any, here: Origin) -> tuple[Any, _Prov]:
        rest["$include"] = spec                           # 해석하지 못한 선언은 남겨 수집기가 unresolved로 기록하게 한다
        rest_p.kids["$include"] = _Prov(here, None)
        return rest, rest_p

    # ---- 출처 평탄화 ---------------------------------------------------------------------------------
    def flatten(self, v: Any, p: _Prov, ptr: tuple, parent: Origin) -> None:
        origin = p.origin or parent
        if origin != parent:
            self.ctx.origins[ptr] = origin
        if isinstance(v, dict) and isinstance(p.kids, dict):
            for k, val in v.items():
                if k in p.kids:
                    self.flatten(val, p.kids[k], ptr + (k,), origin)
        elif isinstance(v, list) and isinstance(p.kids, list):
            for i, val in enumerate(v):
                if i < len(p.kids):
                    self.flatten(val, p.kids[i], ptr + (i,), origin)


def resolve_includes(config_path: Path, root: Any, allowed_roots: list[Path] | None = None) -> IncludeContext:
    """이미 파싱한 최상위 설정 `root`의 `$include`를 펼친다. 실패한 include는 선언을 남기고 `issues`에 사유를 기록한다."""
    r = _Resolver(config_path, allowed_roots)
    value, prov = r.expand(root, r.config_real, MAIN_LABEL, (), 0, (), ())
    r.ctx.root = value
    r.flatten(value, prov, (), _MAIN)
    return r.ctx

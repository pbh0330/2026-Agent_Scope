"""비밀값 가림과 미해석 참조 감지.

원칙
- 비밀값일 가능성이 있으면 보수적으로 가리고, 가린 위치(field_path)와 사유(reason)만 남긴다.
- 가림은 유용한 정보(포트, 패키지명, 경로, 비밀 없는 URL, 인증과 무관한 헤더)를 최대한 보존한다.
- 환경변수 참조(`${VAR}`)는 이름만 남긴다. `${VAR:-기본값}`의 기본값은 `<redacted>`로 바꾸고 사유를 남긴다.
- 실제 환경변수 값을 읽거나 펼치지 않는다. 셸 명령 문자열은 해석·실행하지 않고 통째로 가린다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit, urlunsplit

REDACTED = "<redacted>"

# OpenClaw 환경변수 치환 문법 (docs.openclaw.ai/gateway/config-secrets-env, 2026-09-29 기준)
# - 대문자 이름만 인식: [A-Z_][A-Z0-9_]*
# - `${VAR:-fallback}`의 fallback은 문자 그대로이며 `$`나 `{`를 포함할 수 없다.
#   따라서 `${A:-${B}}`에서 바깥쪽은 표현식이 아니고 안쪽 `${B}`만 참조다.
# - `$${VAR}`, `$${VAR:-x}`는 이스케이프된 문자 그대로의 값이다.
# group(1): 변수 이름, group(2): fallback 텍스트 (없으면 None, `${VAR:-}`면 "")
ENV_REF_RE = re.compile(r"(?<!\$)\$\{([A-Z_][A-Z0-9_]*)(?::-([^${}]*))?\}")

SECRETREF_SOURCES = frozenset({"env", "file", "exec", "store"})
SECRETREF_KEYS = frozenset({"source", "provider", "id"})

# 이름만 보고 비밀값을 담는다고 판단하는 키·플래그·헤더 이름 (대소문자 무시).
_SECRET_NAME_RE = re.compile(
    r"(token|secret|passw(or)?d|pwd|api[-_]?key|apikey|access[-_]?key|private[-_]?key"
    r"|auth|bearer|credential|cookie|session|signature|(^|[-_])key$)",
    re.IGNORECASE,
)

# 값 자체의 모양으로 판단하는 알려진 토큰 형식.
_TOKEN_PATTERNS = [
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")),
    ("github_token", re.compile(r"\b(ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{8,}|\bgithub_pat_[A-Za-z0-9_]{8,}")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{8,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    ("bearer_credential", re.compile(r"\bBearer\s+\S+", re.IGNORECASE)),
]

# 길고 무작위해 보이는 문자열 (경로·패키지명과 구분하기 위해 문자 집합을 제한).
_HIGH_ENTROPY_RE = re.compile(r"^[A-Za-z0-9+/=_-]{32,}$")

# 문자열 안 어디에 있든 URL을 찾는다 (`--endpoint=https://...` 등).
_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>]+")

# `Name: value` 형태의 헤더 문자열 (`-H`, `--header` 값 등).
_HEADER_RE = re.compile(r"^(\s*)([A-Za-z0-9-]+)(\s*:\s*)(\S.*)$", re.DOTALL)

# 다음 인자를 셸 명령 문자열로 받는 플래그 (sh -c, cmd /c, powershell -Command 등).
_SHELL_FLAGS = frozenset({"-c", "/c", "/k", "-command", "--command", "-encodedcommand"})


def is_secret_name(name: str) -> bool:
    return bool(_SECRET_NAME_RE.search(name))


def _looks_high_entropy(value: str) -> bool:
    if not _HIGH_ENTROPY_RE.match(value):
        return False
    has_digit = any(c.isdigit() for c in value)
    has_alpha = any(c.isalpha() for c in value)
    return has_digit and has_alpha


def looks_like_secret_value(value: str) -> bool:
    """식별자(등록키, 참조 이름 등) 자리에 비밀값처럼 보이는 문자열이 들어왔는가."""
    return _looks_high_entropy(value) or any(p.search(value) for _, p in _TOKEN_PATTERNS)


def _pure_ref_without_fallback(value: str) -> bool:
    """값 전체가 기본값 없는 참조(`${VAR}` 또는 `${VAR:-}`)인가."""
    m = ENV_REF_RE.fullmatch(value)
    return bool(m) and not m.group(2)


@dataclass
class Redactor:
    """가림 처리와 참조 감지 결과를 한 서버 항목 단위로 모은다."""

    redactions: list[dict] = field(default_factory=list)
    env_refs: list[dict] = field(default_factory=list)

    def _note(self, field_path: str, reason: str) -> None:
        entry = {"field_path": field_path, "reason": reason}
        if entry not in self.redactions:
            self.redactions.append(entry)

    # ---- 참조 ---------------------------------------------------------------

    def collect_env_refs(self, value: str, field_path: str) -> None:
        for m in ENV_REF_RE.finditer(value):
            name = m.group(1)
            if looks_like_secret_value(name):
                name = REDACTED
                self._note(field_path, "ref_name_looks_like_secret")
            ref = {"kind": "env_var", "name": name, "field_path": field_path}
            if ref not in self.env_refs:
                self.env_refs.append(ref)

    def _strip_env_defaults(self, value: str, field_path: str) -> str:
        def repl(m: re.Match) -> str:
            name, fallback = m.group(1), m.group(2)
            if fallback is None:
                return m.group(0)
            if fallback == "":
                return "${" + name + ":-}"
            self._note(field_path, "env_default_value_removed")
            return "${" + name + ":-" + REDACTED + "}"

        return ENV_REF_RE.sub(repl, value)

    # ---- 문자열 가림 ---------------------------------------------------------

    def _mask_token_patterns(self, value: str, field_path: str) -> str:
        # 환경변수 참조 자리는 비밀값이 아니므로 잠시 보호한다.
        protected: list[str] = []

        def protect(m: re.Match) -> str:
            protected.append(m.group(0))
            return f"\x00{len(protected) - 1}\x00"

        work = ENV_REF_RE.sub(protect, value)
        for reason, pattern in _TOKEN_PATTERNS:
            if pattern.search(work):
                work = pattern.sub(REDACTED, work)
                self._note(field_path, f"token_pattern:{reason}")
        for i, original in enumerate(protected):
            work = work.replace(f"\x00{i}\x00", original)
        return work

    def sanitize_url(self, value: str, field_path: str) -> str:
        try:
            parts = urlsplit(value)
        except ValueError:
            self._note(field_path, "unparseable_url_withheld")
            return REDACTED
        if not parts.scheme or not parts.netloc:
            return value
        netloc = parts.netloc
        if "@" in netloc:
            netloc = REDACTED + "@" + netloc.rsplit("@", 1)[1]
            self._note(field_path, "url_userinfo")
        query = parts.query
        if query:
            pairs = parse_qsl(query, keep_blank_values=True)
            if pairs:
                query = "&".join(f"{k}={REDACTED}" for k, _ in pairs)
            else:
                query = REDACTED
            self._note(field_path, "url_query_values")
        fragment = parts.fragment
        if fragment:
            fragment = REDACTED
            self._note(field_path, "url_fragment")
        path_segments = []
        for seg in parts.path.split("/"):
            if seg and seg != REDACTED and looks_like_secret_value(seg):
                path_segments.append(REDACTED)
                self._note(field_path, "url_path_token")
            else:
                path_segments.append(seg)
        return urlunsplit((parts.scheme, netloc, "/".join(path_segments), query, fragment))

    def _compound_has_secret(self, value: str, field_path: str) -> bool:
        """공백으로 나뉜 여러 단어가 든 문자열을 단어 단위로 검사한다 (해석·실행하지 않음)."""
        tokens = value.split()
        if len(tokens) < 2:
            return False
        probe = Redactor()
        return probe.sanitize_args(tokens, field_path) != tokens

    def sanitize_string(self, value: str, field_path: str) -> str:
        """단일 문자열 값(command, cwd, transport, url, 인자 하나 등)을 가린다."""
        self.collect_env_refs(value, field_path)
        header = _HEADER_RE.match(value)
        if header and is_secret_name(header.group(2)) and not _pure_ref_without_fallback(header.group(4)):
            self._note(field_path, "auth_header_value")
            return header.group(1) + header.group(2) + header.group(3) + REDACTED
        if self._compound_has_secret(value, field_path):
            self._note(field_path, "compound_arg_with_secret_withheld")
            return REDACTED
        out = self._strip_env_defaults(value, field_path)
        out = self._mask_token_patterns(out, field_path)
        out = _URL_RE.sub(lambda m: self.sanitize_url(m.group(0), field_path), out)
        if out == value and _looks_high_entropy(out):
            self._note(field_path, "high_entropy_value")
            out = REDACTED
        return out

    def sanitize_args(self, args: list[str], base_path: str) -> list[str]:
        """명령 인자 목록을 가린다.

        처리 형태: `--token X`, `--token=X`, `API_KEY=X`, `--opt=URL`, `-H "Name: value"`,
        `sh -c "명령 문자열"`(통째로 가림), 공백이 든 복합 인자(비밀이 보이면 통째로 가림).
        """
        out: list[str] = []
        redact_next = False
        prev = ""
        for i, arg in enumerate(args):
            path = f"{base_path}[{i}]"
            after_shell_flag = prev.lower() in _SHELL_FLAGS
            prev = arg
            if redact_next:
                redact_next = False
                self.collect_env_refs(arg, path)
                if not _pure_ref_without_fallback(arg):
                    out.append(REDACTED)
                    self._note(path, "value_after_secret_flag")
                    continue
            if after_shell_flag and any(c.isspace() for c in arg):
                self.collect_env_refs(arg, path)
                out.append(REDACTED)
                self._note(path, "shell_command_string_withheld")
                continue
            flag_match = re.match(r"^(--?[A-Za-z0-9][A-Za-z0-9_.-]*)(=(.*))?$", arg, re.DOTALL)
            if flag_match:
                flag, value = flag_match.group(1), flag_match.group(3)
                if is_secret_name(flag.lstrip("-")):
                    if value is None:
                        out.append(arg)
                        redact_next = True
                        continue
                    self.collect_env_refs(value, path)
                    if _pure_ref_without_fallback(value):
                        out.append(arg)
                    else:
                        out.append(f"{flag}={REDACTED}")
                        self._note(path, "secret_flag_value")
                    continue
                if value is not None:
                    out.append(f"{flag}={self.sanitize_string(value, path)}")
                    continue
            kv_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", arg, re.DOTALL)
            if kv_match and is_secret_name(kv_match.group(1)):
                value = kv_match.group(2)
                self.collect_env_refs(value, path)
                if _pure_ref_without_fallback(value):
                    out.append(arg)
                else:
                    out.append(f"{kv_match.group(1)}={REDACTED}")
                    self._note(path, "secret_assignment_value")
                continue
            out.append(self.sanitize_string(arg, path))
        return out


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def classify_secret_ref(value: object) -> tuple[str, object]:
    """OpenClaw SecretRef 객체인지 판정한다.

    - ("valid", {source, provider?, id}): 형식이 맞는 참조
    - ("invalid", [문제 목록]): 키 구성은 SecretRef(`source`·`provider`·`id`만)인데 값 형식이 틀림.
      문제 목록에는 필드 이름과 자료형만 담고 원래 값은 담지 않는다.
    - ("not_ref", None): SecretRef가 아님. `source` 키가 있어도 다른 키가 섞인 일반 설정 객체는 여기에 해당.
    """
    if not isinstance(value, dict) or "source" not in value or not set(value) <= SECRETREF_KEYS:
        return "not_ref", None
    problems: list[dict] = []
    source = value.get("source")
    if not isinstance(source, str):
        problems.append({"field": "source", "problem": "wrong_type", "actual": _type_name(source)})
    elif source not in SECRETREF_SOURCES:
        problems.append({"field": "source", "problem": "unsupported_value"})
    if "provider" in value and not isinstance(value["provider"], str):
        problems.append({"field": "provider", "problem": "wrong_type", "actual": _type_name(value["provider"])})
    if "id" not in value:
        problems.append({"field": "id", "problem": "missing"})
    elif not isinstance(value["id"], str):
        problems.append({"field": "id", "problem": "wrong_type", "actual": _type_name(value["id"])})
    if problems:
        return "invalid", problems
    ref = {"source": source}
    for key in ("provider", "id"):
        if key in value:
            ref[key] = REDACTED if looks_like_secret_value(value[key]) else value[key]
    return "valid", ref


def secret_ref_summary(value: object) -> dict | None:
    """형식이 맞는 SecretRef면 참조 정보만 돌려준다. 그 외(잘못된 참조 포함)는 None."""
    kind, detail = classify_secret_ref(value)
    return detail if kind == "valid" else None

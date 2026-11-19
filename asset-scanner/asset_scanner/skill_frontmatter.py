"""SKILL.md frontmatter용 한도 있는 YAML 1.2 핵심 자료형 해석기.

근거: OpenClaw 2026.9.6 `docs/tools/skills.md`. PyYAML은 구문 노드 구성에만 사용하고 객체 생성자는 호출하지 않는다.

지원: 중첩 매핑, 목록(`- 값`, `- key: 값` 매핑 항목), 블록 스칼라(`|`·`>`와 chomping `-`/`+`, 들여쓰기 지시자 1~9),
여러 줄 평문·큰따옴표·작은따옴표 스칼라(접기), 흐름 목록/객체(JSON5), 주석(` #`), 숫자·불리언·null.
추가 지원: 한도 안의 비순환 앵커·별칭, 매핑 병합, YAML 흐름 매핑, 핵심 자료형 태그.
미지원: Python/사용자 정의 태그, 순환 별칭, 복합 키, JSON 밖 자료형, 다중 문서. 기존 JSON5 metadata 표기는 호환 해석한다.

한도: 중첩 깊이 20, 노드 2000개, 문자열 하나 64KiB. 한도를 넘으면 그 키만 `unparsed`로 남기고 `limit_hits`에 사유를 기록한다.
같은 키가 한 매핑에서 두 번 나오면 `duplicate_keys`에 경로를 기록한다(값은 마지막 것).
"""

from __future__ import annotations

import json
import re
from typing import Any

import json5

MAX_DEPTH = 20
MAX_NODES = 2000
MAX_STR = 64 * 1024

_KEY = r"(?:[A-Za-z0-9_.-]+|\"[^\"\n]*\"|'[^'\n]*')"
_KV_RE = re.compile(rf"^({_KEY}):(?:\s+(.*))?$")
_BLOCK_RE = re.compile(r"^([|>])([+-]?)([1-9]?)([+-]?)(?:\s+#.*)?$")


class Unparsed(Exception):
    """이 해석기가 해석하지 않는 문법의 표식."""


class _Limit(Unparsed):
    def __init__(self, what: str):
        super().__init__(what)
        self.what = what


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _significant(line: str) -> bool:
    s = line.strip()
    return s != "" and not s.startswith("#")


def _strip_comment(text: str) -> str:
    """따옴표 밖의 ` #` 이후 주석을 제거한다(YAML: 앞에 공백이 있는 #만 주석)."""
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                if quote == "'" and text[i:i + 2] == "''":
                    i += 2
                    continue
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#" and (i == 0 or text[i - 1].isspace()):
            return text[:i].rstrip()
        i += 1
    return text


def _key_name(raw: str) -> str:
    return raw[1:-1] if raw[:1] in "\"'" else raw


class _FlowMap(dict):
    """JSON5의 마지막 값과 함께 중복 키의 증거도 보존한다."""

    def __init__(self, pairs):
        super().__init__()
        self.duplicate_keys = []
        for key, value in pairs:
            if key in self:
                self.duplicate_keys.append(key)
            self[key] = value


def _flow_marks(text: str):
    """문자열·JSON5 주석 밖의 구조 문자만 읽는다. 재귀 파싱 전 깊이를 제한한다."""
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                if quote == "'" and text[i:i + 2] == "''":
                    i += 2
                    continue
                quote = None
        elif c in "\"'":
            quote = c
        elif text[i:i + 2] == "//":
            end = text.find("\n", i + 2)
            if end < 0:
                return
            i = end
        elif text[i:i + 2] == "/*":
            end = text.find("*/", i + 2)
            if end < 0:
                raise Unparsed()
            i = end + 2
            continue
        elif c in "{}[],":
            yield i, c
        i += 1


def _flow_preflight(text: str, depth: int = 0) -> None:
    stack = []
    for _, c in _flow_marks(text):
        if c in "[{":
            stack.append(c)
            if depth + len(stack) > MAX_DEPTH:
                raise _Limit("depth")
        elif c in "]}":
            if not stack or stack.pop() != {"]": "[", "}": "{"}[c]:
                raise Unparsed()
    if stack:
        raise Unparsed()


def _flow_sequence_parts(text: str) -> list[str]:
    parts, start, level = [], 1, 0
    for i, c in _flow_marks(text):
        if c in "[{":
            level += 1
        elif c in "]}":
            level -= 1
        elif c == "," and level == 1:
            parts.append(text[start:i].strip())
            start = i + 1
    tail = text[start:-1].strip()
    if tail:
        parts.append(tail)
    if any(not part for part in parts):
        raise Unparsed()
    return parts


def scalar(text: str) -> Any:
    """한 줄 스칼라·흐름 값. 해석할 수 없으면 Unparsed."""
    t = text.strip()
    if t == "":
        return ""
    if t[0] == '"' and len(t) >= 2 and t[-1] == '"':
        try:
            return json.loads(t)
        except ValueError:
            # JSON과 호환되지 않는 YAML escape는 이 부분집합에서 추측하지 않는다.
            raise Unparsed() from None
    if t[0] == "'" and len(t) >= 2 and t[-1] == "'":
        if "'" in t[1:-1].replace("''", ""):
            raise Unparsed()
        return t[1:-1].replace("''", "'")
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
        _flow_preflight(t)
        try:
            return json5.loads(t, object_pairs_hook=_FlowMap)
        except (ValueError, RecursionError):
            pass
        if t[0] == "[" and t[-1] == "]":
            return [scalar(x) for x in _flow_sequence_parts(t)]
        raise Unparsed()
    if t[0] in "&*!@`" or t.startswith("<<"):
        raise Unparsed()
    return t


class _State:
    def __init__(self) -> None:
        self.nodes = 0
        self.duplicate_keys: list[str] = []
        self.alias_like = 0

    def node(self) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise _Limit("nodes")


def _check_len(s: str) -> str:
    if len(s) > MAX_STR:
        raise _Limit("string")
    return s


def _read_flow(st: _State, text: str, depth: int, path: list[str]) -> Any:
    if text[:1] not in ("[", "{"):
        raise Unparsed()
    _flow_preflight(text, depth)
    value = scalar(text)

    def visit(item, level, field_path, count=True):
        if level > MAX_DEPTH:
            raise _Limit("depth")
        if count:
            st.node()
        if isinstance(item, dict):
            for key in getattr(item, "duplicate_keys", []):
                st.duplicate_keys.append(".".join(field_path + [key]))
            for key, child in item.items():
                _check_len(key)
                visit(child, level + 1, field_path + [key])
        elif isinstance(item, list):
            for i, child in enumerate(item):
                visit(child, level + 1, field_path[:-1] + [f"{field_path[-1]}[{i}]"])
        elif isinstance(item, str):
            _check_len(item)

    visit(value, depth, path, count=False)
    return value


# ---- 블록 스칼라 -----------------------------------------------------------------------------------------

def _block_scalar(header: re.Match, child: list[str], parent_indent: int) -> str:
    style = header.group(1)
    chomp = header.group(2) or header.group(4)
    digit = header.group(3)
    sig = [l for l in child if l.strip() != ""]
    if not sig:
        return "" if chomp != "+" else "\n" * sum(1 for l in child if l.strip() == "")
    if any("\t" in l[:_indent(l)] for l in sig):
        raise Unparsed()
    content_indent = parent_indent + int(digit) if digit else min(_indent(l) for l in sig[:1])
    if not digit and content_indent <= parent_indent:
        raise Unparsed()
    rows: list[str] = []
    for l in child:
        if l.strip() == "":
            rows.append("")
            continue
        if _indent(l) < content_indent:
            raise Unparsed()
        rows.append(l[content_indent:])
    trailing = 0
    while rows and rows[-1] == "":
        rows.pop()
        trailing += 1
    if style == "|":
        body = "\n".join(rows)
    else:
        body, pending, prev_more = "", 0, False
        for r in rows:
            if r == "":
                pending += 1
                continue
            more = r.startswith(" ")
            if body == "":
                body = "\n" * pending + r
            elif pending:
                body += "\n" * (pending + int(more or prev_more)) + r
            elif more or prev_more:
                body += "\n" + r
            else:
                body += " " + r
            pending, prev_more = 0, more
    if chomp == "-" or body == "" and chomp != "+":
        out = body
    elif chomp == "+":
        out = body + "\n" * (1 + trailing) if body else "\n" * trailing
    else:
        out = body + "\n"
    return _check_len(out)


# ---- 값 ---------------------------------------------------------------------------------------------------

def _fold_lines(first: str, lines: list[str]) -> str:
    text, pending = first, 0
    for line in lines:
        part = line.strip()
        if not part:
            pending += 1
            continue
        text += ("\n" * pending if pending else " ") + part
        pending = 0
    return text


def _value(st: _State, rest: str | None, child: list[str], parent_indent: int, depth: int, path: list[str]) -> Any:
    st.node()
    rest = (rest or "").strip()
    if rest != "":
        rest = _strip_comment(rest)
    has_child = any(_significant(l) for l in child)
    if rest == "":
        return _block(st, child, depth + 1, path) if has_child else None
    m = _BLOCK_RE.match(rest)
    if m:
        return _block_scalar(m, child, parent_indent)
    if rest[0] in "|>":
        raise Unparsed()
    if rest[0] in "&*!@`" or rest.startswith("<<"):
        st.alias_like += 1
        raise Unparsed()
    if rest[0] in "\"'":
        q = rest[0]
        text = rest
        if not (len(rest) >= 2 and rest.endswith(q) and not (q == '"' and rest.endswith('\\"') and not rest.endswith('\\\\"'))):
            text = _fold_lines(rest, child)
            if not (len(text) >= 2 and text.endswith(q)):
                raise Unparsed()
        # YAML flow scalars fold blank paragraphs to LF. JSON strings cannot
        # contain literal LF, so escape these before the existing decoder.
        v = scalar(text.replace("\n", "\\n")) if q == '"' else scalar(text)
        return _check_len(v) if isinstance(v, str) else v
    if rest[0] in "[{":
        text = rest
        if has_child and not _balanced(text):
            text = rest + " " + " ".join(l.strip() for l in child if _significant(l))
        return _read_flow(st, text, depth, path)
    if has_child:
        for l in child:
            if _significant(l) and (_KV_RE.match(l.strip()) or l.strip().startswith("- ")):
                raise Unparsed()                       # 평문 스칼라 아래의 매핑·목록은 YAML 오류
        text = _fold_lines(rest, [_strip_comment(l) for l in child if not l.lstrip().startswith("#")])
        return _check_len(text)
    return _check_len(scalar(rest)) if isinstance(scalar(rest), str) else scalar(rest)


def _balanced(text: str) -> bool:
    try:
        _flow_preflight(text)
    except Unparsed:
        return False
    return True


def _split_children(lines: list[str], start: int, base: int) -> tuple[list[str], int]:
    """start 이후에서 들여쓰기가 base보다 깊은 줄(빈 줄·주석 포함)을 다음 의미 있는 줄 전까지 모은다."""
    child: list[str] = []
    i = start
    while i < len(lines):
        l = lines[i]
        if _significant(l) and _indent(l) <= base:
            break
        child.append(l)
        i += 1
    return child, i


def _block(st: _State, lines: list[str], depth: int, path: list[str]) -> Any:
    if depth > MAX_DEPTH:
        raise _Limit("depth")
    sig = [l for l in lines if _significant(l)]
    if not sig:
        return None
    if any("\t" in l[:_indent(l)] for l in sig):
        raise Unparsed()
    base = _indent(sig[0])
    first = sig[0].strip()
    return _seq(st, lines, base, depth, path) if first == "-" or first.startswith("- ") else _map(st, lines, base, depth, path)


def _map(st: _State, lines: list[str], base: int, depth: int, path: list[str]) -> dict:
    out: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        l = lines[i]
        if not _significant(l):
            i += 1
            continue
        if _indent(l) != base:
            raise Unparsed()
        stripped = l.strip()
        m = _KV_RE.match(stripped)
        if not m or stripped.startswith("- "):
            raise Unparsed()
        key = _key_name(m.group(1))
        child, i = _split_children(lines, i + 1, base)
        if key in out:
            st.duplicate_keys.append(".".join(path + [key]))
        out[key] = _value(st, m.group(2), child, base, depth, path + [key])
    return out


def _seq(st: _State, lines: list[str], base: int, depth: int, path: list[str]) -> list:
    out: list[Any] = []
    i = 0
    while i < len(lines):
        l = lines[i]
        if not _significant(l):
            i += 1
            continue
        stripped = l.strip()
        if _indent(l) != base or not (stripped == "-" or stripped.startswith("- ")):
            raise Unparsed()
        item = stripped[1:].strip()
        child, i = _split_children(lines, i + 1, base)
        idx = [f"[{len(out)}]"]
        if item == "":
            out.append(_block(st, child, depth + 1, path[:-1] + [path[-1] + idx[0]] if path else idx) if any(_significant(c) for c in child) else None)
        elif item.startswith("- "):
            raise Unparsed()
        elif _KV_RE.match(item) and item[0] not in "\"'[{":
            virtual = [" " * (base + 2) + item] + child
            out.append(_block(st, virtual, depth + 1, path[:-1] + [path[-1] + idx[0]] if path else idx))
        else:
            out.append(_value(st, item, child, base, depth, path))
        st.node()
    return out


# ---- 진입점 ----------------------------------------------------------------------------------------------

def _parse_legacy_frontmatter_lines(lines: list[str]) -> dict:
    """`---` 사이의 줄들을 읽는다. 반환: `{"value": dict, "unparsed": [키], "duplicate_keys": [경로], "limit_hits": [{key, what}], "alias_keys": [키]}`."""
    out: dict[str, Any] = {}
    unparsed: list[str] = []
    dups: list[str] = []
    limits: list[dict] = []
    alias_keys: list[str] = []
    i = 0
    seen: set[str] = set()
    while i < len(lines):
        line = lines[i]
        if not _significant(line):
            i += 1
            continue
        if line[0] in " \t":                    # 최상위 키 없이 들여쓴 줄은 읽지 않는다(이전 동작과 같음)
            i += 1
            continue
        m = _KV_RE.match(line.rstrip())
        child, i = _split_children(lines, i + 1, 0)
        if not m:
            continue
        key = _key_name(m.group(1))
        if key in seen:
            dups.append(key)
        seen.add(key)
        st = _State()
        try:
            out[key] = _value(st, m.group(2), child, 0, 0, [key])
            dups.extend(st.duplicate_keys)
        except _Limit as lim:
            out.pop(key, None)
            unparsed.append(key)
            limits.append({"key": key, "what": lim.what})
        except Unparsed:
            fallback = None
            if key == "metadata" and not (m.group(2) or "").strip() and any(_significant(c) for c in child):
                # 문서: 중첩 metadata는 JSON5 한 덩어리일 수 있다.
                try:
                    fallback_state = _State()
                    text = "\n".join(c.strip() for c in child if _significant(c))
                    fallback = {"v": _read_flow(fallback_state, text, 0, [key])}
                    dups.extend(fallback_state.duplicate_keys)
                except _Limit as lim:
                    limits.append({"key": key, "what": lim.what})
                    fallback = None
                except (Unparsed, ValueError, RecursionError):
                    fallback = None
            if fallback is not None:
                out[key] = fallback["v"]
            else:
                out.pop(key, None)
                unparsed.append(key)
                if st.alias_like:
                    alias_keys.append(key)
    return {"value": out, "unparsed": sorted(set(unparsed)), "duplicate_keys": sorted(set(dups)), "limit_hits": limits, "alias_keys": sorted(set(alias_keys))}


def parse_frontmatter_lines(lines: list[str]) -> dict:
    """노드 그래프를 한도 내 JSON 자료형으로 복사한다. unsafe/full/load 생성자는 사용하지 않는다."""
    import yaml
    from yaml.nodes import MappingNode, ScalarNode, SequenceNode

    class Loader(yaml.SafeLoader):
        yaml_implicit_resolvers = {k: [(tag, pattern) for tag, pattern in values
                                      if tag.rsplit(":", 1)[-1] not in {"bool", "timestamp", "int", "float"}]
                                   for k, values in yaml.SafeLoader.yaml_implicit_resolvers.items()}

        def __init__(self, text):
            super().__init__(text)
            self.scan_depth = 0
            self.scan_nodes = 0

        def compose_node(self, parent, index):
            self.scan_depth += 1
            self.scan_nodes += 1
            try:
                if self.scan_depth > MAX_DEPTH + 40 or self.scan_nodes > MAX_NODES * 10:
                    raise _Limit("composition")
                return super().compose_node(parent, index)
            finally:
                self.scan_depth -= 1

    Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF"))
    Loader.add_implicit_resolver("tag:yaml.org,2002:int", re.compile(r"^[-+]?(?:[0-9][0-9_]*|0o[0-7_]+|0x[0-9a-fA-F_]+|0b[01_]+)$"), list("-+0123456789"))
    Loader.add_implicit_resolver("tag:yaml.org,2002:float", re.compile(r"^[-+]?(?:(?:[0-9][0-9_]*\.[0-9_]*|\.[0-9_]+)(?:[eE][-+]?[0-9]+)?|[0-9][0-9_]*[eE][-+]?[0-9]+|\.(?:inf|Inf|INF|nan|NaN|NAN))$"), list("-+0123456789."))
    try:
        loader = Loader("\n".join(lines) + "\n")
        try:
            root = loader.get_single_node()
        finally:
            loader.dispose()
    except (yaml.YAMLError, RecursionError, _Limit):
        # OpenClaw가 허용하는 JSON5 metadata와 기존 키별 미해석 진단을 유지한다.
        result = _parse_legacy_frontmatter_lines(lines)
        result["parser"] = "bounded_legacy_json5_fallback"
        return result
    if not isinstance(root, MappingNode):
        result = _parse_legacy_frontmatter_lines(lines)
        result["parser"] = "bounded_legacy_json5_fallback"
        return result
    result = {"value": {}, "unparsed": [], "duplicate_keys": [], "limit_hits": [], "alias_keys": [], "parser": "yaml12_bounded_nodes"}

    document_nodes = 0

    def convert(node, state, path, depth=0, parents=frozenset()):
        nonlocal document_nodes
        document_nodes += 1
        if document_nodes > MAX_NODES * 5:
            raise _Limit("document_nodes")
        state.node()
        if depth > MAX_DEPTH:
            raise _Limit("depth")
        if id(node) in parents:
            raise Unparsed()
        parents = parents | {id(node)}
        kind = node.tag.removeprefix("tag:yaml.org,2002:")
        if isinstance(node, ScalarNode):
            text = _check_len(node.value)
            if kind == "str":
                return text
            if kind == "null":
                return None
            if kind == "bool" and text.lower() in ("true", "false"):
                return text.lower() == "true"
            if kind == "int":
                value = text.replace("_", "")
                return int(value, 0) if value.lstrip("+-").lower().startswith(("0x", "0o", "0b")) else int(value, 10)
            if kind == "float":
                value = text.replace("_", "").lower()
                return float(value.replace(".inf", "inf").replace(".nan", "nan"))
            raise Unparsed()
        if isinstance(node, SequenceNode) and kind == "seq":
            return [convert(child, state, path + [f"[{i}]"], depth + 1, parents) for i, child in enumerate(node.value)]
        if not isinstance(node, MappingNode) or kind != "map":
            raise Unparsed()
        merged, explicit = {}, {}
        for key_node, value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                data = convert(value_node, state, path, depth + 1, parents)
                choices = data if isinstance(data, list) else [data]
                for choice in reversed(choices):
                    if not isinstance(choice, dict):
                        raise Unparsed()
                    merged.update(choice)
                continue
            key = convert(key_node, state, path, depth + 1, parents)
            if not isinstance(key, str):
                raise Unparsed()
            if key in explicit:
                state.duplicate_keys.append(".".join(path + [key]))
            explicit[key] = convert(value_node, state, path + [key], depth + 1, parents)
        merged.update(explicit)
        return merged

    seen = set()
    for key_node, value_node in root.value:
        if not isinstance(key_node, ScalarNode) or key_node.tag != "tag:yaml.org,2002:str":
            continue
        key = key_node.value
        if key in seen:
            result["duplicate_keys"].append(key)
        seen.add(key)
        state = _State()
        try:
            _check_len(key)
            result["value"][key] = convert(value_node, state, [key])
            result["duplicate_keys"].extend(state.duplicate_keys)
        except (Unparsed, ValueError, TypeError, RecursionError) as exc:
            result["value"].pop(key, None)
            result["unparsed"].append(key)
            if isinstance(exc, _Limit):
                result["limit_hits"].append({"key": key, "what": exc.what})
    result["unparsed"] = sorted(set(result["unparsed"]))
    result["duplicate_keys"] = sorted(set(result["duplicate_keys"]))
    return result

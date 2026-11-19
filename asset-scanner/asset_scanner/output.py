"""결과 JSON 저장 도우미 (설정 수집 CLI와 Tool 카탈로그 CLI 공통).

방침
- 결과는 항상 **엄격한 JSON(UTF-8, NaN·Infinity 없음)** 이어야 한다. 직렬화·인코딩은 파일을 열기 **전에** 모두 끝낸다.
- 고립된 surrogate(예: JSON 이스케이프 `\\ud800`)는 UTF-8로 저장할 수 없다. 문자열 값과 객체 키 안의 고립된 surrogate는
  U+FFFD(대체 문자)로 바꾸고 건수를 센다. 유효한 한글·이모지·유럽 문자는 건드리지 않는다. 키가 바뀌어 다른 키와
  겹치면 `<redacted-key-N>` 자리표시자를 쓴다 (서로 다른 항목이 덮어써지지 않게).
- 저장은 같은 폴더의 임시 파일에 쓴 뒤 `os.replace`로 교체한다. 어느 단계에서 실패해도 기존 결과 파일은 그대로이고
  빈 파일·임시 파일이 남지 않는다.
- 실패 사유에는 문자열 내용을 넣지 않는다 (예외 종류 이름만 남긴다).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_LONE_SURROGATE_RE = re.compile("[\ud800-\udfff]")
REPLACEMENT_CHAR = "�"


class OutputError(Exception):
    """결과를 만들거나 저장하지 못했다. `kind`는 원인 예외의 종류 이름이다."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def has_lone_surrogate(text: str) -> bool:
    return bool(_LONE_SURROGATE_RE.search(text))


def normalize_for_output(obj: Any) -> tuple[Any, int]:
    """문자열 값·객체 키 안의 고립된 surrogate를 U+FFFD로 바꾼 사본과 바뀐 문자열 수를 돌려준다."""
    count = 0

    def fix_text(text: str) -> str:
        nonlocal count
        if has_lone_surrogate(text):
            count += 1
            return _LONE_SURROGATE_RE.sub(REPLACEMENT_CHAR, text)
        return text

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            return fix_text(node)
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, dict):
            used = {k for k in node if not (isinstance(k, str) and has_lone_surrogate(k))}
            out: dict = {}
            n = 0
            for k, v in node.items():
                if isinstance(k, str) and has_lone_surrogate(k):
                    new_key = fix_text(k)
                    if new_key in used or new_key in out:
                        while True:
                            n += 1
                            new_key = f"<redacted-key-{n}>"
                            if new_key not in used and new_key not in out:
                                break
                    used.add(new_key)
                    out[new_key] = walk(v)
                else:
                    out[k] = walk(v)
            return out
        return node

    return walk(obj), count


def dumps_strict(obj: Any) -> str:
    """엄격한 JSON 문자열(끝에 줄바꿈 포함)을 만든다. UTF-8로 인코딩할 수 없거나 NaN·Infinity가 있으면 실패한다."""
    try:
        text = json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        text.encode("utf-8")  # 인코딩 가능 여부를 파일을 열기 전에 확인한다
    except (ValueError, TypeError, UnicodeEncodeError, RecursionError) as exc:
        raise OutputError(type(exc).__name__) from None
    return text


def write_json_atomic(path: Path, obj: Any) -> None:
    """결과를 임시 파일에 완전히 쓴 뒤 교체한다. 실패하면 기존 파일은 그대로이고 임시 파일은 지운다."""
    data = dumps_strict(obj).encode("utf-8")
    tmp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing_mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, existing_mode)
        os.replace(tmp_name, path)
        tmp_name = None
    except OSError as exc:
        raise OutputError(type(exc).__name__) from None
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

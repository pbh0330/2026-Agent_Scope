import os
import subprocess
import sys
from pathlib import Path

import pytest

SCANNER_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = SCANNER_ROOT / "examples"


@pytest.fixture
def write_config(tmp_path):
    """테스트용 임시 설정 파일을 만든다."""

    def _write(text: str, name: str = "openclaw.json5", encoding: str = "utf-8") -> Path:
        path = tmp_path / name
        path.write_text(text, encoding=encoding)
        return path

    return _write


def run_cli(config: Path, output: Path) -> subprocess.CompletedProcess:
    """실제 사용자처럼 별도 프로세스로 CLI를 실행한다 (표준출력·오류출력 검사용)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "asset_scanner", "--config", str(config), "--output", str(output)],
        cwd=SCANNER_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
    )

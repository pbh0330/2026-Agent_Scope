"""테스트 전용 **가짜 OpenClaw CLI**. 실제 OpenClaw가 아니며 아무것도 설치·접속·변경하지 않는다.

받은 인자와 범위 환경변수를 `FAKE_OPENCLAW_LOG` 파일에 JSON 줄로 남기고(비밀 환경변수는 값이 아니라 이름만),
`FAKE_OPENCLAW_MODE`에 따라 응답한다. 알려진 하위 명령이 아니면 종료 코드 64로 끝난다(테스트가 "허용하지 않은 명령이 없었다"를 확인).

모드: ok · version_other · fail · badjson · empty · nonutf8 · huge · slow · grandchild
"""
import json
import os
import subprocess
import sys
import time

MODE = os.environ.get("FAKE_OPENCLAW_MODE", "ok")
LOG = os.environ.get("FAKE_OPENCLAW_LOG")
argv = sys.argv[1:]

if LOG:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "argv": argv,
            "scope_env": {k: os.environ.get(k) for k in ("OPENCLAW_CONFIG_PATH", "OPENCLAW_STATE_DIR", "OPENCLAW_HOME", "OPENCLAW_PROFILE")},
            # 값은 기록하지 않고 이름만: 기본 변수 외에 무엇이 넘어왔는지 확인하기 위함
            "interesting_env_names": sorted(k for k in os.environ if k.startswith(("FAKESECRET_", "OPENCLAW_", "FAKE_PASS_"))),
            "cwd": os.getcwd(),
            # Windows에서 NUL 장치는 isatty()가 True이므로 tty 여부가 아니라 "읽으면 즉시 EOF인가"로 닫힌 stdin을 확인한다
            "stdin_first_read": sys.stdin.read(1) if sys.stdin else None,
        }) + "\n")

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 루트 옵션
rest = list(argv)
profile = None
while rest and rest[0] in ("--profile", "--dev"):
    if rest[0] == "--profile":
        profile = rest[1]
        rest = rest[2:]
    else:
        rest = rest[1:]


def emit(obj) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


PLUGIN_ROOT = os.environ.get("FAKE_PLUGIN_ROOT", "")
PLUGINS = {"workspaceDir": "/w", "workspaceScope": "x", "registry": {"source": "persisted", "diagnostics": []}, "diagnostics": [], "plugins": [
    {"id": "voice-call", "name": "Voice Call", "version": "1.2.3", "origin": "workspace", "source": "x", "rootDir": PLUGIN_ROOT, "enabled": True,
     "explicitlyEnabled": True, "activated": True, "status": "loaded", "toolNames": ["call"], "hookNames": []},
    {"id": "only-runtime", "name": "Runtime Only", "origin": "bundled", "enabled": True, "status": "loaded"}]}
SKILLS = {"workspaceDir": "/w", "skills": [
    {"name": "greeter", "source": "openclaw-workspace", "filePath": os.environ.get("FAKE_SKILL_FILE", "/nowhere/SKILL.md"), "bundled": False,
     "disabled": False, "eligible": True, "modelVisible": True}]}
IDENT = {"deviceId": "9f2c" * 16, "publicKey": "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MEFCQ0Q"}

if rest == ["--version"] or argv == ["--version"]:
    print("OpenClaw 2026.10.1 (abcdef0)" if MODE == "version_other" else "OpenClaw 2026.9.6 (eb377ac)")
    sys.exit(0)

if rest[:2] == ["plugins", "list"] and "--json" in rest:
    payload = PLUGINS
elif rest[:2] == ["skills", "list"] and "--json" in rest:
    payload = SKILLS
elif rest[:2] == ["node", "identity"] and "--json" in rest:
    payload = IDENT
elif rest[:3] == ["gateway", "call", "gateway.identity.get"] and "--json" in rest:
    payload = IDENT
else:
    sys.stderr.write("fake-openclaw: unexpected argv\n")
    sys.exit(64)

if MODE == "fail":
    sys.stderr.write("Gateway failed: token=ghp_FAKESTDERRTOKEN1234567890abcdefgh https://u:FAKESTDERRPASS@h.test/x\n")
    emit({"ok": False, "error": {"message": "FAKESTDOUTERRORSECRET"}, "code": "UNAVAILABLE"})
    sys.exit(1)
if MODE == "badjson":
    sys.stdout.write("this is not json FAKEBADJSONSECRET")
    sys.exit(0)
if MODE == "empty":
    sys.exit(0)
if MODE == "nonutf8":
    sys.stdout.buffer.write(b"\xff\xfe\xfa")
    sys.exit(0)
if MODE == "huge":
    for _ in range(400):
        sys.stdout.write("x" * 65536)
        sys.stdout.flush()
    time.sleep(30)
    sys.exit(0)
if MODE == "slow":
    time.sleep(30)
    emit(payload)
    sys.exit(0)
if MODE == "grandchild":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    with open(os.environ["FAKE_OPENCLAW_PIDFILE"], "w", encoding="utf-8") as f:
        f.write(f"{os.getpid()} {child.pid}")
    time.sleep(60)
    sys.exit(0)

if MODE == "secrets":
    payload = json.loads(json.dumps(payload).replace("Voice Call", "Voice ghp_FAKEPLUGINNAMETOKEN1234567890ab"))
emit(payload)
sys.exit(0)

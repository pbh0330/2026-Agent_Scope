# 테스트베드 OVA 패키징 절차

> 목적: `tb-gw`·`tb-node` 두 VM을 배포용 OVA로 내보내 다른 PC에서 그대로 재현한다(데모·인수·재현성 R2).
> 전제: 이 문서는 **절차·스크립트·점검표**다. 실제 `.ova` 내보내기는 VMware가 깔린 작업자 PC에서 `ovftool`로 실행한다(저장소 작업만으로는 만들 수 없다).
> 작업자: 박병하 · 기준 상태: `SNAP-2-P2`(정상군 전체)

## 0. 지금 내보낼 수 있는가

| 항목 | 상태 |
|---|---|
| 기본 VM `tb-gw`·`tb-node` | 빌드 완료(SNAP-0/1/2) |
| 정상군 `SNAP-2-P0/P1/P2` | 완료 → **OVA 기준 상태로 사용** |
| 위협 `SNAP-3-S*` | VM 미반영(저장소에 설정만 있음). OVA에는 넣지 않고, 임포트 후 저장소 설정으로 적용 |

→ **정상군(SNAP-2-P2) 기준으로 OVA v1을 낸다.** 위협 스냅샷까지 담으려면 먼저 각 VM에 `SNAP-3-S*`를 만들어야 한다(별도 작업).

## 1. 무엇을 담을지

- VM 2대라 **OVA 2개**(`agentscope-tb-gw.ova`, `agentscope-tb-node.ova`)로 낸다. VMware Workstation은 vApp(다중 VM 단일 OVA)을 지원하지 않는다. vCenter/Fusion이면 vApp 하나로 묶어도 된다.
- 기준 디스크 상태는 **SNAP-2-P2**(정상군 전체, 전원 끔). 위협 구성은 임포트 후 저장소 설정으로 얹는다.
- OVA에는 스냅샷 트리가 보존되지 않는다(OVF 규격에 스냅샷 개념 없음). 따라서 **SNAP-2-P2에서 전체 복제(full clone) → 복제본을 내보내기**로 단일 상태 깨끗한 OVA를 만든다.

## 2. 절차 개요

```
각 VM마다:
  SNAP-2-P2로 되돌림 → 전체 복제(스냅샷 없는 복제본) → 복제본 부팅
    → ova-sanitize.sh 실행(민감정보·로그·호스트키 정리) → 전원 끔
    → ovftool로 복제본 → .ova 내보내기 → 복제본 삭제
배포 전: 점검표(4절)로 비밀값 유출 여부 확인 → 체크섬 생성 → README 동봉
```

전체 복제본을 쓰는 이유: 원본 VM의 스냅샷 체계(SNAP-0~3)를 그대로 두고, 내보내기용으로만 민감정보를 지운 일회용 사본을 만든다. 내보낸 뒤 사본은 버린다.

## 3. 내보내기 (작업자 PC, ovftool)

VMware Workstation 설치 시 `ovftool`이 함께 깔린다(`C:\Program Files\VMware\VMware Workstation\OVFTool\ovftool.exe`).

```powershell
# 복제본을 전원 끈 상태로 둔 뒤 (예시 경로)
$ovftool = "C:\Program Files\VMware\VMware Workstation\OVFTool\ovftool.exe"

& $ovftool --acceptAllEulas --compress=9 `
  "D:\VMs\agentscope-tb-gw-export\agentscope-tb-gw-export.vmx" `
  "D:\release\agentscope-tb-gw.ova"

& $ovftool --acceptAllEulas --compress=9 `
  "D:\VMs\agentscope-tb-node-export\agentscope-tb-node-export.vmx" `
  "D:\release\agentscope-tb-node.ova"
```

- `--compress=9`로 용량을 줄인다. `--compress` 없이 내보내고 따로 압축해도 된다.
- 내보내기 전에 복제본에서 CD/ISO 마운트·공유 폴더·추가 네트워크 어댑터를 제거한다(불필요한 장치가 OVF에 박히지 않게).

## 4. 배포 전 민감정보 점검표 (필수)

OVA는 디스크 전체를 담으므로 **지운 줄 알았던 값이 남아 있기 쉽다.** 배포 전에 반드시 확인한다. [ova-sanitize.sh](../scripts/ova-sanitize.sh)가 대부분을 처리하지만, 아래를 눈으로 확인한다.

| 대상 | 처리 | 확인 |
|---|---|---|
| `~/.openclaw/.env` (양쪽: `INVENTORY_MCP_TOKEN`, tb-node `EVERYTHING_DEMO_KEY`) | 문서화된 더미 값으로 고정 | 실제 토큰 흔적 없음 |
| `~/inventory-remote/.env` (tb-node: 토큰·TLS 경로·PORT) | `INVENTORY_MCP_TOKEN`을 tb-gw와 같은 더미로 | 두 VM 토큰이 서로 같아야 inventory-remote가 뜸 |
| 게이트웨이 auth 토큰 (`~/.openclaw/openclaw.json#gateway.auth.token`) | 문서화된 더미로 | 로컬 모드라 더미로 충분 |
| 노드 페어링 토큰 (`~/.openclaw/node.systemd.env#OPENCLAW_GATEWAY_TOKEN`) | 유지(페어링 동작 필요). 더미·로컬 전용임을 README에 명시 | 외부 재사용 금지 고지 |
| 실습용 CA·서버 개인키 (`~/ca.key`, `~/*.key`) | **유지**(inventory-remote HTTPS가 바로 뜨도록). 단 "테스트베드 전용·공개된 키, 절대 외부 신뢰 금지" 고지 | README에 경고 |
| OpenClaw 장치 신원 (`~/.openclaw/state/openclaw.sqlite`의 deviceId 키쌍) | **유지**(정답 목록 `raw/*/`의 deviceId와 일치해야 함) | 정답 목록과 deviceId 대조 |
| 셸 히스토리 `~/.bash_history`, `~/.*_history` | 삭제 | 비어 있음 |
| 시스템 로그 `/var/log/*`, journald | 비움 | 토큰·IP 흔적 없음 |
| SSH 호스트키 `/etc/ssh/ssh_host_*` | 삭제(첫 부팅 재생성) | 없음 |
| `/etc/machine-id`, `/var/lib/dbus/machine-id` | 비움(첫 부팅 재생성) | 빈 파일 |
| apt 캐시·`/tmp`·`~/.cache` | 정리 | — |

> 실제 비밀값은 저장소·문서 어디에도 쓰지 않는다. 위 더미 값은 임포트 후 사용자가 바꿔도 되는, 공개를 전제로 한 테스트베드 전용 값이다.

## 5. 임포트 후 첫 실행 (동봉 README에 넣을 내용)

1. 두 OVA를 임포트한다. 네트워크는 **같은 NAT(또는 호스트 전용) 세그먼트**에 둔다(학교망·외부와 격리, 요구사항 R1).
2. 두 VM의 IP를 확인하고 `/etc/hosts`를 맞춘다(서로 `tb-gw`·`tb-node`로 해석돼야 함). inventory-remote 인증서 SAN이 `tb-node`와 `<TB_NODE_IP>`이므로 IP가 바뀌면 `/etc/hosts`의 `tb-node` 매핑을 새 IP로 갱신한다.
3. `tb-node` 먼저 부팅 → `systemctl --user status inventory-remote-mcp` 확인 → `tb-gw` 부팅.
4. 페어링 확인: `tb-gw`에서 `openclaw devices list --json`에 `tb-node`가 보이는지.
5. 정상군 검증: `openclaw mcp probe --json` 등으로 `testbed/ground-truth/P2.json`과 대조.

## 6. 위협 구성(S1~S5) 적용

OVA는 SNAP-2-P2(정상군) 상태다. 위협 구성은 임포트 후 저장소 설정으로 얹는다. 각 구성의 절차는 해당 README를 따른다:

- [S1](../profiles/S1/README.md) · [S2](../profiles/S2/README.md) · [S3](../profiles/S3/README.md) · [S4](../profiles/S4/README.md) · [S5](../profiles/S5-T1/README.md)

위협 스냅샷(`SNAP-3-S*`)까지 담은 OVA가 필요하면, 각 README대로 VM에 구성·스냅샷을 만든 뒤 2~4절을 다시 수행한다(별도 릴리스).

## 7. 배포물 구성

```
release/
├── agentscope-tb-gw.ova
├── agentscope-tb-node.ova
├── SHA256SUMS            # sha256sum *.ova
└── README.txt           # 4절 더미값 고지 + 5절 첫 실행 + 버전(OpenClaw 2026.9.6, Ubuntu 24.04.5)
```

체크섬: `sha256sum agentscope-tb-*.ova > SHA256SUMS`.

## 8. 미결정·주의

- 용량: everything/filesystem/memory 서버 + Node 24 + Ubuntu로 VM당 수 GB. `--compress=9`로도 큰 편이니 배포 경로(용량 제한)를 먼저 확인한다.
- 위협 스냅샷을 OVA에 넣을지, 저장소 설정으로만 재현할지는 데모 범위에 따라 결정한다(현재 권장: 저장소 설정 적용).
- 메모리 기록상 OVA는 "버전 고정 시점의 릴리스 산출물"이다. 활발히 바뀌는 중이면 버전을 찍고 내보낸다(재현성 확보 후).

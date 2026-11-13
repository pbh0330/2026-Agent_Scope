package usagereport

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"sort"
	"strings"
	"unicode"
)

// 매핑 상태(스키마 14.1 mapping_status).
const (
	MappingMatched   = "matched"
	MappingAmbiguous = "ambiguous"
	MappingUnmatched = "unmatched"
)

// OpenClaw가 MCP 도구를 모델에 노출할 때 쓰는 이름 규칙(src/agents/agent-bundle-mcp-names.ts).
//
//	노출 이름 = sanitize(서버키, "mcp", 30자) + "__" + sanitize(도구이름, "tool")[:64-서버길이-2]
//	sanitize: 앞뒤 공백 제거 → [A-Za-z0-9_-] 밖의 문자는 "-" → 비면 대체어 → 영문자로 시작 안 하면 "대체어-" 접두
//
// 이름이 겹치면 OpenClaw가 선언 순서대로 "-2", "-3"을 붙이는데, 이건 실행 시점 상태라 스냅샷만으로
// 재현할 수 없다. 그래서 같은 노출 이름이 나오는 후보가 둘 이상이면 ambiguous로 둔다.
const (
	toolNameSeparator = "__"
	toolNameMaxPrefix = 30
	toolNameMaxTotal  = 64
)

// 노드(tb-node 등)에서 실행되는 MCP 서버(nodeHost.mcp.servers)의 도구는 게이트웨이 쪽과 달리
// "<서버키>_<도구이름>"(밑줄 1개)로 노출된다. 근거: 테스트베드 P2 실측(openclaw nodes describe의
// nodePluginTools, 예: kg-memory_add_observations, demo-everything_echo), PR #17 profiles/README 5절.
// 실측한 이름은 모두 가공 없는 원래 이름이라 sanitize·길이 제한은 적용하지 않는다(규칙 확인 전).
const (
	nodeToolNameSeparator = "_"
	nodeHostConfigPrefix  = "nodeHost."
)

// 서버 부분(fs-2__x) 또는 도구 부분(fs__x-2) 끝의 -N.
var collisionSuffix = regexp.MustCompile(`-[0-9]+(__|$)`)

func isSafeByte(r rune) bool {
	return r < 0x80 && (r == '_' || r == '-' || ('0' <= r && r <= '9') || ('a' <= r && r <= 'z') || ('A' <= r && r <= 'Z'))
}

// isJSSpace는 JS String.prototype.trim()이 지우는 문자(WhiteSpace + LineTerminator)다.
// Go unicode.IsSpace와 달리 U+FEFF를 포함하고 U+0085는 포함하지 않는다.
func isJSSpace(r rune) bool {
	switch r {
	case '\t', '\n', '\v', '\f', '\r', ' ', '\uFEFF', '\u2028', '\u2029':
		return true
	}
	return unicode.Is(unicode.Zs, r)
}

func sanitizeFragment(raw, fallback string, maxChars int) string {
	trimmed := strings.TrimFunc(raw, isJSSpace)
	var b strings.Builder
	for _, r := range trimmed {
		switch {
		case isSafeByte(r):
			b.WriteRune(r)
		case r > 0xFFFF:
			// JS 정규식(플래그 없음)은 UTF-16 단위로 치환하므로 BMP 밖 문자는 "-" 두 개가 된다.
			b.WriteString("--")
		default:
			b.WriteByte('-')
		}
	}
	s := b.String()
	if s == "" {
		s = fallback
	}
	if c := s[0]; !(('a' <= c && c <= 'z') || ('A' <= c && c <= 'Z')) {
		s = fallback + "-" + s
	}
	if maxChars > 0 && len(s) > maxChars {
		s = s[:maxChars]
	}
	return s
}

// ExposedToolName은 서버 키와 MCP 도구 이름으로 OpenClaw의 노출 이름을 재현한다(충돌 접미사 제외).
func ExposedToolName(serverKey, toolName string) string {
	srv := sanitizeFragment(serverKey, "mcp", toolNameMaxPrefix)
	tool := sanitizeFragment(toolName, "tool", 0)
	maxTool := toolNameMaxTotal - len(srv) - len(toolNameSeparator)
	if maxTool < 1 {
		maxTool = 1
	}
	if len(tool) > maxTool {
		tool = tool[:maxTool]
	}
	if tool == "" {
		tool = "tool"
	}
	return srv + toolNameSeparator + tool
}

// NodeExposedToolName은 노드에서 실행되는 MCP 서버의 도구 노출 이름을 재현한다.
func NodeExposedToolName(serverKey, toolName string) string {
	return serverKey + nodeToolNameSeparator + toolName
}

// Inventory는 InventorySnapshot(스키마 2·3절)에서 매핑에 필요한 부분만 읽은 것이다.
type Inventory struct {
	SchemaVersion string  `json:"schema_version"`
	SnapshotID    string  `json:"snapshot_id"`
	EnvironmentID string  `json:"environment_id"`
	ProfileID     string  `json:"profile_id"`
	Assets        []Asset `json:"assets"`

	byExposed map[string][]candidate
	owner     map[string]string // Tool asset_id → 소속 MCP 서버 asset_id
	ownerKey  map[string]string // Tool asset_id → 소속 MCP 서버의 설정 키(화면 표시용)
}

// Asset은 스냅샷 자산의 매핑용 필드.
type Asset struct {
	AssetID      string   `json:"asset_id"`
	AssetType    string   `json:"asset_type"`
	Name         string   `json:"name"`
	OwnerRef     string   `json:"owner_ref"`
	EvidenceRefs []string `json:"evidence_refs"`
	MCP          *struct {
		Definition struct {
			Name string `json:"name"`
		} `json:"definition"`
	} `json:"mcp"`
	Product *struct {
		ConfigPath string `json:"config_path"`
	} `json:"product"`
}

type candidate struct {
	toolID, serverID, serverKey, toolName string
	evidence                              []string
	nodeHosted                            bool // nodeHost.mcp.servers에 선언된 서버(노드에서 실행)
}

// LoadInventory는 snapshot.json을 읽는다.
func LoadInventory(path string) (*Inventory, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var inv Inventory
	if err := json.Unmarshal(b, &inv); err != nil {
		return nil, fmt.Errorf("인벤토리 스냅샷 파싱 실패: %w", err)
	}
	if err := inv.index(); err != nil {
		return nil, err
	}
	return &inv, nil
}

// serverKey는 OpenClaw 설정의 서버 키를 고른다. product.config_path("...servers.<key>")가 있으면
// 그 키를, 없으면 표시 이름을 쓴다.
func serverKey(a Asset) string {
	if a.Product != nil {
		if i := strings.Index(a.Product.ConfigPath, "servers."); i >= 0 {
			if k := a.Product.ConfigPath[i+len("servers."):]; k != "" {
				return k
			}
		}
	}
	return a.Name
}

// nodeHosted는 서버가 노드 쪽 설정(nodeHost.mcp.servers)에 선언됐는지다.
func nodeHosted(a Asset) bool {
	return a.Product != nil && strings.Contains(a.Product.ConfigPath, nodeHostConfigPrefix)
}

func (inv *Inventory) index() error {
	if inv.SnapshotID == "" {
		return fmt.Errorf("인벤토리 스냅샷에 snapshot_id가 없음")
	}
	servers := map[string]Asset{}
	for _, a := range inv.Assets {
		if a.AssetType == "mcp_server" {
			if _, dup := servers[a.AssetID]; dup {
				return fmt.Errorf("스냅샷에 중복 asset_id: %s", a.AssetID)
			}
			servers[a.AssetID] = a
		}
	}
	inv.byExposed = map[string][]candidate{}
	inv.owner = map[string]string{}
	inv.ownerKey = map[string]string{}
	for _, a := range inv.Assets {
		if a.AssetType != "tool" {
			continue
		}
		srv, ok := servers[a.OwnerRef]
		if !ok {
			continue // 소속 서버를 모르는 Tool은 노출 이름을 재현할 수 없음
		}
		name := a.Name
		if a.MCP != nil && a.MCP.Definition.Name != "" {
			name = a.MCP.Definition.Name
		}
		key := serverKey(srv)
		node := nodeHosted(srv)
		exp := ExposedToolName(key, name)
		if node {
			exp = NodeExposedToolName(key, name)
		}
		inv.owner[a.AssetID] = srv.AssetID
		inv.ownerKey[a.AssetID] = key
		inv.byExposed[exp] = append(inv.byExposed[exp], candidate{
			toolID: a.AssetID, serverID: srv.AssetID, serverKey: key, toolName: name, evidence: a.EvidenceRefs, nodeHosted: node,
		})
	}
	return nil
}

func (inv *Inventory) checkContext(env, profile string) error {
	if inv.EnvironmentID != env || inv.ProfileID != profile {
		return fmt.Errorf("인벤토리 스냅샷의 environment_id/profile_id(%s/%s)가 요청(%s/%s)과 다름",
			inv.EnvironmentID, inv.ProfileID, env, profile)
	}
	return nil
}

// ToolOwner는 Tool 자산의 소속 MCP 서버 asset_id를 돌려준다(대시보드에서 서버 단위로 묶을 때 사용).
// inv가 nil이거나 모르는 Tool이면 ok=false.
func (inv *Inventory) ToolOwner(toolAssetID string) (serverAssetID string, ok bool) {
	if inv == nil {
		return "", false
	}
	serverAssetID, ok = inv.owner[toolAssetID]
	return serverAssetID, ok
}

// ToolServerKey는 Tool 자산이 속한 MCP 서버의 설정 키(fs, kg-memory 등)를 돌려준다.
// 노드 쪽 도구(<서버>_<도구>)는 이름만으로 서버를 가를 수 없어서 화면 표시에 이 값을 쓴다.
func (inv *Inventory) ToolServerKey(toolAssetID string) (string, bool) {
	if inv == nil {
		return "", false
	}
	k, ok := inv.ownerKey[toolAssetID]
	return k, ok
}

// Mapping은 한 도구 호출의 자산 매핑 결과.
type Mapping struct {
	AssetRef     *string
	Status       string
	Reason       string
	EvidenceRefs []string
}

// Map은 노출 도구 이름을 스냅샷 Tool 자산에 연결한다. inv가 nil이어도 호출할 수 있다.
func (inv *Inventory) Map(exposedName, source string) Mapping {
	if inv == nil {
		return Mapping{Status: MappingUnmatched, Reason: "no inventory snapshot provided"}
	}
	// 노드 쪽 도구는 tool.source가 mcp가 아닐 수 있어(노드 플러그인 도구로 투영됨) 이름이 노드 서버 후보와
	// 정확히 같을 때만 먼저 연결한다. 내장 도구(core)는 서버 접두어가 없어 여기에 걸리지 않는다.
	if source != "core" && source != "builtin" {
		if cands := inv.byExposed[exposedName]; len(cands) > 0 && allNodeHosted(cands) {
			return inv.decide(cands, exposedName, nodeToolNameSeparator)
		}
	}
	if source != "mcp" {
		return Mapping{Status: MappingUnmatched, Reason: fmt.Sprintf(
			"tool source is %q: built-in/core tools have no MCP Tool asset, so no asset is created or linked", source)}
	}
	if !strings.Contains(exposedName, toolNameSeparator) {
		return Mapping{Status: MappingUnmatched, Reason: "MCP tool name has no <server>__<tool> separator"}
	}
	return inv.decide(inv.byExposed[exposedName], exposedName, toolNameSeparator)
}

func allNodeHosted(cands []candidate) bool {
	for _, c := range cands {
		if !c.nodeHosted {
			return false
		}
	}
	return true
}

// decide는 노출 이름이 같은 후보 목록으로 매핑 상태를 정한다. sep은 근거 문장에 적을 이름 규칙이다.
func (inv *Inventory) decide(cands []candidate, exposedName, sep string) Mapping {
	rule := "provider-safe name"
	if sep == nodeToolNameSeparator {
		rule = "node-hosted name (<server>_<tool>)"
	}
	switch len(cands) {
	case 0:
		reason := fmt.Sprintf("no Tool asset in snapshot %s reproduces the exposed name", inv.SnapshotID)
		if collisionSuffix.MatchString(exposedName) {
			reason += "; the -N suffix may be OpenClaw collision handling, which cannot be resolved statically"
		}
		return Mapping{Status: MappingUnmatched, Reason: reason}
	case 1:
		c := cands[0]
		if len(c.evidence) == 0 {
			return Mapping{Status: MappingUnmatched, Reason: fmt.Sprintf("candidate Tool %s has no evidence_refs", c.toolID)}
		}
		id := c.toolID
		return Mapping{
			AssetRef: &id,
			Status:   MappingMatched,
			Reason: fmt.Sprintf("exposed name equals %s of server key %q + tool %q (Tool %s, server %s) in snapshot %s",
				rule, c.serverKey, c.toolName, c.toolID, c.serverID, inv.SnapshotID),
			EvidenceRefs: append([]string(nil), c.evidence...),
		}
	default:
		ids := make([]string, len(cands))
		for i, c := range cands {
			ids[i] = c.toolID
		}
		sort.Strings(ids)
		return Mapping{Status: MappingAmbiguous, Reason: fmt.Sprintf(
			"%d Tool assets reproduce the same exposed name (%s); OpenClaw's runtime de-duplication order is not in the snapshot",
			len(cands), strings.Join(ids, ", "))}
	}
}

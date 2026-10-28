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

// Inventory는 InventorySnapshot(스키마 2·3절)에서 매핑에 필요한 부분만 읽은 것이다.
type Inventory struct {
	SchemaVersion string  `json:"schema_version"`
	SnapshotID    string  `json:"snapshot_id"`
	EnvironmentID string  `json:"environment_id"`
	ProfileID     string  `json:"profile_id"`
	Assets        []Asset `json:"assets"`

	byExposed map[string][]candidate
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
		exp := ExposedToolName(key, name)
		inv.byExposed[exp] = append(inv.byExposed[exp], candidate{
			toolID: a.AssetID, serverID: srv.AssetID, serverKey: key, toolName: name, evidence: a.EvidenceRefs,
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
	if source != "mcp" {
		return Mapping{Status: MappingUnmatched, Reason: fmt.Sprintf(
			"tool source is %q: built-in/core tools have no MCP Tool asset, so no asset is created or linked", source)}
	}
	if !strings.Contains(exposedName, toolNameSeparator) {
		return Mapping{Status: MappingUnmatched, Reason: "MCP tool name has no <server>__<tool> separator"}
	}
	cands := inv.byExposed[exposedName]
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
			Reason: fmt.Sprintf("exposed name equals provider-safe name of server key %q + tool %q (Tool %s, server %s) in snapshot %s",
				c.serverKey, c.toolName, c.toolID, c.serverID, inv.SnapshotID),
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

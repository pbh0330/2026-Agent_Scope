package usagereport

import (
	"encoding/json"
	"strings"
	"testing"
)

// OpenClaw agent-bundle-mcp-names.ts의 buildSafeToolName / sanitizeServerName과 같은 결과여야 한다.
func TestExposedToolNameMatchesOpenClawRules(t *testing.T) {
	long40 := strings.Repeat("s", 40)
	cases := []struct{ server, tool, want string }{
		{"fs", "read_text_file", "fs__read_text_file"},
		{"my.server", "get item", "my-server__get-item"},                  // 허용 밖 문자 → "-"
		{"1srv", "x", "mcp-1srv__x"},                                      // 영문자로 시작 안 하면 대체어 접두
		{"fs", "9lives", "fs__tool-9lives"},                               // 도구도 같은 규칙
		{"  docs  ", " search ", "docs__search"},                          // 앞뒤 공백 제거
		{long40, "t", strings.Repeat("s", 30) + "__t"},                    // 서버 30자 제한
		{"fs", strings.Repeat("a", 80), "fs__" + strings.Repeat("a", 60)}, // 전체 64자 제한
		{"srv", "검색", "srv__tool---"},                                     // 한글 2자 → "--" 이후 접두 처리
		{"srv", "a😀b", "srv__a--b"},                                       // BMP 밖 문자는 UTF-16 두 단위 → "--"
		{"", "x", "mcp__x"},
		{"\uFEFFdocs", "x", "docs__x"},       // JS trim()은 BOM(U+FEFF)도 지운다
		{"docs", "\u0085x", "docs__tool--x"}, // U+0085는 JS trim() 대상이 아님 → "-"
	}
	for _, c := range cases {
		if got := ExposedToolName(c.server, c.tool); got != c.want {
			t.Errorf("ExposedToolName(%q,%q) = %q, want %q", c.server, c.tool, got, c.want)
		}
	}
	if got := ExposedToolName("fs", strings.Repeat("a", 80)); len(got) != 64 {
		t.Errorf("total length = %d, want 64", len(got))
	}
}

func loadInv(t *testing.T, mutate func(m map[string]any)) *Inventory {
	t.Helper()
	inv, err := LoadInventory("testdata/inventory-fs.json")
	if err != nil {
		t.Fatal(err)
	}
	if mutate == nil {
		return inv
	}
	b, _ := json.Marshal(inv)
	var m map[string]any
	json.Unmarshal(b, &m)
	mutate(m)
	b, _ = json.Marshal(m)
	var out Inventory
	if err := json.Unmarshal(b, &out); err != nil {
		t.Fatal(err)
	}
	if err := out.index(); err != nil {
		t.Fatal(err)
	}
	return &out
}

// 서로 다른 서버의 동명 Tool(read_text_file)은 서버 이름까지 맞는 것 하나에만 연결된다(S3, QA-USE-07).
func TestMapMatchesOnlyOwnServer(t *testing.T) {
	inv := loadInv(t, nil)
	for exposed, wantID := range map[string]string{
		"fs__read_text_file":            "tool-fs-read",
		"docs__read_text_file":          "tool-docs-read",
		"fs__list_directory_with_sizes": "tool-fs-list",
	} {
		m := inv.Map(exposed, "mcp")
		if m.Status != MappingMatched || m.AssetRef == nil || *m.AssetRef != wantID || len(m.EvidenceRefs) == 0 {
			t.Errorf("%s: %+v (asset %v)", exposed, m, deref(m.AssetRef))
		}
	}
}

func TestMapUnmatchedCases(t *testing.T) {
	inv := loadInv(t, nil)
	cases := []struct{ name, source, reason string }{
		{"exec", "core", "built-in/core"},            // 내장 도구는 가짜 MCP 자산 안 만듦
		{"fs__write_file", "mcp", "no Tool asset"},   // 스냅샷에 없는 도구
		{"read_text_file", "mcp", "separator"},       // 서버 접두 없음 → 이름만으로 연결 금지
		{"fs-2__read_text_file", "mcp", "-N suffix"}, // 충돌 접미사(정적으로 못 풂)
	}
	for _, c := range cases {
		m := inv.Map(c.name, c.source)
		if m.Status != MappingUnmatched || m.AssetRef != nil || !strings.Contains(m.Reason, c.reason) {
			t.Errorf("%s: %+v", c.name, m)
		}
	}
	var nilInv *Inventory
	if m := nilInv.Map("fs__read_text_file", "mcp"); m.Status != MappingUnmatched {
		t.Errorf("nil inventory: %+v", m)
	}
}

// 노드 쪽 서버(nodeHost.mcp.servers)의 도구는 "<서버>_<도구>"(밑줄 1개)로 노출된다(테스트베드 P2 실측,
// nodes describe의 nodePluginTools). 같은 서버 키가 Gateway·Node 양쪽에 있어도 이름 규칙이 달라 겹치지 않는다.
func TestMapNodeHostedTools(t *testing.T) {
	inv := loadInv(t, func(m map[string]any) {
		assets := m["assets"].([]any)
		assets = append(assets,
			map[string]any{"asset_id": "srv-fs-node", "asset_type": "mcp_server", "name": "fs", "evidence_refs": []string{"ev-node"},
				"product": map[string]any{"config_path": "nodeHost.mcp.servers.fs"}},
			map[string]any{"asset_id": "tool-fs-node-read", "asset_type": "tool", "name": "read_text_file", "owner_ref": "srv-fs-node",
				"evidence_refs": []string{"ev-node-tools"}, "mcp": map[string]any{"definition": map[string]any{"name": "read_text_file"}}},
			map[string]any{"asset_id": "srv-kg", "asset_type": "mcp_server", "name": "kg-memory", "evidence_refs": []string{"ev-node"},
				"product": map[string]any{"config_path": "nodeHost.mcp.servers.kg-memory"}},
			map[string]any{"asset_id": "tool-kg-add", "asset_type": "tool", "name": "add_observations", "owner_ref": "srv-kg",
				"evidence_refs": []string{"ev-kg-tools"}, "mcp": map[string]any{"definition": map[string]any{"name": "add_observations"}}},
		)
		m["assets"] = assets
	})
	// 게이트웨이 쪽 이름은 게이트웨이 서버 도구에만 연결된다.
	if m := inv.Map("fs__read_text_file", "mcp"); m.Status != MappingMatched || *m.AssetRef != "tool-fs-read" {
		t.Fatalf("gateway: %+v", m)
	}
	// 노드 쪽 이름. 도구 이름 안의 밑줄(add_observations)이 있어도 서버 키로 정확히 맞춘다.
	for _, src := range []string{"mcp", "plugin", ""} {
		m := inv.Map("kg-memory_add_observations", src)
		if m.Status != MappingMatched || *m.AssetRef != "tool-kg-add" || !strings.Contains(m.Reason, "node-hosted") {
			t.Fatalf("node(%q): %+v", src, m)
		}
	}
	if m := inv.Map("fs_read_text_file", "plugin"); m.Status != MappingMatched || *m.AssetRef != "tool-fs-node-read" {
		t.Fatalf("node fs: %+v", m)
	}
	// 내장 도구 출처면 연결하지 않고, 노드 서버를 게이트웨이 규칙(__)으로 부르면 후보가 없다.
	if m := inv.Map("kg-memory_add_observations", "core"); m.Status != MappingUnmatched {
		t.Fatalf("core: %+v", m)
	}
	if m := inv.Map("kg-memory__add_observations", "mcp"); m.Status != MappingUnmatched {
		t.Fatalf("node via __: %+v", m)
	}
	if k, ok := inv.ToolServerKey("tool-kg-add"); !ok || k != "kg-memory" {
		t.Fatalf("server key: %q %v", k, ok)
	}
}

// 스냅샷에 같은 노출 이름이 나오는 Tool이 둘이면(같은 서버의 동명 Tool 중복 등) 어느 쪽인지 모르므로 ambiguous.
func TestMapAmbiguousWhenExposedNameRepeats(t *testing.T) {
	inv := loadInv(t, func(m map[string]any) {
		m["assets"] = append(m["assets"].([]any),
			map[string]any{"asset_id": "tool-fs-read-dup", "asset_type": "tool", "name": "read_text_file", "owner_ref": "srv-fs",
				"evidence_refs": []string{"ev-dup"}, "mcp": map[string]any{"definition": map[string]any{"name": "read_text_file"}}})
	})
	m := inv.Map("fs__read_text_file", "mcp")
	if m.Status != MappingAmbiguous || m.AssetRef != nil || !strings.Contains(m.Reason, "tool-fs-read-dup") {
		t.Fatalf("%+v", m)
	}
	if m := inv.Map("fs__list_directory_with_sizes", "mcp"); m.Status != MappingMatched {
		t.Fatalf("%+v", m)
	}
}

func TestMapRequiresEvidence(t *testing.T) {
	inv := loadInv(t, func(m map[string]any) {
		for _, a := range m["assets"].([]any) {
			if a.(map[string]any)["asset_id"] == "tool-fs-list" {
				a.(map[string]any)["evidence_refs"] = []string{}
			}
		}
	})
	if m := inv.Map("fs__list_directory_with_sizes", "mcp"); m.Status != MappingUnmatched {
		t.Fatalf("matched without evidence: %+v", m)
	}
}

// 실제 로그 + 스냅샷: MCP 도구는 matched, 내장 도구는 unmatched.
func TestBuildWithInventory(t *testing.T) {
	opt := baseOpts()
	opt.Inventory = loadInv(t, nil)
	rep := mustBuild(t, loadFixture(t, "week3-sequential-batch"), opt)
	counts := map[string]int{}
	for _, r := range rep.Records {
		counts[r.ToolSource+"/"+r.MappingStatus]++
		if r.MappingStatus == MappingMatched && (r.AssetRef == nil || *r.AssetRef != "tool-fs-read") {
			t.Errorf("%s mapped to %v", r.ToolName, deref(r.AssetRef))
		}
	}
	if counts["mcp/matched"] != 4 || counts["core/unmatched"] != 9 || len(counts) != 2 {
		t.Fatalf("mapping counts %v", counts)
	}
}

// ToolOwner는 매핑된 Tool의 소속 서버를 돌려준다(대시보드 서버 단위 묶음용).
func TestToolOwner(t *testing.T) {
	inv := loadInv(t, nil)
	if srv, ok := inv.ToolOwner("tool-fs-read"); !ok || srv != "srv-fs" {
		t.Fatalf("tool-fs-read: %q %v", srv, ok)
	}
	if _, ok := inv.ToolOwner("srv-fs"); ok {
		t.Fatal("서버 자산은 Tool이 아님")
	}
	var nilInv *Inventory
	if _, ok := nilInv.ToolOwner("tool-fs-read"); ok {
		t.Fatal("nil inventory")
	}
}

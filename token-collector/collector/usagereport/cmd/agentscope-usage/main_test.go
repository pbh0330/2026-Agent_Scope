package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// CLI 전체 흐름 + 출력에 입력 파일의 전체 경로(사용자 이름 포함 가능)가 남지 않는지(QA-USE-08).
func TestCLIWritesUsageJSONWithoutLocalPaths(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "Users", "someone-private")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	src, err := os.ReadFile("../../../attribution/testdata/week3-sequential-batch.spans.json")
	if err != nil {
		t.Fatal(err)
	}
	in := filepath.Join(dir, "traces.jsonl")
	if err := os.WriteFile(in, src, 0o644); err != nil {
		t.Fatal(err)
	}
	cfg := filepath.Join(dir, "openclaw.json")
	os.WriteFile(cfg, []byte(`{"models":{"providers":{"p":{"apiKey":"sk-test-should-not-leak","models":[{"id":"claude-haiku-4-5-20251001","cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0}}]}}}}`), 0o644)
	out := filepath.Join(dir, "usage.json")

	var stderr bytes.Buffer
	err = run([]string{"--env", "env-test-01", "--profile", "profile-test-01", "--input", in,
		"--inventory", "../../testdata/inventory-fs.json", "--openclaw-config", cfg, "--out", out}, &bytes.Buffer{}, &stderr)
	if err != nil {
		t.Fatalf("%v\n%s", err, stderr.String())
	}
	b, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	for _, leak := range []string{"someone-private", "sk-test-should-not-leak", dir} {
		if strings.Contains(string(b), leak) {
			t.Errorf("output contains %q", leak)
		}
	}
	var rep struct {
		Records []struct {
			MappingStatus string `json:"mapping_status"`
			Pricing       struct {
				Source string `json:"source"`
			} `json:"pricing"`
			EvidenceSourceRefs []string `json:"evidence_source_refs"`
		} `json:"records"`
	}
	if err := json.Unmarshal(b, &rep); err != nil {
		t.Fatal(err)
	}
	if len(rep.Records) != 13 {
		t.Fatalf("records = %d", len(rep.Records))
	}
	for _, r := range rep.Records {
		if r.Pricing.Source != "reference_list_price" { // 설정 단가 0 → 참고 정가
			t.Errorf("pricing source %s", r.Pricing.Source)
		}
		if !strings.HasPrefix(r.EvidenceSourceRefs[0], "otlp-json:traces.jsonl#trace=") {
			t.Errorf("evidence ref %s", r.EvidenceSourceRefs[0])
		}
	}
}

func TestCLIRequiresInputAndIDs(t *testing.T) {
	if err := run([]string{"--env", "e", "--profile", "p"}, &bytes.Buffer{}, &bytes.Buffer{}); err == nil {
		t.Fatal("missing --input must fail")
	}
	if err := run([]string{"--input", "../../../attribution/testdata/week1-sequential.spans.json"}, &bytes.Buffer{}, &bytes.Buffer{}); err == nil {
		t.Fatal("missing --env/--profile must fail")
	}
}

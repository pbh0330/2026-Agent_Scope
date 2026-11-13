package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"
)

func TestRunServesAndShutsDown(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	ready := make(chan string, 1)
	errc := make(chan error, 1)
	var stderr bytes.Buffer
	go func() {
		errc <- run(ctx, []string{"--env", "env-pc", "--profile", "profile-pc",
			"--input", "../../testdata/pc-1029.traces.jsonl", "--addr", "127.0.0.1:0"}, &stderr, ready)
	}()
	var addr string
	select {
	case addr = <-ready:
	case err := <-errc:
		t.Fatalf("run: %v (%s)", err, stderr.String())
	case <-time.After(10 * time.Second):
		t.Fatal("서버가 뜨지 않음")
	}
	resp, err := http.Get("http://" + addr + "/api/v1/usage/health")
	if err != nil {
		t.Fatal(err)
	}
	var h struct {
		Status  string `json:"status"`
		Mode    string `json:"mode"`
		Records int    `json:"records"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&h); err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if h.Status != "ok" || h.Mode != "fixed" || h.Records != 16 {
		t.Fatalf("health: %+v", h)
	}
	cancel()
	select {
	case err := <-errc:
		if err != nil {
			t.Fatalf("shutdown: %v", err)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("종료되지 않음")
	}
}

func TestRunRequiresInput(t *testing.T) {
	var stderr bytes.Buffer
	if err := run(context.Background(), []string{"--env", "e", "--profile", "p"}, &stderr, nil); err == nil {
		t.Fatal("입력 없이 시작하면 안 됨")
	}
}

func TestRunLiveMode(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	ready := make(chan string, 1)
	errc := make(chan error, 1)
	var stderr bytes.Buffer
	missing := t.TempDir() + "/agentscope-traces*.jsonl" // 아직 파일 없음(Collector 첫 요청 전)
	go func() {
		errc <- run(ctx, []string{"--env", "e", "--profile", "p", "--input", missing, "--live",
			"--reload-interval", "1s", "--addr", "127.0.0.1:0"}, &stderr, ready)
	}()
	var addr string
	select {
	case addr = <-ready:
	case err := <-errc:
		t.Fatalf("run: %v (%s)", err, stderr.String())
	case <-time.After(10 * time.Second):
		t.Fatal("서버가 뜨지 않음")
	}
	resp, err := http.Get("http://" + addr + "/api/v1/usage/health")
	if err != nil {
		t.Fatal(err)
	}
	var h struct {
		Status  string `json:"status"`
		Mode    string `json:"mode"`
		Records int    `json:"records"`
	}
	json.NewDecoder(resp.Body).Decode(&h)
	resp.Body.Close()
	if h.Status != "ok" || h.Mode != "live" || h.Records != 0 {
		t.Fatalf("health: %+v", h)
	}
}

func TestRunLiveRejectsFromTo(t *testing.T) {
	var stderr bytes.Buffer
	err := run(context.Background(), []string{"--env", "e", "--profile", "p", "--input", "x", "--live",
		"--from", "2026-10-29T00:00:00Z", "--to", "2026-10-30T00:00:00Z"}, &stderr, nil)
	if err == nil {
		t.Fatal("--live와 --from/--to를 같이 쓰면 안 됨")
	}
}

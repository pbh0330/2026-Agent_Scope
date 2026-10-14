package usagereport

import (
	"bytes"
	"encoding/json"
	"fmt"
	"reflect"
	"testing"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/attribution"
)

// toOTLPLines는 스팬을 Collector file 익스포터와 같은 OTLP JSON 줄로 만든다(chunk개씩 한 줄).
func toOTLPLines(t *testing.T, spans []attribution.Span, chunk int) []byte {
	t.Helper()
	var buf bytes.Buffer
	for i := 0; i < len(spans); i += chunk {
		var out []map[string]any
		for _, s := range spans[i:min(i+chunk, len(spans))] {
			var attrs []map[string]any
			for k, v := range s.Attrs {
				var val map[string]any
				switch x := v.(type) {
				case int64:
					val = map[string]any{"intValue": fmt.Sprint(x)} // OTLP JSON은 int64를 문자열로
				case float64:
					val = map[string]any{"doubleValue": x}
				case bool:
					val = map[string]any{"boolValue": x}
				default:
					val = map[string]any{"stringValue": fmt.Sprint(x)}
				}
				attrs = append(attrs, map[string]any{"key": k, "value": val})
			}
			d := map[string]any{"traceId": s.TraceID, "spanId": s.SpanID, "name": s.Name, "kind": 1, "attributes": attrs}
			if !s.Start.IsZero() {
				d["startTimeUnixNano"] = fmt.Sprint(s.Start.UnixNano())
			}
			if !s.End.IsZero() {
				d["endTimeUnixNano"] = fmt.Sprint(s.End.UnixNano())
			}
			if s.ParentID != "" {
				d["parentSpanId"] = s.ParentID
			}
			out = append(out, d)
		}
		line := map[string]any{"resourceSpans": []any{map[string]any{
			"resource":   map[string]any{"attributes": []any{map[string]any{"key": "service.name", "value": map[string]any{"stringValue": "openclaw"}}}},
			"scopeSpans": []any{map[string]any{"scope": map[string]any{"name": "openclaw"}, "spans": out}},
		}}}
		b, err := json.Marshal(line)
		if err != nil {
			t.Fatal(err)
		}
		buf.Write(b)
		buf.WriteByte('\n')
	}
	return buf.Bytes()
}

// 같은 스팬을 OTLP JSON(file 익스포터 형식)으로 읽어도 픽스처로 읽은 것과 결과가 같아야 한다.
func TestOTLPJSONLinesEqualFixture(t *testing.T) {
	for _, name := range fixtures {
		spans := loadFixture(t, name)
		data := append([]byte{0xEF, 0xBB, 0xBF}, toOTLPLines(t, spans, 3)...) // BOM 포함
		got, err := ReadSpans(bytes.NewReader(data))
		if err != nil {
			t.Fatal(err)
		}
		if len(got) != len(spans) {
			t.Fatalf("%s: spans %d vs %d", name, len(got), len(spans))
		}
		for i := range spans {
			if !reflect.DeepEqual(got[i].Attrs, spans[i].Attrs) || !got[i].Start.Equal(spans[i].Start) || got[i].ParentID != spans[i].ParentID {
				t.Fatalf("%s span %d differs:\n otlp %+v\n fixture %+v", name, i, got[i], spans[i])
			}
		}
		a, b := mustBuild(t, got, baseOpts()), mustBuild(t, spans, baseOpts())
		if a.UsageReportID != b.UsageReportID {
			t.Fatalf("%s: report differs between OTLP and fixture input", name)
		}
	}
}

func TestReadSpansEmptyAndInvalid(t *testing.T) {
	if s, err := ReadSpans(bytes.NewReader([]byte("  \n"))); err != nil || len(s) != 0 {
		t.Fatalf("empty: %v %v", s, err)
	}
	if _, err := ReadSpans(bytes.NewReader([]byte(`{"resourceSpans":[}`))); err == nil {
		t.Fatal("invalid JSON must fail")
	}
}

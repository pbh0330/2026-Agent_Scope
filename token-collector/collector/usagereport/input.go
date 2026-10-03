package usagereport

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strconv"
	"time"

	"github.com/pbh0330/2026-Agent_Scope/token-collector/collector/attribution"
)

// ReadSpansFile은 스팬 파일을 읽는다. 두 형식을 자동 구분한다.
//
//   - OTLP JSON 줄 단위(JSON Lines): Collector file 익스포터 출력. 한 줄 = ExportTraceServiceRequest
//     ({"resourceSpans":[...]}). OTLP/HTTP JSON 요청 본문 하나를 그대로 저장한 파일도 된다.
//   - 픽스처 배열: export_fixtures.py가 만든 [{"trace_id":..,"span_id":..,"attrs":{..}}, ...]
func ReadSpansFile(path string) ([]attribution.Span, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return ReadSpans(f)
}

// ReadSpans는 ReadSpansFile의 io.Reader 버전이다.
func ReadSpans(r io.Reader) ([]attribution.Span, error) {
	br := bufio.NewReaderSize(r, 1<<20)
	first, err := firstNonSpace(br)
	if err == io.EOF {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	if first == '[' {
		return readFixture(br)
	}
	return readOTLPLines(br)
}

func firstNonSpace(br *bufio.Reader) (byte, error) {
	for {
		b, err := br.ReadByte()
		if err != nil {
			return 0, err
		}
		// UTF-8 BOM(EF BB BF)은 건너뛴다(Windows 메모장 저장 파일 대비).
		if b == 0xEF {
			if p, _ := br.Peek(2); len(p) == 2 && p[0] == 0xBB && p[1] == 0xBF {
				br.Discard(2)
				continue
			}
		}
		if b != ' ' && b != '\n' && b != '\r' && b != '\t' {
			return b, br.UnreadByte()
		}
	}
}

// --- OTLP JSON ---

type otlpRequest struct {
	ResourceSpans []struct {
		ScopeSpans []struct {
			Spans []otlpSpan `json:"spans"`
		} `json:"scopeSpans"`
	} `json:"resourceSpans"`
}

type otlpSpan struct {
	TraceID      string     `json:"traceId"`
	SpanID       string     `json:"spanId"`
	ParentSpanID string     `json:"parentSpanId"`
	Name         string     `json:"name"`
	Start        jsonUint64 `json:"startTimeUnixNano"`
	End          jsonUint64 `json:"endTimeUnixNano"`
	Attributes   []struct {
		Key   string    `json:"key"`
		Value otlpValue `json:"value"`
	} `json:"attributes"`
}

type otlpValue struct {
	StringValue *string    `json:"stringValue"`
	IntValue    *jsonInt64 `json:"intValue"`
	DoubleValue *float64   `json:"doubleValue"`
	BoolValue   *bool      `json:"boolValue"`
}

// OTLP JSON은 64비트 정수를 문자열로 싣는다(숫자로 와도 받는다).
type jsonUint64 uint64

func (v *jsonUint64) UnmarshalJSON(b []byte) error {
	s := string(bytes.Trim(b, `"`))
	if s == "" || s == "null" {
		*v = 0
		return nil
	}
	n, err := strconv.ParseUint(s, 10, 64)
	*v = jsonUint64(n)
	return err
}

type jsonInt64 int64

func (v *jsonInt64) UnmarshalJSON(b []byte) error {
	n, err := strconv.ParseInt(string(bytes.Trim(b, `"`)), 10, 64)
	*v = jsonInt64(n)
	return err
}

func readOTLPLines(r io.Reader) ([]attribution.Span, error) {
	dec := json.NewDecoder(r) // 줄바꿈 여부와 관계없이 연속된 JSON 객체를 차례로 읽는다
	var out []attribution.Span
	for n := 1; ; n++ {
		var req otlpRequest
		if err := dec.Decode(&req); err == io.EOF {
			return out, nil
		} else if err != nil {
			return nil, fmt.Errorf("OTLP JSON %d번째 객체 파싱 실패: %w", n, err)
		}
		for _, rs := range req.ResourceSpans {
			for _, ss := range rs.ScopeSpans {
				for _, s := range ss.Spans {
					out = append(out, s.toSpan())
				}
			}
		}
	}
}

func nanoTime(n uint64) time.Time {
	if n == 0 {
		return time.Time{}
	}
	return time.Unix(0, int64(n)).UTC()
}

func (s otlpSpan) toSpan() attribution.Span {
	attrs := make(map[string]any, len(s.Attributes))
	for _, a := range s.Attributes {
		switch v := a.Value; {
		case v.StringValue != nil:
			attrs[a.Key] = *v.StringValue
		case v.IntValue != nil:
			attrs[a.Key] = int64(*v.IntValue)
		case v.DoubleValue != nil:
			attrs[a.Key] = *v.DoubleValue
		case v.BoolValue != nil:
			attrs[a.Key] = *v.BoolValue
		}
	}
	return attribution.Span{
		TraceID: s.TraceID, ParentID: s.ParentSpanID, SpanID: s.SpanID, Name: s.Name,
		Start: nanoTime(uint64(s.Start)), End: nanoTime(uint64(s.End)), Attrs: attrs,
	}
}

// --- 픽스처 배열 ---

type fixtureSpan struct {
	TraceID   string         `json:"trace_id"`
	ParentID  string         `json:"parent_id"`
	SpanID    string         `json:"span_id"`
	Name      string         `json:"name"`
	StartNano *int64         `json:"start_unix_nano"`
	EndNano   *int64         `json:"end_unix_nano"`
	Attrs     map[string]any `json:"attrs"`
}

func readFixture(r io.Reader) ([]attribution.Span, error) {
	dec := json.NewDecoder(r)
	dec.UseNumber()
	var raw []fixtureSpan
	if err := dec.Decode(&raw); err != nil {
		return nil, fmt.Errorf("픽스처 파싱 실패: %w", err)
	}
	out := make([]attribution.Span, 0, len(raw))
	for _, f := range raw {
		attrs := map[string]any{}
		for k, v := range f.Attrs {
			if n, ok := v.(json.Number); ok {
				if i, err := n.Int64(); err == nil {
					attrs[k] = i
				} else if fl, err := n.Float64(); err == nil {
					attrs[k] = fl
				}
				continue
			}
			attrs[k] = v
		}
		s := attribution.Span{TraceID: f.TraceID, ParentID: f.ParentID, SpanID: f.SpanID, Name: f.Name, Attrs: attrs}
		if f.StartNano != nil {
			s.Start = time.Unix(0, *f.StartNano).UTC()
		}
		if f.EndNano != nil {
			s.End = time.Unix(0, *f.EndNano).UTC()
		}
		out = append(out, s)
	}
	return out, nil
}

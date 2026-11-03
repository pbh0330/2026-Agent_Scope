package usageapi

import (
	"errors"
	"fmt"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// MaxWindow는 한 번에 조회할 수 있는 최대 기간이다.
const MaxWindow = 7 * 24 * time.Hour

type window struct{ start, end time.Time }

func (w window) contains(t time.Time) bool { return !t.Before(w.start) && t.Before(w.end) }

// parseWindow는 from/to 또는 range로 조회 구간을 정한다.
//   - 아무것도 없으면 데이터 구간 전체
//   - range(15m, 1h, 24h, 7d 등)는 기준 시각(now)에서 거꾸로 잰다. 고정 응답 모드의 기준 시각은 데이터 구간 끝
//   - from/to는 RFC3339(UTC 권장). 하나만 주면 나머지는 데이터 구간 끝/시작
func parseWindow(q url.Values, ds *Dataset, now time.Time) (window, error) {
	from, to, rng := q.Get("from"), q.Get("to"), q.Get("range")
	if rng != "" && (from != "" || to != "") {
		return window{}, errors.New("range와 from/to는 함께 쓸 수 없음")
	}
	w := window{start: ds.Start, end: ds.End}
	switch {
	case rng != "":
		d, err := parseRange(rng)
		if err != nil {
			return window{}, err
		}
		w = window{start: now.Add(-d), end: now}
	case from != "" || to != "":
		if from != "" {
			t, err := time.Parse(time.RFC3339Nano, from)
			if err != nil {
				return window{}, fmt.Errorf("from: RFC3339 시각이어야 함")
			}
			w.start = t.UTC()
		}
		if to != "" {
			t, err := time.Parse(time.RFC3339Nano, to)
			if err != nil {
				return window{}, fmt.Errorf("to: RFC3339 시각이어야 함")
			}
			w.end = t.UTC()
		}
	}
	if !w.start.Before(w.end) {
		return window{}, errors.New("구간 시작이 끝보다 앞이어야 함")
	}
	if w.end.Sub(w.start) > MaxWindow {
		return window{}, errors.New("조회 구간은 최대 7일")
	}
	return w, nil
}

// parseRange는 "15m", "1h", "24h", "7d" 같은 기간을 읽는다.
func parseRange(s string) (time.Duration, error) {
	var d time.Duration
	if n, ok := strings.CutSuffix(s, "d"); ok {
		days, err := strconv.Atoi(n)
		if err != nil || days <= 0 {
			return 0, fmt.Errorf("range: %q를 읽을 수 없음(예: 15m, 1h, 24h, 7d)", s)
		}
		d = time.Duration(days) * 24 * time.Hour
	} else {
		var err error
		if d, err = time.ParseDuration(s); err != nil || d <= 0 {
			return 0, fmt.Errorf("range: %q를 읽을 수 없음(예: 15m, 1h, 24h, 7d)", s)
		}
	}
	if d > MaxWindow {
		return 0, errors.New("조회 구간은 최대 7일")
	}
	return d, nil
}

// 묶음 기준(by-asset?group=).
const (
	GroupAsset   = "asset"   // 매핑된 자산 ID, 못 찾으면 도구 이름
	GroupTool    = "tool"    // 도구 이름
	GroupServer  = "server"  // MCP 서버(매핑되면 서버 asset_id, 아니면 서버 이름), 내장 도구는 출처별
	GroupPattern = "pattern" // 구간 유형(sequential/parallel/batch/unattributed)
)

func parseGroup(q url.Values) (string, error) {
	switch g := q.Get("group"); g {
	case "":
		return GroupAsset, nil
	case GroupAsset, GroupTool, GroupServer, GroupPattern:
		return g, nil
	default:
		return "", fmt.Errorf("group: asset, tool, server, pattern 중 하나")
	}
}

const (
	defaultLimit = 50
	maxLimit     = 500
)

func parseLimit(q url.Values) (int, error) {
	s := q.Get("limit")
	if s == "" {
		return defaultLimit, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 || n > maxLimit {
		return 0, fmt.Errorf("limit: 1~%d", maxLimit)
	}
	return n, nil
}

// cursor는 다음 쪽 시작 위치(최신순 목록의 오프셋)다. 고정 응답 모드에서는 목록이 바뀌지 않으므로 오프셋으로 충분하다.
func parseCursor(q url.Values) (int, error) {
	s := q.Get("cursor")
	if s == "" {
		return 0, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 0 {
		return 0, errors.New("cursor: 이전 응답의 next_cursor 값을 그대로 쓸 것")
	}
	return n, nil
}

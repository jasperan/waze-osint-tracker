package components

import (
	"sync"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

var sparkChars = []rune{'▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'}

// ThroughputTracker is a ring buffer of 300 one-second buckets (5 minutes).
type ThroughputTracker struct {
	mu      sync.Mutex
	buckets [300]int
	times   [300]int64
	head    int
}

// NewThroughputTracker creates a new ThroughputTracker.
func NewThroughputTracker() *ThroughputTracker {
	return &ThroughputTracker{}
}

// Add increments current bucket by n.
func (t *ThroughputTracker) Add(n int) {
	t.mu.Lock()
	defer t.mu.Unlock()
	now := time.Now().Unix()
	t.advance(now)
	t.buckets[t.head] += n
}

// advance moves head forward to current time, zeroing skipped buckets.
func (t *ThroughputTracker) advance(now int64) {
	last := t.times[t.head]
	if last == 0 {
		t.times[t.head] = now
		return
	}
	diff := now - last
	if diff <= 0 {
		return
	}
	if diff > 300 {
		diff = 300
	}
	for i := int64(0); i < diff; i++ {
		t.head = (t.head + 1) % 300
		t.buckets[t.head] = 0
		t.times[t.head] = last + i + 1
	}
}

// CurrentRate returns events/min averaged over last 5 seconds.
func (t *ThroughputTracker) CurrentRate() float64 {
	t.mu.Lock()
	defer t.mu.Unlock()
	now := time.Now().Unix()
	t.advance(now)

	sum := 0
	for i := 0; i < 5; i++ {
		idx := (t.head - i + 300) % 300
		sum += t.buckets[idx]
	}
	// 5 seconds -> events per minute
	return float64(sum) / 5.0 * 60.0
}

// Sparkline renders last `width` buckets as spark characters.
func (t *ThroughputTracker) Sparkline(width int) string {
	t.mu.Lock()
	defer t.mu.Unlock()
	now := time.Now().Unix()
	t.advance(now)

	if width <= 0 {
		return ""
	}
	if width > 300 {
		width = 300
	}

	vals := make([]int, width)
	maxVal := 0
	for i := 0; i < width; i++ {
		idx := (t.head - (width - 1 - i) + 300) % 300
		v := t.buckets[idx]
		vals[i] = v
		if v > maxVal {
			maxVal = v
		}
	}

	style := lipgloss.NewStyle().Foreground(theme.Primary)

	runes := make([]rune, width)
	for i, v := range vals {
		if maxVal == 0 {
			runes[i] = sparkChars[0]
		} else {
			level := int(float64(v) / float64(maxVal) * float64(len(sparkChars)-1))
			if level >= len(sparkChars) {
				level = len(sparkChars) - 1
			}
			runes[i] = sparkChars[level]
		}
	}

	return style.Render(string(runes))
}

// RenderThroughput combines sparkline + rate text.
func RenderThroughput(t *ThroughputTracker, width int) string {
	rate := t.CurrentRate()
	rateStr := " " + FormatEventRate(rate)
	sparkWidth := width - len([]rune(rateStr))
	if sparkWidth < 1 {
		sparkWidth = 1
	}
	return t.Sparkline(sparkWidth) + rateStr
}

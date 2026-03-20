package components

import (
	"fmt"
	"strings"

	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// StatusBarData holds the three sections of a status bar.
type StatusBarData struct {
	Left   string
	Center string
	Right  string
}

// RenderStatusBar renders a full-width status bar with left/center/right alignment.
func RenderStatusBar(d StatusBarData, width int) string {
	leftW := len([]rune(d.Left))
	centerW := len([]rune(d.Center))
	rightW := len([]rune(d.Right))

	gap1 := width/2 - leftW - centerW/2
	if gap1 < 0 {
		gap1 = 0
	}
	gap2 := width - leftW - gap1 - centerW - rightW
	if gap2 < 0 {
		gap2 = 0
	}

	content := d.Left + strings.Repeat(" ", gap1) + d.Center + strings.Repeat(" ", gap2) + d.Right

	return theme.StatusBar.Copy().Width(width).Render(content)
}

// FormatEventRate formats a float as "X.X evt/min".
func FormatEventRate(eventsPerMin float64) string {
	return fmt.Sprintf("%.1f evt/min", eventsPerMin)
}

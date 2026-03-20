package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// RegionData holds stats for one collection region.
type RegionData struct {
	Name      string
	Running   bool
	Erroring  bool
	Cycle     int
	Events    int
	Delta     int
	Errors    int
	Cells     int
	EventRate float64
}

// RenderRegionPane renders a single region panel with status dot, stats, and colored border.
func RenderRegionPane(d RegionData, width int, active bool) string {
	regionColor := theme.RegionColor(d.Name)
	regionStyle := lipgloss.NewStyle().Foreground(regionColor)
	dimStyle := lipgloss.NewStyle().Foreground(theme.DimColor)
	successStyle := lipgloss.NewStyle().Foreground(theme.Success)
	errorStyle := lipgloss.NewStyle().Foreground(theme.Error)

	// Status dot.
	var dot string
	switch {
	case d.Erroring:
		dot = errorStyle.Render(theme.StatusDot)
	case d.Running:
		dot = successStyle.Render(theme.StatusDot)
	default:
		dot = dimStyle.Render(theme.StatusDotInactive)
	}

	// Header line.
	header := dot + " " + regionStyle.Render(lipgloss.NewStyle().Bold(true).Foreground(regionColor).Render(strings.ToUpper(d.Name)))
	if d.Running {
		header += " " + dimStyle.Render(fmt.Sprintf("cycle %d", d.Cycle))
	}

	// Body.
	var body string
	if !d.Running && !d.Erroring {
		body = dimStyle.Render("Idle")
	} else {
		deltaStr := ""
		if d.Delta > 0 {
			deltaStr = " " + successStyle.Render(fmt.Sprintf("+%d", d.Delta))
		}
		eventsLine := fmt.Sprintf("Events: %d", d.Events) + deltaStr
		errCellsLine := fmt.Sprintf("Errors: %d  Cells: %d", d.Errors, d.Cells)
		rateLine := fmt.Sprintf("Rate:   %.1f/min", d.EventRate)
		body = eventsLine + "\n" + errCellsLine + "\n" + rateLine
	}

	content := header + "\n" + body

	// Inner width: subtract border (2) and padding (2).
	innerWidth := width - 4
	if innerWidth < 1 {
		innerWidth = 1
	}

	var panelStyle lipgloss.Style
	if active {
		panelStyle = theme.ActivePanel.Copy().
			BorderForeground(regionColor).
			Width(innerWidth)
	} else {
		panelStyle = theme.Panel.Copy().
			BorderForeground(regionColor).
			Width(innerWidth)
	}

	return panelStyle.Render(content)
}

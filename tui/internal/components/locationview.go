package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// densityChars maps density levels to display characters.
var densityChars = []rune{' ', '·', '░', '▒', '▓', '█'}

// RenderLocationView renders a density grid of events as a map-like view.
func RenderLocationView(events []api.Event, width, height int) string {
	dimStyle := lipgloss.NewStyle().Foreground(theme.DimColor)

	if len(events) == 0 {
		return dimStyle.Render("  no location data")
	}

	gridW := width - 4
	gridH := height - 4
	if gridW < 2 {
		gridW = 2
	}
	if gridH < 2 {
		gridH = 2
	}

	// Find bounds
	minLat, maxLat := events[0].Latitude, events[0].Latitude
	minLon, maxLon := events[0].Longitude, events[0].Longitude
	for _, e := range events {
		if e.Latitude < minLat {
			minLat = e.Latitude
		}
		if e.Latitude > maxLat {
			maxLat = e.Latitude
		}
		if e.Longitude < minLon {
			minLon = e.Longitude
		}
		if e.Longitude > maxLon {
			maxLon = e.Longitude
		}
	}

	// 5% padding
	latPad := (maxLat - minLat) * 0.05
	lonPad := (maxLon - minLon) * 0.05
	if latPad == 0 {
		latPad = 0.001
	}
	if lonPad == 0 {
		lonPad = 0.001
	}
	minLat -= latPad
	maxLat += latPad
	minLon -= lonPad
	maxLon += lonPad

	latRange := maxLat - minLat
	lonRange := maxLon - minLon

	// Build density grid
	grid := make([][]int, gridH)
	for i := range grid {
		grid[i] = make([]int, gridW)
	}

	for _, e := range events {
		col := int((e.Longitude - minLon) / lonRange * float64(gridW-1))
		row := int((maxLat - e.Latitude) / latRange * float64(gridH-1))
		if col < 0 {
			col = 0
		}
		if col >= gridW {
			col = gridW - 1
		}
		if row < 0 {
			row = 0
		}
		if row >= gridH {
			row = gridH - 1
		}
		grid[row][col]++
	}

	// Find max density
	maxDensity := 1
	for _, row := range grid {
		for _, v := range row {
			if v > maxDensity {
				maxDensity = v
			}
		}
	}

	primaryStyle := lipgloss.NewStyle().Foreground(theme.Primary)

	var sb strings.Builder
	for _, row := range grid {
		sb.WriteString("  ")
		for _, v := range row {
			idx := int(float64(v) / float64(maxDensity) * float64(len(densityChars)-1))
			if idx < 0 {
				idx = 0
			}
			if idx >= len(densityChars) {
				idx = len(densityChars) - 1
			}
			ch := string(densityChars[idx])
			if idx == 0 {
				sb.WriteString(dimStyle.Render(ch))
			} else {
				sb.WriteString(primaryStyle.Render(ch))
			}
		}
		sb.WriteByte('\n')
	}

	// Axis labels
	sb.WriteString(dimStyle.Render(fmt.Sprintf("  lon: %.3f – %.3f  lat: %.3f – %.3f\n",
		minLon, maxLon, minLat, maxLat)))

	return sb.String()
}

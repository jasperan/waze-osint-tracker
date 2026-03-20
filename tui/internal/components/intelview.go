package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// RenderIntelView renders an IntelProfile into a display string.
func RenderIntelView(intel *api.IntelProfile, width int) string {
	if intel == nil {
		return lipgloss.NewStyle().Foreground(theme.DimColor).Render("  no intel data")
	}
	if intel.Error != "" {
		return lipgloss.NewStyle().Foreground(theme.Error).Bold(true).Render("  error: " + intel.Error)
	}

	dimStyle := lipgloss.NewStyle().Foreground(theme.DimColor)
	textStyle := lipgloss.NewStyle().Foreground(theme.TextColor)
	boldStyle := lipgloss.NewStyle().Bold(true).Foreground(theme.TextColor)
	greenDot := lipgloss.NewStyle().Foreground(theme.Success).Render(theme.StatusDot)

	var sb strings.Builder

	// Header
	regionColor := theme.RegionColor(intel.Region)
	regionStyle := lipgloss.NewStyle().Foreground(regionColor).Bold(true)
	sb.WriteString(fmt.Sprintf("  %s  events: %s  geo spread: %.1f km\n",
		regionStyle.Render(intel.Region),
		textStyle.Render(fmt.Sprintf("%d", intel.EventCount)),
		intel.GeoSpreadKm,
	))

	// Centroid
	sb.WriteString(dimStyle.Render(fmt.Sprintf("  centroid: %.4f, %.4f\n",
		intel.CentroidLat, intel.CentroidLon)))
	sb.WriteString("\n")

	// Routines
	if len(intel.Routines) > 0 {
		sb.WriteString(boldStyle.Render("  Routines") + "\n")
		for _, r := range intel.Routines {
			conf := int(r.Confidence * 100)
			line := fmt.Sprintf("  %s %s  %.4f, %.4f  conf:%d%%  evidence:%d",
				greenDot,
				textStyle.Render(r.RoutineType),
				r.Latitude, r.Longitude,
				conf,
				r.EvidenceCount,
			)
			sb.WriteString(line + "\n")
		}
		sb.WriteString("\n")
	} else {
		sb.WriteString(dimStyle.Render("  no routines inferred") + "\n\n")
	}

	// Co-occurrences
	if len(intel.CoOccurrences) > 0 {
		sb.WriteString(boldStyle.Render("  Co-occurrences") + "\n")
		for _, c := range intel.CoOccurrences {
			line := fmt.Sprintf("  %s  %s  avg dist: %.0f m",
				textStyle.Render(c.Partner),
				dimStyle.Render(fmt.Sprintf("×%d", c.CoCount)),
				c.AvgDistanceM,
			)
			sb.WriteString(line + "\n")
		}
	} else {
		sb.WriteString(dimStyle.Render("  no co-occurrences") + "\n")
	}

	_ = width // reserved for future truncation
	return sb.String()
}

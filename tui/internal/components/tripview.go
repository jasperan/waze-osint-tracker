package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// RenderTripView renders a TripResponse into a display string of the given width.
func RenderTripView(resp *api.TripResponse, width int) string {
	if resp == nil {
		return lipgloss.NewStyle().Foreground(theme.DimColor).Render("  no trip data")
	}
	if resp.Error != "" {
		return lipgloss.NewStyle().Foreground(theme.Error).Bold(true).Render("  error: " + resp.Error)
	}
	if len(resp.Trips) == 0 {
		return lipgloss.NewStyle().Foreground(theme.DimColor).Render("  no trips reconstructed")
	}

	greenDot := lipgloss.NewStyle().Foreground(theme.Success).Render(theme.StatusDot)
	boldStyle := lipgloss.NewStyle().Bold(true).Foreground(theme.TextColor)
	dimStyle := lipgloss.NewStyle().Foreground(theme.DimColor)
	mutedStyle := lipgloss.NewStyle().Foreground(theme.DimColor)

	var sb strings.Builder

	for _, t := range resp.Trips {
		// Direction arrows
		var arrows string
		switch t.TripType {
		case "morning_commute":
			arrows = lipgloss.NewStyle().Foreground(theme.Primary).Render("▸▸▸▸▸▸")
		case "evening_commute":
			arrows = lipgloss.NewStyle().Foreground(theme.Oceania).Render("◂◂◂◂◂◂")
		case "round_trip":
			arrows = lipgloss.NewStyle().Foreground(theme.Warning).Render("◂▸◂▸")
		default:
			arrows = dimStyle.Render("──────")
		}

		// Parse time strings to HH:MM — accept RFC3339 or "HH:MM:SS" or pass through
		startTime := formatTripTime(t.StartTime)
		endTime := formatTripTime(t.EndTime)

		typeName := boldStyle.Render(t.TripType)
		meta := fmt.Sprintf("%s–%s  %.1f km  %.0f min", startTime, endTime, t.DistanceKm, t.DurationMin)

		sb.WriteString(fmt.Sprintf("%s %s  %s  %s\n", greenDot, typeName, mutedStyle.Render(meta), arrows))

		// Route line
		if t.StartArea != "" || t.EndArea != "" {
			start := t.StartArea
			end := t.EndArea
			if start == "" {
				start = "?"
			}
			if end == "" {
				end = "?"
			}
			regularity := ""
			if t.Regularity > 0 {
				regularity = fmt.Sprintf(" (%.0f%%)", t.Regularity*100)
			}
			route := fmt.Sprintf("    %s → %s%s", start, end, regularity)
			sb.WriteString(dimStyle.Render(route) + "\n")
		}
		sb.WriteByte('\n')
	}

	// Summary footer
	s := resp.Summary
	sb.WriteString(dimStyle.Render(strings.Repeat("─", width)) + "\n")
	sb.WriteString(fmt.Sprintf("  %s  avg daily: %s",
		dimStyle.Render(fmt.Sprintf("%d trips", s.TotalTrips)),
		dimStyle.Render(fmt.Sprintf("%.1f", s.AvgDailyTrips)),
	) + "\n")
	if s.InferredHome != "" {
		sb.WriteString(dimStyle.Render(fmt.Sprintf("  home: %s", s.InferredHome)) + "\n")
	}
	if s.InferredWork != "" {
		sb.WriteString(dimStyle.Render(fmt.Sprintf("  work: %s", s.InferredWork)) + "\n")
	}

	return sb.String()
}

// formatTripTime extracts HH:MM from various time string formats.
func formatTripTime(ts string) string {
	if len(ts) >= 16 && ts[10] == 'T' {
		// RFC3339: 2006-01-02T15:04:05...
		return ts[11:16]
	}
	if len(ts) >= 5 {
		return ts[:5]
	}
	return ts
}

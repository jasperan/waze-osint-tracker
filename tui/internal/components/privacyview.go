package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// RenderPrivacyView renders a PrivacyScore as horizontal bar charts.
func RenderPrivacyView(score *api.PrivacyScore, width int) string {
	if score == nil {
		return lipgloss.NewStyle().Foreground(theme.DimColor).Render("  no privacy data")
	}
	if score.Error != "" {
		return lipgloss.NewStyle().Foreground(theme.Error).Bold(true).Render("  error: " + score.Error)
	}

	barWidth := width - 30
	if barWidth < 5 {
		barWidth = 5
	}

	type barEntry struct {
		label string
		value float64
	}
	entries := []barEntry{
		{"Home Exposure", score.HomeExposure},
		{"Work Exposure", score.WorkExposure},
		{"Schedule Score", score.ScheduleScore},
		{"Route Score", score.RouteScore},
		{"Identity Score", score.IdentityScore},
		{"Trackability", score.TrackabilityScore},
	}

	var sb strings.Builder

	for _, e := range entries {
		v := e.value
		if v < 0 {
			v = 0
		}
		if v > 100 {
			v = 100
		}
		intScore := int(v)
		riskColor := theme.RiskColor(intScore)
		filled := int(v / 100.0 * float64(barWidth))
		empty := barWidth - filled

		labelStyle := lipgloss.NewStyle().Foreground(theme.TextColor)
		filledStyle := lipgloss.NewStyle().Foreground(riskColor)
		emptyStyle := lipgloss.NewStyle().Foreground(theme.MutedColor)
		valueStyle := lipgloss.NewStyle().Foreground(riskColor).Bold(true)

		label := fmt.Sprintf("%-20s", e.label)
		bar := filledStyle.Render(strings.Repeat("█", filled)) +
			emptyStyle.Render(strings.Repeat("░", empty))
		val := valueStyle.Render(fmt.Sprintf(" %5.1f", v))

		sb.WriteString(labelStyle.Render(label) + bar + val + "\n")
	}

	// Overall gauge
	sb.WriteByte('\n')
	riskColor := theme.RiskColor(score.OverallScore)
	overallStyle := lipgloss.NewStyle().Foreground(riskColor).Bold(true)
	sb.WriteString(overallStyle.Render(
		fmt.Sprintf("  Overall: %d/100  %s", score.OverallScore, score.RiskLevel),
	) + "\n")

	return sb.String()
}

package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// min returns the smaller of two ints.
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// RenderCoOccurrenceView renders convoy pairs and identity correlations.
func RenderCoOccurrenceView(convoys []api.Convoy, correlations []api.Correlation, width int) string {
	dimStyle := lipgloss.NewStyle().Foreground(theme.DimColor)
	boldStyle := lipgloss.NewStyle().Bold(true).Foreground(theme.TextColor)
	textStyle := lipgloss.NewStyle().Foreground(theme.TextColor)
	primaryStyle := lipgloss.NewStyle().Foreground(theme.Primary)

	var sb strings.Builder

	// Convoy Pairs
	sb.WriteString(boldStyle.Render("  Convoy Pairs") + "\n")
	if len(convoys) == 0 {
		sb.WriteString(dimStyle.Render("  no convoy data") + "\n")
	} else {
		for _, c := range convoys {
			barLen := min(c.CoCount, 20)
			bar := primaryStyle.Render(strings.Repeat("█", barLen))
			line := fmt.Sprintf("  %s ↔ %s  %s  ×%d  avg:%.0fm",
				textStyle.Render(c.UserA),
				textStyle.Render(c.UserB),
				bar,
				c.CoCount,
				c.AvgDistanceM,
			)
			sb.WriteString(line + "\n")
		}
	}

	sb.WriteString("\n")

	// Identity Correlations
	sb.WriteString(boldStyle.Render("  Identity Correlations") + "\n")
	if len(correlations) == 0 {
		sb.WriteString(dimStyle.Render("  no correlation data") + "\n")
	} else {
		for _, c := range correlations {
			scorePct := int(c.CombinedScore * 100)
			riskColor := theme.RiskColor(scorePct)
			scoreStyle := lipgloss.NewStyle().Foreground(riskColor).Bold(true)
			line := fmt.Sprintf("  %s ↔ %s  %s  %s",
				textStyle.Render(c.UserA),
				textStyle.Render(c.UserB),
				scoreStyle.Render(fmt.Sprintf("%d%%", scorePct)),
				dimStyle.Render(c.CorrelationType),
			)
			sb.WriteString(line + "\n")
		}
	}

	_ = width // reserved for future truncation
	return sb.String()
}

package theme

import "github.com/charmbracelet/lipgloss"

// Color palette for the Waze TUI.
const (
	ColorPrimary   = lipgloss.Color("#00AAFF")
	ColorSecondary = lipgloss.Color("#FF6600")
	ColorSuccess   = lipgloss.Color("#00CC66")
	ColorWarning   = lipgloss.Color("#FFCC00")
	ColorDanger    = lipgloss.Color("#FF3333")
	ColorMuted     = lipgloss.Color("#666666")
	ColorBg        = lipgloss.Color("#0A0A0F")
	ColorSurface   = lipgloss.Color("#12121A")
	ColorBorder    = lipgloss.Color("#222233")
	ColorText      = lipgloss.Color("#DDDDEE")
	ColorSubtext   = lipgloss.Color("#8888AA")
)

// Base styles.
var (
	Bold   = lipgloss.NewStyle().Bold(true)
	Faint  = lipgloss.NewStyle().Faint(true)
	Border = lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(ColorBorder)
	Title = lipgloss.NewStyle().
		Bold(true).
		Foreground(ColorPrimary)
	Subtitle = lipgloss.NewStyle().
			Foreground(ColorSubtext)
	Success = lipgloss.NewStyle().Foreground(ColorSuccess)
	Warning = lipgloss.NewStyle().Foreground(ColorWarning)
	Danger  = lipgloss.NewStyle().Foreground(ColorDanger)
	Muted   = lipgloss.NewStyle().Foreground(ColorMuted)
)

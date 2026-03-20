package theme

import "github.com/charmbracelet/lipgloss"

// Primary palette.
const (
	Primary    = lipgloss.Color("#e8a817")
	Background = lipgloss.Color("#06080c")
	Surface    = lipgloss.Color("#0f1218")
	TextColor  = lipgloss.Color("#e5e5ea")
	DimColor   = lipgloss.Color("#636366")
	MutedColor = lipgloss.Color("#2a2d35")
)

// Semantic event type colors.
const (
	Police    = lipgloss.Color("#5f87ff")
	Hazard    = lipgloss.Color("#ffd700")
	Jam       = lipgloss.Color("#ff8c00")
	Accident  = lipgloss.Color("#ff3333")
	RoadClose = lipgloss.Color("#ff00ff")
	ChitChat  = lipgloss.Color("#00d7d7")
)

// Status colors.
const (
	Success = lipgloss.Color("#30d158")
	Warning = lipgloss.Color("#ffbf00")
	Error   = lipgloss.Color("#ff453a")
)

// Region colors.
const (
	Europe   = lipgloss.Color("#5f87ff")
	Americas = lipgloss.Color("#30d158")
	Asia     = lipgloss.Color("#ffd700")
	Oceania  = lipgloss.Color("#00d7d7")
	Africa   = lipgloss.Color("#ff00ff")
)

// Status dot constants.
const (
	StatusDot         = "●"
	StatusDotInactive = "○"
)

// Panel styles.
var (
	Panel = lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(MutedColor).
		Padding(0, 1)

	ActivePanel = lipgloss.NewStyle().
			Border(lipgloss.DoubleBorder()).
			BorderForeground(Primary).
			Padding(0, 1)

	HelpPanel = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(Primary).
			Padding(1, 3).
			Background(Surface)
)

// Text styles.
var (
	Title = lipgloss.NewStyle().
		Bold(true).
		Foreground(Primary)

	Subtitle = lipgloss.NewStyle().
			Foreground(TextColor)

	Muted = lipgloss.NewStyle().
		Foreground(DimColor)

	ErrorText = lipgloss.NewStyle().
			Foreground(Error).
			Bold(true)

	SuccessText = lipgloss.NewStyle().
			Foreground(Success).
			Bold(true)

	WarningText = lipgloss.NewStyle().
			Foreground(Warning)
)

// Status bar style.
var StatusBar = lipgloss.NewStyle().
	Background(Surface).
	Foreground(Primary).
	Padding(0, 1)

// EventTypeColor maps a Waze event type string to its semantic color.
func EventTypeColor(t string) lipgloss.Color {
	switch t {
	case "POLICE", "police":
		return Police
	case "HAZARD", "hazard":
		return Hazard
	case "JAM", "jam":
		return Jam
	case "ACCIDENT", "accident":
		return Accident
	case "ROAD_CLOSED", "road_closed", "ROAD_CLOSE", "road_close":
		return RoadClose
	case "CHIT_CHAT", "chit_chat", "CHITCHAT", "chitchat":
		return ChitChat
	default:
		return TextColor
	}
}

// RegionColor maps a region name to its display color.
func RegionColor(r string) lipgloss.Color {
	switch r {
	case "europe", "Europe":
		return Europe
	case "americas", "Americas":
		return Americas
	case "asia", "Asia":
		return Asia
	case "oceania", "Oceania":
		return Oceania
	case "africa", "Africa":
		return Africa
	default:
		return TextColor
	}
}

// RiskColor returns green for low scores, amber for medium, red for high.
func RiskColor(score int) lipgloss.Color {
	switch {
	case score < 30:
		return Success
	case score <= 70:
		return Warning
	default:
		return Error
	}
}

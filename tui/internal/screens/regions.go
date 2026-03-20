package screens

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// ---------------------------------------------------------------------------
// Exported message types originating from this screen.
// ---------------------------------------------------------------------------

// LaunchCollectionMsg asks the parent app to launch the collector for the
// given regions.
type LaunchCollectionMsg struct{ Regions []string }

// ---------------------------------------------------------------------------
// Region metadata
// ---------------------------------------------------------------------------

var allRegions = []string{"europe", "americas", "asia", "oceania", "africa"}

// regionCells holds [P1 cities, P3 cells] per region.
var regionCells = map[string][2]int{
	"europe":   {45, 1204},
	"americas": {38, 2107},
	"asia":     {22, 1891},
	"oceania":  {12, 892},
	"africa":   {15, 562},
}

// ---------------------------------------------------------------------------
// Internal messages
// ---------------------------------------------------------------------------

type regionStatsMsg struct{ stats *api.Stats }

// ---------------------------------------------------------------------------
// Model
// ---------------------------------------------------------------------------

// RegionsModel is the Bubble Tea model for the region-picker screen.
type RegionsModel struct {
	client   *api.Client
	cursor   int
	selected map[string]bool
	stats    *api.Stats
}

// NewRegions constructs a RegionsModel with an empty selection.
func NewRegions(client *api.Client) RegionsModel {
	return RegionsModel{
		client:   client,
		selected: make(map[string]bool),
	}
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

func (m RegionsModel) Init() tea.Cmd {
	if m.client == nil {
		return nil
	}
	return func() tea.Msg {
		stats, err := m.client.Stats()
		if err != nil {
			return regionStatsMsg{stats: nil}
		}
		return regionStatsMsg{stats: stats}
	}
}

// ---------------------------------------------------------------------------
// Update
// ---------------------------------------------------------------------------

func (m RegionsModel) Update(msg tea.Msg) (RegionsModel, tea.Cmd) {
	switch msg := msg.(type) {

	case regionStatsMsg:
		m.stats = msg.stats

	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(allRegions)-1 {
				m.cursor++
			}
		case " ":
			region := allRegions[m.cursor]
			m.selected[region] = !m.selected[region]
		case "a":
			if m.allSelected() {
				// Deselect all.
				m.selected = make(map[string]bool)
			} else {
				// Select all.
				for _, r := range allRegions {
					m.selected[r] = true
				}
			}
		case "enter":
			regions := m.selectedRegions()
			if len(regions) > 0 {
				return m, func() tea.Msg {
					return LaunchCollectionMsg{Regions: regions}
				}
			}
		case "h":
			return m, func() tea.Msg { return NavigateMsg{Screen: ScreenHistory} }
		}
	}

	return m, nil
}

// allSelected returns true when every region is selected.
func (m RegionsModel) allSelected() bool {
	for _, r := range allRegions {
		if !m.selected[r] {
			return false
		}
	}
	return true
}

// selectedRegions returns a sorted slice of selected region names.
func (m RegionsModel) selectedRegions() []string {
	var out []string
	for _, r := range allRegions {
		if m.selected[r] {
			out = append(out, r)
		}
	}
	return out
}

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

const barWidth = 24

func (m RegionsModel) View(width, height int) string {
	var sb strings.Builder

	// Title.
	title := theme.Title.Render("REGION PICKER")
	sb.WriteString(title)
	sb.WriteString("\n\n")

	// Region cards.
	for i, region := range allRegions {
		sb.WriteString(m.renderCard(i, region))
		sb.WriteString("\n")
	}

	sb.WriteString("\n")

	// Footer / key hints.
	n := len(m.selectedRegions())
	enterHint := fmt.Sprintf("[Enter] launch %d region(s)", n)
	footer := theme.Muted.Render(
		"[Space] toggle  [a] all  [h] history  " + enterHint,
	)
	sb.WriteString(footer)

	content := sb.String()

	return lipgloss.Place(
		width, height,
		lipgloss.Center, lipgloss.Center,
		content,
	)
}

// renderCard renders a single region card line.
func (m RegionsModel) renderCard(idx int, region string) string {
	color := theme.RegionColor(region)

	// Cursor prefix.
	cursor := "  "
	if idx == m.cursor {
		cursor = lipgloss.NewStyle().Foreground(theme.Primary).Render("▸ ")
	}

	// Selection indicator.
	var selDot string
	if m.selected[region] {
		selDot = lipgloss.NewStyle().Foreground(color).Bold(true).Render(theme.StatusDot)
	} else {
		selDot = lipgloss.NewStyle().Foreground(theme.DimColor).Render(theme.StatusDotInactive)
	}

	// Region name.
	regionName := lipgloss.NewStyle().Foreground(color).Bold(true).Render(strings.ToUpper(region))

	// Cell counts.
	cells := regionCells[region]
	info := lipgloss.NewStyle().Foreground(theme.DimColor).Render(
		fmt.Sprintf("  P1:%d  P3:%d", cells[0], cells[1]),
	)

	// ASCII progress bar — 50% fill placeholder.
	filled := barWidth / 2
	bar := lipgloss.NewStyle().Foreground(color).Render(strings.Repeat("█", filled)) +
		lipgloss.NewStyle().Foreground(theme.MutedColor).Render(strings.Repeat("░", barWidth-filled))

	return cursor + selDot + " " + regionName + info + "  " + bar
}

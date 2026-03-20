package screens

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/components"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// recentEventsMsg carries events fetched from client.RecentActivity().
type recentEventsMsg struct {
	events []api.Event
}

// HistoryModel is the recent-activity browser screen.
type HistoryModel struct {
	client    *api.Client
	events    []api.Event
	cursor    int
	scrollPos int
}

// NewHistory returns an initialised HistoryModel.
func NewHistory(client *api.Client) HistoryModel {
	return HistoryModel{client: client}
}

// Init fetches recent activity from the API.
func (m HistoryModel) Init() tea.Cmd {
	return fetchRecentActivity(m.client)
}

func fetchRecentActivity(c *api.Client) tea.Cmd {
	return func() tea.Msg {
		events, _ := c.RecentActivity()
		return recentEventsMsg{events: events}
	}
}

// Update handles messages and key input.
func (m HistoryModel) Update(msg tea.Msg) (HistoryModel, tea.Cmd) {
	switch msg := msg.(type) {

	case recentEventsMsg:
		m.events = msg.events
		m.cursor = 0
		m.scrollPos = 0

	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.events)-1 {
				m.cursor++
			}
		case "esc":
			return m, func() tea.Msg { return NavigateMsg{Screen: 1} }
		}
	}

	return m, nil
}

// View renders the history screen into the given dimensions.
func (m HistoryModel) View(width, height int) string {
	// Reserve rows: title (1) + blank (1) + status bar (1) = 3; panel border = 2
	const reservedRows = 5
	listHeight := height - reservedRows
	if listHeight < 1 {
		listHeight = 1
	}

	// ── Title ────────────────────────────────────────────────────────────────
	title := theme.Title.Render("RECENT ACTIVITY")

	// ── Event list ───────────────────────────────────────────────────────────
	var listLines []string

	if len(m.events) == 0 {
		listLines = append(listLines, theme.Muted.Render("No recent events"))
	} else {
		// Adjust scroll window so cursor stays visible.
		if m.cursor < m.scrollPos {
			m.scrollPos = m.cursor
		}
		if m.cursor >= m.scrollPos+listHeight {
			m.scrollPos = m.cursor - listHeight + 1
		}

		end := m.scrollPos + listHeight
		if end > len(m.events) {
			end = len(m.events)
		}

		for i := m.scrollPos; i < end; i++ {
			e := m.events[i]
			selected := i == m.cursor

			// Prefix: arrow or spaces
			prefix := "  "
			if selected {
				prefix = theme.Title.Render("▸ ")
			}

			// Colored dot
			dotColor := theme.EventTypeColor(e.EffectiveType())
			dot := lipgloss.NewStyle().Foreground(dotColor).Render("●")

			// Timestamp (up to 19 chars: "2006-01-02 15:04:05")
			ts := e.Timestamp
			if len(ts) > 19 {
				ts = ts[:19]
			}
			ts = fmt.Sprintf("%-19s", ts)

			// Type name (lowercase, 12 chars)
			typeName := strings.ToLower(e.EffectiveType())
			typeName = fmt.Sprintf("%-12s", typeName)

			// Username (15 chars)
			username := e.Username
			if username == "" {
				username = "anonymous"
			}
			username = fmt.Sprintf("%-15s", username)

			// Coordinates
			coords := fmt.Sprintf("%.2f, %.2f", e.Latitude, e.Longitude)

			line := prefix + dot + " " + ts + "  " + typeName + "  " + username + "  " + coords

			if selected {
				line = lipgloss.NewStyle().Bold(true).Render(line)
			}

			listLines = append(listLines, line)
		}
	}

	// Inner panel width = total width minus border (2) and padding (2)
	panelInnerWidth := width - 4
	if panelInnerWidth < 10 {
		panelInnerWidth = 10
	}

	panel := theme.Panel.Copy().
		Width(panelInnerWidth).
		Height(listHeight).
		Render(strings.Join(listLines, "\n"))

	// ── Status bar ───────────────────────────────────────────────────────────
	leftStatus := fmt.Sprintf("%d events", len(m.events))
	rightStatus := "[Esc] back | [?] help"
	statusBar := components.RenderStatusBar(components.StatusBarData{
		Left:  leftStatus,
		Right: rightStatus,
	}, width)

	return strings.Join([]string{
		title,
		"",
		panel,
		statusBar,
	}, "\n")
}

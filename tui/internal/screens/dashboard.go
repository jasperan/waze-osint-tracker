package screens

import (
	"context"
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/components"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// LayoutMode controls whether the dashboard shows a focus or grid layout.
type LayoutMode int

const (
	LayoutFocus LayoutMode = iota
	LayoutGrid
)

// feedFilters is the ordered cycle of event type filters.
var feedFilters = []string{"", "POLICE", "HAZARD", "JAM", "ACCIDENT", "ROAD_CLOSED"}

// regionNames lists all 5 collection regions in display order.
var regionNames = []string{"europe", "americas", "asia", "oceania", "africa"}

// ── messages ─────────────────────────────────────────────────────────────────

// sseEventMsg wraps an incoming SSE frame from the stream.
type sseEventMsg struct {
	msg api.SSEMessage
}

// statsTickMsg triggers a stats poll.
type statsTickMsg struct{}

// statsResultMsg carries the fetched stats.
type statsResultMsg struct {
	stats *api.Stats
}

// sseConnectedMsg carries the SSE channel and cancel func back through Update.
type sseConnectedMsg struct {
	ch     <-chan api.SSEMessage
	cancel context.CancelFunc
}

// ── model ────────────────────────────────────────────────────────────────────

// DashboardModel is the real-time collection monitor screen.
type DashboardModel struct {
	client     *api.Client
	layout     LayoutMode
	feed       *components.EventFeed
	throughput *components.ThroughputTracker
	stats      *api.Stats
	regions    []components.RegionData
	paused     bool
	filterIdx  int // index into feedFilters

	// SSE stream state.
	sseCh     <-chan api.SSEMessage
	sseCtx    context.Context
	sseCancel context.CancelFunc
}

// NewDashboard creates a DashboardModel with all 5 regions initialised.
func NewDashboard(client *api.Client) DashboardModel {
	regions := make([]components.RegionData, len(regionNames))
	for i, name := range regionNames {
		regions[i] = components.RegionData{Name: name}
	}
	return DashboardModel{
		client:     client,
		layout:     LayoutFocus,
		feed:       components.NewEventFeed(500),
		throughput: components.NewThroughputTracker(),
		regions:    regions,
	}
}

// Init returns the initial command: kick off the stats polling loop and SSE connection.
func (m DashboardModel) Init() tea.Cmd {
	return tea.Batch(pollStats(), m.connectSSE())
}

// connectSSE starts the SSE stream in a goroutine and sends the channel back
// through the Update loop (avoiding the value-receiver Init trap).
func (m DashboardModel) connectSSE() tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithCancel(context.Background())
		ch, err := m.client.StreamEvents(ctx)
		if err != nil {
			cancel()
			return nil
		}
		return sseConnectedMsg{ch: ch, cancel: cancel}
	}
}

// Update handles all messages for the dashboard.
func (m DashboardModel) Update(msg tea.Msg) (DashboardModel, tea.Cmd) {
	switch msg := msg.(type) {

	case statsTickMsg:
		return m, tea.Batch(fetchStats(m.client), pollStats())

	case statsResultMsg:
		m.stats = msg.stats

	case sseConnectedMsg:
		m.sseCh = msg.ch
		m.sseCancel = msg.cancel
		return m, m.waitForSSE()

	case sseEventMsg:
		if !m.paused && msg.msg.Event != nil {
			e := *msg.msg.Event
			m.feed.Push(e)
			m.throughput.Add(1)
			// Update the matching region's event counter.
			for i := range m.regions {
				if strings.EqualFold(m.regions[i].Name, e.Region) {
					m.regions[i].Events++
					m.regions[i].Delta++
					m.regions[i].Running = true
					break
				}
			}
		}
		// Keep listening: re-schedule the wait command.
		if m.sseCh != nil {
			return m, m.waitForSSE()
		}

	case tea.KeyMsg:
		switch msg.String() {
		case "tab":
			if m.layout == LayoutFocus {
				m.layout = LayoutGrid
			} else {
				m.layout = LayoutFocus
			}
		case "p":
			m.paused = !m.paused
		case "i":
			if m.sseCancel != nil {
				m.sseCancel()
			}
			return m, func() tea.Msg { return NavigateMsg{Screen: ScreenInvestigation} }
		case "f":
			m.filterIdx = (m.filterIdx + 1) % len(feedFilters)
			m.feed.Filter = feedFilters[m.filterIdx]
		case "esc":
			if m.sseCancel != nil {
				m.sseCancel()
			}
			return m, func() tea.Msg { return NavigateMsg{Screen: ScreenRegions} }
		}
	}

	return m, nil
}

// View renders the dashboard at the given terminal dimensions.
func (m DashboardModel) View(width, height int) string {
	if m.layout == LayoutGrid {
		return m.viewGrid(width, height)
	}
	return m.viewFocus(width, height)
}

// ── layout: focus ─────────────────────────────────────────────────────────────

func (m DashboardModel) viewFocus(width, height int) string {
	const statusBarHeight = 1
	bodyHeight := height - statusBarHeight

	leftW := width / 3
	rightW := width - leftW

	// Left column: stacked region panes.
	left := m.renderRegionStack(leftW, bodyHeight)

	// Right column: feed (top 2/3) + throughput (bottom 1/3).
	feedHeight := bodyHeight * 2 / 3
	throughputHeight := bodyHeight - feedHeight

	// Inner usable width inside panels (border=2, padding=2 each side → subtract 4).
	rightInner := rightW - 4

	feedTitle := theme.Title.Render("EVENT FEED")
	filterLabel := ""
	if m.feed.Filter != "" {
		filterLabel = " " + lipgloss.NewStyle().Foreground(theme.Primary).Render("["+m.feed.Filter+"]")
	}
	pauseLabel := ""
	if m.paused {
		pauseLabel = " " + lipgloss.NewStyle().Foreground(theme.Warning).Render("[PAUSED]")
	}

	feedContentHeight := feedHeight - 4 // border rows + title row + blank row
	if feedContentHeight < 1 {
		feedContentHeight = 1
	}
	feedContent := feedTitle + filterLabel + pauseLabel + "\n" + m.feed.View(rightInner, feedContentHeight)
	feedPanel := theme.Panel.Copy().
		Width(rightInner).
		Height(feedHeight - 2). // subtract border rows
		Render(feedContent)

	tpInner := rightInner
	tpContent := theme.Title.Render("THROUGHPUT") + "\n" + components.RenderThroughput(m.throughput, tpInner)
	tpPanel := theme.Panel.Copy().
		Width(tpInner).
		Height(throughputHeight - 2).
		Render(tpContent)

	right := lipgloss.JoinVertical(lipgloss.Left, feedPanel, tpPanel)

	body := lipgloss.JoinHorizontal(lipgloss.Top, left, right)

	// Trim/pad body to bodyHeight.
	bodyLines := strings.Split(body, "\n")
	if len(bodyLines) > bodyHeight {
		bodyLines = bodyLines[:bodyHeight]
	}
	for len(bodyLines) < bodyHeight {
		bodyLines = append(bodyLines, "")
	}
	body = strings.Join(bodyLines, "\n")

	statusBar := m.renderStatusBar(width)
	return body + "\n" + statusBar
}

// renderRegionStack stacks all 5 region panes in the given column.
func (m DashboardModel) renderRegionStack(colWidth, totalHeight int) string {
	paneH := totalHeight / len(m.regions)
	if paneH < 5 {
		paneH = 5
	}
	var panes []string
	for _, rd := range m.regions {
		panes = append(panes, components.RenderRegionPane(rd, colWidth, false))
	}
	return lipgloss.JoinVertical(lipgloss.Left, panes...)
}

// ── layout: grid ──────────────────────────────────────────────────────────────

func (m DashboardModel) viewGrid(width, height int) string {
	const statusBarHeight = 1
	bodyHeight := height - statusBarHeight

	// 3 columns, 2 rows (5 regions + 1 spare cell shown as empty).
	cols := 3
	rows := 2
	cellW := width / cols
	cellH := bodyHeight / rows

	// Build cells: 5 region panes + 1 blank.
	cells := make([]string, cols*rows)
	for i, rd := range m.regions {
		cells[i] = components.RenderRegionPane(rd, cellW, false)
	}
	// 6th cell: blank filler.
	cells[5] = theme.Panel.Copy().Width(cellW - 4).Height(cellH - 2).Render("")

	// Trim/pad each cell to cellH lines.
	for i, c := range cells {
		lines := strings.Split(c, "\n")
		if len(lines) > cellH {
			lines = lines[:cellH]
		}
		for len(lines) < cellH {
			lines = append(lines, strings.Repeat(" ", cellW))
		}
		cells[i] = strings.Join(lines, "\n")
	}

	row1 := lipgloss.JoinHorizontal(lipgloss.Top, cells[0], cells[1], cells[2])
	row2 := lipgloss.JoinHorizontal(lipgloss.Top, cells[3], cells[4], cells[5])
	body := lipgloss.JoinVertical(lipgloss.Left, row1, row2)

	statusBar := m.renderStatusBar(width)
	return body + "\n" + statusBar
}

// ── status bar ────────────────────────────────────────────────────────────────

func (m DashboardModel) renderStatusBar(width int) string {
	// Left: events + users from latest stats.
	leftStr := "Events: —  Users: —"
	if m.stats != nil {
		leftStr = fmt.Sprintf("Events: %d  Users: %d", m.stats.TotalEvents, m.stats.UniqueUsers)
	}

	// Center: current event rate.
	rate := m.throughput.CurrentRate()
	centerStr := components.FormatEventRate(rate)

	// Right: key hints (layout-aware).
	layoutHint := "tab:grid"
	if m.layout == LayoutGrid {
		layoutHint = "tab:focus"
	}
	pauseHint := "p:pause"
	if m.paused {
		pauseHint = "p:resume"
	}
	rightStr := fmt.Sprintf("[ %s | %s | f:filter | i:investigate | esc:regions ]", layoutHint, pauseHint)

	return components.RenderStatusBar(components.StatusBarData{
		Left:   leftStr,
		Center: centerStr,
		Right:  rightStr,
	}, width)
}

// ── commands ──────────────────────────────────────────────────────────────────

// waitForSSE returns a tea.Cmd that blocks until one SSE message arrives on the
// channel and delivers it as an sseEventMsg. The Update handler re-schedules it
// after each message, creating a persistent listen loop.
func (m DashboardModel) waitForSSE() tea.Cmd {
	ch := m.sseCh
	return func() tea.Msg {
		msg, ok := <-ch
		if !ok {
			// Channel closed (context cancelled or server gone).
			return nil
		}
		return sseEventMsg{msg: msg}
	}
}

// pollStats schedules a statsTickMsg after 5 seconds.
func pollStats() tea.Cmd {
	return tea.Tick(5*time.Second, func(_ time.Time) tea.Msg {
		return statsTickMsg{}
	})
}

// fetchStats fetches current stats from the API and returns a statsResultMsg.
func fetchStats(client *api.Client) tea.Cmd {
	return func() tea.Msg {
		s, err := client.Stats()
		if err != nil {
			return statsResultMsg{stats: nil}
		}
		return statsResultMsg{stats: s}
	}
}

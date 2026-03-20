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

// Panel identifies which of the three panels is active.
type Panel int

const (
	PanelUsers   Panel = iota
	PanelProfile Panel = iota
	PanelBottom  Panel = iota
	PanelCount   Panel = iota
)

// BottomView identifies which sub-view is shown in the bottom-right panel.
type BottomView int

const (
	ViewTrips    BottomView = iota
	ViewPrivacy  BottomView = iota
	ViewIntel    BottomView = iota
	ViewLocation BottomView = iota
	ViewNetwork  BottomView = iota
)

// ── internal messages ─────────────────────────────────────────────────────────

type usersLoadedMsg struct {
	users []api.UserSummary
}

type profileLoadedMsg struct {
	profile *api.UserProfile
}

type tripsLoadedMsg struct {
	trips *api.TripResponse
}

type privacyLoadedMsg struct {
	score *api.PrivacyScore
}

type intelLoadedMsg struct {
	intel *api.IntelProfile
}

type convoysLoadedMsg struct {
	convoys      []api.Convoy
	correlations []api.Correlation
}

// ── model ─────────────────────────────────────────────────────────────────────

// InvestigationModel is the 3-panel user research workbench screen.
type InvestigationModel struct {
	client       *api.Client
	activePanel  Panel
	bottomView   BottomView
	userList     *components.UserList
	profile      *api.UserProfile
	trips        *api.TripResponse
	privacy      *api.PrivacyScore
	intel        *api.IntelProfile
	convoys      []api.Convoy
	correlations []api.Correlation
	filtering    bool
	filterBuf    string
}

// NewInvestigation returns an initialised InvestigationModel.
func NewInvestigation(client *api.Client) InvestigationModel {
	return InvestigationModel{
		client:      client,
		activePanel: PanelUsers,
		bottomView:  ViewTrips,
		userList:    components.NewUserList(),
	}
}

// ── Init ──────────────────────────────────────────────────────────────────────

// Init fetches the user list from the API.
func (m InvestigationModel) Init() tea.Cmd {
	return func() tea.Msg {
		users, err := m.client.Users()
		if err != nil {
			return usersLoadedMsg{users: nil}
		}
		return usersLoadedMsg{users: users}
	}
}

// ── Update ────────────────────────────────────────────────────────────────────

func (m InvestigationModel) Update(msg tea.Msg) (InvestigationModel, tea.Cmd) {
	switch msg := msg.(type) {

	// ── data messages ──────────────────────────────────────────────────────

	case usersLoadedMsg:
		if msg.users != nil {
			m.userList.SetUsers(msg.users)
		}
		return m, m.onUserChange()

	case profileLoadedMsg:
		m.profile = msg.profile
		return m, nil

	case tripsLoadedMsg:
		m.trips = msg.trips
		return m, nil

	case privacyLoadedMsg:
		m.privacy = msg.score
		return m, nil

	case intelLoadedMsg:
		m.intel = msg.intel
		return m, nil

	case convoysLoadedMsg:
		m.convoys = msg.convoys
		m.correlations = msg.correlations
		return m, nil

	// ── keyboard ───────────────────────────────────────────────────────────

	case tea.KeyMsg:
		// If filtering, handle text input exclusively.
		if m.filtering {
			switch msg.String() {
			case "esc", "enter":
				m.filtering = false
				m.userList.Filter = m.filterBuf
			case "backspace":
				if len(m.filterBuf) > 0 {
					m.filterBuf = m.filterBuf[:len(m.filterBuf)-1]
					m.userList.Filter = m.filterBuf
				}
			default:
				if len(msg.String()) == 1 {
					m.filterBuf += msg.String()
					m.userList.Filter = m.filterBuf
				}
			}
			return m, nil
		}

		switch msg.String() {
		case "tab":
			m.activePanel = (m.activePanel + 1) % PanelCount
		case "shift+tab":
			m.activePanel = (m.activePanel + PanelCount - 1) % PanelCount

		case "c":
			m.bottomView = ViewTrips
			return m, m.fetchBottomView()
		case "v":
			m.bottomView = ViewPrivacy
			return m, m.fetchBottomView()
		case "d":
			m.bottomView = ViewIntel
			return m, m.fetchBottomView()
		case "l":
			m.bottomView = ViewLocation
			return m, nil // location uses profile.Events, no extra fetch
		case "n":
			m.bottomView = ViewNetwork
			return m, m.fetchBottomView()

		case "/":
			m.filtering = true
			m.filterBuf = m.userList.Filter

		case "s":
			m.userList.CycleSort()
			return m, m.onUserChange()

		case "up":
			if m.activePanel == PanelUsers {
				m.userList.MoveUp()
				return m, m.onUserChange()
			}
		case "down":
			if m.activePanel == PanelUsers {
				// Pass a reasonable visible rows estimate; actual height handled in View.
				m.userList.MoveDown(30)
				return m, m.onUserChange()
			}

		case "esc":
			return m, func() tea.Msg { return NavigateMsg{Screen: 2} }
		}
	}

	return m, nil
}

// onUserChange loads the profile and current bottom view data for the selected user.
func (m InvestigationModel) onUserChange() tea.Cmd {
	u := m.userList.SelectedUser()
	if u == nil {
		return nil
	}
	username := u.Username
	return tea.Batch(
		func() tea.Msg {
			p, err := m.client.UserProfile(username)
			if err != nil {
				return profileLoadedMsg{profile: nil}
			}
			return profileLoadedMsg{profile: p}
		},
		m.fetchBottomView(),
	)
}

// fetchBottomView issues the API call appropriate for the current bottomView.
func (m InvestigationModel) fetchBottomView() tea.Cmd {
	u := m.userList.SelectedUser()
	if u == nil {
		return nil
	}
	username := u.Username

	switch m.bottomView {
	case ViewTrips:
		return func() tea.Msg {
			t, err := m.client.Trips(username)
			if err != nil {
				return tripsLoadedMsg{trips: nil}
			}
			return tripsLoadedMsg{trips: t}
		}
	case ViewPrivacy:
		return func() tea.Msg {
			ps, err := m.client.PrivacyScore(username)
			if err != nil {
				return privacyLoadedMsg{score: nil}
			}
			return privacyLoadedMsg{score: ps}
		}
	case ViewIntel:
		return func() tea.Msg {
			ip, err := m.client.IntelProfile(username)
			if err != nil {
				return intelLoadedMsg{intel: nil}
			}
			return intelLoadedMsg{intel: ip}
		}
	case ViewNetwork:
		return func() tea.Msg {
			convoys, _ := m.client.Convoys()
			corrs, _ := m.client.Correlations()
			return convoysLoadedMsg{convoys: convoys, correlations: corrs}
		}
	default:
		return nil
	}
}

// ── View ──────────────────────────────────────────────────────────────────────

// View renders the full investigation screen at the given terminal dimensions.
func (m InvestigationModel) View(width, height int) string {
	const statusBarH = 1
	contentH := height - statusBarH
	if contentH < 4 {
		contentH = 4
	}

	leftW := width / 3
	rightW := width - leftW

	topH := contentH * 2 / 3
	botH := contentH - topH
	if botH < 3 {
		botH = 3
	}

	// ── left panel: user list ──────────────────────────────────────────────
	leftInnerW := leftW - 4 // account for border + padding
	if leftInnerW < 1 {
		leftInnerW = 1
	}
	leftInnerH := contentH - 2
	if leftInnerH < 1 {
		leftInnerH = 1
	}

	userListContent := m.userList.View(leftInnerW, leftInnerH)
	leftPanel := m.panelStyle(PanelUsers).
		Width(leftW - 2).
		Height(contentH - 2).
		Render(userListContent)

	// ── right top panel: profile ───────────────────────────────────────────
	rightInnerW := rightW - 4
	if rightInnerW < 1 {
		rightInnerW = 1
	}
	profileContent := m.renderProfile(rightInnerW)
	topPanel := m.panelStyle(PanelProfile).
		Width(rightW - 2).
		Height(topH - 2).
		Render(profileContent)

	// ── right bottom panel: switchable view ────────────────────────────────
	bottomContent := m.renderBottomView(rightInnerW, botH-2)
	botPanel := m.panelStyle(PanelBottom).
		Width(rightW - 2).
		Height(botH - 2).
		Render(bottomContent)

	// ── compose right column ───────────────────────────────────────────────
	rightCol := lipgloss.JoinVertical(lipgloss.Left, topPanel, botPanel)

	// ── compose main area ──────────────────────────────────────────────────
	mainArea := lipgloss.JoinHorizontal(lipgloss.Top, leftPanel, rightCol)

	// ── status bar ─────────────────────────────────────────────────────────
	statusBar := m.renderStatusBar(width)

	return lipgloss.JoinVertical(lipgloss.Left, mainArea, statusBar)
}

// panelStyle returns the appropriate panel border style based on focus.
func (m InvestigationModel) panelStyle(p Panel) lipgloss.Style {
	if m.activePanel == p {
		return theme.ActivePanel.Copy()
	}
	return theme.Panel.Copy()
}

// renderProfile renders the user profile summary for the top-right panel.
func (m InvestigationModel) renderProfile(width int) string {
	dimStyle := lipgloss.NewStyle().Foreground(theme.DimColor)

	if m.profile == nil {
		u := m.userList.SelectedUser()
		if u == nil {
			return dimStyle.Render("  select a user")
		}
		return dimStyle.Render(fmt.Sprintf("  loading %s…", u.Username))
	}

	p := m.profile
	var sb strings.Builder

	// Title
	titleStyle := theme.Title.Copy()
	sb.WriteString(titleStyle.Render(p.Username) + "\n\n")

	// First / last seen
	textStyle := lipgloss.NewStyle().Foreground(theme.TextColor)
	sb.WriteString(dimStyle.Render("  first seen: ") + textStyle.Render(p.FirstSeen) + "\n")
	sb.WriteString(dimStyle.Render("  last seen:  ") + textStyle.Render(p.LastSeen) + "\n")
	sb.WriteString(dimStyle.Render("  events:     ") + textStyle.Render(fmt.Sprintf("%d", p.EventCount)) + "\n")

	if p.CenterLocation != nil {
		sb.WriteString(dimStyle.Render(fmt.Sprintf("  center:      %.4f, %.4f",
			p.CenterLocation.Lat, p.CenterLocation.Lon)) + "\n")
	}

	// Type breakdown with colored dots
	if len(p.TypeBreakdown) > 0 {
		sb.WriteString("\n")
		sb.WriteString(dimStyle.Render("  event types:") + "\n")
		for evType, count := range p.TypeBreakdown {
			dotColor := theme.EventTypeColor(evType)
			dotStyle := lipgloss.NewStyle().Foreground(dotColor)
			dot := dotStyle.Render(theme.StatusDot)
			pct := 0.0
			if p.EventCount > 0 {
				pct = float64(count) / float64(p.EventCount) * 100
			}
			line := fmt.Sprintf("    %s %-14s %4d  (%.0f%%)", dot, evType, count, pct)
			sb.WriteString(line + "\n")
		}
	}

	// Truncate to available width
	_ = width
	return sb.String()
}

// renderBottomView selects and renders the active bottom sub-view.
func (m InvestigationModel) renderBottomView(width, height int) string {
	switch m.bottomView {
	case ViewTrips:
		return components.RenderTripView(m.trips, width)
	case ViewPrivacy:
		return components.RenderPrivacyView(m.privacy, width)
	case ViewIntel:
		return components.RenderIntelView(m.intel, width)
	case ViewLocation:
		var events []api.Event
		if m.profile != nil {
			events = m.profile.Events
		}
		return components.RenderLocationView(events, width, height)
	case ViewNetwork:
		return components.RenderCoOccurrenceView(m.convoys, m.correlations, width)
	default:
		return ""
	}
}

// renderStatusBar renders the bottom status bar for the investigation screen.
func (m InvestigationModel) renderStatusBar(width int) string {
	left := theme.Title.Copy().Render("INVESTIGATION")

	// Build view toggle labels: active one in Primary+bold, others dimmed.
	type viewLabel struct {
		view  BottomView
		key   string
		label string
	}
	labels := []viewLabel{
		{ViewTrips, "c", "trips"},
		{ViewPrivacy, "v", "privacy"},
		{ViewIntel, "d", "intel"},
		{ViewLocation, "l", "location"},
		{ViewNetwork, "n", "network"},
	}

	var parts []string
	for _, vl := range labels {
		var s string
		if m.bottomView == vl.view {
			s = lipgloss.NewStyle().Foreground(theme.Primary).Bold(true).
				Render(fmt.Sprintf("[%s]%s", vl.key, vl.label))
		} else {
			s = lipgloss.NewStyle().Foreground(theme.DimColor).
				Render(fmt.Sprintf("[%s]%s", vl.key, vl.label))
		}
		parts = append(parts, s)
	}
	center := strings.Join(parts, "  ")

	right := lipgloss.NewStyle().Foreground(theme.DimColor).
		Render("tab:panel  /:filter  s:sort  esc:back")

	return components.RenderStatusBar(components.StatusBarData{
		Left:   left,
		Center: center,
		Right:  right,
	}, width)
}

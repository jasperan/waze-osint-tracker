package app

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/process"
	"github.com/jasperan/waze-madrid-logger/tui/internal/screens"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// Screen identifies the active TUI screen.
type Screen int

const (
	ScreenSplash Screen = iota
	ScreenRegions
	ScreenDashboard
	ScreenInvestigation
	ScreenHistory
)

// SwitchScreenMsg requests a transition to a different screen.
type SwitchScreenMsg struct {
	Screen Screen
	Data   interface{}
}

// App is the root Bubble Tea model.
type App struct {
	client  *api.Client
	proc    *process.Manager
	version string

	width  int
	height int
	screen Screen

	// child screen models
	splash      screens.SplashModel
	regions     screens.RegionsModel
	dashboard   screens.DashboardModel
	investigate screens.InvestigationModel
	history     screens.HistoryModel

	showHelp bool
}

// New creates the root application model.
func New(apiURL, version string) App {
	return App{
		client:      api.NewClient(apiURL),
		proc:        process.NewManager(),
		version:     version,
		screen:      ScreenSplash,
		splash:      screens.NewSplash(),
		regions:     screens.NewRegions(),
		dashboard:   screens.NewDashboard(),
		investigate: screens.NewInvestigation(),
		history:     screens.NewHistory(),
	}
}

// Init runs on startup — nothing to do yet.
func (a App) Init() tea.Cmd {
	return a.splash.Init()
}

// Update is the central event dispatcher.
func (a App) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {

	case tea.WindowSizeMsg:
		a.width = msg.Width
		a.height = msg.Height
		return a, nil

	case tea.KeyMsg:
		// Global keys first.
		switch msg.String() {
		case "ctrl+c", "q":
			a.proc.StopAll()
			return a, tea.Quit
		case "?", "f1":
			a.showHelp = !a.showHelp
			return a, nil
		case "1":
			return a, func() tea.Msg { return SwitchScreenMsg{Screen: ScreenSplash} }
		case "2":
			return a, func() tea.Msg { return SwitchScreenMsg{Screen: ScreenRegions} }
		case "3":
			return a, func() tea.Msg { return SwitchScreenMsg{Screen: ScreenDashboard} }
		case "4":
			return a, func() tea.Msg { return SwitchScreenMsg{Screen: ScreenInvestigation} }
		case "5":
			return a, func() tea.Msg { return SwitchScreenMsg{Screen: ScreenHistory} }
		}
		// Delegate to active screen.
		return a.delegateKey(msg)

	case SwitchScreenMsg:
		a.switchScreen(msg.Screen)
		return a, nil
	}

	// Delegate all other msgs to the active screen.
	return a.delegateMsg(msg)
}

// delegateKey forwards a key message to the active screen.
func (a App) delegateKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	return a.delegateMsg(msg)
}

// delegateMsg forwards any message to the active screen model.
func (a App) delegateMsg(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	switch a.screen {
	case ScreenSplash:
		a.splash, cmd = a.splash.Update(msg)
	case ScreenRegions:
		a.regions, cmd = a.regions.Update(msg)
	case ScreenDashboard:
		a.dashboard, cmd = a.dashboard.Update(msg)
	case ScreenInvestigation:
		a.investigate, cmd = a.investigate.Update(msg)
	case ScreenHistory:
		a.history, cmd = a.history.Update(msg)
	}
	return a, cmd
}

// switchScreen transitions to a new screen.
func (a *App) switchScreen(s Screen) {
	a.screen = s
	a.showHelp = false
}

// View renders the current screen.
func (a App) View() string {
	if a.width == 0 || a.height == 0 {
		return "initialising…"
	}

	// Reserve one line at the bottom for the status bar.
	contentHeight := a.height - 1

	var body string
	switch a.screen {
	case ScreenSplash:
		body = a.splash.View(a.width, contentHeight)
	case ScreenRegions:
		body = a.regions.View(a.width, contentHeight)
	case ScreenDashboard:
		body = a.dashboard.View(a.width, contentHeight)
	case ScreenInvestigation:
		body = a.investigate.View(a.width, contentHeight)
	case ScreenHistory:
		body = a.history.View(a.width, contentHeight)
	default:
		body = "unknown screen"
	}

	statusBar := a.renderStatusBar()

	if a.showHelp {
		body = a.renderHelpOverlay(a.width, contentHeight)
	}

	return lipgloss.JoinVertical(lipgloss.Left, body, statusBar)
}

// renderStatusBar renders the one-line status bar at the bottom.
func (a App) renderStatusBar() string {
	screenNames := map[Screen]string{
		ScreenSplash:        "1:Splash",
		ScreenRegions:       "2:Regions",
		ScreenDashboard:     "3:Dashboard",
		ScreenInvestigation: "4:Investigate",
		ScreenHistory:       "5:History",
	}

	tabs := make([]string, 0, 5)
	for i := Screen(0); i <= ScreenHistory; i++ {
		name := screenNames[i]
		if i == a.screen {
			tabs = append(tabs, theme.Title.Render(fmt.Sprintf("[%s]", name)))
		} else {
			tabs = append(tabs, theme.Muted.Render(name))
		}
	}

	left := strings.Join(tabs, "  ")
	right := theme.Muted.Render(fmt.Sprintf("v%s  ?=help  q=quit", a.version))

	gap := a.width - lipgloss.Width(left) - lipgloss.Width(right)
	if gap < 1 {
		gap = 1
	}

	bar := left + strings.Repeat(" ", gap) + right
	return lipgloss.NewStyle().
		Background(lipgloss.Color("#111122")).
		Width(a.width).
		Render(bar)
}

// renderHelpOverlay renders an F1 help panel centred on the screen.
func (a App) renderHelpOverlay(w, h int) string {
	lines := []string{
		theme.Title.Render("Keyboard Shortcuts"),
		"",
		"  1-5        Switch screens",
		"  ?  / F1    Toggle this help",
		"  q / ctrl+c Quit",
		"",
		theme.Muted.Render("Press ? or F1 to close"),
	}

	content := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(theme.ColorPrimary).
		Padding(1, 3).
		Render(strings.Join(lines, "\n"))

	return lipgloss.Place(w, h, lipgloss.Center, lipgloss.Center, content)
}

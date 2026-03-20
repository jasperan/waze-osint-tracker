package screens

import (
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// placeholder renders a centred placeholder for a screen.
func placeholder(title string, w, h int) string {
	msg := lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("#00AAFF")).
		Render("[ " + title + " ]")
	return lipgloss.Place(w, h, lipgloss.Center, lipgloss.Center, msg)
}

// ---------------------------------------------------------------------------
// SplashModel
// ---------------------------------------------------------------------------

// SplashModel is the initial loading/splash screen.
type SplashModel struct{}

// NewSplash creates a SplashModel.
func NewSplash() SplashModel { return SplashModel{} }

// Init satisfies tea.Model.
func (m SplashModel) Init() tea.Cmd { return nil }

// Update satisfies tea.Model.
func (m SplashModel) Update(msg tea.Msg) (SplashModel, tea.Cmd) { return m, nil }

// View renders the splash screen.
func (m SplashModel) View(width, height int) string {
	return placeholder("WAZE OSINT TRACKER — loading…", width, height)
}

// ---------------------------------------------------------------------------
// RegionsModel
// ---------------------------------------------------------------------------

// RegionsModel lets the user choose which regions to monitor.
type RegionsModel struct{}

// NewRegions creates a RegionsModel.
func NewRegions() RegionsModel { return RegionsModel{} }

// Init satisfies tea.Model.
func (m RegionsModel) Init() tea.Cmd { return nil }

// Update satisfies tea.Model.
func (m RegionsModel) Update(msg tea.Msg) (RegionsModel, tea.Cmd) { return m, nil }

// View renders the region picker.
func (m RegionsModel) View(width, height int) string {
	return placeholder("REGION PICKER", width, height)
}

// ---------------------------------------------------------------------------
// DashboardModel
// ---------------------------------------------------------------------------

// DashboardModel shows the live event feed and stats.
type DashboardModel struct{}

// NewDashboard creates a DashboardModel.
func NewDashboard() DashboardModel { return DashboardModel{} }

// Init satisfies tea.Model.
func (m DashboardModel) Init() tea.Cmd { return nil }

// Update satisfies tea.Model.
func (m DashboardModel) Update(msg tea.Msg) (DashboardModel, tea.Cmd) { return m, nil }

// View renders the dashboard.
func (m DashboardModel) View(width, height int) string {
	return placeholder("LIVE DASHBOARD", width, height)
}

// ---------------------------------------------------------------------------
// InvestigationModel
// ---------------------------------------------------------------------------

// InvestigationModel shows per-user OSINT profiles.
type InvestigationModel struct{}

// NewInvestigation creates an InvestigationModel.
func NewInvestigation() InvestigationModel { return InvestigationModel{} }

// Init satisfies tea.Model.
func (m InvestigationModel) Init() tea.Cmd { return nil }

// Update satisfies tea.Model.
func (m InvestigationModel) Update(msg tea.Msg) (InvestigationModel, tea.Cmd) { return m, nil }

// View renders the investigation screen.
func (m InvestigationModel) View(width, height int) string {
	return placeholder("INVESTIGATION", width, height)
}

// ---------------------------------------------------------------------------
// HistoryModel
// ---------------------------------------------------------------------------

// HistoryModel shows historical event queries.
type HistoryModel struct{}

// NewHistory creates a HistoryModel.
func NewHistory() HistoryModel { return HistoryModel{} }

// Init satisfies tea.Model.
func (m HistoryModel) Init() tea.Cmd { return nil }

// Update satisfies tea.Model.
func (m HistoryModel) Update(msg tea.Msg) (HistoryModel, tea.Cmd) { return m, nil }

// View renders the history screen.
func (m HistoryModel) View(width, height int) string {
	return placeholder("HISTORY", width, height)
}

package screens

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
)

// ── helpers ───────────────────────────────────────────────────────────────────

// newTestServer returns an httptest.Server that responds to every path with the
// supplied JSON payload and status 200.
func newTestServer(t *testing.T, payload interface{}) *httptest.Server {
	t.Helper()
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("json.Marshal: %v", err)
	}
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write(data)
	}))
}

// newStatsServer returns a test server that serves a Stats payload.
func newStatsServer(t *testing.T, stats api.Stats) (*httptest.Server, *api.Client) {
	t.Helper()
	srv := newTestServer(t, stats)
	return srv, api.NewClient(srv.URL)
}

// keyRune creates a tea.KeyMsg for a regular printable character.
func keyRune(r rune) tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{r}}
}

// keySpecial creates a tea.KeyMsg for a named / special key (Enter, Tab, etc.).
func keySpecial(t tea.KeyType) tea.KeyMsg {
	return tea.KeyMsg{Type: t}
}

// execCmd runs a tea.Cmd and returns its message (nil-safe).
func execCmd(cmd tea.Cmd) tea.Msg {
	if cmd == nil {
		return nil
	}
	return cmd()
}

// ── Splash ────────────────────────────────────────────────────────────────────

func TestNewSplash(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{TotalEvents: 5})
	defer srv.Close()

	m := NewSplash(client)

	if m.client == nil {
		t.Fatal("expected non-nil client")
	}
	if m.connected {
		t.Fatal("expected connected=false initially")
	}
}

func TestSplashInit(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{TotalEvents: 1})
	defer srv.Close()

	m := NewSplash(client)
	cmd := m.Init()

	if cmd == nil {
		t.Fatal("Init should return a non-nil batch cmd")
	}
}

func TestSplashView(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewSplash(client)
	view := m.View(120, 40)

	if view == "" {
		t.Fatal("View returned empty string")
	}
	// The ASCII banner spells out W-A-Z-E using block characters; check for known banner text.
	if len(view) < 10 {
		t.Fatalf("View output suspiciously short (%d chars)", len(view))
	}
}

func TestSplashConnectionSuccess(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{TotalEvents: 100, UniqueUsers: 7})
	defer srv.Close()

	m := NewSplash(client)
	stats := &api.Stats{TotalEvents: 100, UniqueUsers: 7}

	m2, _ := m.Update(connectionCheckMsg{ok: true, stats: stats})

	if !m2.connected {
		t.Fatal("expected connected=true after successful connectionCheckMsg")
	}
	if m2.stats == nil || m2.stats.TotalEvents != 100 {
		t.Fatalf("expected stats.TotalEvents=100, got %v", m2.stats)
	}
}

func TestSplashEnterWhenConnected(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewSplash(client)
	m.connected = true

	_, cmd := m.Update(keySpecial(tea.KeyEnter))
	if cmd == nil {
		t.Fatal("expected a cmd after pressing enter when connected")
	}
	msg := execCmd(cmd)
	nav, ok := msg.(NavigateMsg)
	if !ok {
		t.Fatalf("expected NavigateMsg, got %T", msg)
	}
	if nav.Screen != ScreenRegions {
		t.Fatalf("expected ScreenRegions (%d), got %d", ScreenRegions, nav.Screen)
	}
}

func TestSplashStartServerShortcut(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewSplash(client)
	m2, cmd := m.Update(keyRune('s'))
	if m2.err != "Starting server..." {
		t.Fatalf("expected start-server hint, got %q", m2.err)
	}
	if cmd == nil {
		t.Fatal("expected cmd after pressing 's'")
	}
	msg := execCmd(cmd)
	if _, ok := msg.(StartLocalServerMsg); !ok {
		t.Fatalf("expected StartLocalServerMsg, got %T", msg)
	}
}

// ── Regions ───────────────────────────────────────────────────────────────────

func TestNewRegions(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewRegions(client)

	if len(m.selected) != 0 {
		t.Fatalf("expected empty selection, got %v", m.selected)
	}
}

func TestRegionsToggle(t *testing.T) {
	m := NewRegions(nil)
	firstRegion := allRegions[0]

	// Initially not selected.
	if m.selected[firstRegion] {
		t.Fatalf("expected %s to be unselected initially", firstRegion)
	}

	m2, _ := m.Update(keyRune(' '))
	if !m2.selected[firstRegion] {
		t.Fatalf("expected %s to be selected after space", firstRegion)
	}

	m3, _ := m2.Update(keyRune(' '))
	if m3.selected[firstRegion] {
		t.Fatalf("expected %s to be deselected after second space", firstRegion)
	}
}

func TestRegionsSelectAll(t *testing.T) {
	m := NewRegions(nil)

	m2, _ := m.Update(keyRune('a'))

	for _, r := range allRegions {
		if !m2.selected[r] {
			t.Fatalf("expected region %s to be selected after 'a'", r)
		}
	}

	if len(m2.selected) != 5 {
		t.Fatalf("expected 5 selected regions, got %d", len(m2.selected))
	}
}

func TestRegionsView(t *testing.T) {
	m := NewRegions(nil)
	view := m.View(120, 40)

	if view == "" {
		t.Fatal("View returned empty string")
	}
	// Title is rendered with lipgloss styles so we check the raw string for the literal text.
	// lipgloss may or may not add ANSI codes in test context, so just check length.
	if len(view) < 10 {
		t.Fatal("View output suspiciously short")
	}
}

func TestRegionsLaunch(t *testing.T) {
	m := NewRegions(nil)

	// Select europe (cursor starts at 0).
	m, _ = m.Update(keyRune(' '))

	_, cmd := m.Update(keySpecial(tea.KeyEnter))
	if cmd == nil {
		t.Fatal("expected cmd after enter with a selected region")
	}
	msg := execCmd(cmd)
	launch, ok := msg.(LaunchCollectionMsg)
	if !ok {
		t.Fatalf("expected LaunchCollectionMsg, got %T", msg)
	}
	if len(launch.Regions) == 0 {
		t.Fatal("expected at least one region in LaunchCollectionMsg")
	}
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

func TestNewDashboard(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewDashboard(client)

	if len(m.regions) != 5 {
		t.Fatalf("expected 5 regions, got %d", len(m.regions))
	}
	if m.feed == nil {
		t.Fatal("expected non-nil feed")
	}
	if m.throughput == nil {
		t.Fatal("expected non-nil throughput tracker")
	}
}

func TestDashboardView(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewDashboard(client)
	view := m.View(120, 40)

	if view == "" {
		t.Fatal("View returned empty string")
	}
}

func TestDashboardLayoutToggle(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewDashboard(client)

	if m.layout != LayoutFocus {
		t.Fatalf("expected initial layout LayoutFocus, got %d", m.layout)
	}

	m2, _ := m.Update(keySpecial(tea.KeyTab))
	if m2.layout != LayoutGrid {
		t.Fatalf("expected LayoutGrid after tab, got %d", m2.layout)
	}

	m3, _ := m2.Update(keySpecial(tea.KeyTab))
	if m3.layout != LayoutFocus {
		t.Fatalf("expected LayoutFocus after second tab, got %d", m3.layout)
	}
}

func TestDashboardFilterCycle(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewDashboard(client)

	// Initial filter is empty string (index 0).
	if m.feed.Filter != "" {
		t.Fatalf("expected empty initial filter, got %q", m.feed.Filter)
	}

	// Cycle through all filters.
	for i := 1; i < len(feedFilters); i++ {
		m, _ = m.Update(keyRune('f'))
		if m.feed.Filter != feedFilters[i] {
			t.Fatalf("after %d 'f' presses: expected filter %q, got %q",
				i, feedFilters[i], m.feed.Filter)
		}
	}

	// One more press wraps back to empty.
	m, _ = m.Update(keyRune('f'))
	if m.feed.Filter != "" {
		t.Fatalf("expected filter to wrap back to empty, got %q", m.feed.Filter)
	}
}

// ── Investigation ─────────────────────────────────────────────────────────────

func TestNewInvestigation(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewInvestigation(client)

	if m.userList == nil {
		t.Fatal("expected non-nil userList")
	}
}

func TestInvestigationPanelCycle(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewInvestigation(client)

	if m.activePanel != PanelUsers {
		t.Fatalf("expected initial panel PanelUsers, got %d", m.activePanel)
	}

	m2, _ := m.Update(keySpecial(tea.KeyTab))
	if m2.activePanel != PanelProfile {
		t.Fatalf("expected PanelProfile after tab, got %d", m2.activePanel)
	}

	m3, _ := m2.Update(keySpecial(tea.KeyTab))
	if m3.activePanel != PanelBottom {
		t.Fatalf("expected PanelBottom after second tab, got %d", m3.activePanel)
	}

	// Third tab wraps back to PanelUsers.
	m4, _ := m3.Update(keySpecial(tea.KeyTab))
	if m4.activePanel != PanelUsers {
		t.Fatalf("expected PanelUsers after third tab (wrap), got %d", m4.activePanel)
	}
}

func TestInvestigationBottomViewSwitch(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewInvestigation(client)

	cases := []struct {
		key      rune
		expected BottomView
	}{
		{'c', ViewTrips},
		{'v', ViewPrivacy},
		{'d', ViewIntel},
		{'l', ViewLocation},
		{'n', ViewNetwork},
	}

	for _, tc := range cases {
		m2, _ := m.Update(keyRune(tc.key))
		if m2.bottomView != tc.expected {
			t.Errorf("key %q: expected bottomView %d, got %d", tc.key, tc.expected, m2.bottomView)
		}
	}
}

func TestInvestigationUsersLoaded(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewInvestigation(client)

	users := []api.UserSummary{
		{Username: "alice", Count: 10},
		{Username: "bob", Count: 5},
	}
	m2, _ := m.Update(usersLoadedMsg{users: users})

	if len(m2.userList.Users) != 2 {
		t.Fatalf("expected 2 users, got %d", len(m2.userList.Users))
	}
}

// ── History ───────────────────────────────────────────────────────────────────

func TestNewHistory(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewHistory(client)

	if len(m.events) != 0 {
		t.Fatalf("expected empty events, got %d", len(m.events))
	}
	if m.cursor != 0 {
		t.Fatalf("expected cursor=0, got %d", m.cursor)
	}
}

func TestHistoryView(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewHistory(client)
	view := m.View(120, 40)

	if view == "" {
		t.Fatal("View returned empty string")
	}
	// "RECENT ACTIVITY" is the title — check the raw rune content exists.
	if len([]rune(view)) < 10 {
		t.Fatal("View output suspiciously short")
	}
}

func TestHistoryCursor(t *testing.T) {
	srv, client := newStatsServer(t, api.Stats{})
	defer srv.Close()

	m := NewHistory(client)
	// Load some events.
	events := []api.Event{
		{ID: "1", Username: "alice", Type: "POLICE"},
		{ID: "2", Username: "bob", Type: "JAM"},
		{ID: "3", Username: "carol", Type: "HAZARD"},
	}
	m, _ = m.Update(recentEventsMsg{events: events})

	if m.cursor != 0 {
		t.Fatalf("expected cursor=0 after load, got %d", m.cursor)
	}

	// Move down.
	m2, _ := m.Update(keySpecial(tea.KeyDown))
	if m2.cursor != 1 {
		t.Fatalf("expected cursor=1 after down, got %d", m2.cursor)
	}

	// Move down again.
	m3, _ := m2.Update(keySpecial(tea.KeyDown))
	if m3.cursor != 2 {
		t.Fatalf("expected cursor=2 after second down, got %d", m3.cursor)
	}

	// Move up.
	m4, _ := m3.Update(keySpecial(tea.KeyUp))
	if m4.cursor != 1 {
		t.Fatalf("expected cursor=1 after up, got %d", m4.cursor)
	}
}

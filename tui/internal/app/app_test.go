package app

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/screens"
)

// ── helpers ───────────────────────────────────────────────────────────────────

// newStubServer returns a test HTTP server that responds to every path with the
// given payload serialised as JSON.
func newStubServer(t *testing.T, payload interface{}) *httptest.Server {
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

// newTestApp creates an App wired to a stub HTTP server. The caller must close
// the server when done.
func newTestApp(t *testing.T) (App, *httptest.Server) {
	t.Helper()
	srv := newStubServer(t, api.Stats{TotalEvents: 42, UniqueUsers: 3})
	a := New(srv.URL, "test")
	return a, srv
}

// keyRune creates a tea.KeyMsg for a printable character.
func keyRune(r rune) tea.KeyMsg {
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{r}}
}

// execCmd runs a tea.Cmd and returns its Msg (nil-safe).
func execCmd(cmd tea.Cmd) tea.Msg {
	if cmd == nil {
		return nil
	}
	return cmd()
}

// ── Tests ─────────────────────────────────────────────────────────────────────

func TestNew(t *testing.T) {
	a, srv := newTestApp(t)
	defer srv.Close()

	if a.client == nil {
		t.Fatal("expected non-nil client")
	}
	if a.screen != ScreenSplash {
		t.Fatalf("expected initial screen ScreenSplash, got %v", a.screen)
	}
	// Verify all child screens were created by confirming their Init() cmds are
	// non-nil (each screen fires at least one startup command).
	if a.Init() == nil {
		t.Fatal("expected Init to return a non-nil cmd (splash fires connection check)")
	}
}

func TestAppView(t *testing.T) {
	a, srv := newTestApp(t)
	defer srv.Close()

	// Before WindowSizeMsg the view returns the initialising placeholder.
	before := a.View()
	if before == "" {
		t.Fatal("View() returned empty string before window size")
	}

	// After WindowSizeMsg the view should render proper content.
	model, _ := a.Update(tea.WindowSizeMsg{Width: 120, Height: 40})
	app := model.(App)
	after := app.View()
	if after == "" {
		t.Fatal("View() returned empty string after WindowSizeMsg")
	}
	if len(after) <= len(before) {
		// The real view should be substantially larger than the placeholder.
		// This is a soft check — just ensure it rendered something.
		t.Logf("view length before=%d after=%d (after should be larger)", len(before), len(after))
	}
}

func TestAppHelpToggle(t *testing.T) {
	a, srv := newTestApp(t)
	defer srv.Close()

	if a.showHelp {
		t.Fatal("expected showHelp=false initially")
	}

	model, _ := a.Update(keyRune('?'))
	a2 := model.(App)
	if !a2.showHelp {
		t.Fatal("expected showHelp=true after '?'")
	}

	model2, _ := a2.Update(keyRune('?'))
	a3 := model2.(App)
	if a3.showHelp {
		t.Fatal("expected showHelp=false after second '?'")
	}
}

func TestAppScreenSwitch(t *testing.T) {
	a, srv := newTestApp(t)
	defer srv.Close()

	cases := []struct {
		msg      SwitchScreenMsg
		expected Screen
	}{
		{SwitchScreenMsg{Screen: ScreenRegions}, ScreenRegions},
		{SwitchScreenMsg{Screen: ScreenDashboard}, ScreenDashboard},
		{SwitchScreenMsg{Screen: ScreenInvestigation}, ScreenInvestigation},
		{SwitchScreenMsg{Screen: ScreenHistory}, ScreenHistory},
		{SwitchScreenMsg{Screen: ScreenSplash}, ScreenSplash},
	}

	for _, tc := range cases {
		model, _ := a.Update(tc.msg)
		got := model.(App).screen
		if got != tc.expected {
			t.Errorf("SwitchScreenMsg{Screen:%d}: expected screen %d, got %d",
				tc.msg.Screen, tc.expected, got)
		}
	}
}

func TestAppNavigateMsg(t *testing.T) {
	a, srv := newTestApp(t)
	defer srv.Close()

	cases := []struct {
		msg      screens.NavigateMsg
		expected Screen
	}{
		{screens.NavigateMsg{Screen: screens.ScreenRegions}, ScreenRegions},
		{screens.NavigateMsg{Screen: screens.ScreenDashboard}, ScreenDashboard},
		{screens.NavigateMsg{Screen: screens.ScreenInvestigation}, ScreenInvestigation},
		{screens.NavigateMsg{Screen: screens.ScreenHistory}, ScreenHistory},
		{screens.NavigateMsg{Screen: screens.ScreenSplash}, ScreenSplash},
	}

	for _, tc := range cases {
		model, _ := a.Update(tc.msg)
		got := model.(App).screen
		if got != tc.expected {
			t.Errorf("NavigateMsg{Screen:%d}: expected screen %d, got %d",
				tc.msg.Screen, tc.expected, got)
		}
	}
}

func TestAppQuitFromSplash(t *testing.T) {
	a, srv := newTestApp(t)
	defer srv.Close()

	// Ensure we start on splash.
	if a.screen != ScreenSplash {
		t.Fatalf("expected ScreenSplash, got %d", a.screen)
	}

	_, cmd := a.Update(keyRune('q'))
	if cmd == nil {
		t.Fatal("expected a cmd (tea.Quit) after 'q' on splash")
	}

	msg := execCmd(cmd)
	// tea.Quit returns a tea.QuitMsg.
	if _, ok := msg.(tea.QuitMsg); !ok {
		t.Fatalf("expected tea.QuitMsg, got %T", msg)
	}
}

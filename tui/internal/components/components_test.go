package components

import (
	"strings"
	"testing"
	"time"

	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
)

// ─── Toast ───────────────────────────────────────────────────────────────────

func TestNewToast(t *testing.T) {
	toast := NewToast("info", "hello world")
	if toast.Level != "info" {
		t.Errorf("expected level 'info', got %q", toast.Level)
	}
	if toast.Message != "hello world" {
		t.Errorf("expected message 'hello world', got %q", toast.Message)
	}
}

func TestNewToastSuccess(t *testing.T) {
	toast := NewToast("success", "all good")
	if toast.Level != "success" {
		t.Errorf("expected level 'success', got %q", toast.Level)
	}
}

func TestNewToastError(t *testing.T) {
	toast := NewToast("error", "something failed")
	if toast.Level != "error" {
		t.Errorf("expected level 'error', got %q", toast.Level)
	}
}

func TestRenderToast(t *testing.T) {
	tests := []struct {
		level   string
		message string
	}{
		{"info", "info message"},
		{"success", "success message"},
		{"error", "error message"},
	}
	for _, tt := range tests {
		t.Run(tt.level, func(t *testing.T) {
			toast := NewToast(tt.level, tt.message)
			out := RenderToast(toast, 80)
			if out == "" {
				t.Fatal("RenderToast returned empty string")
			}
			if !strings.Contains(out, tt.message) {
				t.Errorf("expected rendered output to contain %q", tt.message)
			}
		})
	}
}

func TestRenderToastNil(t *testing.T) {
	// RenderToast(nil) panics — callers are responsible for guarding.
	// Test that a non-nil toast with each level always produces non-empty output.
	for _, level := range []string{"info", "success", "error", "unknown"} {
		toast := NewToast(level, "msg")
		out := RenderToast(toast, 80)
		if out == "" {
			t.Errorf("RenderToast level=%q returned empty string", level)
		}
	}
}

func TestOverlayToastNil(t *testing.T) {
	// OverlayToast with a real toast appends it below the content.
	toast := NewToast("info", "overlay msg")
	out := OverlayToast("main content", toast, 80)
	if !strings.Contains(out, "main content") {
		t.Error("OverlayToast should preserve original content")
	}
	if !strings.Contains(out, "overlay msg") {
		t.Error("OverlayToast should contain toast message")
	}
}

// ─── StatusBar ────────────────────────────────────────────────────────────────

func TestRenderStatusBar(t *testing.T) {
	d := StatusBarData{
		Left:   "LEFT",
		Center: "CENTER",
		Right:  "RIGHT",
	}
	out := RenderStatusBar(d, 80)
	if out == "" {
		t.Fatal("RenderStatusBar returned empty string")
	}
	if !strings.Contains(out, "LEFT") {
		t.Error("expected LEFT in output")
	}
	if !strings.Contains(out, "CENTER") {
		t.Error("expected CENTER in output")
	}
	if !strings.Contains(out, "RIGHT") {
		t.Error("expected RIGHT in output")
	}
}

func TestRenderStatusBarWidth(t *testing.T) {
	d := StatusBarData{Left: "A", Center: "B", Right: "C"}
	// Should not panic for various widths.
	for _, w := range []int{1, 10, 40, 120} {
		out := RenderStatusBar(d, w)
		if out == "" {
			t.Errorf("RenderStatusBar width=%d returned empty", w)
		}
	}
}

func TestFormatEventRate(t *testing.T) {
	tests := []struct {
		rate float64
		want string
	}{
		{12.5, "12.5 evt/min"},
		{0.0, "0.0 evt/min"},
		{100.0, "100.0 evt/min"},
		{3.333, "3.3 evt/min"},
	}
	for _, tt := range tests {
		got := FormatEventRate(tt.rate)
		if got != tt.want {
			t.Errorf("FormatEventRate(%.3f) = %q, want %q", tt.rate, got, tt.want)
		}
	}
}

// ─── Sparkline / ThroughputTracker ────────────────────────────────────────────

func TestThroughputTrackerEmpty(t *testing.T) {
	tr := NewThroughputTracker()
	rate := tr.CurrentRate()
	if rate != 0 {
		t.Errorf("expected 0 rate for new tracker, got %f", rate)
	}
}

func TestThroughputTrackerAdd(t *testing.T) {
	tr := NewThroughputTracker()
	tr.Add(10)
	// Rate is averaged over last 5 seconds. Adding 10 events now should produce > 0.
	rate := tr.CurrentRate()
	if rate <= 0 {
		t.Errorf("expected positive rate after Add, got %f", rate)
	}
}

func TestThroughputTrackerAddMultiple(t *testing.T) {
	tr := NewThroughputTracker()
	for i := 0; i < 5; i++ {
		tr.Add(3)
	}
	rate := tr.CurrentRate()
	if rate <= 0 {
		t.Errorf("expected positive rate after multiple Add calls, got %f", rate)
	}
}

func TestSparklineWidth(t *testing.T) {
	tr := NewThroughputTracker()
	tr.Add(5)
	// Sleep 1ms to ensure advance can run (same-second is fine for this test).
	time.Sleep(1 * time.Millisecond)

	for _, w := range []int{1, 10, 20, 50} {
		out := tr.Sparkline(w)
		// Strip ANSI escape codes for rune counting.
		plain := stripANSI(out)
		runes := []rune(plain)
		if len(runes) != w {
			t.Errorf("Sparkline(%d) plain rune count = %d, want %d (out=%q)", w, len(runes), w, plain)
		}
	}
}

func TestSparklineEmpty(t *testing.T) {
	tr := NewThroughputTracker()
	// No events added — all chars should be the lowest spark char.
	out := tr.Sparkline(10)
	plain := stripANSI(out)
	for _, ch := range []rune(plain) {
		if ch != sparkChars[0] {
			t.Errorf("expected all lowest spark chars for empty tracker, got %q", ch)
		}
	}
}

func TestSparklineUsesBlockChars(t *testing.T) {
	tr := NewThroughputTracker()
	tr.Add(20)
	out := tr.Sparkline(5)
	// At least one spark character should appear.
	found := false
	for _, ch := range sparkChars {
		if strings.ContainsRune(out, ch) {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected at least one spark block character in sparkline output")
	}
}

func TestSparklineZeroWidth(t *testing.T) {
	tr := NewThroughputTracker()
	out := tr.Sparkline(0)
	if out != "" {
		t.Errorf("Sparkline(0) should return empty string, got %q", out)
	}
}

// ─── EventFeed ────────────────────────────────────────────────────────────────

func TestEventFeedPush(t *testing.T) {
	f := NewEventFeed(5)
	e1 := api.Event{ID: "1", Type: "POLICE", Username: "alice", Timestamp: "2024-01-01T10:00:00"}
	e2 := api.Event{ID: "2", Type: "JAM", Username: "bob", Timestamp: "2024-01-01T10:01:00"}
	f.Push(e1)
	f.Push(e2)

	if len(f.Events) != 2 {
		t.Fatalf("expected 2 events, got %d", len(f.Events))
	}
	// Newest first.
	if f.Events[0].ID != "2" {
		t.Errorf("expected newest event first, got ID=%q", f.Events[0].ID)
	}
}

func TestEventFeedCap(t *testing.T) {
	f := NewEventFeed(3)
	for i := 0; i < 10; i++ {
		f.Push(api.Event{ID: "x", Type: "POLICE"})
	}
	if len(f.Events) > 3 {
		t.Errorf("expected cap at 3, got %d events", len(f.Events))
	}
}

func TestEventFeedDefaultCap(t *testing.T) {
	f := NewEventFeed(0)
	if f.MaxEvents != 500 {
		t.Errorf("expected default MaxEvents=500, got %d", f.MaxEvents)
	}
}

func TestEventFeedFilter(t *testing.T) {
	f := NewEventFeed(10)
	f.Push(api.Event{ID: "1", Type: "POLICE", Username: "alice", Timestamp: "2024-01-01T10:00:00", Latitude: 40.4, Longitude: -3.7})
	f.Push(api.Event{ID: "2", Type: "JAM", Username: "bob", Timestamp: "2024-01-01T10:01:00", Latitude: 40.5, Longitude: -3.6})
	f.Push(api.Event{ID: "3", Type: "POLICE", Username: "carol", Timestamp: "2024-01-01T10:02:00", Latitude: 40.6, Longitude: -3.5})

	f.Filter = "POLICE"
	out := f.View(80, 20)
	if strings.Contains(out, "JAM") {
		t.Error("filter 'POLICE' should not show JAM events")
	}
	if !strings.Contains(out, "alice") && !strings.Contains(out, "carol") {
		t.Error("expected POLICE-type users in filtered view")
	}
}

func TestEventFeedEmpty(t *testing.T) {
	f := NewEventFeed(10)
	out := f.View(80, 20)
	if !strings.Contains(out, "Waiting") {
		t.Errorf("empty feed should show waiting message, got: %q", out)
	}
}

func TestEventFeedView(t *testing.T) {
	f := NewEventFeed(10)
	f.Push(api.Event{
		ID:        "1",
		Type:      "HAZARD",
		Username:  "testuser",
		Timestamp: "2024-06-15T14:30:00",
		Latitude:  40.4168,
		Longitude: -3.7038,
	})
	out := f.View(80, 20)
	if out == "" {
		t.Fatal("expected non-empty view output")
	}
	if !strings.Contains(out, "testuser") {
		t.Error("expected username in view output")
	}
}

// ─── RegionPane ───────────────────────────────────────────────────────────────

func TestRenderRegionPaneRunning(t *testing.T) {
	d := RegionData{
		Name:      "europe",
		Running:   true,
		Cycle:     7,
		Events:    123,
		Delta:     5,
		Errors:    0,
		Cells:     100,
		EventRate: 14.5,
	}
	out := RenderRegionPane(d, 40, false)
	if out == "" {
		t.Fatal("RenderRegionPane returned empty string")
	}
	if !strings.Contains(out, "EUROPE") {
		t.Error("expected region name EUROPE in output")
	}
	if !strings.Contains(out, "cycle 7") {
		t.Error("expected cycle number in running region output")
	}
	if !strings.Contains(out, "14.5") {
		t.Error("expected event rate in running region output")
	}
}

func TestRenderRegionPaneIdle(t *testing.T) {
	d := RegionData{
		Name:    "americas",
		Running: false,
	}
	out := RenderRegionPane(d, 40, false)
	if out == "" {
		t.Fatal("RenderRegionPane returned empty string")
	}
	if !strings.Contains(out, "Idle") {
		t.Errorf("expected 'Idle' for non-running region, got: %q", out)
	}
}

func TestRenderRegionPaneErroring(t *testing.T) {
	d := RegionData{
		Name:     "asia",
		Running:  false,
		Erroring: true,
		Errors:   3,
	}
	out := RenderRegionPane(d, 40, false)
	if out == "" {
		t.Fatal("RenderRegionPane returned empty string for erroring region")
	}
	// Should not show Idle when erroring.
	if strings.Contains(out, "Idle") {
		t.Error("erroring region should not show Idle")
	}
}

func TestRenderRegionPaneActive(t *testing.T) {
	d := RegionData{Name: "oceania", Running: true, Cycle: 1, EventRate: 2.0}
	outActive := RenderRegionPane(d, 40, true)
	outInactive := RenderRegionPane(d, 40, false)
	if outActive == "" || outInactive == "" {
		t.Fatal("both active and inactive renders should be non-empty")
	}
}

// ─── UserList ─────────────────────────────────────────────────────────────────

func makeUsers() []api.UserSummary {
	return []api.UserSummary{
		{Username: "charlie", Count: 10},
		{Username: "alice", Count: 50},
		{Username: "bob", Count: 30},
	}
}

func TestUserListSetUsers(t *testing.T) {
	ul := NewUserList()
	ul.SetUsers(makeUsers())
	if len(ul.Users) != 3 {
		t.Fatalf("expected 3 users, got %d", len(ul.Users))
	}
	// Default sort is by events descending.
	if ul.Users[0].Username != "alice" {
		t.Errorf("expected alice (50 events) first, got %q", ul.Users[0].Username)
	}
}

func TestUserListCycleSort(t *testing.T) {
	ul := NewUserList()
	ul.SetUsers(makeUsers())

	// Start: SortByEvents (0).
	if ul.Sort != SortByEvents {
		t.Errorf("initial sort should be SortByEvents, got %v", ul.Sort)
	}

	ul.CycleSort() // -> SortByName (1)
	if ul.Sort != SortByName {
		t.Errorf("after 1 cycle expected SortByName, got %v", ul.Sort)
	}
	if ul.Users[0].Username != "alice" {
		t.Errorf("SortByName: expected alice first, got %q", ul.Users[0].Username)
	}

	ul.CycleSort() // -> SortByRisk (2)
	if ul.Sort != SortByRisk {
		t.Errorf("after 2 cycles expected SortByRisk, got %v", ul.Sort)
	}

	ul.CycleSort() // -> back to SortByEvents (0)
	if ul.Sort != SortByEvents {
		t.Errorf("after 3 cycles expected SortByEvents, got %v", ul.Sort)
	}
}

func TestUserListFilter(t *testing.T) {
	ul := NewUserList()
	ul.SetUsers(makeUsers())

	ul.Filter = "ali"
	filtered := ul.Filtered()
	if len(filtered) != 1 {
		t.Fatalf("expected 1 filtered user, got %d", len(filtered))
	}
	if filtered[0].Username != "alice" {
		t.Errorf("expected alice in filtered result, got %q", filtered[0].Username)
	}
}

func TestUserListFilterCaseInsensitive(t *testing.T) {
	ul := NewUserList()
	ul.SetUsers(makeUsers())

	ul.Filter = "BOB"
	filtered := ul.Filtered()
	if len(filtered) != 1 || filtered[0].Username != "bob" {
		t.Error("filter should be case-insensitive")
	}
}

func TestUserListFilterNoMatch(t *testing.T) {
	ul := NewUserList()
	ul.SetUsers(makeUsers())
	ul.Filter = "zzz"
	if len(ul.Filtered()) != 0 {
		t.Error("expected 0 results for non-matching filter")
	}
}

func TestUserListMoveDown(t *testing.T) {
	ul := NewUserList()
	ul.SetUsers(makeUsers())

	ul.MoveDown(10)
	if ul.Selected != 1 {
		t.Errorf("after MoveDown expected Selected=1, got %d", ul.Selected)
	}
}

func TestUserListMoveUp(t *testing.T) {
	ul := NewUserList()
	ul.SetUsers(makeUsers())
	ul.Selected = 2

	ul.MoveUp()
	if ul.Selected != 1 {
		t.Errorf("after MoveUp expected Selected=1, got %d", ul.Selected)
	}
}

func TestUserListMoveUpBound(t *testing.T) {
	ul := NewUserList()
	ul.SetUsers(makeUsers())
	ul.Selected = 0

	ul.MoveUp() // should stay at 0
	if ul.Selected != 0 {
		t.Errorf("MoveUp at top should stay at 0, got %d", ul.Selected)
	}
}

func TestUserListMoveDownBound(t *testing.T) {
	ul := NewUserList()
	ul.SetUsers(makeUsers())
	ul.Selected = 2 // last index

	ul.MoveDown(10) // should stay at 2
	if ul.Selected != 2 {
		t.Errorf("MoveDown at bottom should stay at 2, got %d", ul.Selected)
	}
}

func TestUserListSelectedUser(t *testing.T) {
	ul := NewUserList()
	ul.SetUsers(makeUsers())
	ul.Selected = 0

	u := ul.SelectedUser()
	if u == nil {
		t.Fatal("SelectedUser should not be nil")
	}
	if u.Username != "alice" {
		t.Errorf("expected alice (top by events), got %q", u.Username)
	}
}

func TestUserListSelectedUserEmpty(t *testing.T) {
	ul := NewUserList()
	u := ul.SelectedUser()
	if u != nil {
		t.Error("SelectedUser on empty list should return nil")
	}
}

// ─── TripView ─────────────────────────────────────────────────────────────────

func TestRenderTripViewEmpty(t *testing.T) {
	out := RenderTripView(nil, 80)
	if out == "" {
		t.Fatal("RenderTripView(nil) should return non-empty muted text")
	}
	if !strings.Contains(out, "no trip data") {
		t.Errorf("expected 'no trip data' for nil response, got: %q", out)
	}
}

func TestRenderTripViewError(t *testing.T) {
	resp := &api.TripResponse{Error: "user not found"}
	out := RenderTripView(resp, 80)
	if !strings.Contains(out, "error") {
		t.Errorf("expected error message in output, got: %q", out)
	}
}

func TestRenderTripViewNoTrips(t *testing.T) {
	resp := &api.TripResponse{Trips: []api.Trip{}}
	out := RenderTripView(resp, 80)
	if !strings.Contains(out, "no trips") {
		t.Errorf("expected 'no trips' message, got: %q", out)
	}
}

func TestRenderTripViewWithTrips(t *testing.T) {
	resp := &api.TripResponse{
		Username: "alice",
		Trips: []api.Trip{
			{
				TripType:    "morning_commute",
				StartTime:   "2024-06-15T08:00:00",
				EndTime:     "2024-06-15T08:30:00",
				DistanceKm:  12.5,
				DurationMin: 30,
				StartArea:   "Home",
				EndArea:     "Office",
				Regularity:  0.85,
			},
		},
		Summary: api.TripSummary{
			TotalTrips:    1,
			AvgDailyTrips: 2.0,
			InferredHome:  "Home",
			InferredWork:  "Office",
		},
	}
	out := RenderTripView(resp, 80)
	if out == "" {
		t.Fatal("expected non-empty trip view output")
	}
	if !strings.Contains(out, "morning_commute") {
		t.Error("expected trip type in output")
	}
	if !strings.Contains(out, "→") {
		t.Error("expected arrow in route line")
	}
	if !strings.Contains(out, "Home") {
		t.Error("expected start area in output")
	}
	if !strings.Contains(out, "Office") {
		t.Error("expected end area in output")
	}
}

func TestRenderTripViewAllTypes(t *testing.T) {
	tripTypes := []string{"morning_commute", "evening_commute", "round_trip", "other"}
	for _, tt := range tripTypes {
		t.Run(tt, func(t *testing.T) {
			resp := &api.TripResponse{
				Trips: []api.Trip{
					{TripType: tt, StartTime: "08:00", EndTime: "09:00", DistanceKm: 5, DurationMin: 60},
				},
				Summary: api.TripSummary{TotalTrips: 1},
			}
			out := RenderTripView(resp, 80)
			if out == "" {
				t.Errorf("trip type %q produced empty output", tt)
			}
		})
	}
}

// ─── PrivacyView ──────────────────────────────────────────────────────────────

func TestRenderPrivacyViewEmpty(t *testing.T) {
	out := RenderPrivacyView(nil, 80)
	if out == "" {
		t.Fatal("RenderPrivacyView(nil) should return non-empty muted text")
	}
	if !strings.Contains(out, "no privacy data") {
		t.Errorf("expected 'no privacy data', got: %q", out)
	}
}

func TestRenderPrivacyViewError(t *testing.T) {
	score := &api.PrivacyScore{Error: "insufficient data"}
	out := RenderPrivacyView(score, 80)
	if !strings.Contains(out, "error") {
		t.Errorf("expected error text, got: %q", out)
	}
}

func TestRenderPrivacyViewBars(t *testing.T) {
	score := &api.PrivacyScore{
		Username:          "alice",
		OverallScore:      72,
		RiskLevel:         "HIGH",
		HomeExposure:      80.0,
		WorkExposure:      60.0,
		ScheduleScore:     70.0,
		RouteScore:        65.0,
		IdentityScore:     55.0,
		TrackabilityScore: 90.0,
	}
	out := RenderPrivacyView(score, 80)
	if out == "" {
		t.Fatal("expected non-empty privacy view output")
	}

	expectedLabels := []string{
		"Home Exposure",
		"Work Exposure",
		"Schedule Score",
		"Route Score",
		"Identity Score",
		"Trackability",
	}
	for _, label := range expectedLabels {
		if !strings.Contains(out, label) {
			t.Errorf("expected label %q in privacy view output", label)
		}
	}

	if !strings.Contains(out, "Overall") {
		t.Error("expected 'Overall' score line in output")
	}
	if !strings.Contains(out, "72") {
		t.Error("expected overall score 72 in output")
	}
	if !strings.Contains(out, "HIGH") {
		t.Error("expected risk level HIGH in output")
	}
}

// ─── IntelView ────────────────────────────────────────────────────────────────

func TestRenderIntelViewEmpty(t *testing.T) {
	out := RenderIntelView(nil, 80)
	if out == "" {
		t.Fatal("RenderIntelView(nil) should return non-empty muted text")
	}
	if !strings.Contains(out, "no intel data") {
		t.Errorf("expected 'no intel data', got: %q", out)
	}
}

func TestRenderIntelViewError(t *testing.T) {
	intel := &api.IntelProfile{Error: "oracle unavailable"}
	out := RenderIntelView(intel, 80)
	if !strings.Contains(out, "error") {
		t.Errorf("expected error text, got: %q", out)
	}
}

func TestRenderIntelViewNoRoutines(t *testing.T) {
	intel := &api.IntelProfile{
		Username:   "alice",
		Region:     "europe",
		EventCount: 42,
		Routines:   []api.Routine{},
	}
	out := RenderIntelView(intel, 80)
	if !strings.Contains(out, "no routines") {
		t.Errorf("expected 'no routines' message, got: %q", out)
	}
}

func TestRenderIntelViewWithData(t *testing.T) {
	intel := &api.IntelProfile{
		Username:    "alice",
		Region:      "europe",
		EventCount:  150,
		CentroidLat: 40.4168,
		CentroidLon: -3.7038,
		GeoSpreadKm: 5.2,
		Routines: []api.Routine{
			{RoutineType: "home", Latitude: 40.41, Longitude: -3.70, Confidence: 0.92, EvidenceCount: 45},
			{RoutineType: "work", Latitude: 40.45, Longitude: -3.68, Confidence: 0.78, EvidenceCount: 30},
		},
		CoOccurrences: []api.CoOccurrence{
			{Partner: "bob", CoCount: 12, AvgDistanceM: 85.5},
		},
	}
	out := RenderIntelView(intel, 80)
	if out == "" {
		t.Fatal("expected non-empty intel view output")
	}
	if !strings.Contains(out, "europe") {
		t.Error("expected region in output")
	}
	if !strings.Contains(out, "Routines") {
		t.Error("expected 'Routines' section header")
	}
	if !strings.Contains(out, "home") {
		t.Error("expected home routine in output")
	}
	if !strings.Contains(out, "Co-occurrences") {
		t.Error("expected 'Co-occurrences' section header")
	}
	if !strings.Contains(out, "bob") {
		t.Error("expected co-occurrence partner in output")
	}
}

// ─── LocationView ─────────────────────────────────────────────────────────────

func TestRenderLocationViewEmpty(t *testing.T) {
	out := RenderLocationView([]api.Event{}, 80, 20)
	if out == "" {
		t.Fatal("RenderLocationView(empty) should return non-empty muted text")
	}
	if !strings.Contains(out, "no location data") {
		t.Errorf("expected 'no location data', got: %q", out)
	}
}

func TestRenderLocationViewGrid(t *testing.T) {
	events := []api.Event{
		{Latitude: 40.4168, Longitude: -3.7038},
		{Latitude: 40.4200, Longitude: -3.7000},
		{Latitude: 40.4100, Longitude: -3.7100},
		{Latitude: 40.4300, Longitude: -3.6900},
		{Latitude: 40.4250, Longitude: -3.7050},
	}
	out := RenderLocationView(events, 60, 20)
	if out == "" {
		t.Fatal("expected non-empty location view output")
	}
	// Should contain lat/lon axis labels.
	if !strings.Contains(out, "lon:") {
		t.Error("expected 'lon:' in location view output")
	}
	if !strings.Contains(out, "lat:") {
		t.Error("expected 'lat:' in location view output")
	}
}

func TestRenderLocationViewSingleEvent(t *testing.T) {
	events := []api.Event{
		{Latitude: 40.4168, Longitude: -3.7038},
	}
	out := RenderLocationView(events, 40, 10)
	if out == "" {
		t.Fatal("single-event location view should produce output")
	}
}

// ─── CoOccurrence ─────────────────────────────────────────────────────────────

func TestRenderCoOccurrenceEmpty(t *testing.T) {
	out := RenderCoOccurrenceView([]api.Convoy{}, []api.Correlation{}, 80)
	if out == "" {
		t.Fatal("RenderCoOccurrenceView with empty data should return non-empty string")
	}
	if !strings.Contains(out, "no convoy data") {
		t.Errorf("expected 'no convoy data', got: %q", out)
	}
	if !strings.Contains(out, "no correlation data") {
		t.Errorf("expected 'no correlation data', got: %q", out)
	}
}

func TestRenderCoOccurrenceWithData(t *testing.T) {
	convoys := []api.Convoy{
		{UserA: "alice", UserB: "bob", CoCount: 15, AvgDistanceM: 42.5, AvgTimeGapS: 30},
	}
	correlations := []api.Correlation{
		{UserA: "alice", UserB: "charlie", VectorSimilarity: 0.85, GraphScore: 0.7, CombinedScore: 0.78, CorrelationType: "behavioral"},
	}
	out := RenderCoOccurrenceView(convoys, correlations, 80)
	if out == "" {
		t.Fatal("expected non-empty co-occurrence view output")
	}
	if !strings.Contains(out, "Convoy Pairs") {
		t.Error("expected 'Convoy Pairs' section header")
	}
	if !strings.Contains(out, "alice") {
		t.Error("expected alice in convoy output")
	}
	if !strings.Contains(out, "bob") {
		t.Error("expected bob in convoy output")
	}
	if !strings.Contains(out, "↔") {
		t.Error("expected ↔ separator in convoy output")
	}
	if !strings.Contains(out, "Identity Correlations") {
		t.Error("expected 'Identity Correlations' section header")
	}
	if !strings.Contains(out, "charlie") {
		t.Error("expected charlie in correlations output")
	}
	if !strings.Contains(out, "behavioral") {
		t.Error("expected correlation type in output")
	}
}

func TestRenderCoOccurrenceConvoyOnly(t *testing.T) {
	convoys := []api.Convoy{
		{UserA: "x", UserB: "y", CoCount: 5, AvgDistanceM: 100},
	}
	out := RenderCoOccurrenceView(convoys, []api.Correlation{}, 80)
	if !strings.Contains(out, "no correlation data") {
		t.Error("expected 'no correlation data' when correlations are empty")
	}
	if !strings.Contains(out, "x") || !strings.Contains(out, "y") {
		t.Error("expected convoy users in output")
	}
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

// stripANSI removes ANSI escape sequences from a string for plain-text assertions.
func stripANSI(s string) string {
	var b strings.Builder
	inEsc := false
	for _, ch := range s {
		if ch == '\x1b' {
			inEsc = true
			continue
		}
		if inEsc {
			if ch == 'm' {
				inEsc = false
			}
			continue
		}
		b.WriteRune(ch)
	}
	return b.String()
}

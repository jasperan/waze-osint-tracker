package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestClientStats(t *testing.T) {
	want := Stats{
		TotalEvents: 42,
		UniqueUsers: 7,
		FirstEvent:  "2024-01-01T00:00:00",
		LastEvent:   "2024-06-01T12:00:00",
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/stats" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(want)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	got, err := c.Stats()
	if err != nil {
		t.Fatalf("Stats() error: %v", err)
	}
	if got.TotalEvents != want.TotalEvents {
		t.Errorf("TotalEvents: got %d, want %d", got.TotalEvents, want.TotalEvents)
	}
	if got.UniqueUsers != want.UniqueUsers {
		t.Errorf("UniqueUsers: got %d, want %d", got.UniqueUsers, want.UniqueUsers)
	}
	if got.FirstEvent != want.FirstEvent {
		t.Errorf("FirstEvent: got %q, want %q", got.FirstEvent, want.FirstEvent)
	}
	if got.LastEvent != want.LastEvent {
		t.Errorf("LastEvent: got %q, want %q", got.LastEvent, want.LastEvent)
	}
}

func TestClientUsers(t *testing.T) {
	want := []UserSummary{
		{Username: "alice", Count: 10},
		{Username: "bob", Count: 5},
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/users" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(want)
	}))
	defer srv.Close()

	c := NewClient(srv.URL)
	got, err := c.Users()
	if err != nil {
		t.Fatalf("Users() error: %v", err)
	}
	if len(got) != len(want) {
		t.Fatalf("Users() returned %d entries, want %d", len(got), len(want))
	}
	for i, u := range got {
		if u.Username != want[i].Username {
			t.Errorf("Users()[%d].Username: got %q, want %q", i, u.Username, want[i].Username)
		}
		if u.Count != want[i].Count {
			t.Errorf("Users()[%d].Count: got %d, want %d", i, u.Count, want[i].Count)
		}
	}
}

func TestClientHealthCheck(t *testing.T) {
	// Healthy: server returns valid Stats JSON.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(Stats{TotalEvents: 1})
	}))
	defer srv.Close()

	healthy := NewClient(srv.URL)
	if !healthy.HealthCheck() {
		t.Error("HealthCheck() returned false for a healthy server")
	}

	// Unhealthy: point at a URL that will be refused.
	unhealthy := NewClient("http://127.0.0.1:1")
	if unhealthy.HealthCheck() {
		t.Error("HealthCheck() returned true for an unreachable server")
	}
}

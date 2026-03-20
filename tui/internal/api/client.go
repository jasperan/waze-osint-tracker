package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// Client is a minimal HTTP client for the Waze Flask API.
type Client struct {
	baseURL    string
	httpClient *http.Client
}

// NewClient creates a Client pointed at the given base URL.
func NewClient(baseURL string) *Client {
	return &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// get is a convenience wrapper for JSON GET requests.
func (c *Client) get(path string, out interface{}) error {
	resp, err := c.httpClient.Get(fmt.Sprintf("%s%s", c.baseURL, path))
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d from %s", resp.StatusCode, path)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

// StatsResponse mirrors /api/stats JSON.
type StatsResponse struct {
	TotalEvents int            `json:"total_events"`
	TotalUsers  int            `json:"total_users"`
	ByType      map[string]int `json:"by_type"`
	ByRegion    map[string]int `json:"by_region"`
}

// GetStats fetches aggregate stats from the API.
func (c *Client) GetStats() (*StatsResponse, error) {
	var s StatsResponse
	if err := c.get("/api/stats", &s); err != nil {
		return nil, err
	}
	return &s, nil
}

// EventRow mirrors a single event in /api/recent.
type EventRow struct {
	ID        int     `json:"id"`
	Username  string  `json:"username"`
	EventType string  `json:"event_type"`
	Subtype   string  `json:"subtype"`
	Lat       float64 `json:"lat"`
	Lon       float64 `json:"lon"`
	City      string  `json:"city"`
	Region    string  `json:"region"`
	Timestamp string  `json:"timestamp"`
}

// GetRecent fetches recent events from the API.
func (c *Client) GetRecent(limit int) ([]EventRow, error) {
	var rows []EventRow
	if err := c.get(fmt.Sprintf("/api/recent?limit=%d", limit), &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

// UserSummary mirrors a row in /api/users.
type UserSummary struct {
	Username   string  `json:"username"`
	EventCount int     `json:"event_count"`
	LastSeen   string  `json:"last_seen"`
	TopType    string  `json:"top_type"`
	AvgLat     float64 `json:"avg_lat"`
	AvgLon     float64 `json:"avg_lon"`
}

// GetUsers fetches the user summary list.
func (c *Client) GetUsers(limit int) ([]UserSummary, error) {
	var users []UserSummary
	if err := c.get(fmt.Sprintf("/api/users?limit=%d", limit), &users); err != nil {
		return nil, err
	}
	return users, nil
}

// PrivacyScore mirrors /api/privacy-score/<username>.
type PrivacyScore struct {
	Username   string             `json:"username"`
	TotalScore float64            `json:"total_score"`
	SubScores  map[string]float64 `json:"sub_scores"`
	Risk       string             `json:"risk"`
}

// GetPrivacyScore fetches a user's privacy score.
func (c *Client) GetPrivacyScore(username string) (*PrivacyScore, error) {
	var ps PrivacyScore
	if err := c.get(fmt.Sprintf("/api/privacy-score/%s", username), &ps); err != nil {
		return nil, err
	}
	return &ps, nil
}

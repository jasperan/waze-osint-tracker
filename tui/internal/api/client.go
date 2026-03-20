package api

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Client is an HTTP + SSE client for the Waze Flask API.
type Client struct {
	Base string
	HTTP *http.Client
}

// NewClient creates a Client pointed at the given base URL (trailing slash trimmed).
func NewClient(baseURL string) *Client {
	return &Client{
		Base: strings.TrimRight(baseURL, "/"),
		HTTP: &http.Client{Timeout: 10 * time.Second},
	}
}

// HealthCheck returns true if the API is reachable.
func (c *Client) HealthCheck() bool {
	_, err := c.Stats()
	return err == nil
}

// get performs a GET request and JSON-decodes a 200 response into result.
func (c *Client) get(path string, result interface{}) error {
	resp, err := c.HTTP.Get(c.Base + path)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d from %s", resp.StatusCode, path)
	}
	return json.NewDecoder(resp.Body).Decode(result)
}

// Stats fetches aggregate stats from GET /api/stats.
func (c *Client) Stats() (*Stats, error) {
	var s Stats
	if err := c.get("/api/stats", &s); err != nil {
		return nil, err
	}
	return &s, nil
}

// Events fetches events with optional filters from GET /api/events.
func (c *Client) Events(f EventFilter) ([]Event, error) {
	q := url.Values{}
	if f.Type != "" {
		q.Set("type", f.Type)
	}
	if f.SubType != "" {
		q.Set("subtype", f.SubType)
	}
	if f.Since != 0 {
		q.Set("since", fmt.Sprintf("%d", f.Since))
	}
	if f.From != "" {
		q.Set("from", f.From)
	}
	if f.To != "" {
		q.Set("to", f.To)
	}
	if f.User != "" {
		q.Set("user", f.User)
	}
	if f.Region != "" {
		q.Set("region", f.Region)
	}
	if f.Limit != 0 {
		q.Set("limit", fmt.Sprintf("%d", f.Limit))
	}
	path := "/api/events"
	if len(q) > 0 {
		path += "?" + q.Encode()
	}
	var events []Event
	if err := c.get(path, &events); err != nil {
		return nil, err
	}
	return events, nil
}

// Users fetches the user summary list from GET /api/users.
func (c *Client) Users() ([]UserSummary, error) {
	var users []UserSummary
	if err := c.get("/api/users", &users); err != nil {
		return nil, err
	}
	return users, nil
}

// UserProfile fetches a single user profile from GET /api/user/<username>.
func (c *Client) UserProfile(username string) (*UserProfile, error) {
	var p UserProfile
	if err := c.get("/api/user/"+url.PathEscape(username), &p); err != nil {
		return nil, err
	}
	return &p, nil
}

// Trips fetches reconstructed trips for a user from GET /api/trips/<username>.
func (c *Client) Trips(username string) (*TripResponse, error) {
	var t TripResponse
	if err := c.get("/api/trips/"+url.PathEscape(username), &t); err != nil {
		return nil, err
	}
	return &t, nil
}

// PrivacyScore fetches a user's privacy risk score from GET /api/privacy-score/<username>.
func (c *Client) PrivacyScore(username string) (*PrivacyScore, error) {
	var ps PrivacyScore
	if err := c.get("/api/privacy-score/"+url.PathEscape(username), &ps); err != nil {
		return nil, err
	}
	return &ps, nil
}

// PrivacyLeaderboard fetches the top exposed users from GET /api/privacy-score/leaderboard.
func (c *Client) PrivacyLeaderboard() ([]LeaderboardEntry, error) {
	var lb []LeaderboardEntry
	if err := c.get("/api/privacy-score/leaderboard", &lb); err != nil {
		return nil, err
	}
	return lb, nil
}

// IntelProfile fetches the intelligence profile for a user from GET /api/intel/user/<username>.
func (c *Client) IntelProfile(username string) (*IntelProfile, error) {
	var ip IntelProfile
	if err := c.get("/api/intel/user/"+url.PathEscape(username), &ip); err != nil {
		return nil, err
	}
	return &ip, nil
}

// Correlations fetches cross-user behavioural correlations from GET /api/intel/correlations.
func (c *Client) Correlations() ([]Correlation, error) {
	var corrs []Correlation
	if err := c.get("/api/intel/correlations", &corrs); err != nil {
		return nil, err
	}
	return corrs, nil
}

// Convoys fetches co-movement convoy pairs from GET /api/intel/convoys.
func (c *Client) Convoys() ([]Convoy, error) {
	var convoys []Convoy
	if err := c.get("/api/intel/convoys", &convoys); err != nil {
		return nil, err
	}
	return convoys, nil
}

// Status fetches the collector daemon status from GET /api/status.
func (c *Client) Status() (*CollectorStatus, error) {
	var cs CollectorStatus
	if err := c.get("/api/status", &cs); err != nil {
		return nil, err
	}
	return &cs, nil
}

// RecentActivity fetches recent events from GET /api/recent-activity.
func (c *Client) RecentActivity() ([]Event, error) {
	var events []Event
	if err := c.get("/api/recent-activity", &events); err != nil {
		return nil, err
	}
	return events, nil
}

// Heatmap fetches heatmap data points from GET /api/heatmap.
func (c *Client) Heatmap() ([]HeatmapPoint, error) {
	var pts []HeatmapPoint
	if err := c.get("/api/heatmap", &pts); err != nil {
		return nil, err
	}
	return pts, nil
}

// StreamEvents opens the SSE stream at /api/stream and returns a channel of messages.
// It reconnects with exponential backoff on disconnect. The goroutine exits when ctx is cancelled.
func (c *Client) StreamEvents(ctx context.Context) (<-chan SSEMessage, error) {
	// Use a separate client with no timeout for SSE.
	sseClient := &http.Client{}
	ch := make(chan SSEMessage, 100)

	go func() {
		defer close(ch)
		backoff := time.Second
		const maxBackoff = 30 * time.Second

		for {
			if ctx.Err() != nil {
				return
			}
			err := func() error {
				req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.Base+"/api/stream", nil)
				if err != nil {
					return err
				}
				req.Header.Set("Accept", "text/event-stream")

				resp, err := sseClient.Do(req)
				if err != nil {
					return err
				}
				defer resp.Body.Close()

				// Reset backoff on successful connection.
				backoff = time.Second

				scanner := bufio.NewScanner(resp.Body)
				for scanner.Scan() {
					line := scanner.Text()
					if !strings.HasPrefix(line, "data: ") {
						continue
					}
					payload := strings.TrimPrefix(line, "data: ")
					var msg SSEMessage
					if err := json.Unmarshal([]byte(payload), &msg); err != nil {
						continue
					}
					select {
					case ch <- msg:
					case <-ctx.Done():
						return ctx.Err()
					}
				}
				return scanner.Err()
			}()

			if ctx.Err() != nil {
				return
			}
			_ = err // reconnect regardless of error type

			select {
			case <-ctx.Done():
				return
			case <-time.After(backoff):
			}
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
		}
	}()

	return ch, nil
}

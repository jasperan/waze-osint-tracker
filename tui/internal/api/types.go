package api

// Stats mirrors GET /api/stats.
type Stats struct {
	TotalEvents int    `json:"total_events"`
	UniqueUsers int    `json:"unique_users"`
	FirstEvent  string `json:"first_event"`
	LastEvent   string `json:"last_event"`
}

// Event mirrors a single event from GET /api/events and SSE streams.
// SSE frames use report_type instead of type, so both fields are present.
type Event struct {
	ID         string  `json:"id"`
	Username   string  `json:"username"`
	Latitude   float64 `json:"latitude"`
	Longitude  float64 `json:"longitude"`
	Timestamp  string  `json:"timestamp"`
	Type       string  `json:"type"`
	ReportType string  `json:"report_type,omitempty"`
	Subtype    string  `json:"subtype"`
	Region     string  `json:"region"`
	GridCell   string  `json:"grid_cell"`
}

// EffectiveType returns the non-empty type field, preferring Type over ReportType.
func (e *Event) EffectiveType() string {
	if e.Type != "" {
		return e.Type
	}
	return e.ReportType
}

// SSEMessage wraps a server-sent event frame.
type SSEMessage struct {
	Type    string  `json:"type"`
	Message string  `json:"message,omitempty"`
	Event   *Event  `json:"event,omitempty"`
}

// UserSummary mirrors a row in GET /api/users.
type UserSummary struct {
	Username string `json:"username"`
	Count    int    `json:"count"`
}

// Location is a simple lat/lon pair.
type Location struct {
	Lat float64 `json:"lat"`
	Lon float64 `json:"lon"`
}

// UserProfile mirrors GET /api/user/<username>.
type UserProfile struct {
	Username      string         `json:"username"`
	EventCount    int            `json:"event_count"`
	FirstSeen     string         `json:"first_seen"`
	LastSeen      string         `json:"last_seen"`
	TypeBreakdown map[string]int `json:"type_breakdown"`
	CenterLocation *Location     `json:"center_location"`
	Events        []Event        `json:"events"`
}

// EventFilter holds query parameters for event list requests (not serialised to JSON).
type EventFilter struct {
	Type    string
	SubType string
	Since   int
	From    string
	To      string
	User    string
	Region  string
	Limit   int
}

// TripResponse mirrors GET /api/trips/<username>.
type TripResponse struct {
	Username string      `json:"username"`
	Trips    []Trip      `json:"trips"`
	Summary  TripSummary `json:"summary"`
	Error    string      `json:"error,omitempty"`
}

// Trip is a single reconstructed trip.
type Trip struct {
	TripType    string  `json:"trip_type"`
	StartTime   string  `json:"start_time"`
	EndTime     string  `json:"end_time"`
	DistanceKm  float64 `json:"distance_km"`
	DurationMin float64 `json:"duration_min"`
	EventCount  int     `json:"event_count"`
	Regularity  float64 `json:"regularity,omitempty"`
	StartArea   string  `json:"start_area,omitempty"`
	EndArea     string  `json:"end_area,omitempty"`
}

// TripSummary aggregates trip statistics for a user.
type TripSummary struct {
	TotalTrips    int     `json:"total_trips"`
	AvgDailyTrips float64 `json:"avg_daily_trips"`
	InferredHome  string  `json:"inferred_home,omitempty"`
	InferredWork  string  `json:"inferred_work,omitempty"`
}

// PrivacyScore mirrors GET /api/privacy-score/<username>.
type PrivacyScore struct {
	Username          string  `json:"username"`
	EventCount        int     `json:"event_count"`
	OverallScore      int     `json:"overall_score"`
	RiskLevel         string  `json:"risk_level"`
	HomeExposure      float64 `json:"home_exposure"`
	WorkExposure      float64 `json:"work_exposure"`
	ScheduleScore     float64 `json:"schedule_score"`
	RouteScore        float64 `json:"route_score"`
	IdentityScore     float64 `json:"identity_score"`
	TrackabilityScore float64 `json:"trackability_score"`
	Error             string  `json:"error,omitempty"`
}

// LeaderboardEntry is a privacy-score leaderboard row (no error/event_count).
type LeaderboardEntry struct {
	Username          string  `json:"username"`
	OverallScore      int     `json:"overall_score"`
	RiskLevel         string  `json:"risk_level"`
	HomeExposure      float64 `json:"home_exposure"`
	WorkExposure      float64 `json:"work_exposure"`
	ScheduleScore     float64 `json:"schedule_score"`
	RouteScore        float64 `json:"route_score"`
	IdentityScore     float64 `json:"identity_score"`
	TrackabilityScore float64 `json:"trackability_score"`
}

// IntelProfile mirrors GET /api/intel/user/<username>.
type IntelProfile struct {
	Username       string          `json:"username"`
	Region         string          `json:"region"`
	EventCount     int             `json:"event_count"`
	CentroidLat    float64         `json:"centroid_lat"`
	CentroidLon    float64         `json:"centroid_lon"`
	GeoSpreadKm    float64         `json:"geo_spread_km"`
	HourHistogram  interface{}     `json:"hour_histogram"`
	DowHistogram   interface{}     `json:"dow_histogram"`
	TypeDistribution interface{}   `json:"type_distribution"`
	CadenceStats   interface{}     `json:"cadence_stats"`
	Dossier        interface{}     `json:"dossier"`
	Routines       []Routine       `json:"routines"`
	CoOccurrences  []CoOccurrence  `json:"co_occurrences"`
	Error          string          `json:"error,omitempty"`
}

// Routine is an inferred behavioural routine (home, work, commute, etc.).
type Routine struct {
	RoutineType   string  `json:"routine_type"`
	Latitude      float64 `json:"latitude"`
	Longitude     float64 `json:"longitude"`
	Confidence    float64 `json:"confidence"`
	EvidenceCount int     `json:"evidence_count"`
}

// CoOccurrence records how often two users appeared near each other.
type CoOccurrence struct {
	Partner      string  `json:"partner"`
	CoCount      int     `json:"co_count"`
	AvgDistanceM float64 `json:"avg_distance_m"`
	AvgTimeGapS  float64 `json:"avg_time_gap_s,omitempty"`
}

// Correlation mirrors a row in GET /api/intel/correlations.
type Correlation struct {
	UserA            string  `json:"user_a"`
	UserB            string  `json:"user_b"`
	VectorSimilarity float64 `json:"vector_similarity"`
	GraphScore       float64 `json:"graph_score"`
	CombinedScore    float64 `json:"combined_score"`
	CorrelationType  string  `json:"correlation_type"`
	Explanation      string  `json:"explanation"`
}

// Convoy mirrors a row in GET /api/intel/convoys.
type Convoy struct {
	UserA        string  `json:"user_a"`
	UserB        string  `json:"user_b"`
	CoCount      int     `json:"co_count"`
	AvgDistanceM float64 `json:"avg_distance_m"`
	AvgTimeGapS  float64 `json:"avg_time_gap_s"`
}

// CollectorStatus mirrors GET /api/status.
type CollectorStatus struct {
	Status  string `json:"status"`
	Message string `json:"message,omitempty"`
}

// HeatmapPoint is [lat, lon, weight] as returned by the heatmap endpoint.
type HeatmapPoint [3]float64

// TypeBreakdown mirrors a row in GET /api/types.
type TypeBreakdown struct {
	Type     string         `json:"type"`
	Count    int            `json:"count"`
	Subtypes []SubtypeCount `json:"subtypes"`
}

// SubtypeCount is one entry in a TypeBreakdown's subtype list.
type SubtypeCount struct {
	Subtype string `json:"subtype"`
	Count   int    `json:"count"`
}

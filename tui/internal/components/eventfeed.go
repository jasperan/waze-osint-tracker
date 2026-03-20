package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// EventFeed is a scrolling, filterable list of events.
type EventFeed struct {
	Events    []api.Event
	MaxEvents int
	ScrollPos int
	Filter    string
}

// NewEventFeed creates an EventFeed with the given cap (default 500 if <= 0).
func NewEventFeed(maxEvents int) *EventFeed {
	if maxEvents <= 0 {
		maxEvents = 500
	}
	return &EventFeed{MaxEvents: maxEvents}
}

// Push prepends an event (newest first) and caps at MaxEvents.
func (f *EventFeed) Push(e api.Event) {
	f.Events = append([]api.Event{e}, f.Events...)
	if len(f.Events) > f.MaxEvents {
		f.Events = f.Events[:f.MaxEvents]
	}
}

// View renders the visible portion of the feed.
func (f *EventFeed) View(width, height int) string {
	dimStyle := lipgloss.NewStyle().Foreground(theme.DimColor)
	mutedStyle := lipgloss.NewStyle().Foreground(theme.MutedColor)

	// Collect filtered events.
	var filtered []api.Event
	for _, e := range f.Events {
		if f.Filter == "" || strings.EqualFold(e.EffectiveType(), f.Filter) {
			filtered = append(filtered, e)
		}
	}

	if len(filtered) == 0 {
		return mutedStyle.Render("Waiting for events...")
	}

	// Apply scroll window.
	start := f.ScrollPos
	if start < 0 {
		start = 0
	}
	if start >= len(filtered) {
		start = len(filtered) - 1
	}
	end := start + height
	if end > len(filtered) {
		end = len(filtered)
	}
	visible := filtered[start:end]

	var sb strings.Builder
	for i, e := range visible {
		// Timestamp: chars [11:19] of ISO string.
		ts := ""
		if len(e.Timestamp) > 10 {
			ts = e.Timestamp[11:]
			if len(ts) > 8 {
				ts = ts[:8]
			}
		}

		evType := e.EffectiveType()
		color := theme.EventTypeColor(evType)
		typeStyle := lipgloss.NewStyle().Foreground(color)

		// Dot + type name (padded to 12 chars).
		typePadded := fmt.Sprintf("%-12s", evType)
		if len(typePadded) > 12 {
			typePadded = typePadded[:12]
		}

		// Username (padded/truncated to 15 chars).
		username := e.Username
		if username == "" {
			username = "anonymous"
		}
		if len(username) > 15 {
			username = username[:15]
		}
		userPadded := fmt.Sprintf("%-15s", username)

		// Coordinates.
		coords := fmt.Sprintf("%.4f,%.4f", e.Latitude, e.Longitude)

		line := dimStyle.Render(ts) + " " +
			typeStyle.Render("●") + " " +
			typeStyle.Render(typePadded) + " " +
			userPadded + " " +
			dimStyle.Render(coords)

		if i > 0 {
			sb.WriteString("\n")
		}
		sb.WriteString(line)
	}
	return sb.String()
}

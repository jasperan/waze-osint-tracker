package screens

import (
	"fmt"
	"math"
	"strconv"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// NavigateMsg is sent when the splash screen wants to transition to another screen.
// The parent app.go handles this type.
type NavigateMsg struct {
	Screen int
}

// connectionCheckMsg carries the result of an API health check.
type connectionCheckMsg struct {
	ok    bool
	stats *api.Stats
}

// fadeTickMsg drives the banner fade-in animation at ~60fps.
type fadeTickMsg struct{}

// SplashModel is the initial loading/splash screen.
type SplashModel struct {
	client    *api.Client
	connected bool
	stats     *api.Stats
	opacity   float64 // 0→1 for banner fade animation
	retries   int
	err       string
}

// NewSplash returns an initialised SplashModel.
func NewSplash(client *api.Client) SplashModel {
	return SplashModel{
		client:  client,
		opacity: 0,
	}
}

// Init fires the connection check and the first animation tick simultaneously.
func (m SplashModel) Init() tea.Cmd {
	return tea.Batch(checkConnection(m.client), fadeTick())
}

// Update handles messages and returns the updated model plus any follow-up commands.
func (m SplashModel) Update(msg tea.Msg) (SplashModel, tea.Cmd) {
	switch msg := msg.(type) {

	case fadeTickMsg:
		if m.opacity < 1.0 {
			m.opacity = math.Min(m.opacity+0.02, 1.0)
			return m, fadeTick()
		}

	case connectionCheckMsg:
		if msg.ok {
			m.connected = true
			m.stats = msg.stats
			m.err = ""
		} else {
			m.retries++
			m.err = fmt.Sprintf("connection failed (attempt %d/10)", m.retries)
			if m.retries < 10 {
				return m, retryAfter(m.client, 3*time.Second)
			}
			m.err = "could not reach API after 10 attempts — press r to retry"
		}

	case tea.KeyMsg:
		switch msg.String() {
		case "enter":
			if m.connected {
				return m, func() tea.Msg { return NavigateMsg{Screen: 1} }
			}
		case "r":
			m.retries = 0
			m.err = ""
			return m, checkConnection(m.client)
		case "s":
			m.err = "Starting server..."
		}
	}

	return m, nil
}

// View renders the splash screen centred within the given terminal dimensions.
func (m SplashModel) View(width, height int) string {
	banner := `██╗    ██╗ █████╗ ███████╗███████╗
██║    ██║██╔══██╗╚══███╔╝██╔════╝
██║ █╗ ██║███████║  ███╔╝ █████╗
╚██╗██╔╝ ██╔══██║ ███╔╝  ██╔══╝
 ╚███╔╝  ██║  ██║███████╗███████╗
  ╚══╝   ╚═╝  ╚═╝╚══════╝╚══════╝`

	// Interpolate banner color from Surface to Primary based on opacity.
	bannerColor := lerpColor(string(theme.Surface), string(theme.Primary), m.opacity)
	bannerStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(bannerColor))
	coloredBanner := bannerStyle.Render(banner)

	// Subtitle.
	subtitleStyle := lipgloss.NewStyle().
		Bold(true).
		Foreground(theme.Primary)
	subtitle := subtitleStyle.Render("OSINT TRACKER")

	// Connection status dot and label.
	var dotColor lipgloss.Color
	var statusLabel string
	switch {
	case m.connected:
		dotColor = theme.Success
		statusLabel = "connected"
	case m.retries > 0 && !m.connected:
		dotColor = theme.Error
		statusLabel = "connection failed"
	default:
		dotColor = theme.DimColor
		statusLabel = "checking..."
	}
	dotStyle := lipgloss.NewStyle().Foreground(dotColor)
	statusLine := dotStyle.Render(theme.StatusDot) + " " +
		lipgloss.NewStyle().Foreground(theme.TextColor).Render(statusLabel)

	// Stats line.
	var statsLine string
	if m.connected && m.stats != nil {
		statsLine = lipgloss.NewStyle().Foreground(theme.DimColor).
			Render(fmt.Sprintf("Events: %d   Users: %d", m.stats.TotalEvents, m.stats.UniqueUsers))
	} else {
		statsLine = lipgloss.NewStyle().Foreground(theme.DimColor).Render("Events: —   Users: —")
	}

	// Error line (empty string if no error).
	var errLine string
	if m.err != "" {
		errLine = lipgloss.NewStyle().Foreground(theme.Error).Render(m.err)
	}

	// Key hints.
	var hints string
	switch {
	case m.connected:
		hints = lipgloss.NewStyle().Foreground(theme.DimColor).
			Render("[ enter ] open dashboard   [ q ] quit")
	case m.retries >= 10:
		hints = lipgloss.NewStyle().Foreground(theme.DimColor).
			Render("[ r ] retry   [ s ] start server   [ q ] quit")
	default:
		hints = lipgloss.NewStyle().Foreground(theme.DimColor).
			Render("[ r ] retry   [ s ] start server   [ q ] quit")
	}

	// Stack all lines vertically with spacing.
	parts := []string{
		coloredBanner,
		"",
		subtitle,
		"",
		statusLine,
		statsLine,
	}
	if errLine != "" {
		parts = append(parts, errLine)
	}
	parts = append(parts, "", hints)

	content := strings.Join(parts, "\n")

	// Centre everything in the terminal.
	return lipgloss.Place(
		width, height,
		lipgloss.Center, lipgloss.Center,
		content,
	)
}

// ── commands ─────────────────────────────────────────────────────────────────

func checkConnection(client *api.Client) tea.Cmd {
	return func() tea.Msg {
		stats, err := client.Stats()
		if err != nil {
			return connectionCheckMsg{ok: false}
		}
		return connectionCheckMsg{ok: true, stats: stats}
	}
}

func retryAfter(client *api.Client, d time.Duration) tea.Cmd {
	return tea.Tick(d, func(_ time.Time) tea.Msg {
		stats, err := client.Stats()
		if err != nil {
			return connectionCheckMsg{ok: false}
		}
		return connectionCheckMsg{ok: true, stats: stats}
	})
}

func fadeTick() tea.Cmd {
	// ~60fps: 16.6ms per frame
	return tea.Tick(time.Second/60, func(_ time.Time) tea.Msg {
		return fadeTickMsg{}
	})
}

// ── color helpers ─────────────────────────────────────────────────────────────

// lerpColor interpolates between two hex colors (#RRGGBB) by t ∈ [0,1].
func lerpColor(from, to string, t float64) string {
	t = math.Max(0, math.Min(1, t))
	r1, g1, b1 := hexToRGB(from)
	r2, g2, b2 := hexToRGB(to)
	r := int(float64(r1) + (float64(r2)-float64(r1))*t)
	g := int(float64(g1) + (float64(g2)-float64(g1))*t)
	b := int(float64(b1) + (float64(b2)-float64(b1))*t)
	return fmt.Sprintf("#%02x%02x%02x", r, g, b)
}

// hexToRGB parses a #RRGGBB hex string into its R, G, B components.
func hexToRGB(hex string) (int, int, int) {
	hex = strings.TrimPrefix(hex, "#")
	if len(hex) != 6 {
		return 0, 0, 0
	}
	r, _ := strconv.ParseInt(hex[0:2], 16, 32)
	g, _ := strconv.ParseInt(hex[2:4], 16, 32)
	b, _ := strconv.ParseInt(hex[4:6], 16, 32)
	return int(r), int(g), int(b)
}

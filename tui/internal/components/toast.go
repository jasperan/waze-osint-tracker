package components

import (
	"github.com/charmbracelet/lipgloss"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// Toast represents a non-blocking notification overlay.
type Toast struct {
	Level   string // "info", "success", "error"
	Message string
}

// NewToast creates a new Toast with the given level and message.
func NewToast(level, message string) *Toast {
	return &Toast{Level: level, Message: message}
}

// RenderToast renders a toast with colored border based on level.
// success = theme.Success border, error = theme.Error border, default = theme.Primary border
func RenderToast(t *Toast, width int) string {
	if t == nil {
		return ""
	}
	var borderColor lipgloss.Color
	switch t.Level {
	case "success":
		borderColor = theme.Success
	case "error":
		borderColor = theme.Error
	default:
		borderColor = theme.Primary
	}

	style := theme.Panel.
		Copy().
		BorderForeground(borderColor).
		Width(width - 2)

	return style.Render(t.Message)
}

// OverlayToast appends toast below content using lipgloss.JoinVertical.
func OverlayToast(content string, t *Toast, width int) string {
	if t == nil {
		return content
	}
	return lipgloss.JoinVertical(lipgloss.Left, content, RenderToast(t, width))
}

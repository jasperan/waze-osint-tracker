package components

import (
	"fmt"
	"sort"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/jasperan/waze-madrid-logger/tui/internal/api"
	"github.com/jasperan/waze-madrid-logger/tui/internal/theme"
)

// SortMode enumerates user list sort orders.
type SortMode int

const (
	SortByEvents SortMode = iota
	SortByName
	SortByRisk
)

func (s SortMode) String() string {
	switch s {
	case SortByEvents:
		return "events↓"
	case SortByName:
		return "name↑"
	case SortByRisk:
		return "risk↓"
	default:
		return "events↓"
	}
}

// UserList is a sortable, filterable list of users.
type UserList struct {
	Users    []api.UserSummary
	Selected int
	ScrollPos int
	Filter   string
	Sort     SortMode
}

// NewUserList returns an initialised UserList.
func NewUserList() *UserList {
	return &UserList{}
}

// SetUsers stores users and re-sorts.
func (ul *UserList) SetUsers(users []api.UserSummary) {
	ul.Users = make([]api.UserSummary, len(users))
	copy(ul.Users, users)
	ul.sortUsers()
}

// sortUsers sorts in-place according to ul.Sort.
func (ul *UserList) sortUsers() {
	switch ul.Sort {
	case SortByName:
		sort.Slice(ul.Users, func(i, j int) bool {
			return ul.Users[i].Username < ul.Users[j].Username
		})
	default: // SortByEvents, SortByRisk both fall back to event count desc
		sort.Slice(ul.Users, func(i, j int) bool {
			return ul.Users[i].Count > ul.Users[j].Count
		})
	}
}

// CycleSort advances the sort mode and re-sorts.
func (ul *UserList) CycleSort() {
	ul.Sort = (ul.Sort + 1) % 3
	ul.sortUsers()
	ul.Selected = 0
	ul.ScrollPos = 0
}

// Filtered returns users whose username contains Filter (case-insensitive).
func (ul *UserList) Filtered() []api.UserSummary {
	if ul.Filter == "" {
		return ul.Users
	}
	lower := strings.ToLower(ul.Filter)
	out := make([]api.UserSummary, 0, len(ul.Users))
	for _, u := range ul.Users {
		if strings.Contains(strings.ToLower(u.Username), lower) {
			out = append(out, u)
		}
	}
	return out
}

// SelectedUser returns the currently highlighted user, or nil.
func (ul *UserList) SelectedUser() *api.UserSummary {
	filtered := ul.Filtered()
	if len(filtered) == 0 || ul.Selected < 0 || ul.Selected >= len(filtered) {
		return nil
	}
	u := filtered[ul.Selected]
	return &u
}

// MoveUp moves the cursor up by one row.
func (ul *UserList) MoveUp() {
	if ul.Selected > 0 {
		ul.Selected--
		if ul.Selected < ul.ScrollPos {
			ul.ScrollPos = ul.Selected
		}
	}
}

// MoveDown moves the cursor down by one row.
func (ul *UserList) MoveDown(visibleRows int) {
	filtered := ul.Filtered()
	if ul.Selected < len(filtered)-1 {
		ul.Selected++
		if ul.Selected >= ul.ScrollPos+visibleRows {
			ul.ScrollPos = ul.Selected - visibleRows + 1
		}
	}
}

// View renders the user list into a string of the given dimensions.
func (ul *UserList) View(width, height int) string {
	filtered := ul.Filtered()

	selectedStyle := lipgloss.NewStyle().Foreground(theme.Primary).Bold(true)
	normalStyle := lipgloss.NewStyle().Foreground(theme.TextColor)
	dimStyle := lipgloss.NewStyle().Foreground(theme.DimColor)
	countStyle := lipgloss.NewStyle().Foreground(theme.DimColor)

	// Reserve 2 lines for footer
	listHeight := height - 2
	if listHeight < 1 {
		listHeight = 1
	}

	if len(filtered) == 0 {
		placeholder := dimStyle.Render("  no users")
		footer := dimStyle.Render(fmt.Sprintf("sort: %s", ul.Sort))
		return placeholder + "\n" + footer
	}

	// Clamp scroll
	if ul.ScrollPos > len(filtered)-listHeight {
		ul.ScrollPos = len(filtered) - listHeight
	}
	if ul.ScrollPos < 0 {
		ul.ScrollPos = 0
	}

	end := ul.ScrollPos + listHeight
	if end > len(filtered) {
		end = len(filtered)
	}

	var sb strings.Builder
	for i := ul.ScrollPos; i < end; i++ {
		u := filtered[i]
		name := u.Username
		// Truncate name to fit
		maxName := width - 12
		if maxName < 4 {
			maxName = 4
		}
		if len(name) > maxName {
			name = name[:maxName-1] + "…"
		}
		countStr := fmt.Sprintf("%6d", u.Count)
		if i == ul.Selected {
			line := fmt.Sprintf("▸ %-*s %s", maxName, name, countStyle.Render(countStr))
			sb.WriteString(selectedStyle.Render(line))
		} else {
			line := fmt.Sprintf("  %-*s %s", maxName, name, countStyle.Render(countStr))
			sb.WriteString(normalStyle.Render(line))
		}
		sb.WriteByte('\n')
	}

	// Footer: sort label + filter display
	footer := dimStyle.Render(fmt.Sprintf("sort:%s", ul.Sort))
	if ul.Filter != "" {
		footer += "  " + dimStyle.Render(fmt.Sprintf("filter:%s", ul.Filter))
	}
	sb.WriteString(footer)

	return sb.String()
}

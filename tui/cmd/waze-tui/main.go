package main

import (
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/jasperan/waze-madrid-logger/tui/internal/app"
)

var version = "dev"

func main() {
	apiURL := "http://localhost:5000"
	for i, arg := range os.Args[1:] {
		if arg == "--api" && i+2 <= len(os.Args[1:]) {
			apiURL = os.Args[i+2]
		}
	}

	a := app.New(apiURL, version)
	p := tea.NewProgram(a, tea.WithAltScreen(), tea.WithMouseCellMotion())
	if _, err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

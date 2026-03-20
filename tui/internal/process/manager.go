package process

import (
	"os/exec"
	"sync"
)

// Manager tracks child processes launched by the TUI (collector, web server).
type Manager struct {
	mu   sync.Mutex
	procs []*exec.Cmd
}

// NewManager creates a new process Manager.
func NewManager() *Manager {
	return &Manager{}
}

// Add registers a started command so it can be stopped later.
func (m *Manager) Add(cmd *exec.Cmd) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.procs = append(m.procs, cmd)
}

// StopAll sends SIGKILL to every tracked process.
func (m *Manager) StopAll() {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, cmd := range m.procs {
		if cmd.Process != nil {
			_ = cmd.Process.Kill()
		}
	}
	m.procs = nil
}

package process

import (
	"fmt"
	"os"
	"os/exec"
	"sync"
	"syscall"
	"time"
)

// proc holds a named subprocess.
type proc struct {
	Name string
	Cmd  *exec.Cmd
}

// Manager tracks child processes launched by the TUI (collector, web server).
type Manager struct {
	mu    sync.Mutex
	procs map[string]*proc
}

// NewManager creates a new process Manager.
func NewManager() *Manager {
	return &Manager{
		procs: make(map[string]*proc),
	}
}

// StartFlask spawns `waze web --port <port>` as a background subprocess.
// It is a no-op if Flask is already running.
func (m *Manager) StartFlask(port string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, ok := m.procs["flask"]; ok {
		return nil
	}

	cmd := exec.Command("waze", "web", "--port", port)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start flask: %w", err)
	}

	p := &proc{Name: "flask", Cmd: cmd}
	m.procs["flask"] = p

	go func() {
		_ = cmd.Wait()
	}()

	return nil
}

// StartCollector spawns `waze collect --regions region1 region2 ...` as a
// background subprocess. It is a no-op if the collector is already running.
func (m *Manager) StartCollector(regions []string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, ok := m.procs["collector"]; ok {
		return nil
	}

	args := []string{"collect"}
	if len(regions) > 0 {
		args = append(args, "--regions")
		args = append(args, regions...)
	}

	cmd := exec.Command("waze", args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start collector: %w", err)
	}

	p := &proc{Name: "collector", Cmd: cmd}
	m.procs["collector"] = p

	go func() {
		_ = cmd.Wait()
	}()

	return nil
}

// IsRunning returns true if the named process exists and has not yet exited.
// Cleans up the map entry if the process has already exited.
func (m *Manager) IsRunning(name string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()

	p, ok := m.procs[name]
	if !ok {
		return false
	}

	if p.Cmd.ProcessState != nil {
		// Process has exited; clean up.
		delete(m.procs, name)
		return false
	}

	return true
}

// Stop sends SIGTERM to the named process group, waits up to 5 s, then
// falls back to SIGKILL. Removes the entry from the map when done.
func (m *Manager) Stop(name string) {
	m.mu.Lock()
	p, ok := m.procs[name]
	if !ok {
		m.mu.Unlock()
		return
	}
	delete(m.procs, name)
	m.mu.Unlock()

	if p.Cmd.Process == nil {
		return
	}

	pgid := -p.Cmd.Process.Pid

	// SIGTERM to the whole process group.
	_ = syscall.Kill(pgid, syscall.SIGTERM)

	done := make(chan struct{})
	go func() {
		_ = p.Cmd.Wait()
		close(done)
	}()

	select {
	case <-done:
		// Exited cleanly within 5 s.
	case <-time.After(5 * time.Second):
		// Force-kill the group.
		_ = syscall.Kill(pgid, syscall.SIGKILL)
		<-done
	}
}

// StopAll stops every tracked process.
func (m *Manager) StopAll() {
	m.mu.Lock()
	names := make([]string, 0, len(m.procs))
	for name := range m.procs {
		names = append(names, name)
	}
	m.mu.Unlock()

	for _, name := range names {
		m.Stop(name)
	}
}

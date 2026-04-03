package process

import (
	"os/exec"
	"reflect"
	"testing"
)

func TestStartCollectorUsesRepeatedRegionFlags(t *testing.T) {
	m := NewManager()
	var gotName string
	var gotArgs []string

	originalExec := execCommand
	execCommand = func(name string, args ...string) *exec.Cmd {
		gotName = name
		gotArgs = append([]string{}, args...)
		return exec.Command("sh", "-c", "sleep 0.01")
	}
	defer func() { execCommand = originalExec }()

	if err := m.StartCollector([]string{"europe", "asia"}); err != nil {
		t.Fatalf("StartCollector() error: %v", err)
	}

	wantArgs := []string{"collect", "--region", "europe", "--region", "asia"}
	if gotName != "waze" {
		t.Fatalf("expected command name waze, got %q", gotName)
	}
	if !reflect.DeepEqual(gotArgs, wantArgs) {
		t.Fatalf("expected args %v, got %v", wantArgs, gotArgs)
	}
}

func TestStartFlaskPassesPortFlag(t *testing.T) {
	m := NewManager()
	var gotName string
	var gotArgs []string

	originalExec := execCommand
	execCommand = func(name string, args ...string) *exec.Cmd {
		gotName = name
		gotArgs = append([]string{}, args...)
		return exec.Command("sh", "-c", "sleep 0.01")
	}
	defer func() { execCommand = originalExec }()

	if err := m.StartFlask("5007"); err != nil {
		t.Fatalf("StartFlask() error: %v", err)
	}

	wantArgs := []string{"web", "--port", "5007"}
	if gotName != "waze" {
		t.Fatalf("expected command name waze, got %q", gotName)
	}
	if !reflect.DeepEqual(gotArgs, wantArgs) {
		t.Fatalf("expected args %v, got %v", wantArgs, gotArgs)
	}
}

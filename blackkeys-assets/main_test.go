package main

import (
	"context"
	"errors"
	"net"
	"os"
	"testing"
	"time"

	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/handling"
	assetsv1 "github.com/plaza-san-miguel/blackkeys/blackkeys-assets/gen/assetsv1"
	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/samples"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/status"
)

func serveOnEphemeral(t *testing.T) *grpc.ClientConn {
	t.Helper()

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}

	server, err := newServer(context.Background(), func(context.Context) (*handling.BrandsService, error) {
		return handling.NewBrandsServiceFromSnapshot(samples.BrandsParquet)
	})
	if err != nil {
		t.Fatalf("newServer: %v", err)
	}
	go func() { _ = server.Serve(listener) }()
	t.Cleanup(server.Stop)

	conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })

	return conn
}

func testContext(t *testing.T) context.Context {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	t.Cleanup(cancel)
	return ctx
}

func TestListReturnsEmbeddedSnapshot(t *testing.T) {
	client := assetsv1.NewBrandsClient(serveOnEphemeral(t))

	response, err := client.List(testContext(t), &assetsv1.ListRequest{})
	if err != nil {
		t.Fatalf("List: %v", err)
	}

	if got := len(response.GetBrands()); got != 318 {
		t.Fatalf("got %d brands, want 318", got)
	}
}

func TestHealthReportsServing(t *testing.T) {
	client := healthpb.NewHealthClient(serveOnEphemeral(t))

	for _, service := range []string{"", assetsv1.Brands_ServiceDesc.ServiceName} {
		response, err := client.Check(testContext(t), &healthpb.HealthCheckRequest{Service: service})
		if err != nil {
			t.Fatalf("Check(%q): %v", service, err)
		}
		if response.GetStatus() != healthpb.HealthCheckResponse_SERVING {
			t.Errorf("Check(%q): got %v, want SERVING", service, response.GetStatus())
		}
	}
}

func TestHealthRejectsUnregisteredService(t *testing.T) {
	client := healthpb.NewHealthClient(serveOnEphemeral(t))

	_, err := client.Check(testContext(t), &healthpb.HealthCheckRequest{Service: "nope"})
	if status.Code(err) != codes.NotFound {
		t.Errorf("got %v, want NotFound", status.Code(err))
	}
}

func TestListenAddr(t *testing.T) {
	for _, tc := range []struct {
		name, host, port, want string
	}{
		{"defaults", "", "", "0.0.0.0:50051"},
		{"environment", "127.0.0.1", "50555", "127.0.0.1:50555"},
		{"host only", "127.0.0.1", "", "127.0.0.1:50051"},
		{"port only", "", "50555", "0.0.0.0:50555"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv("GRPC_ADDRESS", tc.host)
			t.Setenv("GRPC_PORT", tc.port)
			if got := listenAddr(); got != tc.want {
				t.Errorf("got %q, want %q", got, tc.want)
			}
		})
	}
}

func TestStartNodeExporterUsesConfiguredPath(t *testing.T) {
	var gotName string
	var gotArgs []string
	t.Setenv("NODE_EXPORTER_PATH", "/test/node_exporter")

	err := startNodeExporter(func(name string, args ...string) error {
		gotName = name
		gotArgs = args
		return nil
	})
	if err != nil {
		t.Fatalf("startNodeExporter: %v", err)
	}
	if gotName != "/test/node_exporter" {
		t.Errorf("got command %q, want %q", gotName, "/test/node_exporter")
	}
	if len(gotArgs) != 1 || gotArgs[0] != "--web.listen-address=:9100" {
		t.Errorf("got arguments %q, want [--web.listen-address=:9100]", gotArgs)
	}
}

func TestServeSkipsNodeExporterWhenPathIsUnsetOrEmpty(t *testing.T) {
	for _, tc := range []struct {
		name  string
		unset bool
	}{
		{"unset", true},
		{"empty", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if tc.unset {
				value, wasSet := os.LookupEnv("NODE_EXPORTER_PATH")
				if err := os.Unsetenv("NODE_EXPORTER_PATH"); err != nil {
					t.Fatalf("unset NODE_EXPORTER_PATH: %v", err)
				}
				t.Cleanup(func() {
					if wasSet {
						_ = os.Setenv("NODE_EXPORTER_PATH", value)
						return
					}
					_ = os.Unsetenv("NODE_EXPORTER_PATH")
				})
			} else {
				t.Setenv("NODE_EXPORTER_PATH", "")
			}

			listener, err := net.Listen("tcp", "127.0.0.1:0")
			if err != nil {
				t.Fatalf("listen: %v", err)
			}
			if err := listener.Close(); err != nil {
				t.Fatalf("close listener: %v", err)
			}

			started := false
			err = serve(
				context.Background(),
				func(context.Context) (*handling.BrandsService, error) {
					return handling.NewBrandsServiceFromSnapshot(samples.BrandsParquet)
				},
				func(string, string) (net.Listener, error) {
					return listener, nil
				},
				func(string, ...string) error {
					started = true
					return nil
				},
			)
			if !errors.Is(err, net.ErrClosed) {
				t.Errorf("got %v, want closed-listener error", err)
			}
			if started {
				t.Error("started node exporter with no configured path")
			}
		})
	}
}

func TestServeClosesListenerWhenNodeExporterFails(t *testing.T) {
	t.Setenv("NODE_EXPORTER_PATH", "/test/node_exporter")

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}

	startErr := errors.New("node exporter unavailable")
	events := make([]string, 0, 3)
	err = serve(
		context.Background(),
		func(context.Context) (*handling.BrandsService, error) {
			events = append(events, "stores")
			return handling.NewBrandsServiceFromSnapshot(samples.BrandsParquet)
		},
		func(string, string) (net.Listener, error) {
			events = append(events, "listener")
			return listener, nil
		},
		func(string, ...string) error {
			events = append(events, "exporter")
			return startErr
		},
	)
	if !errors.Is(err, startErr) {
		t.Errorf("got %v, want wrapped %v", err, startErr)
	}
	if got, want := len(events), 3; got != want {
		t.Fatalf("got events %v, want stores, listener, exporter", events)
	}
	for i, want := range []string{"stores", "listener", "exporter"} {
		if events[i] != want {
			t.Errorf("event %d: got %q, want %q", i, events[i], want)
		}
	}
	if err := listener.Close(); !errors.Is(err, net.ErrClosed) {
		t.Errorf("listener was not closed: %v", err)
	}
}

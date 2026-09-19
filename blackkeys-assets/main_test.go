package main

import (
	"context"
	"net"
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

	server, err := newServer(context.Background(), func(context.Context) (*handling.StoresService, error) {
		return handling.NewStoresServiceFromSnapshot(samples.StoresParquet)
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
	client := assetsv1.NewStoresClient(serveOnEphemeral(t))

	response, err := client.List(testContext(t), &assetsv1.ListRequest{})
	if err != nil {
		t.Fatalf("List: %v", err)
	}

	if got := len(response.GetStores()); got != 318 {
		t.Fatalf("got %d stores, want 318", got)
	}
	if got := response.GetStores()[0].GetName(); got != "ADIDAS" {
		t.Errorf("got first store %q, want %q", got, "ADIDAS")
	}
}

func TestHealthReportsServing(t *testing.T) {
	client := healthpb.NewHealthClient(serveOnEphemeral(t))

	for _, service := range []string{"", assetsv1.Stores_ServiceDesc.ServiceName} {
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

package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"

	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/handling"
	assetsv1 "github.com/plaza-san-miguel/blackkeys/blackkeys-assets/gen/assetsv1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
)

type processStarter func(string, ...string) error

func listenAddr() string {
	host := os.Getenv("GRPC_ADDRESS")
	if host == "" {
		host = "0.0.0.0"
	}
	port := os.Getenv("GRPC_PORT")
	if port == "" {
		port = "50051"
	}
	return net.JoinHostPort(host, port)
}

func newServer(ctx context.Context, newBrandsService func(context.Context) (*handling.BrandsService, error)) (*grpc.Server, error) {
	service, err := newBrandsService(ctx)
	if err != nil {
		return nil, err
	}

	server := grpc.NewServer()
	assetsv1.RegisterBrandsServer(server, service)

	checker := health.NewServer()
	healthpb.RegisterHealthServer(server, checker)
	checker.SetServingStatus("", healthpb.HealthCheckResponse_SERVING)
	checker.SetServingStatus(assetsv1.Brands_ServiceDesc.ServiceName, healthpb.HealthCheckResponse_SERVING)

	return server, nil
}

func startProcess(name string, args ...string) error {
	return exec.Command(name, args...).Start()
}

func startNodeExporter(start processStarter) error {
	path := os.Getenv("NODE_EXPORTER_PATH")
	if path == "" {
		return nil
	}
	return start(path, "--web.listen-address=:9100")
}

func serve(
	ctx context.Context,
	newBrandsService func(context.Context) (*handling.BrandsService, error),
	listen func(string, string) (net.Listener, error),
	start processStarter,
) error {
	server, err := newServer(ctx, newBrandsService)
	if err != nil {
		return err
	}

	listener, err := listen("tcp", listenAddr())
	if err != nil {
		return err
	}

	if err := startNodeExporter(start); err != nil {
		if closeErr := listener.Close(); closeErr != nil {
			return fmt.Errorf("start node exporter: %w; close listener: %v", err, closeErr)
		}
		return fmt.Errorf("start node exporter: %w", err)
	}

	return server.Serve(listener)
}

func main() {
	if err := serve(context.Background(), handling.NewBrandsService, net.Listen, startProcess); err != nil {
		log.Fatal(err)
	}
}

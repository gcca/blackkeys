package main

import (
	"context"
	"log"
	"net"
	"os"

	"github.com/plaza-san-miguel/blackkeys/blackkeys-assets/blackkeys/handling"
	assetsv1 "github.com/plaza-san-miguel/blackkeys/blackkeys-assets/gen/assetsv1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
)

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

func newServer(ctx context.Context, newStoresService func(context.Context) (*handling.StoresService, error)) (*grpc.Server, error) {
	service, err := newStoresService(ctx)
	if err != nil {
		return nil, err
	}

	server := grpc.NewServer()
	assetsv1.RegisterStoresServer(server, service)

	checker := health.NewServer()
	healthpb.RegisterHealthServer(server, checker)
	checker.SetServingStatus("", healthpb.HealthCheckResponse_SERVING)
	checker.SetServingStatus(assetsv1.Stores_ServiceDesc.ServiceName, healthpb.HealthCheckResponse_SERVING)

	return server, nil
}

func main() {
	server, err := newServer(context.Background(), handling.NewStoresService)
	if err != nil {
		log.Fatal(err)
	}

	listener, err := net.Listen("tcp", listenAddr())
	if err != nil {
		log.Fatal(err)
	}

	if err := server.Serve(listener); err != nil {
		log.Fatal(err)
	}
}

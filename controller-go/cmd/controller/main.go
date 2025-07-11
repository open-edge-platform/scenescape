package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	"scenescape-controller/internal/controller"
	"scenescape-controller/internal/config"
)

func main() {
	// Command line flags
	var (
		rewriteBadTime      = flag.Bool("rewriteBadTime", false, "Rewrite bad time stamps instead of discarding data")
		rewriteAllTime      = flag.Bool("rewriteAllTime", false, "Rewrite all time stamps")
		maxLag              = flag.Float64("maxlag", 1.0, "Maximum amount of lag in seconds")
		broker              = flag.String("broker", "broker.scenescape.intel.com:1883", "MQTT broker hostname:port")
		brokerAuth          = flag.String("brokerauth", "/run/secrets/controller.auth", "MQTT authentication file")
		restURL             = flag.String("resturl", "https://web.scenescape.intel.com/api/v1", "REST server URL")
		restAuth            = flag.String("restauth", "", "REST authentication (required)")
		rootCert            = flag.String("rootcert", "/run/secrets/certs/scenescape-ca.pem", "Path to CA certificate")
		clientCert          = flag.String("cert", "", "Path to client certificate")
		ntpServer           = flag.String("ntp", "", "NTP server (default: use MQTT broker)")
		trackerConfigFile   = flag.String("tracker_config_file", "config/tracker-config.json", "Tracker configuration JSON file")
		schemaFile          = flag.String("schema_file", "config/metadata.schema.json", "Metadata schema JSON file")
		visibilityTopic     = flag.String("visibility_topic", "regulated", "Visibility topic (unregulated|regulated|none)")
		verbose             = flag.Bool("verbose", false, "Enable verbose logging")
	)
	
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: %s [OPTIONS]\n\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "SceneScape Controller - Go Implementation\n\n")
		fmt.Fprintf(os.Stderr, "Options:\n")
		flag.PrintDefaults()
	}
	
	flag.Parse()
	
	// Validate required arguments
	if *restAuth == "" {
		fmt.Fprintf(os.Stderr, "Error: --restauth is required\n")
		flag.Usage()
		os.Exit(1)
	}
	
	// Create configuration
	cfg := &config.Config{
		RewriteBadTime:     *rewriteBadTime,
		RewriteAllTime:     *rewriteAllTime,
		MaxLag:             *maxLag,
		Broker:             *broker,
		BrokerAuth:         *brokerAuth,
		RestURL:            *restURL,
		RestAuth:           *restAuth,
		RootCert:           *rootCert,
		ClientCert:         *clientCert,
		NTPServer:          *ntpServer,
		TrackerConfigFile:  *trackerConfigFile,
		SchemaFile:         *schemaFile,
		VisibilityTopic:    *visibilityTopic,
		Verbose:            *verbose,
	}
	
	// Create scene controller
	sceneController, err := controller.NewSceneController(cfg)
	if err != nil {
		log.Fatalf("Failed to create scene controller: %v", err)
	}
	
	// Set up signal handling for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	
	// Start the controller in a goroutine
	errChan := make(chan error, 1)
	go func() {
		fmt.Println("SceneScape Controller (Go) starting...")
		errChan <- sceneController.Run()
	}()
	
	// Wait for either an error or shutdown signal
	select {
	case err := <-errChan:
		if err != nil {
			log.Fatalf("Controller error: %v", err)
		}
	case sig := <-sigChan:
		fmt.Printf("\nReceived signal %s, shutting down...\n", sig)
		if err := sceneController.Shutdown(); err != nil {
			log.Fatalf("Shutdown error: %v", err)
		}
	}
}

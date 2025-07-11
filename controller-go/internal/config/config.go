package config

// Config holds all configuration parameters for the scene controller
type Config struct {
	// Time handling
	RewriteBadTime bool
	RewriteAllTime bool
	MaxLag         float64
	
	// MQTT configuration
	Broker     string
	BrokerAuth string
	
	// REST API configuration
	RestURL  string
	RestAuth string
	
	// Security certificates
	RootCert   string
	ClientCert string
	
	// Network time
	NTPServer string
	
	// Configuration files
	TrackerConfigFile string
	SchemaFile        string
	
	// Publishing options
	VisibilityTopic string
	
	// Logging
	Verbose bool
}

// TrackerConfig holds timing parameters for object tracking
type TrackerConfig struct {
	MaxUnreliableTime           float64 `json:"max_unreliable_time"`
	NonMeasurementTimeDynamic   float64 `json:"non_measurement_time_dynamic"`
	NonMeasurementTimeStatic    float64 `json:"non_measurement_time_static"`
	MaxUnreliableFrames         int     `json:"max_unreliable_frames"`
	NonMeasurementFramesDynamic int     `json:"non_measurement_frames_dynamic"`
	NonMeasurementFramesStatic  int     `json:"non_measurement_frames_static"`
	BaselineFrameRate           float64 `json:"baseline_frame_rate"`
}

// Validate checks if the configuration is valid
func (c *Config) Validate() error {
	if c.RestAuth == "" {
		return fmt.Errorf("REST authentication is required")
	}
	
	if c.MaxLag <= 0 {
		return fmt.Errorf("MaxLag must be positive")
	}
	
	validVisibilityTopics := map[string]bool{
		"unregulated": true,
		"regulated":   true,
		"none":        true,
	}
	
	if !validVisibilityTopics[c.VisibilityTopic] {
		return fmt.Errorf("invalid visibility topic: %s", c.VisibilityTopic)
	}
	
	return nil
}

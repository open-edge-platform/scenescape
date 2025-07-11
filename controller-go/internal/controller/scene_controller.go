package controller

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/pkg/errors"
	"github.com/sirupsen/logrus"

	"scenescape-controller/internal/config"
	"scenescape-controller/internal/scene"
	"scenescape-controller/internal/cache"
	"scenescape-controller/pkg/geometry"
	"scenescape-controller/pkg/timestamp"
)

const (
	avgFrames = 100
)

// SceneController is the main controller that orchestrates scene processing
type SceneController struct {
	config     *config.Config
	logger     *logrus.Logger
	ctx        context.Context
	cancel     context.CancelFunc
	wg         sync.WaitGroup
	
	// MQTT client
	mqttClient mqtt.Client
	
	// Cache manager
	cacheManager *cache.Manager
	
	// Scenes and tracking
	scenes        map[string]*scene.Scene
	scenesMutex   sync.RWMutex
	regulateCache map[string]map[string]float64
	
	// Time synchronization
	timeOffset     float64
	lastTimeSync   time.Time
	
	// Tracker configuration
	trackerConfig map[string]interface{}
}

// NewSceneController creates a new scene controller instance
func NewSceneController(cfg *config.Config) (*SceneController, error) {
	if err := cfg.Validate(); err != nil {
		return nil, errors.Wrap(err, "invalid configuration")
	}
	
	ctx, cancel := context.WithCancel(context.Background())
	
	logger := logrus.New()
	if cfg.Verbose {
		logger.SetLevel(logrus.DebugLevel)
	}
	
	sc := &SceneController{
		config:        cfg,
		logger:        logger,
		ctx:           ctx,
		cancel:        cancel,
		scenes:        make(map[string]*scene.Scene),
		regulateCache: make(map[string]map[string]float64),
		trackerConfig: make(map[string]interface{}),
	}
	
	// Load tracker configuration
	if err := sc.loadTrackerConfig(); err != nil {
		return nil, errors.Wrap(err, "failed to load tracker config")
	}
	
	// Initialize cache manager
	cacheManager, err := cache.NewManager(cfg.RestURL, cfg.RestAuth, cfg.RootCert, sc.trackerConfig)
	if err != nil {
		return nil, errors.Wrap(err, "failed to create cache manager")
	}
	sc.cacheManager = cacheManager
	
	// Initialize MQTT client
	if err := sc.initMQTT(); err != nil {
		return nil, errors.Wrap(err, "failed to initialize MQTT")
	}
	
	return sc, nil
}

// Run starts the scene controller and blocks until shutdown
func (sc *SceneController) Run() error {
	sc.logger.Info("Starting SceneScape Controller (Go)")
	
	// Connect to MQTT broker
	if token := sc.mqttClient.Connect(); token.Wait() && token.Error() != nil {
		return errors.Wrap(token.Error(), "failed to connect to MQTT broker")
	}
	
	sc.logger.Infof("Publishing camera visibility info on %s topic", sc.config.VisibilityTopic)
	
	// Start background tasks
	sc.wg.Add(2)
	go sc.timeSync()
	go sc.cacheRefresh()
	
	// Wait for shutdown
	<-sc.ctx.Done()
	return nil
}

// Shutdown gracefully shuts down the controller
func (sc *SceneController) Shutdown() error {
	sc.logger.Info("Shutting down SceneScape Controller")
	
	// Cancel context to stop background tasks
	sc.cancel()
	
	// Disconnect MQTT client
	sc.mqttClient.Disconnect(250)
	
	// Wait for background tasks to complete
	sc.wg.Wait()
	
	sc.logger.Info("Shutdown complete")
	return nil
}

// loadTrackerConfig loads tracker configuration from file
func (sc *SceneController) loadTrackerConfig() error {
	if sc.config.TrackerConfigFile == "" {
		return nil
	}
	
	data, err := os.ReadFile(sc.config.TrackerConfigFile)
	if err != nil {
		return errors.Wrap(err, "failed to read tracker config file")
	}
	
	var trackerCfg config.TrackerConfig
	if err := json.Unmarshal(data, &trackerCfg); err != nil {
		return errors.Wrap(err, "failed to parse tracker config")
	}
	
	// Convert frame-based parameters to time-based
	if trackerCfg.BaselineFrameRate > 0 {
		sc.trackerConfig["max_unreliable_time"] = float64(trackerCfg.MaxUnreliableFrames) / trackerCfg.BaselineFrameRate
		sc.trackerConfig["non_measurement_time_dynamic"] = float64(trackerCfg.NonMeasurementFramesDynamic) / trackerCfg.BaselineFrameRate
		sc.trackerConfig["non_measurement_time_static"] = float64(trackerCfg.NonMeasurementFramesStatic) / trackerCfg.BaselineFrameRate
	}
	
	return nil
}

// initMQTT initializes the MQTT client and sets up callbacks
func (sc *SceneController) initMQTT() error {
	opts := mqtt.NewClientOptions()
	opts.AddBroker(fmt.Sprintf("tcp://%s", sc.config.Broker))
	opts.SetClientID("scenescape-controller-go")
	opts.SetKeepAlive(60 * time.Second)
	opts.SetDefaultPublishHandler(sc.onMessage)
	opts.SetConnectionLostHandler(sc.onConnectionLost)
	opts.SetOnConnectHandler(sc.onConnect)
	
	// Set authentication if provided
	if sc.config.BrokerAuth != "" {
		if err := sc.setMQTTAuth(opts); err != nil {
			return errors.Wrap(err, "failed to set MQTT authentication")
		}
	}
	
	// Set TLS if certificates are provided
	if sc.config.RootCert != "" {
		if err := sc.setMQTTTLS(opts); err != nil {
			return errors.Wrap(err, "failed to set MQTT TLS")
		}
	}
	
	sc.mqttClient = mqtt.NewClient(opts)
	return nil
}

// onConnect is called when MQTT connection is established
func (sc *SceneController) onConnect(client mqtt.Client) {
	sc.logger.Info("Connected to MQTT broker")
	
	// Subscribe to relevant topics
	topics := map[string]byte{
		"scenescape/data/camera/+":     0,
		"scenescape/external/+/+":      0,
		"scenescape/data/sensor/+":     0,
		"scenescape/cmd/scene/update/+": 0,
	}
	
	for topic, qos := range topics {
		if token := client.Subscribe(topic, qos, sc.onMessage); token.Wait() && token.Error() != nil {
			sc.logger.Errorf("Failed to subscribe to %s: %v", topic, token.Error())
		} else {
			sc.logger.Debugf("Subscribed to %s", topic)
		}
	}
	
	// Refresh scenes from cache
	go func() {
		if err := sc.cacheManager.RefreshScenes(); err != nil {
			sc.logger.Errorf("Failed to refresh scenes: %v", err)
		}
	}()
}

// onConnectionLost is called when MQTT connection is lost
func (sc *SceneController) onConnectionLost(client mqtt.Client, err error) {
	sc.logger.Errorf("MQTT connection lost: %v", err)
}

// onMessage handles incoming MQTT messages
func (sc *SceneController) onMessage(client mqtt.Client, msg mqtt.Message) {
	topic := msg.Topic()
	payload := string(msg.Payload())
	
	sc.logger.Debugf("Received message on topic %s", topic)
	
	// Parse JSON payload
	var data map[string]interface{}
	if err := json.Unmarshal([]byte(payload), &data); err != nil {
		sc.logger.Errorf("Failed to parse JSON message: %v", err)
		return
	}
	
	// Route message based on topic
	switch {
	case strings.Contains(topic, "/data/camera/"):
		sc.handleCameraData(topic, data)
	case strings.Contains(topic, "/external/"):
		sc.handleExternalData(topic, data)
	case strings.Contains(topic, "/data/sensor/"):
		sc.handleSensorData(topic, data)
	case strings.Contains(topic, "/cmd/scene/update/"):
		sc.handleSceneUpdate(topic, data)
	default:
		sc.logger.Debugf("Unhandled topic: %s", topic)
	}
}

// handleCameraData processes camera detection data
func (sc *SceneController) handleCameraData(topic string, data map[string]interface{}) {
	// Extract camera ID from topic
	parts := strings.Split(topic, "/")
	if len(parts) < 4 {
		sc.logger.Errorf("Invalid camera topic format: %s", topic)
		return
	}
	cameraID := parts[len(parts)-1]
	
	// Find scene for this camera
	scene := sc.cacheManager.GetSceneByCameraID(cameraID)
	if scene == nil {
		sc.logger.Errorf("No scene found for camera: %s", cameraID)
		return
	}
	
	// Process detections
	if objects, ok := data["objects"].(map[string]interface{}); ok {
		if timestampStr, ok := data["timestamp"].(string); ok {
			timestamp, err := timestamp.ParseISO(timestampStr)
			if err != nil {
				sc.logger.Errorf("Failed to parse timestamp: %v", err)
				return
			}
			
			adjustedTime := sc.adjustTime(timestamp)
			
			for objectType, detections := range objects {
				if detArray, ok := detections.([]interface{}); ok && len(detArray) > 0 {
					scene.ProcessDetections(cameraID, detArray, adjustedTime, objectType)
					
					// Get tracked objects and publish
					trackedObjects := scene.GetTrackedObjects(objectType)
					sc.publishDetections(scene, trackedObjects, adjustedTime, objectType, data, cameraID)
				}
			}
		}
	}
}

// handleExternalData processes external sensor data
func (sc *SceneController) handleExternalData(topic string, data map[string]interface{}) {
	// Extract scene ID and object type from topic
	parts := strings.Split(topic, "/")
	if len(parts) < 4 {
		sc.logger.Errorf("Invalid external topic format: %s", topic)
		return
	}
	
	sceneID := parts[len(parts)-2]
	objectType := parts[len(parts)-1]
	
	scene := sc.cacheManager.GetSceneByUID(sceneID)
	if scene == nil {
		sc.logger.Errorf("No scene found for ID: %s", sceneID)
		return
	}
	
	if timestampStr, ok := data["timestamp"].(string); ok {
		timestamp, err := timestamp.ParseISO(timestampStr)
		if err != nil {
			sc.logger.Errorf("Failed to parse timestamp: %v", err)
			return
		}
		
		adjustedTime := sc.adjustTime(timestamp)
		
		// Process external detection
		detections := []interface{}{data}
		scene.ProcessDetections("external", detections, adjustedTime, objectType)
		
		trackedObjects := scene.GetTrackedObjects(objectType)
		sc.publishDetections(scene, trackedObjects, adjustedTime, objectType, data, "external")
	}
}

// handleSensorData processes sensor data
func (sc *SceneController) handleSensorData(topic string, data map[string]interface{}) {
	// TODO: Implement sensor data handling
	sc.logger.Debugf("Sensor data received on topic %s", topic)
}

// handleSceneUpdate processes scene update commands
func (sc *SceneController) handleSceneUpdate(topic string, data map[string]interface{}) {
	sc.logger.Debug("Scene update command received, refreshing cache")
	go func() {
		if err := sc.cacheManager.RefreshScenes(); err != nil {
			sc.logger.Errorf("Failed to refresh scenes: %v", err)
		}
	}()
}

// publishDetections publishes detection data to various topics
func (sc *SceneController) publishDetections(scene *scene.Scene, objects []scene.MovingObject, timestamp float64, objectType string, data map[string]interface{}, cameraID string) {
	sc.publishSceneDetections(scene, objects, objectType, data)
	sc.publishRegulatedDetections(scene, objects, objectType, data, cameraID)
	sc.publishRegionDetections(scene, objects, objectType, data)
}

// publishSceneDetections publishes to scene-level topics
func (sc *SceneController) publishSceneDetections(scene *scene.Scene, objects []scene.MovingObject, objectType string, data map[string]interface{}) {
	// Build detections list
	pubData := make(map[string]interface{})
	for k, v := range data {
		pubData[k] = v
	}
	
	// TODO: Implement buildDetectionsList equivalent
	pubData["objects"] = objects // Placeholder
	
	objectCount := len(objects)
	cacheID := scene.GetName() + "/" + objectType
	
	// Check if we should publish
	lastCount, exists := scene.GetLastPubCount(cacheID)
	if objectCount > 0 || (exists && lastCount > 0) {
		// Add processing time if available
		if debugStart, ok := data["debug_hmo_start_time"].(float64); ok {
			pubData["debug_hmo_processing_time"] = timestamp.GetEpochTime() - debugStart
		}
		
		topic := fmt.Sprintf("scenescape/data/scene/%s/%s", scene.GetUID(), objectType)
		sc.publishJSON(topic, pubData)
		
		scene.SetLastPubCount(cacheID, objectCount)
	}
}

// publishRegulatedDetections publishes to regulated topics with rate limiting
func (sc *SceneController) publishRegulatedDetections(scene *scene.Scene, objects []scene.MovingObject, objectType string, data map[string]interface{}, cameraID string) {
	if sc.config.VisibilityTopic != "regulated" {
		return
	}
	
	now := timestamp.GetEpochTime()
	maxDelay := 1.0 // 1 second max delay
	
	regulateKey := scene.GetName() + "/" + cameraID + "/" + objectType
	sceneName := scene.GetName()
	
	if sc.regulateCache[sceneName] == nil {
		sc.regulateCache[sceneName] = make(map[string]float64)
	}
	
	lastTime, exists := sc.regulateCache[sceneName][regulateKey]
	if !exists || (now-lastTime) >= maxDelay {
		regulatedData := make(map[string]interface{})
		for k, v := range data {
			regulatedData[k] = v
		}
		
		// TODO: Implement buildDetectionsList equivalent
		regulatedData["objects"] = objects // Placeholder
		
		topic := fmt.Sprintf("scenescape/regulated/scene/%s", scene.GetUID())
		sc.publishJSON(topic, regulatedData)
		
		sc.regulateCache[sceneName][regulateKey] = now
	}
}

// publishRegionDetections publishes region and tripwire events
func (sc *SceneController) publishRegionDetections(scene *scene.Scene, objects []scene.MovingObject, objectType string, data map[string]interface{}) {
	// TODO: Implement region and tripwire event detection
	// This would involve checking objects against regions and tripwires
	sc.logger.Debug("Region detection publishing not yet implemented")
}

// publishJSON publishes a JSON message to the specified topic
func (sc *SceneController) publishJSON(topic string, data interface{}) {
	jsonData, err := json.Marshal(data)
	if err != nil {
		sc.logger.Errorf("Failed to marshal JSON: %v", err)
		return
	}
	
	token := sc.mqttClient.Publish(topic, 0, false, jsonData)
	if token.Wait() && token.Error() != nil {
		sc.logger.Errorf("Failed to publish to %s: %v", topic, token.Error())
	}
}

// adjustTime adjusts timestamp based on configuration
func (sc *SceneController) adjustTime(ts float64) float64 {
	if sc.config.RewriteAllTime {
		return timestamp.GetEpochTime()
	}
	
	adjusted := ts + sc.timeOffset
	now := timestamp.GetEpochTime()
	
	if sc.config.RewriteBadTime && math.Abs(adjusted-now) > sc.config.MaxLag {
		return now
	}
	
	return adjusted
}

// timeSync runs time synchronization in background
func (sc *SceneController) timeSync() {
	defer sc.wg.Done()
	
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	
	for {
		select {
		case <-sc.ctx.Done():
			return
		case <-ticker.C:
			// TODO: Implement NTP time synchronization
			// For now, just reset offset to 0
			sc.timeOffset = 0.0
			sc.lastTimeSync = time.Now()
		}
	}
}

// cacheRefresh runs cache refresh in background
func (sc *SceneController) cacheRefresh() {
	defer sc.wg.Done()
	
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()
	
	for {
		select {
		case <-sc.ctx.Done():
			return
		case <-ticker.C:
			if err := sc.cacheManager.RefreshScenes(); err != nil {
				sc.logger.Errorf("Failed to refresh scenes: %v", err)
			}
		}
	}
}

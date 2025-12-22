#include "config/cli.hpp"
#include "config/config_validation.hpp"

#include <CLI/CLI.hpp>
#include <cstdlib>
#include <stdexcept>
#include <string>

namespace config_args {

Config load_config_from_argv(int argc, char* argv[]) {
    // Stage A: capture paths only (allow extras to avoid early help exits)
    std::string config_path;
    std::string schema_path;
    try {
        CLI::App pathApp{"Tracker config path capture"};
        pathApp.allow_extras(true);
        pathApp.add_option("--config", config_path, "Service configuration JSON path");
        pathApp.add_option("--schema", schema_path, "Optional JSON Schema for config");
        pathApp.parse(argc, argv);
    } catch (const CLI::ParseError&) {
        // Defer to full app below for help and error handling
    }

    if (config_path.empty()) {
        throw std::runtime_error("Service configuration path is required. Use --config <path> [--schema <path>]");
    }

    // Load base config with optional schema validation (default or provided)
    Config cfg = service_config::load_and_validate_from_paths(config_path, schema_path);

    // Stage B: full app with env + CLI overlays; handle help/errors here
    CLI::App app{"Tracker Service"};
    std::string dummy_config, dummy_schema;
    register_dummy_config_options(app, dummy_config, dummy_schema);
    register_cli_options(app, cfg, /*with_env_names=*/true);
    try {
        app.parse(argc, argv);
    } catch (const CLI::ParseError &e) {
        std::exit(app.exit(e));
    }

    return cfg;
}

} // namespace config_args

// ---- CLI options registration implementation ----

// Persistent holders for transient CLI option values to ensure lifetime across parse
static std::string s_mqtt_host;
static int s_mqtt_port = -1;
static bool s_no_ssl_verify_flag = false;

void register_cli_options(CLI::App &app, Config &cfg, bool with_env_names) {
    // MQTT
    auto *mqttServer = app.add_option("--mqtt", cfg.mqtt.server_address, "MQTT server URI (e.g. tcp://host:1883 or ssl://host:8883)");
    auto *mqttHost = app.add_option("--mqtt-host", s_mqtt_host);
    auto *mqttPort = app.add_option("--mqtt-port", s_mqtt_port);
    auto *mqttClient = app.add_option("--client-id", cfg.mqtt.client_id, "MQTT client id");
    auto *mqttQos = app.add_option("--qos", cfg.mqtt.qos, "MQTT QoS (0-2)");
    auto *mqttSsl = app.add_flag("--ssl", cfg.mqtt.ssl.enabled, "Enable MQTT SSL");
    auto *sslCa = app.add_option("--ssl-ca", cfg.mqtt.ssl.ca_cert_path, "SSL CA certificate path");
    auto *sslCert = app.add_option("--ssl-cert", cfg.mqtt.ssl.client_cert_path, "SSL client certificate path");
    auto *sslKey = app.add_option("--ssl-key", cfg.mqtt.ssl.client_key_path, "SSL client key path");
    auto *sslVerify = app.add_flag_function("--ssl-verify", [&](size_t){ cfg.mqtt.ssl.verify_server = true; }, "Verify server certificate (default true)");
    auto *noSslVerify = app.add_flag("--no-ssl-verify", s_no_ssl_verify_flag, "Disable server certificate verification");

    // Separate host/port overlay: recompute server_address after parse
    if(with_env_names) {
        mqttServer->envname("MQTT_SERVER");
        mqttClient->envname("MQTT_CLIENT_ID");
        mqttQos->envname("MQTT_QOS");
        mqttSsl->envname("MQTT_SSL");
        sslCa->envname("MQTT_CA_CERT");
        sslCert->envname("MQTT_CLIENT_CERT");
        sslKey->envname("MQTT_CLIENT_KEY");
        sslVerify->envname("MQTT_SSL_VERIFY");
        // Compose compatibility
        mqttHost->envname("MQTT_BROKER_HOST");
        mqttPort->envname("MQTT_BROKER_PORT");
    }
    mqttHost->description("MQTT host (compose env: MQTT_BROKER_HOST)");
    mqttPort->description("MQTT port (compose env: MQTT_BROKER_PORT)");
    mqttHost->type_name("TEXT");
    mqttPort->type_name("INT");
    app.callback([&](){
        if(s_no_ssl_verify_flag) cfg.mqtt.ssl.verify_server = false;
        if(!s_mqtt_host.empty() || s_mqtt_port > 0) {
            std::string scheme = cfg.mqtt.ssl.enabled ? "ssl://" : "tcp://";
            std::string host = s_mqtt_host;
            if(host.empty()) {
                // extract host from existing server_address
                auto sa = cfg.mqtt.server_address;
                auto pos = sa.find("://");
                if(pos != std::string::npos) sa = sa.substr(pos+3);
                auto colon = sa.find(":");
                host = (colon == std::string::npos) ? sa : sa.substr(0, colon);
            }
            int port = (s_mqtt_port > 0) ? s_mqtt_port : 1883;
            cfg.mqtt.server_address = scheme + host + ":" + std::to_string(port);
        }
    });

    // Metrics
    auto *metricsEnabled = app.add_flag_function("--metrics", [&](size_t){ cfg.metrics.enabled = true; }, "Enable metrics");
    auto *metricsEndpoint = app.add_option("--metrics-endpoint", cfg.metrics.otlp_endpoint, "OTLP metrics endpoint");
    auto *metricsService = app.add_option("--metrics-service-name", cfg.metrics.service_name, "Metrics service name");
    auto *metricsInterval = app.add_option("--metrics-interval", cfg.metrics.export_interval_seconds, "Metrics export interval (s)");
    if(with_env_names) {
        metricsEnabled->envname("METRICS_ENABLED");
        metricsEndpoint->envname("METRICS_OTLP_ENDPOINT");
        metricsService->envname("METRICS_SERVICE_NAME");
        metricsInterval->envname("METRICS_EXPORT_INTERVAL");
    }

    // Tracing
    auto *tracingEnabled = app.add_flag_function("--tracing", [&](size_t){ cfg.tracing.enabled = true; }, "Enable tracing");
    auto *tracingEndpoint = app.add_option("--tracing-endpoint", cfg.tracing.otlp_endpoint, "OTLP trace endpoint");
    auto *tracingService = app.add_option("--tracing-service-name", cfg.tracing.service_name, "Tracing service name");
    if(with_env_names) {
        tracingEnabled->envname("TRACING_ENABLED");
        tracingEndpoint->envname("TRACING_OTLP_ENDPOINT");
        tracingService->envname("TRACING_SERVICE_NAME");
    }

    // Logging
    auto *logLevel = app.add_option("--log-level", cfg.logging.level, "Logging level (trace,debug,info,warning,error)");
    if(with_env_names) logLevel->envname("LOG_LEVEL");

    // Scenes
    auto *scenesSource = app.add_option("--scenes-source", cfg.scenes.source, "Scenes source (file|api)");
    auto *scenesFile = app.add_option("--scenes", cfg.scenes.file_path, "Scenes file path");
    if(with_env_names) {
        scenesSource->envname("SCENES_SOURCE");
        scenesFile->envname("SCENES_FILE");
    }
    // API endpoint
    auto *apiUrl = app.add_option("--scenes-api-url", cfg.scenes.api_endpoint.url, "Scenes API URL");
    auto *apiUser = app.add_option("--scenes-api-user", cfg.scenes.api_endpoint.username, "Scenes API username");
    auto *apiPass = app.add_option("--scenes-api-pass", cfg.scenes.api_endpoint.password, "Scenes API password");
    auto *apiSkip = app.add_flag_function("--scenes-api-skip-ssl-verify", [&](size_t){ cfg.scenes.api_endpoint.skip_ssl_verification = true; }, "Skip SSL verification for scenes API");
    auto *apiReload = app.add_option("--scenes-api-reload-topic", cfg.scenes.api_endpoint.reload_topic, "Scenes reload topic");
    auto *apiOut = app.add_option("--scenes-api-output", cfg.scenes.api_endpoint.output_file, "Scenes output file");
    if(with_env_names) {
        apiUrl->envname("SCENES_API_URL");
        apiUser->envname("SCENES_API_USER");
        apiPass->envname("SCENES_API_PASS");
        apiSkip->envname("SCENES_API_SKIP_SSL_VERIFY");
        apiReload->envname("SCENES_API_RELOAD_TOPIC");
        apiOut->envname("SCENES_API_OUTPUT_FILE");
    }

    // Time chunking
    auto *fps = app.add_option("--fps", cfg.time_chunking_fps, "Time chunking FPS");
    auto *lag = app.add_option("--lag", cfg.max_lag_seconds, "Max lag seconds");
    if(with_env_names) {
        fps->envname("TIME_CHUNKING_FPS");
        lag->envname("MAX_LAG_SECONDS");
    }
}

void register_dummy_config_options(CLI::App &app, std::string &config_path, std::string &schema_path) {
    app.add_option("--config", config_path, "Path to service configuration JSON")->configurable(false);
    app.add_option("--schema", schema_path, "Optional JSON Schema for service configuration")->configurable(false);
}

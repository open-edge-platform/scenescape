#include <iostream>
#include <string>
#include <cstring>
#include <getopt.h>
#include "scene_controller.h"

using namespace scenescape;

void printUsage(const char* program_name) {
    std::cout << "Usage: " << program_name << " [OPTIONS]\n\n"
              << "Options:\n"
              << "  --rewriteBadTime          Rewrite bad time stamps instead of discarding data\n"
              << "  --rewriteAllTime          Rewrite all time stamps\n"
              << "  --maxlag SECONDS          Maximum amount of lag in seconds (default: 1.0)\n"
              << "  --broker BROKER           MQTT broker hostname:port (default: broker.scenescape.intel.com:1883)\n"
              << "  --brokerauth AUTH         MQTT authentication (default: /run/secrets/controller.auth)\n"
              << "  --resturl URL             REST server URL (default: https://web.scenescape.intel.com/api/v1)\n"
              << "  --restauth AUTH           REST authentication (required)\n"
              << "  --rootcert CERT           Path to CA certificate (default: /run/secrets/certs/scenescape-ca.pem)\n"
              << "  --cert CERT               Path to client certificate\n"
              << "  --ntp SERVER              NTP server (default: use MQTT broker)\n"
              << "  --tracker_config_file CFG Tracker configuration JSON file\n"
              << "  --schema_file SCHEMA      Metadata schema JSON file\n"
              << "  --visibility_topic TOPIC  Visibility topic (unregulated|regulated|none, default: regulated)\n"
              << "  --verbose                 Enable verbose logging\n"
              << "  --help                    Show this help message\n";
}

int main(int argc, char* argv[]) {
    // Default values
    bool rewrite_bad_time = false;
    bool rewrite_all_time = false;
    double max_lag = 1.0;
    std::string broker = "broker.scenescape.intel.com:1883";
    std::string broker_auth = "/run/secrets/controller.auth";
    std::string rest_url = "https://web.scenescape.intel.com/api/v1";
    std::string rest_auth;
    std::string root_cert = "/run/secrets/certs/scenescape-ca.pem";
    std::string client_cert;
    std::string ntp_server;
    std::string tracker_config_file = "config/tracker-config.json";
    std::string schema_file = "config/metadata.schema.json";
    std::string visibility_topic = "regulated";
    bool verbose = false;
    
    // Long options
    static struct option long_options[] = {
        {"rewriteBadTime", no_argument, 0, 0},
        {"rewriteAllTime", no_argument, 0, 1},
        {"maxlag", required_argument, 0, 2},
        {"broker", required_argument, 0, 3},
        {"brokerauth", required_argument, 0, 4},
        {"resturl", required_argument, 0, 5},
        {"restauth", required_argument, 0, 6},
        {"rootcert", required_argument, 0, 7},
        {"cert", required_argument, 0, 8},
        {"ntp", required_argument, 0, 9},
        {"tracker_config_file", required_argument, 0, 10},
        {"schema_file", required_argument, 0, 11},
        {"visibility_topic", required_argument, 0, 12},
        {"verbose", no_argument, 0, 13},
        {"help", no_argument, 0, 14},
        {0, 0, 0, 0}
    };
    
    int option_index = 0;
    int c;
    
    while ((c = getopt_long(argc, argv, "", long_options, &option_index)) != -1) {
        switch (c) {
            case 0: rewrite_bad_time = true; break;
            case 1: rewrite_all_time = true; break;
            case 2: max_lag = std::stod(optarg); break;
            case 3: broker = optarg; break;
            case 4: broker_auth = optarg; break;
            case 5: rest_url = optarg; break;
            case 6: rest_auth = optarg; break;
            case 7: root_cert = optarg; break;
            case 8: client_cert = optarg; break;
            case 9: ntp_server = optarg; break;
            case 10: tracker_config_file = optarg; break;
            case 11: schema_file = optarg; break;
            case 12: visibility_topic = optarg; break;
            case 13: verbose = true; break;
            case 14:
                printUsage(argv[0]);
                return 0;
            default:
                printUsage(argv[0]);
                return 1;
        }
    }
    
    // Validate required arguments
    if (rest_auth.empty()) {
        std::cerr << "Error: --restauth is required\n";
        printUsage(argv[0]);
        return 1;
    }
    
    try {
        // Create and start the scene controller
        SceneController controller(
            rewrite_bad_time,
            rewrite_all_time,
            max_lag,
            broker,
            broker_auth,
            rest_url,
            rest_auth,
            client_cert,
            root_cert,
            ntp_server,
            tracker_config_file,
            schema_file,
            visibility_topic
        );
        
        std::cout << "SceneScape Controller (C++) starting...\n";
        controller.loopForever();
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}

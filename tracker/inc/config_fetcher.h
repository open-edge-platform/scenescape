#pragma once

#include <memory>
#include <string>

// Forward declaration to avoid including httplib.h in header
namespace httplib {
class Client;
}

/**
 * ConfigFetcher - Fetches scene and camera configuration from Manager API
 *
 * This class handles:
 * - Authentication with the Manager service
 * - Fetching scenes and cameras via REST API
 * - Writing results to JSON file for later use
 * - Error handling and logging
 */
class ConfigFetcher {
public:
    struct AuthConfig {
        std::string manager_url;    // e.g., "https://localhost"
        std::string username;       // e.g., "scenectrl"
        std::string password;       // e.g., from secrets
        bool skip_ssl_verification; // For development (-k flag)
    };

    /**
     * Constructor
     * @param auth_config Authentication configuration for Manager API
     */
    explicit ConfigFetcher(const AuthConfig& auth_config);

    /**
     * Destructor - cleanup resources
     */
    ~ConfigFetcher();

    // Disable copy
    ConfigFetcher(const ConfigFetcher&) = delete;
    ConfigFetcher& operator=(const ConfigFetcher&) = delete;

    /**
     * Fetch configuration from Manager API and save to file
     * @param output_file Path to output JSON file (e.g., "config/scenes-from-api.json")
     * @return true on success, false on failure
     */
    bool fetch_and_save(const std::string& output_file);

    /**
     * Get the authentication token (for debugging/logging)
     * @return The current auth token, or empty string if not authenticated
     */
    std::string get_token() const { return auth_token_; }

private:
    /**
     * Authenticate with Manager API and get token
     * @return true on success, false on failure
     */
    bool authenticate();

    /**
     * Fetch scenes from Manager API
     * @return JSON string with scenes data, or empty string on failure
     */
    std::string fetch_scenes();

    AuthConfig config_;
    std::string auth_token_;
    std::unique_ptr<httplib::Client> client_;
};

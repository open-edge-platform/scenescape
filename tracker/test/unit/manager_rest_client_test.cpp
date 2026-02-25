// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "logger.hpp"
#include "manager_rest_client.hpp"
#include "scene_loader.hpp"

#include <chrono>
#include <thread>

#include <gtest/gtest.h>
#include <httplib.h>

using namespace tracker;

// ---------------------------------------------------------------------------
// Fixture: spins up a local httplib::Server on an ephemeral port so the real
// ManagerRestClient can be exercised end-to-end without external services.
// ---------------------------------------------------------------------------
class ManagerRestClientTest : public ::testing::Test {
protected:
    void SetUp() override {
        Logger::init("warn");

        server_.Post("/api/v1/auth", [this](const httplib::Request& req, httplib::Response& res) {
            auth_handler(req, res);
        });
        server_.Get("/api/v1/scenes", [this](const httplib::Request& req, httplib::Response& res) {
            scenes_handler(req, res);
        });

        // Listen on ephemeral port on localhost
        port_ = server_.bind_to_any_port("127.0.0.1");
        ASSERT_GT(port_, 0) << "Failed to bind to ephemeral port";

        server_thread_ = std::thread([this] { server_.listen_after_bind(); });

        // Wait until server is ready
        for (int i = 0; i < 50; ++i) {
            if (server_.is_running())
                break;
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }

        base_url_ = "http://127.0.0.1:" + std::to_string(port_);
    }

    void TearDown() override {
        server_.stop();
        if (server_thread_.joinable()) {
            server_thread_.join();
        }
        Logger::shutdown();
    }

    // Configurable handler callbacks (tests override these)
    std::function<void(const httplib::Request&, httplib::Response&)> auth_handler =
        [](const httplib::Request&, httplib::Response& res) {
            res.set_content(R"({"token":"test-token-123"})", "application/json");
        };

    std::function<void(const httplib::Request&, httplib::Response&)> scenes_handler =
        [](const httplib::Request&, httplib::Response& res) {
            res.set_content(R"({"results":[]})", "application/json");
        };

    httplib::Server server_;
    std::thread server_thread_;
    int port_ = 0;
    std::string base_url_;
};

// ===== Constructor =====

TEST_F(ManagerRestClientTest, ConstructWithUrlOnly) {
    ManagerRestClient client(base_url_);
    // No crash — just construction
}

TEST_F(ManagerRestClientTest, ConstructWithCaCertPath) {
    ManagerRestClient client(base_url_, "/some/ca.pem");
    // No crash
}

TEST_F(ManagerRestClientTest, ConstructWithNulloptCaCert) {
    ManagerRestClient client(base_url_, std::nullopt);
    // No crash
}

// ===== authenticate() — happy path =====

TEST_F(ManagerRestClientTest, AuthenticateSuccess) {
    ManagerRestClient client(base_url_);
    EXPECT_NO_THROW(client.authenticate("admin", "password"));
}

TEST_F(ManagerRestClientTest, AuthenticateReceivesCredentials) {
    std::string captured_username;
    std::string captured_password;
    auth_handler = [&](const httplib::Request& req, httplib::Response& res) {
        captured_username = req.get_param_value("username");
        captured_password = req.get_param_value("password");
        res.set_content(R"({"token":"tok"})", "application/json");
    };

    ManagerRestClient client(base_url_);
    client.authenticate("myuser", "mypass");

    EXPECT_EQ(captured_username, "myuser");
    EXPECT_EQ(captured_password, "mypass");
}

// ===== authenticate() — error cases =====

TEST_F(ManagerRestClientTest, AuthenticateInvalidUrlNoScheme) {
    ManagerRestClient client("no-scheme-host");
    EXPECT_THROW(client.authenticate("u", "p"), std::runtime_error);
}

TEST_F(ManagerRestClientTest, AuthenticateInvalidUrlBadScheme) {
    ManagerRestClient client("ftp://host");
    EXPECT_THROW(client.authenticate("u", "p"), std::runtime_error);
}

TEST_F(ManagerRestClientTest, AuthenticateInvalidUrlEmpty) {
    ManagerRestClient client("");
    EXPECT_THROW(client.authenticate("u", "p"), std::runtime_error);
}

TEST_F(ManagerRestClientTest, AuthenticateConnectionRefused) {
    // Bind to an ephemeral port, then close it to guarantee connection refusal
    httplib::Server tmp_server;
    int closed_port = tmp_server.bind_to_any_port("127.0.0.1");
    ASSERT_GT(closed_port, 0) << "Failed to bind to ephemeral port";
    tmp_server.stop();

    // Use 50ms timeout to keep the unit test fast (TCP RST is near-instant)
    ManagerRestClient client("http://127.0.0.1:" + std::to_string(closed_port), std::nullopt,
                             std::chrono::milliseconds(50), std::chrono::milliseconds(50));
    EXPECT_THROW(client.authenticate("u", "p"), std::runtime_error);
}

TEST_F(ManagerRestClientTest, AuthenticateHttpError401) {
    auth_handler = [](const httplib::Request&, httplib::Response& res) {
        res.status = 401;
        res.set_content("Unauthorized", "text/plain");
    };

    ManagerRestClient client(base_url_);
    EXPECT_THROW(client.authenticate("u", "p"), std::runtime_error);
}

TEST_F(ManagerRestClientTest, AuthenticateHttpError500) {
    auth_handler = [](const httplib::Request&, httplib::Response& res) {
        res.status = 500;
        res.set_content("Internal Server Error", "text/plain");
    };

    ManagerRestClient client(base_url_);
    EXPECT_THROW(client.authenticate("u", "p"), std::runtime_error);
}

TEST_F(ManagerRestClientTest, AuthenticateResponseNotJson) {
    auth_handler = [](const httplib::Request&, httplib::Response& res) {
        res.set_content("not json at all", "text/plain");
    };

    ManagerRestClient client(base_url_);
    EXPECT_THROW(client.authenticate("u", "p"), std::runtime_error);
}

TEST_F(ManagerRestClientTest, AuthenticateResponseJsonArray) {
    auth_handler = [](const httplib::Request&, httplib::Response& res) {
        res.set_content("[1,2,3]", "application/json");
    };

    ManagerRestClient client(base_url_);
    EXPECT_THROW(client.authenticate("u", "p"), std::runtime_error);
}

TEST_F(ManagerRestClientTest, AuthenticateResponseMissingTokenField) {
    auth_handler = [](const httplib::Request&, httplib::Response& res) {
        res.set_content(R"({"not_token":"abc"})", "application/json");
    };

    ManagerRestClient client(base_url_);
    EXPECT_THROW(client.authenticate("u", "p"), std::runtime_error);
}

TEST_F(ManagerRestClientTest, AuthenticateResponseTokenNotString) {
    auth_handler = [](const httplib::Request&, httplib::Response& res) {
        res.set_content(R"({"token":42})", "application/json");
    };

    ManagerRestClient client(base_url_);
    EXPECT_THROW(client.authenticate("u", "p"), std::runtime_error);
}

// ===== fetchScenes() — not authenticated =====

TEST_F(ManagerRestClientTest, FetchScenesWithoutAuthThrows) {
    ManagerRestClient client(base_url_);
    EXPECT_THROW(client.fetchScenes(), std::runtime_error);
}

// ===== fetchScenes() — happy path =====

TEST_F(ManagerRestClientTest, FetchScenesSuccess) {
    scenes_handler = [](const httplib::Request&, httplib::Response& res) {
        res.set_content(R"({"results":[{"name":"scene1"}]})", "application/json");
    };

    ManagerRestClient client(base_url_);
    client.authenticate("u", "p");
    std::string body = client.fetchScenes();
    EXPECT_NE(body.find("scene1"), std::string::npos);
}

TEST_F(ManagerRestClientTest, FetchScenesPassesAuthHeader) {
    std::string captured_auth;
    scenes_handler = [&](const httplib::Request& req, httplib::Response& res) {
        captured_auth = req.get_header_value("Authorization");
        res.set_content("{}", "application/json");
    };

    ManagerRestClient client(base_url_);
    client.authenticate("u", "p");
    client.fetchScenes();

    EXPECT_EQ(captured_auth, "Token test-token-123");
}

// ===== fetchScenes() — error cases =====

TEST_F(ManagerRestClientTest, FetchScenesHttpError403) {
    scenes_handler = [](const httplib::Request&, httplib::Response& res) {
        res.status = 403;
        res.set_content("Forbidden", "text/plain");
    };

    ManagerRestClient client(base_url_);
    client.authenticate("u", "p");
    EXPECT_THROW(client.fetchScenes(), std::runtime_error);
}

TEST_F(ManagerRestClientTest, FetchScenesConnectionRefused) {
    // Authenticate against the real server first
    ManagerRestClient client(base_url_);
    client.authenticate("u", "p");

    // Now stop the server so fetchScenes cannot connect
    server_.stop();
    if (server_thread_.joinable()) {
        server_thread_.join();
    }

    EXPECT_THROW(client.fetchScenes(), std::runtime_error);
}

// ===== URL parsing edge cases (tested through authenticate) =====

TEST_F(ManagerRestClientTest, AuthenticateUrlWithPathPrefix) {
    std::string captured_path;
    auth_handler = [&](const httplib::Request& req, httplib::Response& res) {
        captured_path = req.path;
        res.set_content(R"({"token":"tok"})", "application/json");
    };

    // Re-bind server with a custom prefix handler
    // httplib matches exact paths, so we need to register prefix+path
    server_.stop();
    if (server_thread_.joinable())
        server_thread_.join();

    httplib::Server prefix_server;
    prefix_server.Post("/prefix/api/v1/auth",
                       [&](const httplib::Request& req, httplib::Response& res) {
                           captured_path = req.path;
                           res.set_content(R"({"token":"tok"})", "application/json");
                       });
    int prefix_port = prefix_server.bind_to_any_port("127.0.0.1");
    std::thread t([&] { prefix_server.listen_after_bind(); });

    for (int i = 0; i < 50; ++i) {
        if (prefix_server.is_running())
            break;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    std::string url = "http://127.0.0.1:" + std::to_string(prefix_port) + "/prefix";
    ManagerRestClient client(url);
    client.authenticate("u", "p");
    EXPECT_EQ(captured_path, "/prefix/api/v1/auth");

    prefix_server.stop();
    t.join();
}

TEST_F(ManagerRestClientTest, AuthenticateUrlWithTrailingSlash) {
    std::string captured_path;
    auth_handler = [&](const httplib::Request& req, httplib::Response& res) {
        captured_path = req.path;
        res.set_content(R"({"token":"tok"})", "application/json");
    };

    // URL with trailing slash — parse_url should strip it
    std::string url = base_url_ + "/";
    ManagerRestClient client(url);
    client.authenticate("u", "p");
    EXPECT_EQ(captured_path, "/api/v1/auth");
}

TEST_F(ManagerRestClientTest, FetchScenesUrlWithPathPrefix) {
    std::string captured_path;

    server_.stop();
    if (server_thread_.joinable())
        server_thread_.join();

    httplib::Server prefix_server;
    prefix_server.Post("/sub/api/v1/auth", [](const httplib::Request&, httplib::Response& res) {
        res.set_content(R"({"token":"tok"})", "application/json");
    });
    prefix_server.Get("/sub/api/v1/scenes",
                      [&](const httplib::Request& req, httplib::Response& res) {
                          captured_path = req.path;
                          res.set_content(R"({"results":[]})", "application/json");
                      });
    int prefix_port = prefix_server.bind_to_any_port("127.0.0.1");
    std::thread t([&] { prefix_server.listen_after_bind(); });

    for (int i = 0; i < 50; ++i) {
        if (prefix_server.is_running())
            break;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    std::string url = "http://127.0.0.1:" + std::to_string(prefix_port) + "/sub";
    ManagerRestClient client(url);
    client.authenticate("u", "p");
    client.fetchScenes();
    EXPECT_EQ(captured_path, "/sub/api/v1/scenes");

    prefix_server.stop();
    t.join();
}

// ===== HTTPS-related construction (no real TLS server - just verifies no crash) =====

TEST_F(ManagerRestClientTest, ConstructWithHttpsUrlAndEmptyCaCert) {
    ManagerRestClient client("https://localhost:9999", "");
    // Construction succeeds; actual connection would fail (no server).
}

TEST_F(ManagerRestClientTest, ConstructWithHttpsUrlAndCaCertPath) {
    ManagerRestClient client("https://localhost:9999", "/nonexistent/ca.pem");
    // Construction succeeds; actual connection would fail.
}

// ===== default_manager_client_factory =====

TEST_F(ManagerRestClientTest, DefaultFactoryCreatesManagerRestClient) {
    ManagerConfig cfg;
    cfg.url = base_url_;
    cfg.auth_path = "/unused";
    auto client = default_manager_client_factory(cfg);
    ASSERT_NE(client, nullptr);
    // Verify it's a real ManagerRestClient by calling authenticate against our server
    EXPECT_NO_THROW(client->authenticate("u", "p"));
}

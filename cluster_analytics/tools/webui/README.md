# Cluster Analytics WebUI - Demo Setup

This README explains how to enable the WebUI for Cluster Analytics in the Scenescape demo setup.

> **Note:** The WebUI is not part of the production image. It is shipped in a
> separate demo image (`scenescape-cluster-analytics-demo`) and is intended for
> development and demo use only.

## Cluster Analytics WebUI Features

- Real-time cluster visualization
- Scene selection and filtering
- Dynamic clustering parameter adjustment

## 🚀 Quick Start

The WebUI is **disabled by default**. To enable it:

1. **Build the demo image** (includes WebUI dependencies):

   ```bash
   cd /path/to/scenescape
   make -C cluster_analytics build-demo
   ```

2. **Update docker-compose** to use the demo image for the `cluster-analytics` service:

   ```yaml
   cluster-analytics:
     image: scenescape-cluster-analytics-demo:${VERSION:-latest}
   ```

3. **Follow the enable steps below**, then run:

   ```bash
   SUPASS=admin123 make demo-cluster-analytics
   ```

After enabling, access the WebUI at: **https://localhost:9443**

## ⚠️ Important Note

When you modify the `command` section in docker-compose.yml (commenting/uncommenting WebUI flags), you **must recreate** the container, not just restart it:

```bash
docker compose up -d --force-recreate cluster-analytics
```

## Enable WebUI

The WebUI is **disabled by default** in `docker-compose.yml`. To enable it, **uncomment** these lines:

1. **Uncomment the port mapping:**

   ```yaml
   cluster-analytics:
     # ... other config ...
     # Uncomment the following lines to enable WebUI:
     ports: # ✅ Uncomment this line
       - "9443:9443" # ✅ Uncomment this line
   ```

2. **Uncomment the WebUI command flags:**

   ```yaml
   command: >
     # ... other config ...
     # Uncomment the following lines to enable WebUI:
      --webui                                  # ✅ Uncomment this line
      --webui-certfile /run/secrets/web-cert   # ✅ Uncomment this line
      --webui-keyfile /run/secrets/web-key     # ✅ Uncomment this line
   ```

3. **Uncomment the SSL certificate secrets:**

   ```yaml
   secrets:
     - source: root-cert
       target: certs/scenescape-ca.pem
     - controller.auth
     # Uncomment the following lines to enable WebUI:
     - web-cert # ✅ Uncomment this line
     - web-key # ✅ Uncomment this line
   ```

4. **Recreate the service (important - restart is not enough):**
   ```bash
   docker compose up -d --force-recreate cluster-analytics
   ```

## To Disable WebUI

If you want to **disable** the WebUI again, **comment out** these lines in `docker-compose.yml`:

1. **Comment out the port mapping:**

   ```yaml
   # ports:
   #   - "9443:9443"        # ❌ Port not exposed
   ```

2. **Comment out the WebUI command flags:**

   ```yaml
   command: >
     --broker broker.scenescape.intel.com
     --brokerauth /run/secrets/controller.auth

   # --webui              # ❌ WebUI disabled
   # --webui-certfile /run/secrets/web-cert
   # --webui-keyfile /run/secrets/web-key
   ```

3. **Comment out the SSL certificate secrets:**

   ```yaml
   secrets:
     - source: root-cert
       target: certs/scenescape-ca.pem
     - controller.auth
     # - web-cert           # ❌ WebUI certificates disabled
     # - web-key            # ❌ WebUI certificates disabled
   ```

4. **Recreate the service (important - restart is not enough):**
   ```bash
   docker compose up -d --force-recreate cluster-analytics
   ```

## ✅ Verification

After enabling WebUI, verify it's working:

```bash
# Check service logs
docker compose logs cluster-analytics | grep -i webui

# Expected output:
# "WebUI initialized successfully"
# "WebUI server started on https://0.0.0.0:9443"

# Test WebUI endpoint
curl -k https://localhost:9443
```

## 🌐 Accessing the WebUI

- **URL**: https://localhost:9443
- **Protocol**: HTTPS only (uses SSL certificates)

## 🛠️ Troubleshooting

**WebUI not accessible?**

- Ensure port 9443 is not blocked by firewall
- Check that SSL certificates are properly mounted
- Verify the `--webui` flag is uncommented in docker-compose.yml

**Service fails to start?**

- Check that all SSL certificate files exist in `manager/secrets/certs/`
- Verify MQTT broker is running and accessible

**Need help?**
Check the service logs: `docker compose logs cluster-analytics`

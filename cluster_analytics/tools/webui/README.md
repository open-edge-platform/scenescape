# Cluster Analytics WebUI - Demo Setup

This README explains how to enable the WebUI for Cluster Analytics in the SceneScape demo setup.

## 🚀 Quick Start

The WebUI is **disabled by default**. To enable it, follow the instructions below, then run:

```bash
cd /path/to/scenescape
SUPASS=admin123 make demo
```

After enabling, access the WebUI at: **https://localhost:5000**

## � To Enable WebUI

The WebUI is **disabled by default** in `docker-compose.yml`. To enable it, **uncomment** these lines:

1. **Uncomment the port mapping:**
   ```yaml
   cluster-analytics:
     # ... other config ...
     # Uncomment the following lines to enable WebUI:
     ports:                    # ✅ Uncomment this line
       - "5000:5000"           # ✅ Uncomment this line
   ```

2. **Uncomment the WebUI command flags:**
   ```yaml
   command: >
     --broker broker.scenescape.intel.com
     --brokerauth /run/secrets/controller.auth
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
     - web-cert               # ✅ Uncomment this line
     - web-key                # ✅ Uncomment this line
   ```

4. **Restart the service:**
   ```bash
   docker-compose restart cluster-analytics
   ```

## 🔄 To Disable WebUI

If you want to **disable** the WebUI again, **comment out** these lines in `docker-compose.yml`:

1. **Comment out the port mapping:**
   ```yaml
   # ports:
   #   - "5000:5000"        # ❌ Port not exposed
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

4. **Restart the service:**
   ```bash
   docker-compose restart cluster-analytics
   ```

## ✅ Verification

After enabling WebUI, verify it's working:

```bash
# Check service logs
docker-compose logs cluster-analytics | grep -i webui

# Expected output:
# "WebUI initialized successfully"
# "WebUI server started on https://0.0.0.0:5000"

# Test WebUI endpoint
curl -k https://localhost:5000
```

## 🌐 Accessing the WebUI

- **URL**: https://localhost:5000
- **Protocol**: HTTPS only (uses SSL certificates)
- **Features**: 
  - Real-time cluster visualization
  - Scene selection and filtering
  - Dynamic clustering parameter adjustment
  - Live data updates

## 🛠️ Troubleshooting

**WebUI not accessible?**
- Ensure port 5000 is not blocked by firewall
- Check that SSL certificates are properly mounted
- Verify the `--webui` flag is uncommented in docker-compose.yml

**Service fails to start?**
- Check that all SSL certificate files exist in `manager/secrets/certs/`
- Verify MQTT broker is running and accessible

**Need help?**
Check the service logs: `docker-compose logs cluster-analytics`

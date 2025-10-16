# SceneScape Cluster Analytics Demo

This demo provides a minimal SceneScape deployment focused exclusively on cluster analytics testing, without the overhead of retail and queuing video processing components.

> **⚠️ Important**: All Docker Compose commands in this guide include `--env-file .env` parameter. This is required to load environment variables like database passwords and certificate paths. Running commands without this parameter will result in configuration errors.

## 🎯 What's Included

### Essential Services Only

- **MQTT Broker** - Message communication hub
- **PostgreSQL Database** - Data persistence
- **Web Manager** - REST API and web interface
- **Scene Controller** - Scene management and coordination
- **Cluster Analytics** - The main service for spatial clustering

### What's NOT Included

- ❌ Retail video processing pipeline
- ❌ Queuing video processing pipeline
- ❌ Media servers and camera feeds
- ❌ DL Streamer pipeline servers
- ❌ Camera calibration service

## 🚀 Quick Start

### 1. Build and Deploy

```bash
# Build all components and start cluster demo
SUPASS=your_password make build-all demo-cluster

# Or if already built, just start the demo
SUPASS=your_password make demo-cluster
```

### 2. Verify Deployment

```bash
# Check service status
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env ps

# View cluster analytics logs
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env logs -f cluster-analytics
```

### 3. Access Services

- **Web Interface**: https://localhost:443
- **MQTT Broker**: localhost:1883 (TLS enabled)
- **PostgreSQL**: localhost:5432

## 📊 Testing Cluster Analytics

### Using K6 Load Testing

The existing K6 simulation scripts work perfectly with this deployment:

```bash
# Navigate to K6 testing directory
cd /path/to/k6/clustering-sim

# Run cluster analytics simulation
./run-cluster-analytics.sh
```

### Manual MQTT Testing

Publish test object metadata directly:

```bash
# Example: Publish object metadata
mosquitto_pub -h localhost -p 1883 \
  --cafile manager/secrets/certs/scenescape-ca.pem \
  --cert manager/secrets/certs/scenescape-broker.crt \
  --key manager/secrets/certs/scenescape-broker.key \
  -t "scenescape/regulated/scene/your-scene-id" \
  -m '{"timestamp": "2025-10-16T10:00:00Z", "objects": [...]}'
```

## 🔧 Management

### Start/Stop Services

```bash
# Start cluster analytics demo
SUPASS=your_password make demo-cluster

# Stop services
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env down

# Clean up everything (volumes, containers)
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env down -v
```

### Monitor Services

```bash
# View all service logs
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env logs -f

# View specific service logs
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env logs -f cluster-analytics
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env logs -f broker
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env logs -f web
```

### Service Health

```bash
# Check service status
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env ps

# Check container health
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env ps --format "table {{.Service}}\t{{.State}}\t{{.Status}}"
```

## 🐛 Troubleshooting

### Services Won't Start

1. Ensure SUPASS environment variable is set
2. Check that certificates exist in `manager/secrets/certs/`
3. Verify no port conflicts (443, 1883, 5432)
4. Check Docker daemon is running

### Cluster Analytics Issues

1. Verify MQTT broker is running: `docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env logs broker`
2. Check scene controller connectivity: `docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env logs scene`
3. Monitor cluster analytics processing: `docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env logs -f cluster-analytics`

### Database Problems

1. Check PostgreSQL logs: `docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env logs pgserver`
2. Reset database volume: `docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env down -v`

## 🔍 Expected Behavior

When working correctly, cluster analytics should show logs like:

```
[INFO] Received 3 objects for scene ac17e315-35c7-44c7-9aaf-3cd18b96e610
[INFO] Clustering result: 1 clusters, 0 noise points
[INFO] Published cluster metadata to scenescape/analytics/clusters/ac17e315-35c7-44c7-9aaf-3cd18b96e610
```

## 🎯 Perfect For

- ✅ Algorithm testing and validation
- ✅ Load testing with K6 scripts
- ✅ Parameter tuning and optimization
- ✅ CI/CD integration testing
- ✅ Rapid development and debugging

## 📚 Related Files

- `sample_data/cluster_analytics_demo/docker-compose-cluster.yml` - Main compose file
- `Makefile` - Build and deployment automation
- `manager/secrets/` - TLS certificates and authentication
- `cluster_analytics/` - Cluster analytics source code

## 🔧 Quick Reference

### Essential Commands

```bash
# Start demo
SUPASS=your_password make demo-cluster

# Stop demo
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env down

# View logs
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env logs -f cluster-analytics

# Check status
docker compose -f sample_data/cluster_analytics_demo/docker-compose-cluster.yml --env-file .env ps
```

### Important Notes

- ⚠️ **Always include `--env-file .env`** in Docker Compose commands
- 🔑 **SUPASS environment variable** is required for initial setup
- 📁 **Run commands from project root** (`/home/labrat/Cluster_Microservice_SC/`)
- 🏗️ **Build images first** if they don't exist: `make build-all`

# Scenescape's Cluster Analytics Service

The Cluster Analytics microservice provides objects clustering, cluster tracking, cluster's shape and movement patterns analysis capabilities for Scenescape.

## Key Features

- **DBSCAN Clustering**: Density-based spatial clustering with category-specific parameters
- **Tracking**: Persistent cluster tracking across frames with UUID persistence via greedy nearest-centroid matching
- **Shape Detection**: ML-based geometric pattern recognition (circle, rectangle, line, irregular)
- **Velocity Analysis**: Movement pattern classification (stationary, coordinated, converging, etc.)

## Documentation

- **Overview**
  - [Overview and Architecture](../docs/user-guide/microservices/cluster-analytics/cluster-analytics.md): Comprehensive introduction to features and algorithms

- **Getting Started**
  - [Get Started](../docs/user-guide/microservices/cluster-analytics/get-started.md): Step-by-step guide to running the service

- **Deployment**
  - [How to Build from Source](../docs/user-guide/microservices/cluster-analytics/get-started/build-from-source.md): Building and deployment instructions

## Quick Start

```bash
# Build the service
make cluster_analytics

# Run using Docker Compose
docker compose up -d cluster-analytics
```

## Testing

### Unit tests (no Docker required)

```bash
# From repo root
python -m pytest tests/sscape_tests/cluster_analytics/ -v -p no:django
```

### Component tests (requires Docker image)

```bash
# Build the test image first (only needed once per code change)
make test-build             # run from cluster_analytics/

# Run component tests from repo root
pip install -r cluster_analytics/tests/service/requirements.txt
pytest cluster_analytics/tests/service/ -v
```

See [cluster_analytics/tests/README.md](tests/README.md) for details.

## License

Apache 2.0 License - See LICENSE file for details

# Intel® SceneScape's Cluster Analytics Service

The Cluster Analytics microservice provides objects clustering, cluster tracking, cluster's shape and movement patterns analysis capabilities for Intel® SceneScape.

## Key Features

- **DBSCAN Clustering**: Density-based spatial clustering with category-specific parameters
- **Tracking**: Persistent cluster tracking across frames with state-based lifecycle management
- **Shape Detection**: ML-based geometric pattern recognition (circle, rectangle, line, irregular)
- **Velocity Analysis**: Movement pattern classification (stationary, coordinated, converging, etc.)

## Documentation

- **Overview**
  - [Overview and Architecture](docs/user-guide/overview.md): Comprehensive introduction to features and algorithms

- **Getting Started**
  - [Get Started](docs/user-guide/get-started.md): Step-by-step guide to running the service

- **Deployment**
  - [How to Build from Source](docs/user-guide/How-to-build-source.md): Building and deployment instructions

## Quick Start

```bash
# Build the service
make cluster_analytics

# Run using Docker Compose
docker compose up -d cluster-analytics
```

## License

Apache 2.0 License - See LICENSE file for details

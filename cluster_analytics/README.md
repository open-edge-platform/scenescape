# Intel® SceneScape's Cluster Analytics Microservice

The Cluster Analytics microservice provides advanced object clustering, temporal tracking, and movement analysis capabilities for Intel® SceneScape.

## Key Features

- **DBSCAN Clustering**: Density-based spatial clustering with category-specific parameters
- **Temporal Tracking**: Persistent cluster tracking across frames with state-based lifecycle management
- **Confidence Scoring**: Dynamic confidence calculation based on detection consistency
- **Shape Detection**: ML-based geometric pattern recognition (circle, rectangle, line, irregular)
- **Velocity Analysis**: Movement pattern classification (stationary, coordinated, converging, etc.)
- **Real-time WebUI**: Interactive visualization with live parameter adjustment
- **Hungarian Matching**: Optimal cluster-to-detection assignment for robust tracking

## Documentation

- **Overview**
  - [Overview and Architecture](docs/user-guide/overview.md): Comprehensive introduction to features and algorithms
  - [Cluster Tracking System](docs/user-guide/cluster-tracking.md): Detailed guide to temporal tracking and state management

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

## What's New

### Version 3.0 - Cluster Tracking System

- Persistent cluster IDs across video frames
- Five-state lifecycle FSM (NEW → ACTIVE → STABLE → FADING → LOST)
- Confidence and stability scoring
- Historical data tracking (positions, velocities, shapes)
- Prediction-based matching for improved accuracy

### Version 2.0 - WebUI Integration

- Real-time interactive visualization
- Dynamic parameter configuration per category and scene
- Live cluster and object display

## License

Apache 2.0 License - See LICENSE file for details

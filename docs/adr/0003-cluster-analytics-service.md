# ADR 3: DBSCAN-based Cluster Analytics Service for Intel® SceneScape

- **Author(s)**: [Dmytro Yermolenko](https://github.com/dmytroye)
- **Date**: 2025-10-10
- **Status**: `Proposed`

## Context

### Why we need it?

In very dense scenes with thousands of people, it is expensive to track each object individually and it is not valuable to track every single object, crowd patterns are more useful to understand that individual behavior.

### Complexity Challenges of Individual Object Analysis

Analyzing individual objects in complex scenes creates exponential complexity:

**Key Challenges:**

- **Computational Overhead**: N² relationship analysis between objects becomes computationally expensive at scale
- **Data Complexity**: Processing hundreds of individual object streams without contextual grouping overwhelms systems and analysts
- **Scalability Issues**: System performance degrades non-linearly as object counts increase

**Result:** Individual object analysis leads to delayed insights, increased costs, and missed opportunities for effective crowd management and traffic optimization.

## Decision

### Implement DBSCAN-based Cluster Analytics Service

We will implement a post-tracking clustering microservice using **DBSCAN (Density-Based Spatial Clustering)** algorithm with shape and velocity analysis.

#### Core Approach

- **DBSCAN Clustering**: Groups objects based on spatial proximity with category-specific parameters for different object types (people, vehicles, bicycles etc.)
- **Shape Detection**: Identifies cluster formations (circular, linear, rectangular, irregular patterns)
- **Velocity Analysis**: Classifies movement patterns (stationary, coordinated, converging/diverging, chaotic)

#### Implementation Architecture

Post-tracking clustering implemented as a separate microservice that:

1. Consumes tracked objects from Scene Controller via MQTT
2. Applies category-specific DBSCAN clustering
3. Performs shape and velocity analysis on detected clusters
4. Publishes enriched cluster metadata to dedicated MQTT topics

## Alternatives Considered

### Pre-tracking clustering

Reduces overhead on tracker by replacing individual objects with clusters and allows it to scale to very large numbers without frame drop.

- **Challenges**: Fusion from multiple cameras with deduplication, no spatial temporal data i.e no velocity/heading.

## Consequences

### Positive

- Anomaly detection for predicting stampedes through flow analytics does not need individual object tracking.
- Simplified implementation, single responsibility principle, can be used without Scene Controller.
- Customers can implement their own business logic based on clusters metadata.
- Consumers can reduce analysis overhead with clustered blob.

### Negative

- Cannot use the clusters metadata to perform any base analytics in Scene Controller.
- If base analytics are separated from Scene Controller, the base analytics microservice can consume the output of the tracker or it consumes the output of clustering microservice that need additional code changes.

## References

- [Comparing different clustering algorithms on toy datasets](https://scikit-learn.org/stable/auto_examples/cluster/plot_cluster_comparison.html#sphx-glr-auto-examples-cluster-plot-cluster-comparison-py)
- [A Density-Based Algorithm for Discovering Clusters in Large Spatial Databases with Noise](https://www.dbs.ifi.lmu.de/Publikationen/Papers/KDD-96.final.frame.pdf)

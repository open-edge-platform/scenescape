# ADR 4: DBSCAN-based Cluster Analytics Service for Intel® SceneScape

- **Author(s)**: [Dmytro Yermolenko](https://github.com/dmytroye)
- **Date**: 2025-10-14
- **Status**: `Accepted`

## Context

### Why we need it?

In very dense scenes with thousands of objects, it is expensive to track each object individually and it is not valuable to track every single object. For example crowd patterns are more useful to understand that individual behavior.

**Additional Use Cases:**

- **Traffic Management**: Analyzing vehicle clusters in traffic jams, convoy formations, and highway congestion patterns provides better flow optimization than individual vehicle tracking
- **Public Transportation**: Monitoring passenger clusters at bus stops, train platforms, and boarding areas helps optimize service schedules and capacity planning
- **Event Management**: Large gatherings, concerts, and sports events benefit from crowd cluster analysis for safety monitoring and crowd control
- **Retail Spaces**: Shopping mall and store analytics focus on customer group behaviors and flow patterns rather than individual shopper tracking
- **Security Applications**: Detecting unusual group formations or crowd dispersal patterns for threat assessment and emergency response

### Challenges in Individual Object Analysis for Dense Scenes

Analyzing individual objects in complex scenes creates limitations for meaningful business insights:

**Key Challenges:**

- **Information Overload**: Tracking hundreds of individual objects generates excessive granular data that obscures meaningful patterns and group behaviors
- **Missing Context**: Individual object analysis fails to capture crowd dynamics, flow patterns, and collective behaviors that drive decisions based on exact consumer use case
- **Insight Complexity**: Business logic requiring group analysis (queue management, crowd safety, traffic flow optimization) becomes difficult to extract from individual object streams

**Result:** Individual object analysis alone does not provide actionable insights in dense scenes. Instead it leads to information noise, missed pattern recognition opportunities, and inability to implement effective crowd management or traffic optimization strategies.

## Decision

### Implement DBSCAN-based Cluster Analytics Service

We will implement a post-tracking clustering microservice in Python using **DBSCAN (Density-Based Spatial Clustering)** algorithm from SciKit Learn library with additional shape and velocity analysis.

Choosing implementation in Python we want to be flexible and nimble in our design and execution in the first few iterations as we need to gather feedback from customers/users/business units and evolve the cluster analytics. Performance will be in focus when we are confident about the long term roadmap and what the market desires.

#### Core Approach

- **DBSCAN Clustering**: Groups objects based on spatial proximity with category-specific parameters for different object types (people, vehicles, bicycles etc.)
- **Shape Detection**: Identifies cluster formations (circular, linear, rectangular, irregular patterns)
- **Velocity Analysis**: Classifies movement patterns (stationary, coordinated, converging/diverging, chaotic)

#### Related Pull Request

- [Object clustering is available in SceneScape](https://github.com/open-edge-platform/scenescape/pull/443)

#### Implementation Architecture

Post-tracking clustering implemented as a separate microservice that:

1. Consumes objects metadata from DATA_REGULATED MQTT topic
2. Applies category-specific DBSCAN clustering
3. Performs shape and velocity analysis on detected clusters
4. Publishes enriched cluster metadata to dedicated MQTT topics

## Alternatives Considered

### Pre-tracking clustering

Reduces overhead on tracker by replacing individual objects with clusters and allows it to scale to very large numbers without frame drop.

- **Challenges**: Fusion from multiple cameras with deduplication, no spatial temporal data i.e no velocity/heading.

#### Related Pull Request (Pre-tracking Clustering)

- [PoC Pre-tracking Clustering](https://github.com/open-edge-platform/scenescape/pull/407)

## Consequences

### Positive

- **Actionable Insights**: Cluster analytics provides meaningful pattern recognition for crowd dynamics, queue management, and traffic flow optimization that individual object tracking cannot deliver.
- **Context-Rich Analysis**: Groups objects into meaningful clusters that reveal collective behaviors, movement patterns, and spatial relationships essential for business decision-making.
- **Simplified Business Logic**: Customers can implement their own business logic based on cluster metadata rather than processing overwhelming streams of individual object data.
- **Reduced Information Noise**: Consumers can focus on cluster-level insights instead of being overwhelmed by granular individual object streams that obscure meaningful patterns.
- **Enhanced Use Case Support**: Enables effective crowd management, traffic optimization, and safety monitoring strategies that are impossible with individual object analysis alone.
- **Flexible Implementation**: Single responsibility principle allows standalone operation for alternative object metadata sources, supporting diverse customer deployment scenarios.

### Negative

- Cannot use the clusters metadata to perform any base analytics in Scene Controller.
- Potential performance gaps in comparison to C++ implementation on high scale (5k objects and more).
- Solution does not provide any performance impovements of the Scene Controller itself or reducing tracker's computational overhead.
- Post-tracking clustering depends on receiving data from the tracker, which introduces extra latency. In dense scenes, if the tracker drops frames or loses tracks due to computational limitations, the clustering service may receive incomplete object data.

### Future extension

- If base analytics are separated from Scene Controller, the base analytics microservice can consume the output of the tracker or it consumes the output of clustering microservice.

## References

- [Comparing different clustering algorithms on toy datasets](https://scikit-learn.org/stable/auto_examples/cluster/plot_cluster_comparison.html#sphx-glr-auto-examples-cluster-plot-cluster-comparison-py)
- [A Density-Based Algorithm for Discovering Clusters in Large Spatial Databases with Noise](https://www.dbs.ifi.lmu.de/Publikationen/Papers/KDD-96.final.frame.pdf)

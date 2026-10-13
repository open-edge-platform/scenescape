# DBSCAN Noise Point Explanation

In the DBSCAN clustering algorithm, **noise points** are objects that do not belong to any cluster. Understanding noise points is important for interpreting analytics results in the Cluster Analytics microservice.

## DBSCAN Algorithm Overview

DBSCAN (Density-Based Spatial Clustering of Applications with Noise) classifies each data point as one of:

- **Core points**: Have at least `min_samples` neighbors within `eps` distance.
- **Border points**: Are within `eps` distance of a core point but do not have enough neighbors to be core points themselves.
- **Noise points**: Are neither core nor border points—these are isolated from other points.

## Noise Points in Cluster Analytics

In this service, noise points are objects that:

- Are farther than the configured `eps` distance (e.g., 1.5 meters) from any other object of the same category.
- Do not have enough nearby neighbors to form a cluster (fewer than `min_samples`).

**Example Scenarios:**

- **Queuing Scene**:
  - 5 people detected.
  - 3 people stand close together (within 1.5m): form 1 cluster.
  - 2 people stand alone, each more than 1.5m from others: these are noise points.
- **Retail Scene**:
  - 4 people detected.
  - 2 people are near each other: form 1 cluster.
  - 2 people are isolated: noise points.

## Code Representation

In DBSCAN output, objects labeled with `-1` are noise points. These represent people or objects that are spatially isolated and do not form meaningful groups with others of the same category.

## Why Noise Points Matter

Identifying noise points helps distinguish between:

- **Clustered behavior**: People or objects grouping together.
- **Individual behavior**: People or objects standing alone or isolated.

This distinction is valuable for analytics, enabling insights into both group dynamics and solitary activity within a scene.

## Logging Benefits

- **Reduced Log Volume**: Eliminates verbose JSON serialization in production.
- **Performance**: Avoids expensive string formatting when not needed.
- **Operational**: Clear cluster summaries for monitoring and alerting.
- **Debugging**: Full metadata available when debug logging is enabled.

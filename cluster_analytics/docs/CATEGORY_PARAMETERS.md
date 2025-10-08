# Category-Specific DBSCAN Parameters Implementation

## Overview

The Cluster Analytics service has been enhanced to support category-specific DBSCAN parameters, allowing different object types to use optimized clustering parameters based on their spatial characteristics.

## Implementation Details

### 1. Configuration Structure

**New Configuration System:**
```python
# Category-specific DBSCAN parameters
CATEGORY_DBSCAN_PARAMS = {
    'person': {'eps': 2.0, 'min_samples': 3},
    'vehicle': {'eps': 4.0, 'min_samples': 2},
    'bicycle': {'eps': 1.5, 'min_samples': 2},
    'motorcycle': {'eps': 2.5, 'min_samples': 2},
    'truck': {'eps': 5.0, 'min_samples': 2},
    'bus': {'eps': 6.0, 'min_samples': 2}
}

# Default parameters for unknown categories
DEFAULT_DBSCAN_EPS = 1.5
DEFAULT_DBSCAN_MIN_SAMPLES = 3
```

**Replaced:** Single global parameters (`DBSCAN_EPS`, `DBSCAN_MIN_SAMPLES`)

### 2. Core Implementation

**New Method:**
```python
def get_dbscan_params_for_category(self, category):
    """Get DBSCAN parameters optimized for a specific object category"""
    category_lower = category.lower()
    
    if category_lower in self.CATEGORY_DBSCAN_PARAMS:
        params = self.CATEGORY_DBSCAN_PARAMS[category_lower]
        log.debug(f"Using category-specific parameters for '{category}': {params}")
        return params
    else:
        default_params = {
            'eps': self.DEFAULT_DBSCAN_EPS,
            'min_samples': self.DEFAULT_DBSCAN_MIN_SAMPLES
        }
        log.debug(f"Using default parameters for unknown category '{category}': {default_params}")
        return default_params
```

**Updated Clustering Logic:**
```python
# Automatic parameter selection per category
for category, category_objects in objects_by_category.items():
    dbscan_params = self.get_dbscan_params_for_category(category)
    
    if len(category_objects) < dbscan_params['min_samples']:
        continue
    
    # Apply DBSCAN with category-specific parameters
    clustering = DBSCAN(
        eps=dbscan_params['eps'], 
        min_samples=dbscan_params['min_samples']
    ).fit(coordinates_array)
```

## Parameter Rationale

### Category-Specific Parameters

| Category    | eps (m) | min_samples | Rationale |
|-------------|---------|-------------|-----------|
| **person**  | 2.0     | 3           | Social distancing, queue formations, group interactions |
| **vehicle** | 4.0     | 2           | Parking lots, traffic clusters, larger spacing needs |
| **bicycle** | 1.5     | 2           | Bike racks, tight groupings, smaller footprint |
| **motorcycle** | 2.5 | 2           | Moderate spacing, smaller than cars but larger than bikes |
| **truck**   | 5.0     | 2           | Large vehicle spacing, loading zones, truck stops |
| **bus**     | 6.0     | 2           | Bus stops, depots, very large spacing requirements |

### Design Principles

1. **Larger vehicles require larger epsilon values** due to physical size and operational spacing
2. **Smaller min_samples for vehicles** since even 2 vehicles can form meaningful clusters
3. **People require higher min_samples** since individual pairs are less significant than groups
4. **Fallback to defaults** for unknown or new object categories

## Code Changes Summary

### Files Modified

1. **`cluster_analytics_context.py`**
   - Replaced single DBSCAN constants with category-specific configuration
   - Added `get_dbscan_params_for_category()` method
   - Updated clustering logic to use category-specific parameters
   - Enhanced logging to show which parameters are used
   - Added category information to cluster metadata

### Backwards Compatibility

- **Default parameters** maintain existing behavior for unknown categories
- **Existing API** unchanged - no breaking changes to external interfaces
- **Gradual rollout** possible by adding categories incrementally

## Benefits

### 1. **Improved Clustering Accuracy**
- Object-type optimized parameters reduce false positives/negatives
- Better separation between different types of clusters
- More realistic clustering for mixed-category scenes

### 2. **Operational Flexibility**
- Easy to add new object categories
- Parameters can be tuned per category without affecting others
- Clear rationale for parameter choices

### 3. **Enhanced Monitoring**
- Metadata includes which parameters were used
- Logging shows parameter selection process
- Better debugging and analysis capabilities

## Output Changes

### Enhanced Metadata

```json
{
  "dbscan_params": {
    "eps": 2.0,          // Category-specific epsilon
    "min_samples": 3,    // Category-specific min_samples  
    "category": "person" // Object category used for optimization
  }
}
```

### Optimized Logging

```
INFO : Scene abc123: Found 2 clusters for category 'person' (8 objects, 1 noise points) using eps=2.0, min_samples=3
INFO : Scene abc123: Cluster 1 for 'person' - 3 objects, shape: triangle, size: 2.3m
DEBUG: Published cluster 1 metadata for scene abc123 category 'person'
DEBUG: Detailed cluster metadata: {full JSON structure}
```

**Production Benefits:**
- INFO level shows concise cluster summaries for monitoring
- DEBUG level contains detailed JSON metadata for development
- Eliminates verbose JSON logging in production environments
- Reduces log volume and improves performance

## Future Enhancements

### 1. **Runtime Configuration**
- Environment variable support for parameter overrides
- REST API for dynamic parameter updates
- Configuration file support

### 2. **Machine Learning Optimization**
- Automatic parameter tuning based on historical data
- Scene-specific parameter adaptation
- Performance feedback loops

### 3. **Extended Categories**
- Support for subcategories (sedan, SUV, etc.)
- Custom category definitions
- Dynamic category learning

## Testing

### Test Coverage

1. **Unit Tests**: Parameter selection logic
2. **Integration Tests**: End-to-end clustering with mixed categories
3. **Performance Tests**: Clustering accuracy improvements

### Test Scenarios

```python
# Example test scenarios
test_scenarios = [
    {
        'name': 'Mixed Traffic Scene',
        'objects': [
            {'category': 'person', 'translation': [1, 1, 0]},
            {'category': 'vehicle', 'translation': [10, 5, 0]},
            {'category': 'bicycle', 'translation': [50, 10, 0]}
        ]
    }
]
```

## Deployment Notes

### 1. **No Breaking Changes**
- Existing deployments will continue to work
- New functionality activated automatically

### 2. **Performance Impact**
- Minimal overhead from parameter lookup
- Potential accuracy improvements may affect cluster counts

### 3. **Monitoring**
- Monitor cluster metadata for parameter usage
- Check logs for parameter selection information

## Conclusion

The category-specific DBSCAN parameters implementation provides:

- **Better clustering accuracy** through object-type optimization
- **Operational flexibility** for different deployment scenarios  
- **Clear upgrade path** with backwards compatibility
- **Enhanced observability** through improved logging and metadata

This enhancement makes the cluster analytics service more intelligent and adaptable to real-world scenarios where different object types have different spatial clustering characteristics.
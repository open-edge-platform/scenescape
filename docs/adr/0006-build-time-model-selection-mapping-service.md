# ADR 6: Build-Time Model Selection for 3D Mapping Service

- **Author(s)**: [Intel SceneScape Team](https://github.com/open-edge-platform/scenescape)
- **Date**: 2025-10-30
- **Status**: `Accepted`

## Context

The top challenges in configuring a new scene in SceneScape are:

- **Map Availability:** Obtaining a suitable map for the scene.
- **Camera Calibration:** Calibrating cameras with respect to the map.

Previously, these tasks required:

- Acquiring floor blueprints or reconstructing meshes using third-party software for map configuration.
- Manual camera calibration or assisted calibration involving:
  - Scene augmentation with apriltags
  - Reliance on the output format of specific third-party reconstruction tools

These steps create significant barriers to:

- Evaluation
- Adoption
- Large-scale deployment

They demand substantial labor cost from users. Furthermore, any changes incur the same high costs repeatedly. Changes like:

- Moving cameras (which requires recalibration)
- Modifying the scene (which requires a fresh map)

## Decision

Intel® SceneScape will include a REST API based 3D Mapping service that will leverage state-of-the-art, deep learning based, 3D reconstruction models to generate a mesh purely from the camera inputs. It will be integrated with the SceneScape Web UI to provide a seamless workflow for configuring a scene.

The current set of models the service will support out-of-the-box are:

- **MapAnything**: Universal Feed-Forward Metric 3D Reconstruction (Apache 2.0 license)
- **VGGT**: Visual Geometry Grounded Transformer for sparse view reconstruction

#### Core Architecture Principles

1. **Plugin Interface**: Defines a standard API all models must implement. Easy to maintain and extend as the state-of-the-art in 3D reconstruction evolves.

2. **Unified API**: All model-specific containers expose the same REST API endpoints.

3. **Consistent Output**: Output mesh pose and camera poses are consistent irrespective of model chosen.

## Alternatives Considered

1. Alternatives to a Mapping Service:
   - Documentation that educates how to leverage these models to generate a glb and import the glb
   - Map generation tool that is run once to generate mesh and provide camera coordinates
     Pros:
     - Lower effort of development and maintenance
       Cons:
     - Workflows still requires time and skill to configure the scene
     - Multiple points of failure
     - Not dynamic to handle evolving scenes, changing camera parameters (intrinsic and extrinsic), adding new cameras.
2. Alternative methods for reconstruction:
   - Dust3R, NeuralRecon, NoPoSplat etc.
     Each alternative has one or more of these cons:
     - Not state-of-the-art
     - Not end-to-end
     - Require a GPU for acceptable performance
     - Do not work with sparse camera views
     - Require camera poses

## References

- [MapAnything Repository](https://github.com/facebookresearch/map-anything): Original MapAnything model
- [VGGT Repository](https://github.com/facebookresearch/vggt): Original VGGT model

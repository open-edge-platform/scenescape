# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Generated from observation_processor/proto/observation_processor.proto - do not edit.
# pylint: skip-file
# flake8: noqa
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ConditioningMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CONDITIONING_MODE_AUTO: _ClassVar[ConditioningMode]
    CONDITIONING_MODE_FULL: _ClassVar[ConditioningMode]
    CONDITIONING_MODE_FRUSTUM_ONLY: _ClassVar[ConditioningMode]

class MeasurementStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MEASUREMENT_STATUS_UNSPECIFIED: _ClassVar[MeasurementStatus]
    MEASUREMENT_STATUS_OK: _ClassVar[MeasurementStatus]
    MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE: _ClassVar[MeasurementStatus]

class DepthSource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DEPTH_SOURCE_UNSPECIFIED: _ClassVar[DepthSource]
    DEPTH_SOURCE_FRUSTUM: _ClassVar[DepthSource]
    DEPTH_SOURCE_AMODAL: _ClassVar[DepthSource]
    DEPTH_SOURCE_MESH_FOOT: _ClassVar[DepthSource]

class ImageEdge(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    IMAGE_EDGE_UNSPECIFIED: _ClassVar[ImageEdge]
    IMAGE_EDGE_LEFT: _ClassVar[ImageEdge]
    IMAGE_EDGE_RIGHT: _ClassVar[ImageEdge]
    IMAGE_EDGE_TOP: _ClassVar[ImageEdge]
    IMAGE_EDGE_BOTTOM: _ClassVar[ImageEdge]
CONDITIONING_MODE_AUTO: ConditioningMode
CONDITIONING_MODE_FULL: ConditioningMode
CONDITIONING_MODE_FRUSTUM_ONLY: ConditioningMode
MEASUREMENT_STATUS_UNSPECIFIED: MeasurementStatus
MEASUREMENT_STATUS_OK: MeasurementStatus
MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE: MeasurementStatus
DEPTH_SOURCE_UNSPECIFIED: DepthSource
DEPTH_SOURCE_FRUSTUM: DepthSource
DEPTH_SOURCE_AMODAL: DepthSource
DEPTH_SOURCE_MESH_FOOT: DepthSource
IMAGE_EDGE_UNSPECIFIED: ImageEdge
IMAGE_EDGE_LEFT: ImageEdge
IMAGE_EDGE_RIGHT: ImageEdge
IMAGE_EDGE_TOP: ImageEdge
IMAGE_EDGE_BOTTOM: ImageEdge

class ProcessDetectionsRequest(_message.Message):
    __slots__ = ("scene_id", "camera_id", "timestamp", "mode", "detections", "include_diagnostics")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    CAMERA_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_DIAGNOSTICS_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    camera_id: str
    timestamp: _timestamp_pb2.Timestamp
    mode: ConditioningMode
    detections: _containers.RepeatedCompositeFieldContainer[CameraDetection]
    include_diagnostics: bool
    def __init__(self, scene_id: _Optional[str] = ..., camera_id: _Optional[str] = ..., timestamp: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., mode: _Optional[_Union[ConditioningMode, str]] = ..., detections: _Optional[_Iterable[_Union[CameraDetection, _Mapping]]] = ..., include_diagnostics: bool = ...) -> None: ...

class CameraDetection(_message.Message):
    __slots__ = ("detection_id", "category", "bounding_box_px", "axis_aware_sizing", "project_to_map")
    DETECTION_ID_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    BOUNDING_BOX_PX_FIELD_NUMBER: _ClassVar[int]
    AXIS_AWARE_SIZING_FIELD_NUMBER: _ClassVar[int]
    PROJECT_TO_MAP_FIELD_NUMBER: _ClassVar[int]
    detection_id: str
    category: str
    bounding_box_px: BoundingBoxPx
    axis_aware_sizing: bool
    project_to_map: bool
    def __init__(self, detection_id: _Optional[str] = ..., category: _Optional[str] = ..., bounding_box_px: _Optional[_Union[BoundingBoxPx, _Mapping]] = ..., axis_aware_sizing: bool = ..., project_to_map: bool = ...) -> None: ...

class BoundingBoxPx(_message.Message):
    __slots__ = ("x", "y", "width", "height")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    width: float
    height: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., width: _Optional[float] = ..., height: _Optional[float] = ...) -> None: ...

class ProcessDetectionsResponse(_message.Message):
    __slots__ = ("scene_id", "camera_id", "timestamp", "mode", "measurements")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    CAMERA_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    MEASUREMENTS_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    camera_id: str
    timestamp: _timestamp_pb2.Timestamp
    mode: ConditioningMode
    measurements: _containers.RepeatedCompositeFieldContainer[DetectionMeasurement]
    def __init__(self, scene_id: _Optional[str] = ..., camera_id: _Optional[str] = ..., timestamp: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., mode: _Optional[_Union[ConditioningMode, str]] = ..., measurements: _Optional[_Iterable[_Union[DetectionMeasurement, _Mapping]]] = ...) -> None: ...

class DetectionMeasurement(_message.Message):
    __slots__ = ("detection_id", "status", "measurement", "depth_source", "frustum", "amodal")
    DETECTION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MEASUREMENT_FIELD_NUMBER: _ClassVar[int]
    DEPTH_SOURCE_FIELD_NUMBER: _ClassVar[int]
    FRUSTUM_FIELD_NUMBER: _ClassVar[int]
    AMODAL_FIELD_NUMBER: _ClassVar[int]
    detection_id: str
    status: MeasurementStatus
    measurement: Measurement
    depth_source: DepthSource
    frustum: FrustumGaussian
    amodal: AmodalConditioning
    def __init__(self, detection_id: _Optional[str] = ..., status: _Optional[_Union[MeasurementStatus, str]] = ..., measurement: _Optional[_Union[Measurement, _Mapping]] = ..., depth_source: _Optional[_Union[DepthSource, str]] = ..., frustum: _Optional[_Union[FrustumGaussian, _Mapping]] = ..., amodal: _Optional[_Union[AmodalConditioning, _Mapping]] = ...) -> None: ...

class Measurement(_message.Message):
    __slots__ = ("mean", "noise_covariance", "z_measured", "has_orientation")
    MEAN_FIELD_NUMBER: _ClassVar[int]
    NOISE_COVARIANCE_FIELD_NUMBER: _ClassVar[int]
    Z_MEASURED_FIELD_NUMBER: _ClassVar[int]
    HAS_ORIENTATION_FIELD_NUMBER: _ClassVar[int]
    mean: _containers.RepeatedScalarFieldContainer[float]
    noise_covariance: _containers.RepeatedScalarFieldContainer[float]
    z_measured: bool
    has_orientation: bool
    def __init__(self, mean: _Optional[_Iterable[float]] = ..., noise_covariance: _Optional[_Iterable[float]] = ..., z_measured: bool = ..., has_orientation: bool = ...) -> None: ...

class FrustumGaussian(_message.Message):
    __slots__ = ("ray_origin", "ray", "mean", "covariance", "depth_est", "depth_sigma", "depth_lo", "depth_hi", "score", "edge_valid_mask")
    RAY_ORIGIN_FIELD_NUMBER: _ClassVar[int]
    RAY_FIELD_NUMBER: _ClassVar[int]
    MEAN_FIELD_NUMBER: _ClassVar[int]
    COVARIANCE_FIELD_NUMBER: _ClassVar[int]
    DEPTH_EST_FIELD_NUMBER: _ClassVar[int]
    DEPTH_SIGMA_FIELD_NUMBER: _ClassVar[int]
    DEPTH_LO_FIELD_NUMBER: _ClassVar[int]
    DEPTH_HI_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    EDGE_VALID_MASK_FIELD_NUMBER: _ClassVar[int]
    ray_origin: Vector3
    ray: Vector3
    mean: Vector3
    covariance: _containers.RepeatedScalarFieldContainer[float]
    depth_est: float
    depth_sigma: float
    depth_lo: float
    depth_hi: float
    score: float
    edge_valid_mask: int
    def __init__(self, ray_origin: _Optional[_Union[Vector3, _Mapping]] = ..., ray: _Optional[_Union[Vector3, _Mapping]] = ..., mean: _Optional[_Union[Vector3, _Mapping]] = ..., covariance: _Optional[_Iterable[float]] = ..., depth_est: _Optional[float] = ..., depth_sigma: _Optional[float] = ..., depth_lo: _Optional[float] = ..., depth_hi: _Optional[float] = ..., score: _Optional[float] = ..., edge_valid_mask: _Optional[int] = ...) -> None: ...

class AmodalConditioning(_message.Message):
    __slots__ = ("depth", "depth_variance")
    DEPTH_FIELD_NUMBER: _ClassVar[int]
    DEPTH_VARIANCE_FIELD_NUMBER: _ClassVar[int]
    depth: float
    depth_variance: float
    def __init__(self, depth: _Optional[float] = ..., depth_variance: _Optional[float] = ...) -> None: ...

class Vector3(_message.Message):
    __slots__ = ("x", "y", "z")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ...) -> None: ...

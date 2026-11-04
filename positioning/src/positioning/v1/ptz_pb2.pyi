# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Generated from docs/user-guide/api-docs/positioning/v1/ptz.proto - do not edit.
# pylint: skip-file
# flake8: noqa
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ReportedMoveStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    REPORTED_MOVE_STATUS_UNSPECIFIED: _ClassVar[ReportedMoveStatus]
    REPORTED_MOVE_STATUS_IDLE: _ClassVar[ReportedMoveStatus]
    REPORTED_MOVE_STATUS_MOVING: _ClassVar[ReportedMoveStatus]

class PTZSampleResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PTZ_SAMPLE_RESULT_UNSPECIFIED: _ClassVar[PTZSampleResult]
    PTZ_SAMPLE_RESULT_ACCEPTED: _ClassVar[PTZSampleResult]
    PTZ_SAMPLE_RESULT_DUPLICATE: _ClassVar[PTZSampleResult]
    PTZ_SAMPLE_RESULT_OUT_OF_ORDER: _ClassVar[PTZSampleResult]
    PTZ_SAMPLE_RESULT_UNKNOWN_CAMERA: _ClassVar[PTZSampleResult]
    PTZ_SAMPLE_RESULT_INVALID: _ClassVar[PTZSampleResult]
REPORTED_MOVE_STATUS_UNSPECIFIED: ReportedMoveStatus
REPORTED_MOVE_STATUS_IDLE: ReportedMoveStatus
REPORTED_MOVE_STATUS_MOVING: ReportedMoveStatus
PTZ_SAMPLE_RESULT_UNSPECIFIED: PTZSampleResult
PTZ_SAMPLE_RESULT_ACCEPTED: PTZSampleResult
PTZ_SAMPLE_RESULT_DUPLICATE: PTZSampleResult
PTZ_SAMPLE_RESULT_OUT_OF_ORDER: PTZSampleResult
PTZ_SAMPLE_RESULT_UNKNOWN_CAMERA: PTZSampleResult
PTZ_SAMPLE_RESULT_INVALID: PTZSampleResult

class PTZSample(_message.Message):
    __slots__ = ("camera_id", "adapter_instance_id", "sequence", "measured_at", "timestamp_uncertainty_ns", "position", "reported_move_status")
    CAMERA_ID_FIELD_NUMBER: _ClassVar[int]
    ADAPTER_INSTANCE_ID_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    MEASURED_AT_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_UNCERTAINTY_NS_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    REPORTED_MOVE_STATUS_FIELD_NUMBER: _ClassVar[int]
    camera_id: str
    adapter_instance_id: str
    sequence: int
    measured_at: _timestamp_pb2.Timestamp
    timestamp_uncertainty_ns: int
    position: PTZPosition
    reported_move_status: ReportedMoveStatus
    def __init__(self, camera_id: _Optional[str] = ..., adapter_instance_id: _Optional[str] = ..., sequence: _Optional[int] = ..., measured_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., timestamp_uncertainty_ns: _Optional[int] = ..., position: _Optional[_Union[PTZPosition, _Mapping]] = ..., reported_move_status: _Optional[_Union[ReportedMoveStatus, str]] = ...) -> None: ...

class PTZPosition(_message.Message):
    __slots__ = ("pan", "tilt", "zoom", "position_space_uri", "pan_min", "pan_max", "tilt_min", "tilt_max")
    PAN_FIELD_NUMBER: _ClassVar[int]
    TILT_FIELD_NUMBER: _ClassVar[int]
    ZOOM_FIELD_NUMBER: _ClassVar[int]
    POSITION_SPACE_URI_FIELD_NUMBER: _ClassVar[int]
    PAN_MIN_FIELD_NUMBER: _ClassVar[int]
    PAN_MAX_FIELD_NUMBER: _ClassVar[int]
    TILT_MIN_FIELD_NUMBER: _ClassVar[int]
    TILT_MAX_FIELD_NUMBER: _ClassVar[int]
    pan: float
    tilt: float
    zoom: float
    position_space_uri: str
    pan_min: float
    pan_max: float
    tilt_min: float
    tilt_max: float
    def __init__(self, pan: _Optional[float] = ..., tilt: _Optional[float] = ..., zoom: _Optional[float] = ..., position_space_uri: _Optional[str] = ..., pan_min: _Optional[float] = ..., pan_max: _Optional[float] = ..., tilt_min: _Optional[float] = ..., tilt_max: _Optional[float] = ...) -> None: ...

class PTZSampleAck(_message.Message):
    __slots__ = ("result", "detail", "accepted_sequence")
    RESULT_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    ACCEPTED_SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    result: PTZSampleResult
    detail: str
    accepted_sequence: int
    def __init__(self, result: _Optional[_Union[PTZSampleResult, str]] = ..., detail: _Optional[str] = ..., accepted_sequence: _Optional[int] = ...) -> None: ...

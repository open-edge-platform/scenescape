#!/usr/bin/env python3
"""
Unified Serialization Benchmark for Tracker Messages

Tests serialization/deserialization performance for:
- Detection messages (DetectionMessage)
- Regulated messages (RegulatedMessage)

With formats:
- JSON (orjson)
- Protocol Buffers
- FlatBuffers
"""

from pathlib import Path
import sys
import pytest
import orjson
import flatbuffers

# Add generated code to path
benchmark_dir = Path(__file__).parent.parent
data_dir = benchmark_dir / 'data'
sys.path.insert(0, str(Path(__file__).parent / 'generated' / 'proto'))
sys.path.insert(0, str(Path(__file__).parent / 'generated' / 'fbs'))

# Import protobuf classes
import detection_message_pb2 as detection_pb
import regulated_message_pb2 as regulated_pb

# Import FlatBuffers classes
import SceneScape.Tracker.DetectionMessage as DetectionMessageFB
import SceneScape.Tracker.DetectedObjects as DetectedObjectsFB
import SceneScape.Tracker.DetectedObject as DetectedObjectFB
import SceneScape.Tracker.Point as PointFB
from scenescape.tracker.regulated.fb import (
    Box, Vector3, Quaternion, CameraBound, CameraRate,
    RegulatedObject, RegulatedMessage
)

#=============================================================================
# Detection Message Builders
#=============================================================================

def build_detection_protobuf(json_data):
    """Convert JSON dict to protobuf DetectionMessage object."""
    msg = detection_pb.DetectionMessage()
    msg.id = json_data['id']
    msg.debug_mac = json_data['debug_mac']
    msg.timestamp = json_data['timestamp']
    msg.debug_timestamp_end = json_data['debug_timestamp_end']
    msg.debug_processing_time = json_data['debug_processing_time']
    msg.rate = json_data['rate']
    
    for person_data in json_data['objects']['person']:
        person = msg.objects.person.add()
        person.category = person_data['category']
        person.confidence = person_data['confidence']
        person.id = person_data['id']
        
        person.center_of_mass.x = person_data['center_of_mass']['x']
        person.center_of_mass.y = person_data['center_of_mass']['y']
        person.center_of_mass.width = person_data['center_of_mass']['width']
        person.center_of_mass.height = person_data['center_of_mass']['height']
        
        person.bounding_box_px.x = person_data['bounding_box_px']['x']
        person.bounding_box_px.y = person_data['bounding_box_px']['y']
        person.bounding_box_px.width = person_data['bounding_box_px']['width']
        person.bounding_box_px.height = person_data['bounding_box_px']['height']
    
    return msg


def build_detection_flatbuffers(json_data):
    """Convert JSON dict to FlatBuffers DetectionMessage."""
    builder = flatbuffers.Builder(1024 * 16)
    
    # Build person objects
    person_offsets = []
    for person_data in json_data['objects']['person']:
        category = builder.CreateString(person_data['category'])
        
        # Build center of mass
        PointFB.Start(builder)
        PointFB.AddX(builder, person_data['center_of_mass']['x'])
        PointFB.AddY(builder, person_data['center_of_mass']['y'])
        PointFB.AddWidth(builder, person_data['center_of_mass']['width'])
        PointFB.AddHeight(builder, person_data['center_of_mass']['height'])
        com_offset = PointFB.End(builder)
        
        # Build bounding box
        PointFB.Start(builder)
        PointFB.AddX(builder, person_data['bounding_box_px']['x'])
        PointFB.AddY(builder, person_data['bounding_box_px']['y'])
        PointFB.AddWidth(builder, person_data['bounding_box_px']['width'])
        PointFB.AddHeight(builder, person_data['bounding_box_px']['height'])
        bbox_offset = PointFB.End(builder)
        
        # Build person object
        DetectedObjectFB.Start(builder)
        DetectedObjectFB.AddCategory(builder, category)
        DetectedObjectFB.AddConfidence(builder, person_data['confidence'])
        DetectedObjectFB.AddCenterOfMass(builder, com_offset)
        DetectedObjectFB.AddBoundingBoxPx(builder, bbox_offset)
        DetectedObjectFB.AddId(builder, person_data['id'])
        person_offsets.append(DetectedObjectFB.End(builder))
    
    # Build DetectedObjects
    DetectedObjectsFB.StartPersonVector(builder, len(person_offsets))
    for offset in reversed(person_offsets):
        builder.PrependUOffsetTRelative(offset)
    person_vector = builder.EndVector()
    
    DetectedObjectsFB.Start(builder)
    DetectedObjectsFB.AddPerson(builder, person_vector)
    objects_offset = DetectedObjectsFB.End(builder)
    
    # Build DetectionMessage
    id_str = builder.CreateString(json_data['id'])
    debug_mac = builder.CreateString(json_data['debug_mac'])
    timestamp = builder.CreateString(json_data['timestamp'])
    debug_timestamp_end = builder.CreateString(json_data['debug_timestamp_end'])
    
    DetectionMessageFB.Start(builder)
    DetectionMessageFB.AddId(builder, id_str)
    DetectionMessageFB.AddDebugMac(builder, debug_mac)
    DetectionMessageFB.AddTimestamp(builder, timestamp)
    DetectionMessageFB.AddDebugTimestampEnd(builder, debug_timestamp_end)
    DetectionMessageFB.AddDebugProcessingTime(builder, json_data['debug_processing_time'])
    DetectionMessageFB.AddRate(builder, json_data['rate'])
    DetectionMessageFB.AddObjects(builder, objects_offset)
    detection_offset = DetectionMessageFB.End(builder)
    
    builder.Finish(detection_offset)
    return bytes(builder.Output())


#=============================================================================
# Regulated Message Builders
#=============================================================================

def build_regulated_protobuf(json_data):
    """Convert JSON dict to protobuf RegulatedMessage object."""
    msg = regulated_pb.RegulatedMessage()
    msg.timestamp = json_data['timestamp']
    msg.id = json_data['id']
    msg.name = json_data['name']
    msg.scene_rate = json_data['scene_rate']
    
    for camera_id, rate in json_data['rate'].items():
        msg.rate[camera_id] = rate
    
    for obj_data in json_data['objects']:
        obj = msg.objects.add()
        obj.category = obj_data['category']
        obj.confidence = obj_data['confidence']
        obj.id = obj_data['id']
        obj.type = obj_data['type']
        obj.first_seen = obj_data['first_seen']
        
        obj.center_of_mass.x = obj_data['center_of_mass']['x']
        obj.center_of_mass.y = obj_data['center_of_mass']['y']
        obj.center_of_mass.width = obj_data['center_of_mass']['width']
        obj.center_of_mass.height = obj_data['center_of_mass']['height']
        
        obj.translation.x = obj_data['translation'][0]
        obj.translation.y = obj_data['translation'][1]
        obj.translation.z = obj_data['translation'][2]
        
        obj.size.x = obj_data['size'][0]
        obj.size.y = obj_data['size'][1]
        obj.size.z = obj_data['size'][2]
        
        obj.velocity.x = obj_data['velocity'][0]
        obj.velocity.y = obj_data['velocity'][1]
        obj.velocity.z = obj_data['velocity'][2]
        
        obj.rotation.x = obj_data['rotation'][0]
        obj.rotation.y = obj_data['rotation'][1]
        obj.rotation.z = obj_data['rotation'][2]
        obj.rotation.w = obj_data['rotation'][3]
        
        obj.visibility.extend(obj_data['visibility'])
        
        if obj_data['similarity'] is not None:
            obj.similarity = obj_data['similarity']
        
        for camera_id, bounds in obj_data['camera_bounds'].items():
            cam_bound = obj.camera_bounds[camera_id]
            cam_bound.x = bounds['x']
            cam_bound.y = bounds['y']
            cam_bound.width = bounds['width']
            cam_bound.height = bounds['height']
    
    return msg


def build_regulated_flatbuffers(json_data):
    """Convert JSON dict to FlatBuffers RegulatedMessage."""
    builder = flatbuffers.Builder(1024 * 64)
    
    # Build rate entries
    rate_offsets = []
    for camera_id, rate in json_data['rate'].items():
        camera_str = builder.CreateString(camera_id)
        CameraRate.CameraRateStart(builder)
        CameraRate.CameraRateAddCameraId(builder, camera_str)
        CameraRate.CameraRateAddRate(builder, rate)
        rate_offsets.append(CameraRate.CameraRateEnd(builder))
    
    CameraRate.CameraRateStartRateVector(builder, len(rate_offsets))
    for offset in reversed(rate_offsets):
        builder.PrependUOffsetTRelative(offset)
    rate_vector = builder.EndVector()
    
    # Build objects
    object_offsets = []
    for obj_data in json_data['objects']:
        category = builder.CreateString(obj_data['category'])
        obj_id = builder.CreateString(obj_data['id'])
        obj_type = builder.CreateString(obj_data['type'])
        first_seen = builder.CreateString(obj_data['first_seen'])
        
        # Build visibility
        visibility_offsets = [builder.CreateString(v) for v in obj_data['visibility']]
        RegulatedObject.RegulatedObjectStartVisibilityVector(builder, len(visibility_offsets))
        for offset in reversed(visibility_offsets):
            builder.PrependUOffsetTRelative(offset)
        visibility_vector = builder.EndVector()
        
        # Build camera bounds
        bounds_offsets = []
        for camera_id, bounds in obj_data['camera_bounds'].items():
            camera_str = builder.CreateString(camera_id)
            
            Box.BoxStart(builder)
            Box.BoxAddX(builder, bounds['x'])
            Box.BoxAddY(builder, bounds['y'])
            Box.BoxAddWidth(builder, bounds['width'])
            Box.BoxAddHeight(builder, bounds['height'])
            box_offset = Box.BoxEnd(builder)
            
            CameraBound.CameraBoundStart(builder)
            CameraBound.CameraBoundAddCameraId(builder, camera_str)
            CameraBound.CameraBoundAddBounds(builder, box_offset)
            bounds_offsets.append(CameraBound.CameraBoundEnd(builder))
        
        RegulatedObject.RegulatedObjectStartCameraBoundsVector(builder, len(bounds_offsets))
        for offset in reversed(bounds_offsets):
            builder.PrependUOffsetTRelative(offset)
        camera_bounds_vector = builder.EndVector()
        
        # Build center of mass
        Box.BoxStart(builder)
        Box.BoxAddX(builder, obj_data['center_of_mass']['x'])
        Box.BoxAddY(builder, obj_data['center_of_mass']['y'])
        Box.BoxAddWidth(builder, obj_data['center_of_mass']['width'])
        Box.BoxAddHeight(builder, obj_data['center_of_mass']['height'])
        com_offset = Box.BoxEnd(builder)
        
        # Build object
        RegulatedObject.RegulatedObjectStart(builder)
        RegulatedObject.RegulatedObjectAddCategory(builder, category)
        RegulatedObject.RegulatedObjectAddConfidence(builder, obj_data['confidence'])
        RegulatedObject.RegulatedObjectAddCenterOfMass(builder, com_offset)
        RegulatedObject.RegulatedObjectAddId(builder, obj_id)
        RegulatedObject.RegulatedObjectAddType(builder, obj_type)
        RegulatedObject.RegulatedObjectAddTranslation(builder, Vector3(
            obj_data['translation'][0], obj_data['translation'][1], obj_data['translation'][2]))
        RegulatedObject.RegulatedObjectAddSize(builder, Vector3(
            obj_data['size'][0], obj_data['size'][1], obj_data['size'][2]))
        RegulatedObject.RegulatedObjectAddVelocity(builder, Vector3(
            obj_data['velocity'][0], obj_data['velocity'][1], obj_data['velocity'][2]))
        RegulatedObject.RegulatedObjectAddRotation(builder, Quaternion(
            obj_data['rotation'][1], obj_data['rotation'][2], obj_data['rotation'][3], obj_data['rotation'][0]))
        RegulatedObject.RegulatedObjectAddVisibility(builder, visibility_vector)
        RegulatedObject.RegulatedObjectAddSimilarity(builder, obj_data['similarity'] or 0.0)
        RegulatedObject.RegulatedObjectAddFirstSeen(builder, first_seen)
        RegulatedObject.RegulatedObjectAddCameraBounds(builder, camera_bounds_vector)
        object_offsets.append(RegulatedObject.RegulatedObjectEnd(builder))
    
    RegulatedMessage.RegulatedMessageStartObjectsVector(builder, len(object_offsets))
    for offset in reversed(object_offsets):
        builder.PrependUOffsetTRelative(offset)
    objects_vector = builder.EndVector()
    
    # Build message
    timestamp = builder.CreateString(json_data['timestamp'])
    msg_id = builder.CreateString(json_data['id'])
    name = builder.CreateString(json_data['name'])
    
    RegulatedMessage.RegulatedMessageStart(builder)
    RegulatedMessage.RegulatedMessageAddTimestamp(builder, timestamp)
    RegulatedMessage.RegulatedMessageAddObjects(builder, objects_vector)
    RegulatedMessage.RegulatedMessageAddId(builder, msg_id)
    RegulatedMessage.RegulatedMessageAddName(builder, name)
    RegulatedMessage.RegulatedMessageAddSceneRate(builder, json_data['scene_rate'])
    RegulatedMessage.RegulatedMessageAddRate(builder, rate_vector)
    regulated_offset = RegulatedMessage.RegulatedMessageEnd(builder)
    
    builder.Finish(regulated_offset)
    return bytes(builder.Output())


#=============================================================================
# Fixtures
#=============================================================================

@pytest.fixture(scope='session')
def detection_json_1000():
    """Load detection message with 1000 objects."""
    return orjson.loads((data_dir / 'detection-message-1000.json').read_bytes())

@pytest.fixture(scope='session')
def regulated_json_1000():
    """Load regulated message with 1000 objects."""
    return orjson.loads((data_dir / 'regulated-message-1000.json').read_bytes())

# Pre-built messages for deserialization benchmarks
@pytest.fixture(scope='session')
def detection_pb_1000(detection_json_1000):
    return build_detection_protobuf(detection_json_1000).SerializeToString()

@pytest.fixture(scope='session')
def detection_fb_1000(detection_json_1000):
    return build_detection_flatbuffers(detection_json_1000)

@pytest.fixture(scope='session')
def regulated_pb_1000(regulated_json_1000):
    return build_regulated_protobuf(regulated_json_1000).SerializeToString()

@pytest.fixture(scope='session')
def regulated_fb_1000(regulated_json_1000):
    return build_regulated_flatbuffers(regulated_json_1000)


#=============================================================================
# Detection Message Benchmarks (1000 objects)
#=============================================================================

# JSON Serialize
def test_detection_json_serialize(benchmark, detection_json_1000):
    """Benchmark JSON serialization with 1000 objects."""
    benchmark(orjson.dumps, detection_json_1000)

# JSON Deserialize
def test_detection_json_deserialize(benchmark):
    """Benchmark JSON deserialization with 1000 objects."""
    json_bytes = (data_dir / 'detection-message-1000.json').read_bytes()
    benchmark(orjson.loads, json_bytes)

# Protobuf Serialize
def test_detection_protobuf_serialize(benchmark, detection_json_1000):
    """Benchmark Protobuf serialization with 1000 objects."""
    msg = build_detection_protobuf(detection_json_1000)
    benchmark(msg.SerializeToString)

# Protobuf Deserialize
def test_detection_protobuf_deserialize(benchmark, detection_pb_1000):
    """Benchmark Protobuf deserialization with 1000 objects."""
    def deserialize():
        msg = detection_pb.DetectionMessage()
        msg.ParseFromString(detection_pb_1000)
        return msg
    benchmark(deserialize)

# FlatBuffers Serialize
def test_detection_flatbuffers_serialize(benchmark, detection_json_1000):
    """Benchmark FlatBuffers serialization with 1000 objects."""
    benchmark(build_detection_flatbuffers, detection_json_1000)

# FlatBuffers Deserialize (zero-copy)
def test_detection_flatbuffers_deserialize(benchmark, detection_fb_1000):
    """Benchmark FlatBuffers deserialization with 1000 objects."""
    benchmark(DetectionMessageFB.DetectionMessage.GetRootAs, detection_fb_1000, 0)


#=============================================================================
# Regulated Message Benchmarks (1000 objects)
#=============================================================================

# JSON Serialize
def test_regulated_json_serialize(benchmark, regulated_json_1000):
    """Benchmark JSON serialization with 1000 objects."""
    benchmark(orjson.dumps, regulated_json_1000)

# JSON Deserialize
def test_regulated_json_deserialize(benchmark):
    """Benchmark JSON deserialization with 1000 objects."""
    json_bytes = (data_dir / 'regulated-message-1000.json').read_bytes()
    benchmark(orjson.loads, json_bytes)

# Protobuf Serialize
def test_regulated_protobuf_serialize(benchmark, regulated_json_1000):
    """Benchmark Protobuf serialization with 1000 objects."""
    msg = build_regulated_protobuf(regulated_json_1000)
    benchmark(msg.SerializeToString)

# Protobuf Deserialize
def test_regulated_protobuf_deserialize(benchmark, regulated_pb_1000):
    """Benchmark Protobuf deserialization with 1000 objects."""
    def deserialize():
        msg = regulated_pb.RegulatedMessage()
        msg.ParseFromString(regulated_pb_1000)
        return msg
    benchmark(deserialize)

# FlatBuffers Serialize
def test_regulated_flatbuffers_serialize(benchmark, regulated_json_1000):
    """Benchmark FlatBuffers serialization with 1000 objects."""
    benchmark(build_regulated_flatbuffers, regulated_json_1000)

# FlatBuffers Deserialize (zero-copy)
def test_regulated_flatbuffers_deserialize(benchmark, regulated_fb_1000):
    """Benchmark FlatBuffers deserialization with 1000 objects."""
    benchmark(RegulatedMessage.RegulatedMessage.GetRootAs, regulated_fb_1000, 0)

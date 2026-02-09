# DL Streamer Pipeline Server (DLSPS) Pipelines for Re-Identification (ReID)

This document provides example GStreamer pipelines for implementing person and vehicle re-identification scenarios using Intel DL Streamer Pipeline Server. Each pipeline includes both CPU and GPU variants, along with raw metadata output and SceneScape-processed metadata examples.

## Table of Contents

- [Overview](#overview)
- [Person Re-Identification](#person-re-identification)
  - [Gender and Age Classification](#gender-and-age-classification)
  - [Person Attributes Classification](#person-attributes-classification)
  - [Combined Person Metadata (Age, Gender, and Attributes with ReID)](#combined-person-metadata-age-gender-and-attributes-with-reid)
- [Vehicle Re-Identification](#vehicle-re-identification)
  - [Vehicle Color and Type Classification](#vehicle-color-and-type-classification)

## Overview

Re-identification (ReID) enables tracking and matching objects across different camera views or time periods. This document covers:

- **Person ReID**: Track individuals with optional age, gender, and attribute classification
- **Vehicle ReID**: Track vehicles with color and type classification

All pipelines are based on Intel OpenVINO models and can be deployed on edge devices with CPU or GPU acceleration.

### Key Features

- **Multiple Acceleration Options**: All pipelines support both CPU and GPU (with VA-API surface sharing for optimal performance)
- **Flexible Model Combinations**: Mix and match detection, classification, and re-identification models based on your use case
- **Rich Metadata Output**: Raw GStreamer metadata and processed SceneScape format for easy integration

### Model Information

The pipelines use the following Intel OpenVINO models:

**Person Detection & Classification:**

- `person-detection-retail-0013`: Person detection
- `age-gender-recognition-retail-0013`: Age and gender classification
- `person-attributes-recognition-crossroad-0238`: Physical attributes (bag, clothing, etc.)
- `person-reidentification-retail-0277`: ReID embeddings (256-dimensional vectors)

**Vehicle Detection & Classification:**

- `vehicle-detection-0200`: Vehicle detection
- `vehicle-attributes-recognition-barrier-0042`: Color and type classification

---

## Person Re-Identification

### Gender and Age Classification

These pipelines detect persons and classify their age and gender. They are based on the out-of-box (OOB) queuing scene use case.

<details>
<summary>CPU</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=CPU inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.xml model_proc=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.json device=CPU inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

**Example raw output metadata:**

```text
{
    "objects": [
        {
            "age": {
                "label": "20",
                "model": {
                    "name": "age_gender"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.7249742746353149,
                    "x_min": 0.609031081199646,
                    "y_max": 0.5583772659301758,
                    "y_min": 0.023048222064971924
                },
                "confidence": 0.9954169988632202,
                "label": "person",
                "label_id": 1
            },
            "gender": {
                "confidence": 0.8373871445655823,
                "label": "Female",
                "label_id": 0,
                "model": {
                    "name": "age_gender"
                }
            },
            "h": 385,
            "region_id": 1,
            "roi_type": "person",
            "tensors": [
                {
                    "confidence": 0.9954169988632202,
                    "label_id": 1,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "ResMobNet_v4 (LReLU) with single SSD head",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "data": [
                        0.20418204367160797
                    ],
                    "dims": [
                        1,
                        1,
                        1,
                        1
                    ],
                    "label": "20",
                    "layer_name": "age_conv3",
                    "layout": "ANY",
                    "model_name": "age_gender",
                    "name": "age",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.8373871445655823,
                    "data": [
                        0.8373871445655823,
                        0.1626128852367401
                    ],
                    "dims": [
                        1,
                        2,
                        1,
                        1
                    ],
                    "label": "Female",
                    "label_id": 0,
                    "layer_name": "prob",
                    "layout": "ANY",
                    "model_name": "age_gender",
                    "name": "gender",
                    "precision": "FP32"
                }
            ],
            "w": 148,
            "x": 780,
            "y": 17
        }
    ],
    "resolution": {
        "height": 720,
        "width": 1280
    },
    "tags": {},
    "timestamp": 13500000000
}
{
    "objects": [
        {
            "age": {
                "label": "21",
                "model": {
                    "name": "age_gender"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.7117733955383301,
                    "x_min": 0.6061434745788574,
                    "y_max": 0.556983232498169,
                    "y_min": 0.01952219009399414
                },
                "confidence": 0.9919682145118713,
                "label": "person",
                "label_id": 1
            },
            "gender": {
                "confidence": 0.8258437514305115,
                "label": "Male",
                "label_id": 1,
                "model": {
                    "name": "age_gender"
                }
            },
            "h": 387,
            "region_id": 1,
            "roi_type": "person",
            "tensors": [
                {
                    "confidence": 0.9919682145118713,
                    "label_id": 1,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "ResMobNet_v4 (LReLU) with single SSD head",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "data": [
                        0.2093944549560547
                    ],
                    "dims": [
                        1,
                        1,
                        1,
                        1
                    ],
                    "label": "21",
                    "layer_name": "age_conv3",
                    "layout": "ANY",
                    "model_name": "age_gender",
                    "name": "age",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.8258437514305115,
                    "data": [
                        0.17415624856948853,
                        0.8258437514305115
                    ],
                    "dims": [
                        1,
                        2,
                        1,
                        1
                    ],
                    "label": "Male",
                    "label_id": 1,
                    "layer_name": "prob",
                    "layout": "ANY",
                    "model_name": "age_gender",
                    "name": "gender",
                    "precision": "FP32"
                }
            ],
            "w": 135,
            "x": 776,
            "y": 14
        }
    ],
    "resolution": {
        "height": 720,
        "width": 1280
    },
    "tags": {},
    "timestamp": 13600000000
}
```

**Example SceneScape output metadata:**

```text
{
    "id": "atag-qcam1",
    "debug_mac": "8f:e9:3c:63:e8:f6",
    "timestamp": "2026-02-09T14:09:14.862Z",
    "debug_timestamp_end": "2026-02-09T14:09:17.585Z",
    "debug_processing_time": 2.723006248474121,
    "rate": 10.584537744588053,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9210688471794128,
                "center_of_mass": {
                    "x": 27,
                    "y": 95,
                    "width": 27.666666666666668,
                    "height": 67.25
                },
                "bounding_box_px": {
                    "x": 0,
                    "y": 29,
                    "width": 83,
                    "height": 269
                },
                "age": "32",
                "gender": "Male",
                "gender_model_confidence": 0.7973728775978088,
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "8f:e9:3c:63:e8:f6",
    "timestamp": "2026-02-09T14:09:15.162Z",
    "debug_timestamp_end": "2026-02-09T14:09:17.685Z",
    "debug_processing_time": 2.52290940284729,
    "rate": 10.584537744588053,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.7274594306945801,
                "center_of_mass": {
                    "x": 17,
                    "y": 153,
                    "width": 16.0,
                    "height": 40.0
                },
                "bounding_box_px": {
                    "x": 2,
                    "y": 114,
                    "width": 47,
                    "height": 160
                },
                "age": "48",
                "gender": "Male",
                "gender_model_confidence": 0.8721968531608582,
                "id": 1
            }
        ]
    }
}
```

</details>

<details>
<summary>CPU with REID</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=CPU inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.xml model_proc=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.json device=CPU inference-region=1 ! queue ! gvainference scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-reidentification-retail-0277/FP32/person-reidentification-retail-0277.xml device=CPU inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

Example raw output metadata:

[See JSON](./example_output/agegender_reid_cpu_raw.jsonl)

**Example SceneScape output metadata:**

```text
{
    "id": "atag-qcam1",
    "debug_mac": "25:70:bf:d5:c0:da",
    "timestamp": "2026-02-09T14:13:50.266Z",
    "debug_timestamp_end": "2026-02-09T14:13:53.914Z",
    "debug_processing_time": 3.648651599884033,
    "rate": 5.0,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9919352531433105,
                "center_of_mass": {
                    "x": 302,
                    "y": 96,
                    "width": 76.33333333333333,
                    "height": 87.0
                },
                "bounding_box_px": {
                    "x": 227,
                    "y": 10,
                    "width": 228,
                    "height": 348
                },
                "age": "40",
                "gender": "Male",
                "gender_model_confidence": 0.9240210652351379,
                "reid": "HJCnPpo7jj0JMUq/6PEUu4DTaj+igN6+Dx2TPjK8jr3Y1xG9+2bQvpeOD7/JBYG+kJSGvZBmAj8laRM/Hs/pvZpeab7j/jw/GHcJvmgx1z2ItDM/GjpMvIgjDr82c8s+CfHKvtUY6Ttp8MA+XqAIv7yX175u+Q8/1IqgvgrrSz/osH2/nrk2P4rVxD4KYF2/d+TUvsz2WD4+Qek+OnvWvmHR7z4aHlu+Y5wAv+tAJb5lS5G+EKIgPpsU3b2F3ke/0g8zvFPdDr8wfwc+Vd3PvnIxqL0+FwO/V3zFPrdUMD7EoPQ92IvvPk3vaz9LnNc9I+IMv9YoLD5g8ma+fCTvPqBaFj/Njy8+aPAvP+MGYz1U22E/5NUIP/RqhD5yxSG+Q46Pvevvgj7rn4u/yJiUvRl+CT80GEW+6vOVPaLIwr7xeI8/lqV4vg7Uzj7ilPW+PrJ9PwO1BD+iZQI/EUiXvkxS6j41PJ++DzQ1Pxj0fr91/0G93Vv0PSkcbT4+iQw+YLQMvryisT3xnbO+eMHmPlwtRj/Mmkc/gwc5PuhDcj4np6++9PwKP12+NT6quKq/AMAHv4Nsj77yIxS+1xPQvYsKsLqoaQK/6PSsPR6UKb+K0NY/qiYJv3J46r17gYM9/wK3PugSU7/gzQe/QchMv+dibL4mOV4/udozv5ho2TwLd6W9bOidvlqLDT9lRh+/Wu0iP9qUDT5YbAy/QrnVPmvqZT4/lTI+HwLhPkIllb4kVvA8SbAHP8IyWD/sPXQ+ZyJ1P08lPb8pL/w+Xo5jPai0P7+bYC6/sGdqP6SjG79iacE+9gFBP1sJFr69ppS+h8kkv5S3sT6utUW/flBWvmuus70kPia/i96Evk5Wxr7br8I+RxckPmycfD+4JZ2+7N85PvAMLz/w1Ta+gCijvrZOcj6Nh5W9WvbtvfolUT8Grai9rceHP9urHr5tgFu/z8v8viakOT+A3CO/P1k7vpIWWL+JyhA++BQwPR/mIT8eOv0+Ecwdv5OL3b7uXIO+IuwNP0n/p74NsRG/5A8YvaEThr4ARGq/TlMIP5YV3T5RwXK+v02Ev3FNib54cqw+w/udPkec5j0SfFi+IVUev1i3mr4MVtK+wFjZPbmwQj5s4gm/oAVZv9wNbT/EhZi+eeU0vwaKiL84wyA/MfgLP6UdFb4/UdU/obCdPze91b2MIzk+I8XRvroCGD9jva4+LdRrP/0PSL8tteQ8Awp0P1RjqT0kal4+lF5xP4Vq+j4NTW296WyyP6SJ+b1YZ+Y+xcjhO9mc9b61X8k9Bv11vuYuDb7lnYq+HznnvYPyjr1bt5Q9duARPc26ob46qNk9FN0bviAF5D6A4h8/J4Pdvg==",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "25:70:bf:d5:c0:da",
    "timestamp": "2026-02-09T14:13:50.268Z",
    "debug_timestamp_end": "2026-02-09T14:13:54.015Z",
    "debug_processing_time": 3.746978282928467,
    "rate": 5.0,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9963571429252625,
                "center_of_mass": {
                    "x": 268,
                    "y": 93,
                    "width": 72.0,
                    "height": 88.0
                },
                "bounding_box_px": {
                    "x": 197,
                    "y": 5,
                    "width": 216,
                    "height": 352
                },
                "age": "39",
                "gender": "Male",
                "gender_model_confidence": 0.8637242317199707,
                "reid": "BI3iPlOK/z0YEW6/ezcivvBUjj+gvzi//5TgPutKpb4ArDe+YFbovh5b+r79RoM+Y2pgvovHpD4u4WA/5nsRvqTknTzu0Cw/XxnjvhOS8D4iMWc/lq04vlusAL9Y848+gYVqvsYIJ76sqdM87M8Ov6ZC277XTSk/aBMCvwn8iD+J2Se/XJQYPxes5z5n3Dq/PRMkv5a9xr4X0D4/mP8Hv68Ouj5YBKC+7fLGvpN5Gb5BMcS+EmqvPfh3tr5UYAy/Q35GvlmOO7/xoRo+kaHZvpeiGz7WDdu+XPahPsP/uTy24z8+T/TTPpAWkj/QKZE+IpRJvhd+Rr7hWMy+8DW2Pvl16j5Fj+M9qFjLPvcmrTzTlF0/37CpPqbmAT81uCS+JiC/vkjQ9j5P2W2/fasBvr4bgz5kQve+fHjiPVvJn77VJzg/SIacvj4YZT7YA6W8xjaAP2xBJz9FpBU/UlPcvYJT8D4x8w2/coLkPn5icr89lcG9uEZxvQ6cIz69KiE+7vRxvugIRT4+v529VAOQPpScTj+fLzo/ZJQiPnrKmj3ioLG+w/juPlss3b7qTXS/fv7Ovq0QLb4E86y9jIXwvsFtJz5OVje+Ym70PhW0TL9W0L8/t7LsvuwtQL7AAoE9K/DdPlDXF7//gtW+JXoBv72mKL7d1gw/Os75vnD7zD04w8g9K7Uwv8D0dD7gJAG/R9i1PuOk2T6UKSO/+k6aPdeUNz1y9VM+nheLP9e1Eb4HGyo9MgodPxOsUD+ERfA9v92IP88+QL8935U+wc47PmRZKL9sTai+OedMPy9+Gr8VWuI9PdfcPg4JDL5QY/q+Ei3GvtP28D6o/Si/BB5IvYqs7j2kLRm/WPUVv9/M0b67d+8+/sUpPq2MXz+nsuG+TG3NPZMFAj9fLSG+3vuNPFShIL54Tj8+q8DNPW19OT9aoIw+fG1HP2rVj71Nezy/TvG4vgAf5z6ymCa/pEoDvtqd/L6PDjQ/O60CPlZHVD8iUkk/8ZUUv9fLtr4J37a+bEwgP/5hfr6SfjK+QlikvBK+rr7gEFi/9wOHPkUb0D4d/kS+k1Z2v3c41L4FOq69VAKkPj5cHj5gnZM9gOKzvuHvhj3XJr+93334vPuWsD7h+Cy/VTpDv8X1Pj/MpgS/JrZov/Oefb/EeUo/U3s2PxLgf74qVLA/K6lCP6g/274M9Gw+Yng8vknrQD+na64+UEpvPz8aqr6zSTm+ivMmP9ju0D1i3Uq9ZIWLP/g4GT+SY+69gjOpPw/1Sb6Xc80+j3QmPlxTAL+rm089dM6BvlntlbxZAxC+VBi7PWdSsz2nram8yPu8PFbCv77CDN28Y92Ivv/2WT43CYg+5wp0vg==",
                "id": 1
            }
        ]
    }
}
```

</details>

<details>
<summary>GPU</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw(memory:VAMemory) ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.xml model_proc=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! vapostproc ! video/x-raw,format=BGRA ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

**Example raw output metadata:**

```text
{
    "objects": [
        {
            "age": {
                "label": "21",
                "model": {
                    "name": "age_gender"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.2389734536409378,
                    "x_min": 0.11233659088611603,
                    "y_max": 0.5371507704257965,
                    "y_min": 0.0038546621799468994
                },
                "confidence": 0.98095703125,
                "label": "person",
                "label_id": 1
            },
            "gender": {
                "confidence": 0.52880859375,
                "label": "Male",
                "label_id": 1,
                "model": {
                    "name": "age_gender"
                }
            },
            "h": 384,
            "region_id": 1,
            "roi_type": "person",
            "tensors": [
                {
                    "confidence": 0.98095703125,
                    "label_id": 1,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "ResMobNet_v4 (LReLU) with single SSD head",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "data": [
                        0.2117919921875
                    ],
                    "dims": [
                        1,
                        1,
                        1,
                        1
                    ],
                    "label": "21",
                    "layer_name": "age_conv3",
                    "layout": "ANY",
                    "model_name": "age_gender",
                    "name": "age",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.52880859375,
                    "data": [
                        0.471435546875,
                        0.52880859375
                    ],
                    "dims": [
                        1,
                        2,
                        1,
                        1
                    ],
                    "label": "Male",
                    "label_id": 1,
                    "layer_name": "prob",
                    "layout": "ANY",
                    "model_name": "age_gender",
                    "name": "gender",
                    "precision": "FP32"
                }
            ],
            "w": 162,
            "x": 144,
            "y": 3
        },
        {
            "age": {
                "label": "22",
                "model": {
                    "name": "age_gender"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.9929608106613159,
                    "x_min": 0.9076164960861206,
                    "y_max": 1.0,
                    "y_min": 0.5140655040740967
                },
                "confidence": 0.51318359375,
                "label": "person",
                "label_id": 1
            },
            "gender": {
                "confidence": 0.97900390625,
                "label": "Male",
                "label_id": 1,
                "model": {
                    "name": "age_gender"
                }
            },
            "h": 350,
            "region_id": 2,
            "roi_type": "person",
            "tensors": [
                {
                    "confidence": 0.51318359375,
                    "label_id": 1,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "ResMobNet_v4 (LReLU) with single SSD head",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "data": [
                        0.215576171875
                    ],
                    "dims": [
                        1,
                        1,
                        1,
                        1
                    ],
                    "label": "22",
                    "layer_name": "age_conv3",
                    "layout": "ANY",
                    "model_name": "age_gender",
                    "name": "age",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.97900390625,
                    "data": [
                        0.0210418701171875,
                        0.97900390625
                    ],
                    "dims": [
                        1,
                        2,
                        1,
                        1
                    ],
                    "label": "Male",
                    "label_id": 1,
                    "layer_name": "prob",
                    "layout": "ANY",
                    "model_name": "age_gender",
                    "name": "gender",
                    "precision": "FP32"
                }
            ],
            "w": 109,
            "x": 1162,
            "y": 370
        }
    ],
    "resolution": {
        "height": 720,
        "width": 1280
    },
    "rtp": {
        "sequence": 157,
        "ssrc": 2627509403,
        "timestamp": 2644352413
    },
    "tags": {},
    "timestamp": 17200000000
}
{
    "objects": [
        {
            "age": {
                "label": "22",
                "model": {
                    "name": "age_gender"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.2433776706457138,
                    "x_min": 0.09513337910175323,
                    "y_max": 0.5219325125217438,
                    "y_min": 0.005645424127578735
                },
                "confidence": 0.986328125,
                "label": "person",
                "label_id": 1
            },
            "gender": {
                "confidence": 0.5400390625,
                "label": "Female",
                "label_id": 0,
                "model": {
                    "name": "age_gender"
                }
            },
            "h": 372,
            "region_id": 1,
            "roi_type": "person",
            "tensors": [
                {
                    "confidence": 0.986328125,
                    "label_id": 1,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "ResMobNet_v4 (LReLU) with single SSD head",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "data": [
                        0.219970703125
                    ],
                    "dims": [
                        1,
                        1,
                        1,
                        1
                    ],
                    "label": "22",
                    "layer_name": "age_conv3",
                    "layout": "ANY",
                    "model_name": "age_gender",
                    "name": "age",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.5400390625,
                    "data": [
                        0.5400390625,
                        0.4599609375
                    ],
                    "dims": [
                        1,
                        2,
                        1,
                        1
                    ],
                    "label": "Female",
                    "label_id": 0,
                    "layer_name": "prob",
                    "layout": "ANY",
                    "model_name": "age_gender",
                    "name": "gender",
                    "precision": "FP32"
                }
            ],
            "w": 190,
            "x": 122,
            "y": 4
        }
    ],
    "resolution": {
        "height": 720,
        "width": 1280
    },
    "rtp": {
        "sequence": 157,
        "ssrc": 2627509403,
        "timestamp": 2644352413
    },
    "tags": {},
    "timestamp": 17300000000
}
```

**Example SceneScape output metadata:**

```text
{
    "id": "atag-qcam1",
    "debug_mac": "9b:2e:b3:82:52:7b",
    "timestamp": "2026-02-09T14:08:20.417Z",
    "debug_timestamp_end": "2026-02-09T14:08:22.624Z",
    "debug_processing_time": 2.207106590270996,
    "rate": 9.947163685470464,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.99609375,
                "center_of_mass": {
                    "x": 859,
                    "y": 110,
                    "width": 58.0,
                    "height": 100.25
                },
                "bounding_box_px": {
                    "x": 802,
                    "y": 11,
                    "width": 174,
                    "height": 400
                },
                "age": "20",
                "gender": "Male",
                "gender_model_confidence": 0.6650390625,
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "9b:2e:b3:82:52:7b",
    "timestamp": "2026-02-09T14:08:20.508Z",
    "debug_timestamp_end": "2026-02-09T14:08:22.724Z",
    "debug_processing_time": 2.2153384685516357,
    "rate": 9.947163685470464,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9951171875,
                "center_of_mass": {
                    "x": 839,
                    "y": 110,
                    "width": 53.666666666666664,
                    "height": 95.5
                },
                "bounding_box_px": {
                    "x": 786,
                    "y": 16,
                    "width": 162,
                    "height": 382
                },
                "age": "20",
                "gender": "Female",
                "gender_model_confidence": 0.62890625,
                "id": 1
            }
        ]
    }
}
```

</details>

<details>
<summary>GPU with REID</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw(memory:VAMemory) ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.xml model_proc=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvainference scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-reidentification-retail-0277/FP32/person-reidentification-retail-0277.xml device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! vapostproc ! video/x-raw,format=BGRA ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

Example raw output metadata:

[See JSON](./example_output/agegender_reid_gpu_raw.jsonl)

**Example SceneScape output metadata:**

```text
{
    "id": "atag-qcam1",
    "debug_mac": "55:a6:67:ba:98:e1",
    "timestamp": "2026-02-09T14:12:55.645Z",
    "debug_timestamp_end": "2026-02-09T14:12:58.949Z",
    "debug_processing_time": 3.3045613765716553,
    "rate": 10.419819775033613,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9912109375,
                "center_of_mass": {
                    "x": 426,
                    "y": 93,
                    "width": 77.33333333333333,
                    "height": 85.25
                },
                "bounding_box_px": {
                    "x": 350,
                    "y": 8,
                    "width": 232,
                    "height": 341
                },
                "age": "43",
                "gender": "Male",
                "gender_model_confidence": 0.9111328125,
                "reid": "5NcqPxrdw77DKYC+DenivdpKAz/daxq+5MIwPcqxMb3Z/2Q+8bv8vk88oz1SKQ2/DkjmPViZGb7haR0/vieSvipogr5nMPE+zH1FPT/tWb7HgYE/v1cXv9P6Ir6mu/s9k1mHv0/uIb45h44+gr74vc65Jz8/v5c+J9ZPPkTAxj54IHo/usjIPpZGsL7Ydfi+znGyvmBfNL9EJvU+tWe0Pog6gT/m2z69ZjrGvgJa3L5r5Vi+OZ/YPftqIr9pm4u++6xwvoYeEr+SwrK9vO88v+YVEj6WmLy+OFhoPuQSeb1gjRC/gBuDPEUmnz+2g2O+eHwgvzBMmD2oujI//4iEvubjpb7fPRW+4c4nvlJHhL760NU+frITPxwEML4HGou+8zDivP/5hb3RclM/9gNOP07mEL/4sDg+zDpZPybqLL/sCb0+AGp2PJKilT4fnYa9ofHCPlrLiT7YnOk+fpcUv6/S/L5axRS/sG6pPdXEe75Mdsq9irT0PhqsJj568hA/HmrBvY7UAT7PYpE+Ig3DvaxbNj0AkQk9lGV5PX9M374AdWA/TfPJvie8h75EPV49sFAXP7WHMr8Q0Si/TcYeP/4Gab4Ypw2/mITDvvMcJb9ijBk/9qovv261tb4uc48+FdGSvvzVKL+HZwO/ZjWWv5GjDr+8/M09c8uUPb1N1D6IzOk+lVpSPkexgL54CNE907nIPij9l7++4ge/5ocZvfhu2jyExPE9Nhl/PxtKBD7Sp7C+fW0UP3TsTT8+ovs+vRmPPk23RL4WH2q/7McYv8idTL9JRDG/yoJzvXgmaz2MvDM/dkOuPlKEED/qkIk+VoWQvfPmYr/ZC2y/YGhTvrsS9L5PMc2+cTYsvpFdob1kGA8/otJjPzafTT9mwJA/GcoPP+4yEb72F+y+VP97vnjXLj/b9rI+bNvbPsDUEjyvpx2/MCBHv+UDrL2K+K8+Y2k6vhCMLT/g3X2+Eye3PA40W7+J8Gc/U7sSv0myIz9R87u+MhDlvp5ctr7U/Ja+0pG2PlMn+b5Qux49WG4Pv4/AB7+uvB+/6ucrPmLMxT6QE/g9lrEivo5MKr/ZxwM/Ok6rPqVuLb5JGBU/dI4qviwJdTxbz3K+Yd82vuTBr72E9CQ+y95PvwBc0jmnOIA9+SrcvXbJQr/arGk+ycmnPXf+Jr1AE1s/YAhCPIAU87u9cF2/pOE+P1ig6r7gD+E8WlR5P4DiDb6hpf4+a89ovmSNZT//R729YtEfP5QkVz7GMNG9QdUjv1QQjb3YYgw+My2sv+CuNT3l7YK+sYPOvgvVTb5Q/SC+jG8huwNqpb6RPta+jbfbvhjIJjwQZRi+TgRgvnAl/j4MdSi/O6sUvQ==",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "55:a6:67:ba:98:e1",
    "timestamp": "2026-02-09T14:12:55.745Z",
    "debug_timestamp_end": "2026-02-09T14:12:59.050Z",
    "debug_processing_time": 3.3049228191375732,
    "rate": 10.419819775033613,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9384765625,
                "center_of_mass": {
                    "x": 408,
                    "y": 90,
                    "width": 65.33333333333333,
                    "height": 86.75
                },
                "bounding_box_px": {
                    "x": 343,
                    "y": 5,
                    "width": 196,
                    "height": 346
                },
                "age": "38",
                "gender": "Male",
                "gender_model_confidence": 0.90283203125,
                "reid": "UvocP2xr+b7gd889w6MrvVsx6z4/jAi9z1/ZPmq3pz0yuYo+bFNCv8GPjT5NrwC/Pzk5vk2kgb36s0c/pJKivmJwwr4ybC8/8ItDvhmKmbtK7IM/oGIVv2iRHb78c3o+KYSVv/ztqr0gAB8/saQDvaXxMT+CmrE+Dn6DPnpKLj4IcFs/LD+nPgnvE79fikK/ySjDvcoGTb4P69o+/CqwPiUgeT8ShAc+qe8bvyYI+75oXl09gxRSPlscHr8ERgW/Y3DfvreXNb6RKyi9NjRlv5jm9D1lBxa/6Bo3PjP/Hr6PId2+dRocPhrdqT+Xbcy+OgFGv1o6Gz7wbTE/TGQsvqjPZr7U/5K+UF2Lvr1rBL95UCU+cKwyP7Ker71Ma6q+GAxxPepOBb17V0c/MsFeP2MXO7+8+h4/z7Z4P91ESL/FHhs/gVelvnZGhj4A6So7dBIbP7iCYz5mvLc+bcoIv1Nxjb4h6k6/yKqJPmsdGL/2nui6dVc2P3zRrD0s1hA/ZRGpvTItA75ufHo+zKHZPWRWdL3AucY9Pj0lPjJH2b6FeSw/LSL8vihGrb72HhY+jOgkP1C2b78cyhS/1DFGP/VyBr8Pgza/NcUkv9ByJr+kAAk/hU09v2gN5L7wIL0+2Zs5vr9SbL+0zV+/BrKcv2sASr8o5jI+Ly+WvQxj+D7SG5E+YTShPjDqhL7298g9Xj0hPyggh7/4ieq+YeXDvXx8Wz5yR6k+wOFTP+HPoT1QP5a+Cj09P046kD+sK8c+TErHPuhpHb6Cx2y/EN0ov+6BTb9f30a/GGVnPrnF3r1OgyA/kpjFPjoujj7mPVM+k+xkvq/VV79I3Wi/lyr0vULuWb8JDBW/heWHvhd9/r2NTQE/RjSCP4reMz8j868/0YvKPnFkLr4v2y2/JArhvAmN+j4kJ2w+zvDwPtzrUr4/mju/P4NOvyripb3Zqa8+G58bvYsUFz+vqO2+P7+JPXlUMr9cbkE/G2ABv97LGz/sNoK+xTkdvu532r77ZGO+YEnQPH84874zHjg+9OGfvhnvP794dVC/EvdSPu4f1D7Egr89Fv4sPk2nP7+AYk8/8C77Po0Dlb4Czwk/b1mlvpYRwb03eNm+G/GovsjADT2q2aI+m/nUvuiLvD04HQg/RGs9vknfgL/utJg+ZE7+PIK8i77KUXQ/UE8RPQEdDD4mnjC/bLsEP+8l5b4AeGw5yO53P0a0lb6Elc8+QNVrPJzeZj9ohXY9IIFcP7qntD4DdIK+uhgSvxMxcL1QmDY9mWq7v6Q4Qj5W7qC+Z3vxvlDMo765TYw9RkEKvuf93L7YG5W+nWDHvsbVD71TdqK+xY9zvs4w7T4btSK/wOgtPA==",
                "id": 1
            }
        ]
    }
}
```

</details>

### Person Attributes Classification

These pipelines detect persons and classify their physical attributes (bag, clothing, etc.) with a gender classification.

<details>
<summary>CPU</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=CPU inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.xml model_proc=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.json device=CPU inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

**Example raw output metadata:**

```text
{
    "objects": [
        {
            "detection": {
                "bounding_box": {
                    "x_max": 0.2936754822731018,
                    "x_min": 0.11932967603206635,
                    "y_max": 0.5053764581680298,
                    "y_min": 0.006453663110733032
                },
                "confidence": 0.9970619082450867,
                "label": "person",
                "label_id": 1
            },
            "h": 359,
            "person-attributes": {
                "confidence": 0.9034316539764404,
                "label": "M: has_longpants",
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "region_id": 1,
            "roi_type": "person",
            "tensors": [
                {
                    "confidence": 0.9970619082450867,
                    "label_id": 1,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "ResMobNet_v4 (LReLU) with single SSD head",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "confidence": 0.9034316539764404,
                    "data": [
                        0.9034316539764404,
                        0.4278976321220398,
                        0.051091331988573074,
                        0.4855940341949463,
                        0.8908972144126892,
                        0.03612656146287918,
                        0.18303154408931732
                    ],
                    "dims": [
                        1,
                        7
                    ],
                    "label": "M: has_longpants",
                    "layer_name": "attributes",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "person-attributes",
                    "precision": "FP32"
                }
            ],
            "w": 223,
            "x": 153,
            "y": 5
        }
    ],
    "resolution": {
        "height": 720,
        "width": 1280
    },
    "tags": {},
    "timestamp": 5000000000
}
{
    "objects": [
        {
            "detection": {
                "bounding_box": {
                    "x_max": 0.28621968626976013,
                    "x_min": 0.09097802639007568,
                    "y_max": 0.5112739205360413,
                    "y_min": 0.000809788703918457
                },
                "confidence": 0.9953031539916992,
                "label": "person",
                "label_id": 1
            },
            "h": 368,
            "person-attributes": {
                "confidence": 0.9799158573150635,
                "label": "M: has_bag has_longpants",
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "region_id": 1,
            "roi_type": "person",
            "tensors": [
                {
                    "confidence": 0.9953031539916992,
                    "label_id": 1,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "ResMobNet_v4 (LReLU) with single SSD head",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "confidence": 0.9799158573150635,
                    "data": [
                        0.9371567368507385,
                        0.6347797513008118,
                        0.012316623702645302,
                        0.48053136467933655,
                        0.9799158573150635,
                        0.014167477376759052,
                        0.05790301412343979
                    ],
                    "dims": [
                        1,
                        7
                    ],
                    "label": "M: has_bag has_longpants",
                    "layer_name": "attributes",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "person-attributes",
                    "precision": "FP32"
                }
            ],
            "w": 250,
            "x": 116,
            "y": 1
        }
    ],
    "resolution": {
        "height": 720,
        "width": 1280
    },
    "tags": {},
    "timestamp": 5100000000
}
```

**Example SceneScape output metadata:**

```text
{
    "id": "atag-qcam1",
    "debug_mac": "a9:ab:26:a4:1a:30",
    "timestamp": "2026-02-09T14:16:35.186Z",
    "debug_timestamp_end": "2026-02-09T14:16:37.808Z",
    "debug_processing_time": 2.622206687927246,
    "rate": 10.748823196028948,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9888612627983093,
                "center_of_mass": {
                    "x": 108,
                    "y": 87,
                    "width": 69.0,
                    "height": 79.5
                },
                "bounding_box_px": {
                    "x": 40,
                    "y": 8,
                    "width": 206,
                    "height": 319
                },
                "person-attributes": "F: has_bag has_longsleeves has_longpants has_longhair",
                "person-attributes_model_confidence": 0.965659499168396,
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "a9:ab:26:a4:1a:30",
    "timestamp": "2026-02-09T14:16:35.286Z",
    "debug_timestamp_end": "2026-02-09T14:16:37.908Z",
    "debug_processing_time": 2.6223485469818115,
    "rate": 10.560970853876366,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9806967377662659,
                "center_of_mass": {
                    "x": 95,
                    "y": 83,
                    "width": 76.66666666666667,
                    "height": 76.5
                },
                "bounding_box_px": {
                    "x": 19,
                    "y": 8,
                    "width": 230,
                    "height": 305
                },
                "person-attributes": "M: has_bag has_longsleeves has_longpants",
                "person-attributes_model_confidence": 0.9729161858558655,
                "id": 1
            }
        ]
    }
}
```

</details>

<details>
<summary>CPU with REID</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=CPU inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.xml model_proc=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.json device=CPU inference-region=1 ! queue ! gvainference scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-reidentification-retail-0277/FP32/person-reidentification-retail-0277.xml device=CPU inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

Example raw output metadata:

[See JSON](./example_output/personattr_reid_cpu_raw.jsonl)

**Example SceneScape output metadata:**

```text
{
    "id": "atag-qcam1",
    "debug_mac": "b9:ef:9a:d0:b5:9a",
    "timestamp": "2026-02-09T14:18:29.287Z",
    "debug_timestamp_end": "2026-02-09T14:18:32.812Z",
    "debug_processing_time": 3.5257043838500977,
    "rate": 8.86458507917628,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.7940923571586609,
                "center_of_mass": {
                    "x": 15,
                    "y": 161,
                    "width": 15.333333333333334,
                    "height": 30.5
                },
                "bounding_box_px": {
                    "x": 0,
                    "y": 131,
                    "width": 46,
                    "height": 122
                },
                "person-attributes": "M: has_bag has_longsleeves has_longpants",
                "person-attributes_model_confidence": 0.9634445905685425,
                "reid": "9jGVPypVAz7wNsC91o7+vjyl679s2Za/qqwfP2SLnD4hAgQ+6wigvoRYgD4zADO+lqoIP2IziD4aEJa75tUnvnKABb9qvB4/sBEIvt/oET4g+HC8HrSXvnK77LsjagG///Tdvp5c1b6Shx4/SHifPphZB78RuWU/G1kQPqr1nL7EDjm/nEh0P8agNj+gtci+Z+cdv05cXL+NYCw+xk5Xvr5CZz99Hru+cK7pPgPNar8k6Z6/e3EVPPJdub7xnCW+K6lxPtVOybzE8nm/arvMvlYhPb46fEy/Ob6uPjBOnT99eXe/TUM8PnQJBT3+1rg9VXK6vnshmL4hXJw/f5TAu0nyOz7QyMa/fNJRPoM0rL54dV67DzEuv+HSxD5bGdO+UY87v4an/j4J1fi+EPAjPXe2Jz+gXDy/VdcQPlaDcD4BcIg/PFcHv9X3mT7MSue+3Ywlv+w+rr7o2W2/dZUMP6/dNT98tNK9jdWgvRvnKL8K0ma9u50fv/p+Ir6D/qI+Lw3mPdn++D7lkbU9Yy6+PBu7gT8odyw/thhdvRNmxz7fdVW+qgOUvqOBrr47YYy9hWBTvp4MuL+tN1G/bQgyPcz1qL8+Lmu/RMkDvkwgnL60V1U/frw+P9J/dj6QDL2+ubLpvteXJD/7ypM8Szikv4jOv77pmYk/9P4uv4acwL5P9DM/Syc9PqTHWz8/Ys++RCtRP+PqB77K5Ke8mptvvqUfhj60BsY+rz6qPp+YZ77aIgc/KS5YPuHsnD61XsE+Yc2Ju8oWb79839E+VsyHvwBdl76x5Ru+g9qYPm69Jb/5Vxe+w40BP8ELsL5yX6w9/5ddvr6Ghz0I8VG/PU6dPpz2DD9jgRa+NTWIv+7gEL6lvBS+/qWTPangLT8pi40+/uKOP2Wb6j62S+++i4Asv9q3Ib5Otrg+5AuaPlRK+z00vRw+OUrqPQZBlr841p08a+c4viUopj55zUe/pU2dvjHeyr5ZLH2/ke8mP14lJb6LyYY+USeiviUGmT0MrLk9xmebPsnAbL6NdSo/1HqVv/GGCT9s4o2+FyltP4VLKz7CpiE+e9NOPlL0KD8+DIg+TVwQP32FYD8rmgG/QlnCvpZWDb8ek/Q+4RouPgemSb4HczY/2SqYv47yOj+5yso+3DGYvpS3FL+4Id0+1uJ/P2JD+72TPfE9MS1zP1ewHb/m5ry+HbbePlrHw726lrM+j5FeP+mpkL5ZKNq8Z69gvVmbdD16Mqe96iuVvjOdDz+gXd89e1u6PWoPGL6Nr06+m8UAv79Tz771Yww/i5myvf/jr71rCD0/F8fVvqle1b6NSCi/zNckvbSnhL3Rczi+uVz1vuv1rD4ZgIS8RWJpvw==",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "b9:ef:9a:d0:b5:9a",
    "timestamp": "2026-02-09T14:18:29.386Z",
    "debug_timestamp_end": "2026-02-09T14:18:32.912Z",
    "debug_processing_time": 3.5251872539520264,
    "rate": 8.86458507917628,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.5004321336746216,
                "center_of_mass": {
                    "x": 11,
                    "y": 178,
                    "width": 11.333333333333334,
                    "height": 24.5
                },
                "bounding_box_px": {
                    "x": 0,
                    "y": 154,
                    "width": 35,
                    "height": 99
                },
                "person-attributes": "M: has_longpants",
                "person-attributes_model_confidence": 0.7642964720726013,
                "reid": "8445PzyYjD8w2b0+F1BWv1nU4r//cjc+cAyEP7E7WT+1j906Stu4vV4vQr+Fsbq+8TR8P4LT3r7gF6S/f6hUvkn/p7/OZQ4+WPOgP7a/cL4xzaI+3wGavvBcgT6zTpc9QQwCP92mrD71ylw8fYkkPhZtFb8OjAQ94rK+vT49qT49cDu/L80JvwudsD6L9je/ASiJPp1BxD7MHwi/MgsGP5oVjj/s4Rg+/0mOvbQRQ74pT5W/AV4Bv02xcb49Oyw/kXoBP2ddN7/2BVO/zQe6viQOvr0cPo2/aSEqPmd9hj+f4Jy8F2x3vyLAFb9YTec/u74IPdYA7D3PfMg+ZcnUPvn8zz6FBd2/dqBdvc0BSj6IGw6/ip2Ovvxv2L6UXd48HauYvD+wsT6icHI+JYKHveaehTtLR4u+hDl1vdCExb5+soA/W5alPkoqPb4yzcy+TpCivUw8sb250Ke/ZTgPP8SKdT4Ynxm/HhH0Po9AEj4xmNS/EuT3vh60Kz8fTZw+fu3zPr2ePz8Uq7S+kMA2v5icIT8SoQs/96gNP4NVvD+uyc0+KRuRv4KnP74iRBg/RtyVPSqFir8gdQa/BRvkPf4hzL/IzV49IorrvnRfnz/jthS/erZlPzeKDz//pMW9y0YFPg+wID/LcN+9Fu8av764rr8X/CU//eSCv8sws7zEfdc+uU3zPquinz8yW5y/+KoOP7udGb/Nb2Q/SbPMPwExAT9QSHe+zzrIPtorBz7G2qC9n5cGvybF3r4zMbA+5gimv9Ya1b5VTyu/2VPav1X7vD61S4Y+Puh7vtxt4b4waVY9XPu4PT4Lez9v2E8/eGeZvWTBML4kBFq/19Q7Py8CcD87WLS+vAXSPg61pT45rNi+C1YQv9Nd5j7KENG+VxCnvjBZyryBmaM9mNavvgcmGr/hHqw9l7kNP9ICrb73cRc/2OM3P2Mvsr+gpMc+Y1ecPmaD2T5iL06/QbgcPQ+5zj2epOy+ZA7sPbvpyjw2yJ29d2l6P8iwQb9moMq9TpoCPkWPwD4L78U+WcVQvysmkjuF4kC+JbSePwn28z0HIgM/M/IhPzxwrT0O+Ky+Fh2gvvdzjD9Hg1m+NiAdPlfWQ7+Mt7G9RQwGv/bD1DuIkzA/A+gNPaJLR77zfTE/fbPnPo9apLmmcze9rk+MPzON0r9kr8q+1o4aPa36BL/kOsa8u1YKP9lph7/AwXI/Hk8wvuiVor6FfBG/ljDovmQjFr/lwTq/dRSlv/LRoj5AXog8QOjkPkDcaL6h1AO/UWcBv4II1j5tWxW+kvZlPn8wZb7KX4G8f82QvlfKMz+CLu2+mcN2P/cB9T5QE9G+Kh5VPbscLz4IpPA90G75vg==",
                "id": 1
            }
        ]
    }
}
```

</details>

<details>
<summary>GPU</summary>

**Pipeline:**

```text
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw(memory:VAMemory) ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.xml model_proc=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! vapostproc ! video/x-raw,format=BGRA ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

**Example raw output metadata:**

```text
{
    "objects": [
        {
            "detection": {
                "bounding_box": {
                    "x_max": 0.762357234954834,
                    "x_min": 0.6262110471725464,
                    "y_max": 0.5709785223007202,
                    "y_min": 0.014946818351745605
                },
                "confidence": 0.99609375,
                "label": "person",
                "label_id": 1
            },
            "h": 400,
            "person-attributes": {
                "confidence": 0.89453125,
                "label": "M: has_hat has_longsleeves has_longpants",
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "region_id": 1,
            "roi_type": "person",
            "tensors": [
                {
                    "confidence": 0.99609375,
                    "label_id": 1,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "ResMobNet_v4 (LReLU) with single SSD head",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "confidence": 0.89453125,
                    "data": [
                        0.89453125,
                        0.453857421875,
                        0.6845703125,
                        0.5322265625,
                        0.87451171875,
                        0.00826263427734375,
                        0.42333984375
                    ],
                    "dims": [
                        1,
                        7
                    ],
                    "label": "M: has_hat has_longsleeves has_longpants",
                    "layer_name": "attributes",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "person-attributes",
                    "precision": "FP32"
                }
            ],
            "w": 174,
            "x": 802,
            "y": 11
        }
    ],
    "resolution": {
        "height": 720,
        "width": 1280
    },
    "rtp": {
        "sequence": 155,
        "ssrc": 2627509404,
        "timestamp": 2610666395
    },
    "tags": {},
    "timestamp": 13200000000
}
{
    "objects": [
        {
            "detection": {
                "bounding_box": {
                    "x_max": 0.7490353584289551,
                    "x_min": 0.6269749402999878,
                    "y_max": 0.5585204064846039,
                    "y_min": 0.04181739687919617
                },
                "confidence": 0.9912109375,
                "label": "person",
                "label_id": 1
            },
            "h": 372,
            "person-attributes": {
                "confidence": 0.82373046875,
                "label": "M: has_bag has_longsleeves has_longpants has_coat_jacket",
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "region_id": 1,
            "roi_type": "person",
            "tensors": [
                {
                    "confidence": 0.9912109375,
                    "label_id": 1,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "ResMobNet_v4 (LReLU) with single SSD head",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "confidence": 0.82373046875,
                    "data": [
                        0.8076171875,
                        0.546875,
                        0.425048828125,
                        0.58349609375,
                        0.82373046875,
                        0.0914306640625,
                        0.5869140625
                    ],
                    "dims": [
                        1,
                        7
                    ],
                    "label": "M: has_bag has_longsleeves has_longpants has_coat_jacket",
                    "layer_name": "attributes",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "person-attributes",
                    "precision": "FP32"
                }
            ],
            "w": 156,
            "x": 803,
            "y": 30
        }
    ],
    "resolution": {
        "height": 720,
        "width": 1280
    },
    "rtp": {
        "sequence": 155,
        "ssrc": 2610666395,
        "timestamp": 2610666395
    },
    "tags": {},
    "timestamp": 13300000000
}
```

**Example SceneScape output metadata:**

```text
{
    "id": "atag-qcam1",
    "debug_mac": "a7:e9:dc:50:16:d9",
    "timestamp": "2026-02-09T14:15:45.001Z",
    "debug_timestamp_end": "2026-02-09T14:15:47.206Z",
    "debug_processing_time": 2.205275297164917,
    "rate": 10.063923088812928,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9931640625,
                "center_of_mass": {
                    "x": 453,
                    "y": 87,
                    "width": 66.66666666666667,
                    "height": 87.0
                },
                "bounding_box_px": {
                    "x": 387,
                    "y": 1,
                    "width": 200,
                    "height": 347
                },
                "person-attributes": "M: has_bag has_longpants",
                "person-attributes_model_confidence": 0.9091796875,
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "a7:e9:dc:50:16:d9",
    "timestamp": "2026-02-09T14:15:45.097Z",
    "debug_timestamp_end": "2026-02-09T14:15:47.309Z",
    "debug_processing_time": 2.2120001316070557,
    "rate": 10.063923088812928,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.994140625,
                "center_of_mass": {
                    "x": 437,
                    "y": 94,
                    "width": 75.66666666666667,
                    "height": 85.75
                },
                "bounding_box_px": {
                    "x": 362,
                    "y": 9,
                    "width": 227,
                    "height": 343
                },
                "person-attributes": "M: has_bag has_longpants",
                "person-attributes_model_confidence": 0.85888671875,
                "id": 1
            }
        ]
    }
}
```

</details>

<details>
<summary>GPU with REID</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw(memory:VAMemory) ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.xml model_proc=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvainference scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-reidentification-retail-0277/FP32/person-reidentification-retail-0277.xml device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! vapostproc ! video/x-raw,format=BGRA ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

Example raw output metadata:

[See JSON](./example_output/personattr_reid_gpu_raw.jsonl)

**Example SceneScape output metadata:**

```text
{
    "id": "atag-qcam1",
    "debug_mac": "97:0d:05:e8:81:94",
    "timestamp": "2026-02-09T14:20:08.184Z",
    "debug_timestamp_end": "2026-02-09T14:20:11.488Z",
    "debug_processing_time": 3.304837465286255,
    "rate": 10.547318264418443,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.986328125,
                "center_of_mass": {
                    "x": 570,
                    "y": 85,
                    "width": 67.0,
                    "height": 81.25
                },
                "bounding_box_px": {
                    "x": 503,
                    "y": 4,
                    "width": 201,
                    "height": 325
                },
                "person-attributes": "F: has_bag has_longsleeves has_longpants has_coat_jacket",
                "person-attributes_model_confidence": 0.86572265625,
                "reid": "dJU0P8SVCb+uUEu+JHXDPlT9Dz/VX9q+e7toPigx+77c3mY9FGKAv0EIr77DNgK/ywoQPvs+hT5oLk0+3u17PlAxzr5egqk+7hLJvg+b0r4IJXw/doPvvsxfFb9xMKK8Y2fxvm08tb5G8ZE+UBjqPW6wkT5epxQ+eQTkPkyQ4T3kb1s/HlQnP7aIsb0Q8g2/HS8fvwphTr/98wE/0Gx3PYGEVz8aBVU+qG8Lv7a5275SI7o+ZrMyvhVHPb/2cqq+5sICv2eC6b4b7yU+vBiOv7JZzD7fwgu/5ajgvEFpy72Zg16+egiWPhqctT+RMXq+SCMlv/3RFr0Y/Jo+sVWfvMjkujzQS3u+ePB/vSuZor4UsOw+W+QVP8M/ub6Vnle+gigmvhjMZT06Bos+cik3P8OJC79LgZA+svC1P91VD7/tZDM/qVSlvv8YNj8pGKK+R1r2PtAEJz7QT9s+3VGHvrYRpL7YQ4O/OMVtPirEj70vSZ0+bMShPpRUmL5Mcy4/IHXCPfj4sT3ZDTM+l1WGPrcz072DshI+Yx6uvrOx4b5092g/5JQnvgg+6b4gNYc8bpNIP6IyUb9z2Oy+omwwP4WShb5fb3C/AfH7vZrnbb8rago/xKJxvw60Hr6GbVY/hHloPvrf6L6FxzG/vS24v4M3I78oVay+MiUFPnAmyL2Q88U+irWAPSS4Cb7tdIC9jlVVPwb9iL/nShi/hWSFvnS3gz239fk+zFiWPijUVT52xOS+JiyCP2Cjiz9lKv0+LEb0PQIrEz2e42W/a5ZsvxMaB78gTh2/fPJYvj5eyj7YfS8/AJYYPuRSKD/cAWI+uNyvPjaHi7+7f1G/PWFmvqD59741+9m+fDQCve6YRL7p4o8/5lhbPwBhNz+90D4/K8P4Puz9rbx8w7e+dGHWvSwDsT4PSmc/1AdDP9PVCr+FEne+8NvlvsKT4r5i8S4+NPa5ve+r2T7Umog87za7PiO7FL/WhRc/BswXv39ogD4pHRi/GoCTvgJUjr4p+4y+QJ9UPZPZXb7+r+Y+0ge+vmseS7+r8gi/HAX0PY4+sj4q46Y+rRPJvkuhNL+jJws/BSa0Pkot7r14lBo/2L1KPs8fbT4VfAO/wHP+PORN+r0eyoY9IuEsv1ruCD8pp8g+guElPmIyU7/dALk+n6eCvgBMMTtKyyM/IB7hvozZwL427nG/RU/gPhI+5b1krh2+sdqVP4OsAL2nd08/xplsvhwN+j5hpo6+OjAVP6OFQD8dGhS+RI49v1O8fz3DkCq+13jCv3iYj73q942+K6wPv2OYsL5PBHk9SYeHvsNMCr/VINS+czWfvjNWjL13FYK8r6OSvjALHD9z1Ca/ooRLPg==",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "97:0d:05:e8:81:94",
    "timestamp": "2026-02-09T14:20:08.284Z",
    "debug_timestamp_end": "2026-02-09T14:20:11.591Z",
    "debug_processing_time": 3.3074374198913574,
    "rate": 10.547318264418443,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.97705078125,
                "center_of_mass": {
                    "x": 531,
                    "y": 80,
                    "width": 41.666666666666664,
                    "height": 77.25
                },
                "bounding_box_px": {
                    "x": 491,
                    "y": 3,
                    "width": 125,
                    "height": 309
                },
                "person-attributes": "F: has_bag has_longsleeves has_longpants has_longhair has_coat_jacket",
                "person-attributes_model_confidence": 0.9560546875,
                "reid": "TQ4LP2cM3b5EU9u+uHctPoK4Bj8PeFS+1icjP30h/L6ZpbU+gQQJv23K/Dx4z8G+grXePpy+Bb0WUuE+/FHgvXk0m76FTgs+IpFrvkhEBD4mDi8/djBVv/ixJr6LXgS8lyvovrVkCz53ms0+proKPpAI2T73G6c9NbPOPl4u0T6aD4M/uowKP0fc1roCHg2+A2rbvtOfab8kBw4/EBLAPVq0Dz+4JoU+j3EaPkOs8r44HKs8WX7wO2LKNr/A3Fc87T1bvWqtrr57ozq+7InsvsoOIz5EAjq/Fqg/PlWm277Am6k+ax3kvUxRoT+wC648eOe2PMDa1b2MmWO9+Uz7vS90ub56buq8ptZqvtyoHr6hsao+JJUWP3ju07477Qy+xuYFP1CrJD2zjsY+7WguPzy4E79i1Qs/u7J9PxFe4b69aH8+81JEvlbNAj8UpaC+QNPwPGBQ3jxqgVM+f7H0vjfrp76+yJC/IBPDPBlGtb4kOT8+nVmgPpdFx77mwhk/3FShvgA2RTy8elQ+kgmYPuyYrb3FONM+GtDTvYHN6L1o52E/F2Icvl4NF704VKC8Ig5UP537Ib9J7EG/ZwNCPx4WkL0FqBO/B7qnvrS/ib7ECYo+svICv484gL3CRZQ+y98kvgA08L6f1CW/gYB6vy/8+L6e5Wi+HuxGPf3KLz6T8Bs/dawrvhntmL65itI9nk9qP7SIZb8v80C/llZLPtm4Mr58/m4+nLgzP8qTwT5ago++EPQ4P5k/XT+yVQ0/GK3wPu9thr7vaF2/ublwv+HW3b5BRo+/qL44vaQuzLwgqSc/tdGkPhSzFT+uhhw+4Aa3Pd5E/b4+BV2/UN3IvmwsBr/w3dm+iHepvuxVwr7MkV0/3oQXP455jz6cXZQ/vgi1PoiqZD06+8+9mpQRvIiqyD4PpZw+/lQpP7uDKL2tBPa9WxMTv5fapb7nFIs+QIt0vfgayT61kLq+MgEOP7mZKr+v+Xs/OXWwvtpAoz7HuCy/GqTlvsgFwr4gq/m+TJJAPk+hgr5pjpc+imHbvuq+Wb9SXCe/vOQHPuBbrD3EB9Q9MkMHvZx+R78mX6M+YhKzPkiySr46tTI/Wavivtp+gjxHV3O+OLjePAxzpbvXZwu+foKAvzIedz7HCrU9G38Ivnu/Bb9jYYQ+D36Fvpu1qb6XEUk/RGv4voWBL74xv0e/2hYMP7rnT74vE2m+3swIP9xn+b2fdbo+cX+dvq9WIT9t3wm/9g9vP3vdjD/gtdq+Gccpv6cnQr6Ppvi9445vvwDM+zqhBMW9BJvTPSsbsL2bCJC98QytviT+pr1cIuS++goWvxj9Rz7UHns9Gp6gvZ5/KT+Vrg+/jnoKvg==",
                "id": 1
            }
        ]
    }
}
```

</details>

### Combined Person Metadata (Age, Gender, and Attributes with ReID)

These pipelines combine all person detection capabilities: age, gender, physical attributes, and re-identification embeddings. Based on the OOB queuing scene use case.

<details>
<summary>CPU</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=CPU inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.xml model_proc=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.json device=CPU inference-region=1 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.xml model_proc=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.json device=CPU inference-region=1 ! queue ! gvainference scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-reidentification-retail-0277/FP32/person-reidentification-retail-0277.xml device=CPU inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

**Example raw output metadata:**

[See JSON](./example_output/person_metadata_cpu_raw.jsonl)

**Example SceneScape output metadata:**

```text
{
    "id": "atag-qcam1",
    "debug_mac": "7f:88:8d:a9:ba:c1",
    "timestamp": "2026-02-09T11:10:06.579Z",
    "debug_timestamp_end": "2026-02-09T11:10:12.379Z",
    "debug_processing_time": 5.799445152282715,
    "rate": 15.777117409972615,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9881600141525269,
                "center_of_mass": {
                    "x": 569,
                    "y": 85,
                    "width": 67.33333333333333,
                    "height": 81.25
                },
                "bounding_box_px": {
                    "x": 503,
                    "y": 5,
                    "width": 201,
                    "height": 325
                },
                "age": "50",
                "gender": "Male",
                "gender_model_confidence": 0.902121365070343,
                "person-attributes": "F: has_bag has_longsleeves has_longpants has_longhair has_coat_jacket",
                "person-attributes_model_confidence": 0.6650304794311523,
                "reid": "IfANPyX3rT7AypM+DyDSvuf0wztKUqg90RSIvnxWXL9ud2w/yI9+vnslYz87Hae+aM6gv4u2rT7Qw5Q+5XzWPmfHwr5MIYm8vvSSPsAFrz3/bsI/dN1Ov9dXlz4GEZ6+265Cv4Y5Az5yLFi+ur+9uweBez8pV8g+Ad01P4lZMD+JwI8+P8zzPulsNL+wh2W+OsBgv6XL7r3j+iY+eYojv9hPSb6hGAc/CDSgvjVTrL7XczM/lMXLN5EwgL+xg/y+0J8wvvUiwr7C99i+pWscv1xGgD4EvcE+xjGJPcS+Mr6JAhK/fxNOv1VTa7y1DLg+fwsqv5yafr5sDeu+pKRwPkaPA72ICLO+c9FPv4KtLL/QPQc/hL9bP9NSB7+atew+/ifuvV/fBj/ci9S9QsBXPxcsA7/6qYs+yBm3Pn0pDr/XqJ89OC00voTcvT43kvA9RmhEvyO2Az4PufI+vyVSP1HVHr/iICa/pfrGPs0Un74HxCg/mtRTP5SOyb1WDII95YYtvwDQGr/8OCY+HEsQP3VESb/5wwm+YjZWvZRc0r2kkwE/jQq1vqPlxj43cJe/aFSaP8lhjL2i8ek+NhgzP9K3Yj7I2CS/howSv/KgqL5AFZM/84r8vtiHrb1M0e8+QZFhPuN3o751mFW/ADA8v8+oMr7VHo6+XOQ4PO44Yz0l3I4/wFgfPy3DNb43Htq+zy3bPuTgVb9+rYu9wL/svYdy7L3P4Tc/EhUKv/ljwT4Ps5a+NFaDP6ELBz8Bx7i9JZlNvqFzfD2PLDy/i9hWv1Huh74g8AI/2Pu1PpNJk77VqcE96LYZPjz33D6kURq+NvuJP+Dwnr8+uBw982oAv8O0RL2Mugo+Wg1mvhPbvj4iOMQ+bcQGP2+CVz9V304/Ct7WvmfH4j6qjvW849NCPrZqHb/IYCk958wTP2bgsb1vwO++VaNavOZfIb+OM68+3JI5vyTpij2ylMA+z6yXPj1xF79OvM0+MwIiv1QEAj43Okk8aGMcvrNwAj5xHSi/9S9lvmCSQr87voq9Iuvfvirlbr9VbGO/IXqCvvXuED+pypO+CG2Hv3YxHL4MD1Q/O7XoPSQAG79OO1s+tyiwvk2dVz4YKFS/BexxPhYuFz2xqCC/lzeRPihWrb70Iz2+b40fPZXVxb6Tkdw98JB9PrnlmT51Bug+Yeg/v6OEs75zjia/xEsdP/ksWj+EX28+sTVPPvoEvL/fkQQ/8kvrPI5yv70LiOq+trQaPrl7jj81bDW/uy+9ve25Vz70//W+g7yDPjZCHT2Zhw6/Izs5v040NL6F4KS+M5yivo/Dl7yeYQu/vcyFPQaAhT2q25i9BBNWvgLY8L5H1Ou+URyqPQ==",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "7f:88:8d:a9:ba:c1",
    "timestamp": "2026-02-09T11:10:06.588Z",
    "debug_timestamp_end": "2026-02-09T11:10:12.487Z",
    "debug_processing_time": 5.899734735488892,
    "rate": 15.777117409972615,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9578379988670349,
                "center_of_mass": {
                    "x": 564,
                    "y": 85,
                    "width": 63.333333333333336,
                    "height": 80.75
                },
                "bounding_box_px": {
                    "x": 501,
                    "y": 6,
                    "width": 190,
                    "height": 322
                },
                "age": "25",
                "gender": "Male",
                "gender_model_confidence": 0.9393385648727417,
                "person-attributes": "F: has_bag has_longsleeves has_longpants has_longhair has_coat_jacket",
                "person-attributes_model_confidence": 0.9285990595817566,
                "reid": "W8YiPzGEqb7ENRi+gsSTPvcY0z7aAdi+Ie2yPnD90b7KP2E8yUlovz47k75zOBe/p5/8PYKzkjz4e5s+ysgePiunm76B8do+gCILvpqG/L3/oVQ/oNYgvxjUv77x6ic9G/PXvrOOt75Cn34+NGyyPqBUgz4PQRw+2C3UPqw6ez6qOXo/gA31Pq1cPr6cWSC/aT6rvgCsHb+SdCM//DVBParJRj8Cb+E9rVSivlSyz777LgM+Q7kBvSujVb8daG2+dfeCvuBgq74CHCk+QjRivzrERT7BA+K+Wh+TPTFMvb1nTqS9XggdPXiIkj80xCy+nC3svsXSjL2V7Jw+KC2SvXHIFb7IWCO+A//hvUCqmL3sJc4+6DoKP0uhsL4Ze5i+LI33PHXtlz086mU+4/Y8Pwxi+r67W9M+4YKmP9UQ9751Vw8/6fWAvkFQNT8FNjq+HhLIPtAMrD3eaWg+Cue5vtCCwr4yoYC/ahcjPeI0Yr45NI8+G9ymPtRIAr7Qgh0/mf2rPSfHJzwWI4M+koqMPq9soLwEcYQ+3qqfvqXY1L4bcQ0/hT44vkcN0r7E6HU+aWJQP/zFRr9ZRCS/soogPxusqL595kO/yMkBvGIHM7/dxfY+oeU1v4OJYr3cGCw/Zm8QPqSbF7/zIS+//zKWv6qEHb+jd16+XR8xPbIi/7x//BM/nCT0vYDey76+byI8xbNYP5V5dL+Urh2/vRAdvpzhkLxu79M+uwXlPv2cUD4Xgb2+M1JnP4ADOj9RPRo/g/UlPuUOF733x1u/ATlgv8C6OL8bwiq/8NGVvgQ3iz4lliE/yO+GPjwmRj+i+L68KHx7Ppz2cL9fLi+/dEOGvr8PFr/8IAa/AWVDviD2q713Xog/nfMhP5x9Ez9OM2c/vMmfPm/ixL2DOCS+W0OcPNaAmT5uqjQ/Yj1PP+ok3r57g3G+Ckkgvwxjnb6Ydrw+Z+57vmVp5T5Ew5m9cvfsPlqU9b6a4y8/gAjHvm2Qqz5qGju/h8F7vtC2oL7q9ri+ZHtRPh5DkL4Iab0+9znqvi8gEr+uWx+/INw6PmA5UD5V3wU+a/drvvnlEL/KiBY/a741PrnTVb77VCg/hR2vPUNLCz7le+e+WzJBvvSdyjy6oXk+wTZQv5s/zD5MeJQ+PVQSvWVZar/UW4k+5Y1fvl5HcL7BRSQ/G/HuvqDu3r573FK/JR4IPyR7Nb62kP69LyuGP1rK3bwtzBM/Bt6JvgzbID/Mlii+KJ4zP4pgMz8O3QK+OQM6v95gdj0Bf0i9a069v0TsBD07ezG++jLDvno5bL5CYC48ZndivrRPyL5LvGK+EBeIvgqqlL1SKtI86Q5IvnaQCz/fKhm/LQC6PQ==",
                "id": 1
            }
        ]
    }
}
```

</details>

<details>
<summary>GPU</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw(memory:VAMemory) ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.xml model_proc=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.xml model_proc=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvainference scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-reidentification-retail-0277/FP32/person-reidentification-retail-0277.xml device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! vapostproc ! video/x-raw,format=BGRA ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

**Example raw output metadata:**

[See JSON](./example_output/person_metadata_gpu_raw.jsonl)

**Example SceneScape output metadata:**

```text
{
    "id": "atag-qcam1",
    "debug_mac": "57:9a:35:9c:22:dc",
    "timestamp": "2026-02-09T11:12:13.948Z",
    "debug_timestamp_end": "2026-02-09T11:12:18.043Z",
    "debug_processing_time": 4.094555139541626,
    "rate": 10.283004713511401,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9951171875,
                "center_of_mass": {
                    "x": 829,
                    "y": 112,
                    "width": 50.0,
                    "height": 97.0
                },
                "bounding_box_px": {
                    "x": 780,
                    "y": 15,
                    "width": 150,
                    "height": 388
                },
                "age": "20",
                "gender": "Female",
                "gender_model_confidence": 0.85546875,
                "person-attributes": "M: has_bag has_longsleeves has_longpants has_coat_jacket",
                "person-attributes_model_confidence": 0.96533203125,
                "reid": "k0PJPqo4ST445W8+5BQcPqDHJj9BD8u+FMDXPnd7aL51APw+wmJUv2UhpL7WqpO+WrCfvqzywj7lAQU/I56JPDhw873x4QQ/U/AtvrTGfr4eHeo+uZiLvh0UAL+N8XQ+aaNiv6y9zT131po+gF0TPhRDVz/SKgE/Do+TPrC6ij6Q5Ig/5R7HPr3egL2zlQ+/9Ds3vdTZOr3wvgG9lkxOvTBYIz+7r4g+vesHv0dqDL/ooUM9PlAkPVzZbb7F0YW+Hl5CvwplBr/bpIi8QioNv53E9r4P+iC/qibkPOP2Hr7/aTi+oI+GPmmXjD/JriK/f3Mpv8Myd73YmkM/4KtlvbsNgL0dtpC+Yze/vUOsOrtPjq8+QasgPx2HRb6IP/E9pMiMPUJE8b2RW+k+l8Y7P1FQD7+a9a8+2TxfP35XF78r5cc+0TJXvlaIzj6x1YC9nWv1PhzQbj5m9o+8dMU8v28bEb9eUWi/MFCUPQTMND0qa7C9WMGlPmuThL6weeI+gownPt+ykb4gtrY9YAAVPKegJz6iD7U+lZr4PdATPj32qNY+F6kUvxuS/r7fXOo93rDmPhG+2L5pfU6/2G8FP57yGb9QNlC/x3itvpR9wb6HSry7fv/uvh3Ql77QXJo+pDiWPvWDg7+YX0+/6Kqkv5lP3L4cKG++ctyLPsq9MT7d+IE+gqy+vfup4j1OsBm9ZHdQP+WtSb8Llny+hqsVvQQw9j4njwg+ZkfKPuRgEj8yMzy+ZNS7PumNJD++quE+GnPMPpaGsbsG+Bu/xeKuvuyi4L5vJ9O+zcUSvj+y/by+8vw+CuYDPpQ9zT5sTew9ZEeqPSnlPb+d8XW/U+6yvmd7jL5CWSW/oFZkvqa0Jry2qj4/2KxwP7daIj9rH4Q/+FytPoAskb6AwoS+VTBIvvuRjz7kpsw+HV+bPsDFJTzOrYq+vQkdv2aCnT3ikgw/BEoUPqBTkD17ePO+VhwHPgpIqL7WLyE/ncMgvpq05T4kHps9UHqLvT1Gtb5Sa4a++P2KPcG3Wr5SD1E+uculvpv4Gb+JO0+/8eCiPtxQ1z5ZuYk+hBKHPnAdJ79ojUc/exUGP3ot27t1o+A+xCrsvtNzyr3qL8a+VAGqvfGTHD5jt4a9ZrvHvjb2O73afP0+1wmBvvhkBr+6hhM/Rp6QPuHQtb1SMFE/IMJ2PTyg4z2QxC++kuopPhqCaL4ZDwG/PpRDP7fT/77+XSE/CUnavfg5yT5wc6y+mv5SPzxz5j7ES42+mLuhvu0ai71D5lE+O/u9v8Irwz5ZAIS+VF3KPWyMFb7LVNO9r+VPvjUJ8r5OMQm/l5UUv9wjPL5Ko3M9r5aavg86Hj84cQC/DtNfvQ==",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "57:9a:35:9c:22:dc",
    "timestamp": "2026-02-09T11:12:13.951Z",
    "debug_timestamp_end": "2026-02-09T11:12:18.146Z",
    "debug_processing_time": 4.195011377334595,
    "rate": 10.283004713511401,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9912109375,
                "center_of_mass": {
                    "x": 854,
                    "y": 123,
                    "width": 52.0,
                    "height": 93.0
                },
                "bounding_box_px": {
                    "x": 803,
                    "y": 30,
                    "width": 156,
                    "height": 372
                },
                "age": "21",
                "gender": "Male",
                "gender_model_confidence": 0.5126953125,
                "person-attributes": "F: has_bag has_longsleeves has_longpants has_coat_jacket",
                "person-attributes_model_confidence": 0.93017578125,
                "reid": "so6pPqC11z3otQI9vuScPo6oTz+wKeu+1oegPodGX77Gxxs/YIMhv1Yyxb7ri7a+KWCNvQ7d6D63yYA+jZJAPmdPWb1qQIw+bMWmvcZ0zb4Qfy8/ArSMvsKJDr9D45Y+3kZxv4MIRj0iRwa7hUeCPl437T5ETwQ/WuMrP7Km+T6fDKk/jI0lP2C/97vDUiq/BpGevt/XHr1ME6k84CgCPcp7Dz/ON7U+E0sTv1qp5L6va5A+wr0gvbaENL4Sz3O+6NA9v+OlCr+9zH++GNcAv1APHD7bOiW/GIDiPVJBvT14fN2+h0VnPq/7oz+v4jG/h1X8vj+wgb14EQ8/ucRdvsPxBj4lb5q+QrtAvtD7y70Caus+/OWSPuJrxj0qora+uRwYvnS1Jj2Ipzk+EP5ePx3Ojb6IT2U+4HZ3P/cdkL6bKyE/L5QavkJDBj+50ey9J45xPjDwPT4iNAg+1jQcv5+iIr8Rj2C/oAYXPtAXrjzAmui7/k3CPjPGzb4wQWY+5OOjPiZF2r3AyjU+BAOEPYQBnDyfl8E+aE0CPuA4fL3NJg4/rSfcvkJALL8PRyU+NJnGPhu2sb4vZWy/wSoIPxp8HL+wyCy/L58dvl0eMr9wPYi+lMcOv20MIb+ynuE+loCFPoFne797FzG/42Ogv6SUsb4kQi++i/TnPtyrkj7sOa8+5xzGvgCNIDxmfpm+HnMuPx8jeb+rjpm+W6fPvTQMzT48h7Y+kj3PPjlF2T7Mqo2+dlkNPyEXZj/HsdQ+GKDkPuZoCT7Aaxe/8DPnvh+KEb9t3he/0/QAvwiBhD0cBPo+2h8svoCwZD760o4+iNwqPdIgFL8hEzq/1j8IvwCDM7/ZJui+EoC3vn1uMb3m1WM/KT6WP/I+ID98s28/WLM2P4C/sr36Wqe+VXa6vSPEJz8JkNE+EK7kPuBjVr5Laqe9bolJv+Tto7urTdk+Oe2OPjRxFD7tzKS+a8+0PpAmr74iuaE+1BaRvd8sJz/HNwi+jTyIvl8M77430ji+lwm9PoC8W741JWQ+Y5Z7vqvRL79JMnW/h4NmvaStqT5U9cs92b4Wvb9Pa7+7mA0/Yc0wP1pDOz4lSSA/9vhWvlwYzDyi5w2/UI7+PeonND45q6G9SWzLvlLU/j2Bmsw+PbrFvW9DSr9bdxY/dVecPqK/Zj7Xk2Q/TwP3vWb75T3wiQW+TmL0PmWkt77gtsW+dC9sP6QDLr8rglE/hbi1vdismT4chZ++ILaNPwqpCT8gEt+91lsIv/z2OL6dMEC9w5bUv9y5rLyn9Nq9ijgKPvOiIr6kEQ4+OtmRvpv7Jr+6HBa/e9YOvxOQuL1ooVs9E6Rmvrwb8j4QgxW/u3bwvQ==",
                "id": 1
            }
        ]
    }
}
```

</details>

## Vehicle Re-Identification

### Vehicle Color and Type Classification

These pipelines detect vehicles and classify their color and type. Uses the input video `fixed_ANPR_Cam1` (adjust as needed for your environment).

<details>
<summary>CPU</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/fixed_ANPR_Cam1.ts name=source ! decodebin3 ! video/x-raw ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/vehicle-detection-0200/FP32/vehicle-detection-0200.xml model_proc=/home/pipeline-server/models/intel/vehicle-detection-0200/FP32/vehicle-detection-0200.json device=CPU inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/vehicle-attributes-recognition-barrier-0042/FP32/vehicle-attributes-recognition-barrier-0042.xml model_proc=/home/pipeline-server/models/intel/vehicle-attributes-recognition-barrier-0042/FP32/vehicle-attributes-recognition-barrier-0042.json device=CPU inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

<details>
<summary>Example raw output metadata:</summary>

```text
{
    "objects": [
        {
            "color": {
                "confidence": 0.9996287822723389,
                "label": "white",
                "label_id": 0,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.6075114011764526,
                    "x_min": 0.2871137857437134,
                    "y_max": 0.2685202658176422,
                    "y_min": 0.0
                },
                "confidence": 0.9084001779556274,
                "label": "vehicle",
                "label_id": 0
            },
            "h": 290,
            "region_id": 1,
            "roi_type": "vehicle",
            "tensors": [
                {
                    "confidence": 0.9084001779556274,
                    "label_id": 0,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "confidence": 0.9996287822723389,
                    "data": [
                        0.9996287822723389,
                        0.0003627121914178133,
                        3.297728426332469e-06,
                        2.504187932572677e-06,
                        2.1115255322001758e-07,
                        2.111142066496541e-06,
                        2.3517074509982194e-07
                    ],
                    "dims": [
                        1,
                        7
                    ],
                    "label": "white",
                    "label_id": 0,
                    "layer_name": "color",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "color",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.8611056804656982,
                    "data": [
                        0.002265576273202896,
                        0.025034068152308464,
                        0.8611056804656982,
                        0.1115947961807251
                    ],
                    "dims": [
                        1,
                        4
                    ],
                    "label": "truck",
                    "label_id": 2,
                    "layer_name": "type",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "type",
                    "precision": "FP32"
                }
            ],
            "type": {
                "confidence": 0.8611056804656982,
                "label": "truck",
                "label_id": 2,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "w": 615,
            "x": 551,
            "y": 0
        },
        {
            "color": {
                "confidence": 0.9917084574699402,
                "label": "yellow",
                "label_id": 2,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.1252022199332714,
                    "x_min": 0.0,
                    "y_max": 0.5210926532745361,
                    "y_min": 0.01505213975906372
                },
                "confidence": 0.566472053527832,
                "label": "vehicle",
                "label_id": 0
            },
            "h": 547,
            "region_id": 2,
            "roi_type": "vehicle",
            "tensors": [
                {
                    "confidence": 0.566472053527832,
                    "label_id": 0,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "confidence": 0.9917084574699402,
                    "data": [
                        0.006282460410147905,
                        5.3240648412611336e-05,
                        0.9917084574699402,
                        0.0018176068551838398,
                        6.512588879559189e-05,
                        9.679758477432188e-06,
                        6.332881457637995e-05
                    ],
                    "dims": [
                        1,
                        7
                    ],
                    "label": "yellow",
                    "label_id": 2,
                    "layer_name": "color",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "color",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.6901025772094727,
                    "data": [
                        0.6901025772094727,
                        0.09535824507474899,
                        0.20791573822498322,
                        0.00662342319265008
                    ],
                    "dims": [
                        1,
                        4
                    ],
                    "label": "car",
                    "label_id": 0,
                    "layer_name": "type",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "type",
                    "precision": "FP32"
                }
            ],
            "type": {
                "confidence": 0.6901025772094727,
                "label": "car",
                "label_id": 0,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "w": 240,
            "x": 0,
            "y": 16
        }
    ],
    "resolution": {
        "height": 1080,
        "width": 1920
    },
    "tags": {},
    "timestamp": 3300000000
}
{
    "objects": [
        {
            "color": {
                "confidence": 0.9780423045158386,
                "label": "yellow",
                "label_id": 2,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.1293528899550438,
                    "x_min": 0.0,
                    "y_max": 0.4978461414575577,
                    "y_min": 0.004883959889411926
                },
                "confidence": 0.6818462014198303,
                "label": "vehicle",
                "label_id": 0
            },
            "h": 532,
            "region_id": 1,
            "roi_type": "vehicle",
            "tensors": [
                {
                    "confidence": 0.6818462014198303,
                    "label_id": 0,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "confidence": 0.9780423045158386,
                    "data": [
                        0.02084587700664997,
                        0.00011048035230487585,
                        0.9780423045158386,
                        0.00072418840136379,
                        0.00011830057337647304,
                        4.65218436147552e-05,
                        0.00011237963917665184
                    ],
                    "dims": [
                        1,
                        7
                    ],
                    "label": "yellow",
                    "label_id": 2,
                    "layer_name": "color",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "color",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.5657919645309448,
                    "data": [
                        0.13835278153419495,
                        0.5657919645309448,
                        0.2629131078720093,
                        0.03294219821691513
                    ],
                    "dims": [
                        1,
                        4
                    ],
                    "label": "bus",
                    "label_id": 1,
                    "layer_name": "type",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "type",
                    "precision": "FP32"
                }
            ],
            "type": {
                "confidence": 0.5657919645309448,
                "label": "bus",
                "label_id": 1,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "w": 248,
            "x": 0,
            "y": 5
        },
        {
            "color": {
                "confidence": 0.9986801743507385,
                "label": "white",
                "label_id": 0,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.6084014177322388,
                    "x_min": 0.2849857211112976,
                    "y_max": 0.24655453860759735,
                    "y_min": 0.00451032817363739
                },
                "confidence": 0.6236904859542847,
                "label": "vehicle",
                "label_id": 0
            },
            "h": 261,
            "region_id": 2,
            "roi_type": "vehicle",
            "tensors": [
                {
                    "confidence": 0.6236904859542847,
                    "label_id": 0,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "confidence": 0.9986801743507385,
                    "data": [
                        0.9986801743507385,
                        0.0004708733467850834,
                        8.045486902119592e-05,
                        0.0002800092624966055,
                        3.96221767005045e-05,
                        0.0003025019250344485,
                        0.00014628286589868367
                    ],
                    "dims": [
                        1,
                        7
                    ],
                    "label": "white",
                    "label_id": 0,
                    "layer_name": "color",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "color",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.930264413356781,
                    "data": [
                        0.02080393210053444,
                        0.012033670209348202,
                        0.930264413356781,
                        0.036898065358400345
                    ],
                    "dims": [
                        1,
                        4
                    ],
                    "label": "truck",
                    "label_id": 2,
                    "layer_name": "type",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "type",
                    "precision": "FP32"
                }
            ],
            "type": {
                "confidence": 0.930264413356781,
                "label": "truck",
                "label_id": 2,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "w": 621,
            "x": 547,
            "y": 5
        }
    ],
    "resolution": {
        "height": 1080,
        "width": 1920
    },
    "tags": {},
    "timestamp": 3380000000
}
```

</details>

**Example SceneScape output metadata:**

```text
{
    "id": "car-reid",
    "debug_mac": "cf:4a:8f:83:6f:fd",
    "timestamp": "2026-02-06T11:57:53.329Z",
    "debug_timestamp_end": "2026-02-06T11:57:54.320Z",
    "debug_processing_time": 0.9917025566101074,
    "rate": 17.734405306595058,
    "objects": {
        "vehicle": [
            {
                "category": "vehicle",
                "confidence": 0.9596372842788696,
                "center_of_mass": {
                    "x": 311,
                    "y": 311,
                    "width": 311.6666666666667,
                    "height": 254.5
                },
                "bounding_box_px": {
                    "x": 0,
                    "y": 57,
                    "width": 935,
                    "height": 1018
                },
                "color": "red",
                "type": "truck",
                "id": 1
            }
        ]
    }
}
{
    "id": "car-reid",
    "debug_mac": "cf:4a:8f:83:6f:fd",
    "timestamp": "2026-02-06T11:57:53.408Z",
    "debug_timestamp_end": "2026-02-06T11:57:54.355Z",
    "debug_processing_time": 0.9468543529510498,
    "rate": 17.734405306595058,
    "objects": {
        "vehicle": [
            {
                "category": "vehicle",
                "confidence": 0.9893819093704224,
                "center_of_mass": {
                    "x": 311,
                    "y": 292,
                    "width": 310.6666666666667,
                    "height": 261.25
                },
                "bounding_box_px": {
                    "x": 1,
                    "y": 31,
                    "width": 932,
                    "height": 1046
                },
                "color": "white",
                "type": "truck",
                "id": 1
            }
        ]
    }
}
```

</details>

<details>
<summary>GPU</summary>

**Pipeline:**

```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/fixed_ANPR_Cam1.ts name=source ! decodebin3 ! video/x-raw(memory:VAMemory) ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/vehicle-detection-0200/FP32/vehicle-detection-0200.xml model_proc=/home/pipeline-server/models/intel/vehicle-detection-0200/FP32/vehicle-detection-0200.json device=GPU pre-process-backend=va-surface-sharing inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/vehicle-attributes-recognition-barrier-0042/FP32/vehicle-attributes-recognition-barrier-0042.xml model_proc=/home/pipeline-server/models/intel/vehicle-attributes-recognition-barrier-0042/FP32/vehicle-attributes-recognition-barrier-0042.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! vapostproc ! video/x-raw,format=BGRA ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

<details>
<summary>Example raw output metadata:</summary>

```text
{
    "objects": [
        {
            "color": {
                "confidence": 0.9912109375,
                "label": "white",
                "label_id": 0,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.6744450330734253,
                    "x_min": 0.2787874937057495,
                    "y_max": 0.5803180932998657,
                    "y_min": 0.0
                },
                "confidence": 1.0,
                "label": "vehicle",
                "label_id": 0
            },
            "h": 627,
            "region_id": 1,
            "roi_type": "vehicle",
            "tensors": [
                {
                    "confidence": 1.0,
                    "label_id": 0,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "confidence": 0.9912109375,
                    "data": [
                        0.9912109375,
                        0.00913238525390625,
                        1.341104507446289e-05,
                        2.384185791015625e-07,
                        5.364418029785156e-07,
                        8.344650268554688e-07,
                        2.86102294921875e-06
                    ],
                    "dims": [
                        1,
                        7
                    ],
                    "label": "white",
                    "label_id": 0,
                    "layer_name": "color",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "color",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.5830078125,
                    "data": [
                        0.413330078125,
                        0.5830078125,
                        0.00185394287109375,
                        0.0011510848999023438
                    ],
                    "dims": [
                        1,
                        4
                    ],
                    "label": "bus",
                    "label_id": 1,
                    "layer_name": "type",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "type",
                    "precision": "FP32"
                }
            ],
            "type": {
                "confidence": 0.5830078125,
                "label": "bus",
                "label_id": 1,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "w": 760,
            "x": 535,
            "y": 0
        }
    ],
    "resolution": {
        "height": 1080,
        "width": 1920
    },
    "tags": {},
    "timestamp": 2980000000
}
{
    "objects": [
        {
            "color": {
                "confidence": 0.998046875,
                "label": "white",
                "label_id": 0,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "detection": {
                "bounding_box": {
                    "x_max": 0.6655248999595642,
                    "x_min": 0.27872854471206665,
                    "y_max": 0.5719943642616272,
                    "y_min": 0.0
                },
                "confidence": 0.998046875,
                "label": "vehicle",
                "label_id": 0
            },
            "h": 618,
            "region_id": 1,
            "roi_type": "vehicle",
            "tensors": [
                {
                    "confidence": 0.998046875,
                    "label_id": 0,
                    "layer_name": "detection_out",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "detection",
                    "precision": "UNSPECIFIED"
                },
                {
                    "confidence": 0.998046875,
                    "data": [
                        0.998046875,
                        0.0016756057739257813,
                        6.973743438720703e-05,
                        3.993511199951172e-06,
                        2.4437904357910156e-06,
                        8.940696716308594e-07,
                        2.1755695343017578e-05
                    ],
                    "dims": [
                        1,
                        7
                    ],
                    "label": "white",
                    "label_id": 0,
                    "layer_name": "color",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "color",
                    "precision": "FP32"
                },
                {
                    "confidence": 0.97265625,
                    "data": [
                        0.97265625,
                        0.0245361328125,
                        0.0004723072052001953,
                        0.0032806396484375
                    ],
                    "dims": [
                        1,
                        4
                    ],
                    "label": "car",
                    "label_id": 0,
                    "layer_name": "type",
                    "layout": "ANY",
                    "model_name": "torch-jit-export",
                    "name": "type",
                    "precision": "FP32"
                }
            ],
            "type": {
                "confidence": 0.97265625,
                "label": "car",
                "label_id": 0,
                "model": {
                    "name": "torch-jit-export"
                }
            },
            "w": 743,
            "x": 535,
            "y": 0
        }
    ],
    "resolution": {
        "height": 1080,
        "width": 1920
    },
    "tags": {},
    "timestamp": 3020000000
}
```

</details>

**Example SceneScape output metadata:**

```text
{
    "id": "car-reid",
    "debug_mac": "1f:c2:b1:27:78:b5",
    "timestamp": "2026-02-06T12:04:22.444Z",
    "debug_timestamp_end": "2026-02-06T12:04:23.183Z",
    "debug_processing_time": 0.7384850978851318,
    "rate": 16.440405311111583,
    "objects": {
        "vehicle": [
            {
                "category": "vehicle",
                "confidence": 0.857421875,
                "center_of_mass": {
                    "x": 155,
                    "y": 913,
                    "width": 155.66666666666666,
                    "height": 55.25
                },
                "bounding_box_px": {
                    "x": 0,
                    "y": 859,
                    "width": 467,
                    "height": 221
                },
                "color": "white",
                "type": "truck",
                "id": 1
            }
        ]
    }
}
{
    "id": "car-reid",
    "debug_mac": "1f:c2:b1:27:78:b5",
    "timestamp": "2026-02-06T12:04:22.515Z",
    "debug_timestamp_end": "2026-02-06T12:04:23.216Z",
    "debug_processing_time": 0.7015526294708252,
    "rate": 16.440405311111583,
    "objects": {
        "vehicle": [
            {
                "category": "vehicle",
                "confidence": 0.89599609375,
                "center_of_mass": {
                    "x": 154,
                    "y": 866,
                    "width": 154.33333333333334,
                    "height": 71.25
                },
                "bounding_box_px": {
                    "x": 0,
                    "y": 796,
                    "width": 464,
                    "height": 284
                },
                "color": "white",
                "type": "van",
                "id": 1
            }
        ]
    }
}
```

</details>

---

## Pipeline Customization Guide

### Modifying Video Sources

Replace the video source location in any pipeline:

```bash
multifilesrc loop=TRUE location=/path/to/your/video.ts
```

For live camera feeds, replace `multifilesrc` with appropriate source elements (e.g., `v4l2src`, `rtspsrc`).

### Adjusting Inference Parameters

Key parameters you can adjust:

- **`batch-size`**: Number of frames processed together (default: 1)
- **`inference-interval`**: Process every Nth frame (default: 1 for all frames)
- **`scheduling-policy`**: Set to `latency` for real-time or `throughput` for batch processing
- **`device`**: `CPU`, `GPU`, or `MULTI:CPU,GPU` for hybrid execution

Example for processing every 5th frame:

```bash
gvadetect ... inference-interval=5 ...
```

### Model Precision

All examples use FP32 models. For better performance on supported hardware, use FP16 or INT8:

```bash
model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP16/person-detection-retail-0013.xml
```

---

## Troubleshooting

### Common Issues

**Pipeline fails to start:**

- Verify all model paths exist
- Check that video source is accessible
- Ensure device (CPU/GPU) is available

**Low performance:**

- Increase `inference-interval` to process fewer frames
- Use FP16/INT8 models instead of FP32
- Enable GPU acceleration for VA-API surface sharing
- Reduce batch size or number of concurrent streams

**Missing metadata fields:**

- Ensure all classification models in the pipeline are running
- Check that `gvametaconvert add-tensor-data=true` is present
- Verify model_proc JSON files are correctly specified

---

## Additional Resources

- [Intel DL Streamer Documentation](https://dlstreamer.github.io/)
- [OpenVINO Model Zoo](https://github.com/openvinotoolkit/open_model_zoo)
- [SceneScape User Guide](../README.md)
- [GStreamer Pipeline Reference](https://gstreamer.freedesktop.org/documentation/)

---

## License

These pipelines use Intel OpenVINO models and DL Streamer components. Refer to individual component licenses for usage terms.

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
    "debug_mac": "3d:b5:63:bf:f3:43",
    "timestamp": "2026-02-10T12:24:49.303Z",
    "debug_timestamp_end": "2026-02-10T12:24:50.910Z",
    "debug_processing_time": 1.6070775985717773,
    "rate": 5.0,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9986047148704529,
                "center_of_mass": {
                    "x": 719,
                    "y": 228,
                    "width": 71.33333333333333,
                    "height": 124.75
                },
                "bounding_box_px": {
                    "x": 649,
                    "y": 105,
                    "width": 214,
                    "height": 498
                },
                "metadata": {
                    "age": {
                        "label": "47",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.7667971253395081,
                        "model": "age_gender"
                    }
                },
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "3d:b5:63:bf:f3:43",
    "timestamp": "2026-02-10T12:24:49.304Z",
    "debug_timestamp_end": "2026-02-10T12:24:51.011Z",
    "debug_processing_time": 1.7062125205993652,
    "rate": 5.0,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9970062375068665,
                "center_of_mass": {
                    "x": 703,
                    "y": 209,
                    "width": 69.66666666666667,
                    "height": 126.5
                },
                "bounding_box_px": {
                    "x": 635,
                    "y": 84,
                    "width": 209,
                    "height": 506
                },
                "metadata": {
                    "age": {
                        "label": "45",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.8546144366264343,
                        "model": "age_gender"
                    }
                },
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
    "debug_mac": "97:0e:38:74:25:34",
    "timestamp": "2026-02-10T12:28:49.398Z",
    "debug_timestamp_end": "2026-02-10T12:28:50.735Z",
    "debug_processing_time": 1.3373005390167236,
    "rate": 5.0,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9959391355514526,
                "center_of_mass": {
                    "x": 1061,
                    "y": 359,
                    "width": 97.33333333333333,
                    "height": 119.75
                },
                "bounding_box_px": {
                    "x": 965,
                    "y": 240,
                    "width": 292,
                    "height": 479
                },
                "metadata": {
                    "age": {
                        "label": "45",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.8176454901695251,
                        "model": "age_gender"
                    },
                    "reid": {
                        "embedding": "qnuzvi9EBz0SYwq/mFopv/bVTT7idXe9TZCrPVO4R74eCLO+A03JPti95r0RNYk+iY47v8daKb7Xfda+y9Anvywe5L6amoI+qZGXv7X2IL6JV9M+EP6dvtgMhb3QkDW/nIgJv7vZtj21XVi+6AP4vuVgND5Az4Q+YdZUvj/jRT+JsxS/E8skPN2VZj9Jwjq/x+iAvhG6oztjzMQ+SgPhvrx0g74gqtC+F0BHPih+ML783SE+4ytYv2PVjz6ik0y/7ZhevSm7mrxMAK8+UDQCPkjggL9q11++OptfPuUzg76XxKi+EywkPpRDND6kccI+cQ5fvtEDi75iBQW+rRdNvufQgD5LqA8+uwK/vQdh6Tu2dI0+wziJP22wUz+YE6C9pLUJPEh1Z70vmoG/BsPwvoUHGT8IUeu9viPsPnjKQL+tsWU+ShjKvj5fQz5tWqC+/pNkvjFT4j7akCg99fYtPg3lNb8qtSa/fEkYvkz/MD/u0rQ+VWC2vjOBLT49FJo9pI4Dv8IQ7b6ICgA/Bo2MPeUYQj9nOg6/Hd4aPhwZ474lGvi9GrqAPReW8r3HPJC/50gcPy52Tb4nDsm+0tAZvns9TT6h/2g+ZJiCvnH+qr6qKFY/zRcaPhFzqT73nxk9IL+kPteyS7/JIuW+uwXwvbjQ375fcZa+s/cnvmok6z08/II+eMMjvj+ERb9x7du8/2YZP5rzoD06utG9o++oPnpebD1T3m4+llgGPkwxVr4VwzO9yxroPT2UJz/63hm9FYDoPuzXcb6k8Ig+nBHUPmn8j75CUFy9kmwPPyVr3r7FUly/nqQevviByr7HjuA9mtLDPpTkPL9vCk6+UG+YPvIEFz+43UO/M6CCPc6hLr/1sIc8dpzlPQbbWj9CteG+X3hoPq8UML2Wqfk8ed2Jvqh8CD8tGGO+2bVqvrbjWT2y5i0/Xzqru18oD7/OEdy+RFNnPiNxaT8t+rg+2VehvdMxZT402Xg+vYLqPVTs8D7aAwU/+NOmvtun5rw3yqi+MV2lPMONeT7Muc0+zCM9PnoVWr+8QsA9XNpBP5GgUz/11BG+NjjWPVasxz7WBqK+0wdfPyoanD4cepU9yQbyvom9aD3t2NS9LhSjvjeCpT5R7SS/KBY4vjX7vj5fhUu+eFZ9v9sqCr9Y9hY/vTMhPuSem7xRlpY+EKyHvmlVgr2evNW+uFzJvjqyEr6ezyG+zPdIP4FNFr8AzIg+qPomP9iOHT0i+Zu9AlAYPwgamD5vy149GZwEP8QsQD6IbbY+g877PgUyKb/6mwG+ZnjNPgUB9L2cScK+pJJaPvTX7j2YRb8+FXB5Ph3yy74C+gw/uMARPhdSAT9VJEO+2BOOvg==",
                        "model": "torch-jit-export"
                    }
                },
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "97:0e:38:74:25:34",
    "timestamp": "2026-02-10T12:28:49.402Z",
    "debug_timestamp_end": "2026-02-10T12:28:50.835Z",
    "debug_processing_time": 1.4329888820648193,
    "rate": 5.0,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9895775318145752,
                "center_of_mass": {
                    "x": 1017,
                    "y": 337,
                    "width": 89.33333333333333,
                    "height": 126.0
                },
                "bounding_box_px": {
                    "x": 929,
                    "y": 211,
                    "width": 268,
                    "height": 505
                },
                "metadata": {
                    "age": {
                        "label": "48",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.7938673496246338,
                        "model": "age_gender"
                    },
                    "reid": {
                        "embedding": "CwUOvvSCDD76S2y+duF6PeHtvj2oOa2+OnivPhLqFT6DqOi+UGeLvPlfk77DjT0+EPe/vpMbdT5/4lK8cwfgvpQH5b0v4Bg/115jvxiDF714aqY+XDHZvhCp9r63t+m+UD8hv+9ajj6YSIq+/2ivvcgVJb5KnUQ/1FUKvue8Lz+bn+a+oL9UvbRPXz/A4YG/nhwgvzmomb4vSw8/9erBvjIpsL2xA+C+73OdvaiEIL8GEYK+byU0v5ONiz6D9Ua/qGBQvSlPnzwg2nu94lYEvk8gIL8vD6u+ZOWZPgQlKT3B0BO/9p0LPymbAT+vPog+aW2evgMrr75fwtK89RyvvCzyqD48tMm7CBhDvoZocT3S06s+NkIlP7zJNj+55Za+hWCKvnDL+r2/Ape/C5kGvz4J9D54Z2q+m+a2PrbA/L5IkOA+GY3QvmkElz6KJiq+HPidvstesD66Lxk+MrerPU/1kb6/m+6+Au5FPbX+fb0F8Vg+9qrOvgYK5TwXTnI9LAPwvlQB477skz4+GK/QPqLCUj8dAfi9Qt1oviI0Lr4HtbO+uGOiPmSn1b1gT3C/DNaXPhUB5L5k/ti+AGeSvckEaj4KBzq+FJmovWpnrb6t8HU/x00CvjhdLrvAwLk96WQkPqYtmb6obG++KSy2vvSisb6gPlo93/tOvh2p2b6FXbU9tT8Pv5ObeL9RvvS9HWAdP3GPsz59nf69vNFTPhxVer2aVxw/sbP2PlWKHz69J/y99BLSPlJ+IT9eFZM+skK1Pq90ur5q8RM/cWauPpWZdDzry4O+NBgkPzAwA79ZS2++hCyJPYuJ5r1LIzi8Z7pkPXqJoL0KRt6+IToiPkGw5T4/q0O/fWKCvnuC/772zcM8KgscPpRHNj/bwMa+zYTRPoGWPb335AO/qDdqvmKdbj4fKpc+RoORvMDrwztKLRc/nDaqPXaouL6vbri+pl17PvOWAT8E2e+9OfX/vaMSE76LyH4+9lgCPgCL5T5P/90+JO4Qv5PA87w8G8a+cOLjPfEIKr5AxBY+dIPauv9EKL/+8YK9MUv8PqGnKT//UZq9iPrTvWurkz4CV7a+9ygKP/6Y2z6mh8U9FxS/vvoDa76rQq6+7XDkvXBOFz7SrA6/D5UEv1CxMT8Nioy+UTlYv2VVDL+Rp2o/AlgAP4tkTj6W0PQ+OXr2Pgjis75WHCS/XHSfvXmZqj18khq8+WiFP4Id0r7SWoO+zousPrdUfz5BYLU+tutaP3DJiz1hIrA+Xq2aPvAfbT6gmaI+7UO7Prv6975zd+y9G6KnPSScGj0PN+E9fzqBPqmRX73atVY+ehu+PSHtyr6b49I+tuPPu0SVsT61JJi+pVEcvg==",
                        "model": "torch-jit-export"
                    }
                },
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
    "debug_mac": "3d:b5:63:bf:f3:43",
    "timestamp": "2026-02-10T12:25:00.688Z",
    "debug_timestamp_end": "2026-02-10T12:25:03.112Z",
    "debug_processing_time": 2.423408031463623,
    "rate": 10.871774069612869,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9864488244056702,
                "center_of_mass": {
                    "x": 651,
                    "y": 82,
                    "width": 35.0,
                    "height": 77.0
                },
                "bounding_box_px": {
                    "x": 616,
                    "y": 5,
                    "width": 105,
                    "height": 308
                },
                "metadata": {
                    "age": {
                        "label": "38",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.9458864331245422,
                        "model": "age_gender"
                    }
                },
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "3d:b5:63:bf:f3:43",
    "timestamp": "2026-02-10T12:25:00.788Z",
    "debug_timestamp_end": "2026-02-10T12:25:03.210Z",
    "debug_processing_time": 2.4226315021514893,
    "rate": 10.871774069612869,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9827247262001038,
                "center_of_mass": {
                    "x": 620,
                    "y": 83,
                    "width": 47.0,
                    "height": 78.25
                },
                "bounding_box_px": {
                    "x": 574,
                    "y": 6,
                    "width": 141,
                    "height": 313
                },
                "metadata": {
                    "age": {
                        "label": "39",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.9501286745071411,
                        "model": "age_gender"
                    }
                },
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
    "debug_mac": "97:0e:38:74:25:34",
    "timestamp": "2026-02-10T12:29:01.412Z",
    "debug_timestamp_end": "2026-02-10T12:29:05.137Z",
    "debug_processing_time": 3.7242965698242188,
    "rate": 11.286951072899647,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9580399394035339,
                "center_of_mass": {
                    "x": 410,
                    "y": 90,
                    "width": 69.0,
                    "height": 86.75
                },
                "bounding_box_px": {
                    "x": 342,
                    "y": 4,
                    "width": 207,
                    "height": 347
                },
                "metadata": {
                    "age": {
                        "label": "28",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.8981321454048157,
                        "model": "age_gender"
                    },
                    "reid": {
                        "embedding": "mosdPx2a/r6BbHE+oq3jPBAhzz5uC6k9jHu0Pi9ThbkBD8o+qmRIvxYRUz7j6xC/kVKAvl5mAb4iYVI/RzOjvr5xvb4N6h4/PU+TvkMYXz144lY/Xi7lvq6dO77gl2k+xg2Kv0Qvsz1Q5As/oLELvQpZMz9oYmY+qVSBPn3FLz4+LmE/tLWKPoYx2L7UplC/gmx1vWZhdr4QIsE+xfi9Ppjdbz9ICQ8+lvP8vlQW6b6hqoi9A1MivaC89L79YNm+ixPrvr8YtL7PsLk9C7hTv3wIkD0mjRq/glo3Po2amL4eNNi+X3lcvZMLrD/dZKq+DyEhvwWKqT3doCc/Xf9hvavyLL5l3Ze+x5Wyvt6h5L5fpLE+O6gvP/pOC76MaL6+W5QnPlr2krxCbjs/pAZPP3M9P7+u4Ss/8vlUP58zX79CeRc/A7n6vpv6oz4Jv+c9zu3hPmiQRT5HnbY+pG/mvhSsuL5PLke/zc6jPiRb87513F29Dw8KP73B/T02jCM/voFqveX8Fr6LQnI+KO0hPuHhj7yFbYa8j8kePfgMn77Kcic/iXuYvsJq5r4vmQQ+kdQlPxJbXb+5OhO/cI09P2Xt8L6UHyu/yFwev+m3JL+VTQI/f9I6v2ep2b7xvr4+vpbovRXPZ796FlG/OdKZv0TNTL/IWjw+AU20vdPWxz4BVNo+DBpOPsXNpL5YVAM+JWMfPxGxdb/soPu+SSaNvfGoCD5qtIY+EpxPP8Px/z3WaK6+9I4bP1injj8pbqs+cZ2kPhBdtL4YZ1q/ykEYv+Mscb+exUu/gyclPrkGz71T8B0/2P+4PkmM6z7vLUQ+pbtlvpUcWr9TYlq/zAlsvY9ZQL/lTAe/MHJ2vXDDRr4/2xg/r0pVP/5sLD8awqw/jBrUPgSBZr5AL0W/x+QPvcFv5j5N01w+1LwaP1+ffb5DQUW/e3ZBv84BDL67ppo+6JDtvVpxFj9AO9S+l7DqPbiLEb+4RVs/2LLwvu+AEj8WyIu+NlzWvSTt4b4ZpTG+FTDmvWZj5r7oJCk+WMkBvkZePb8qiUe/Nm24PldosT7G+Aq8RxYfPoydHb9IoCk/eI6pPslgjL7H+K4+NYauvpOYbb0xENm+truRvrq+vLxGO48+C3akvqs4LT6Tp/A+0ZKDvhbZUb/wPoo+kGoDvV7llr5e/m0/wL/ivbM2eT3ZUDq/a8jzPtcC0L6ItyS9axNyP2vnh762hIc+A+qBvL7vWD+k4HE9yyEwP1zTQj6lYYe+tBYFv0LEEL3Rn969zhSuvw6uHD4MQLi+ImXVvq7Dv74wnOC8TPRbvm4Tyb6J+KC+s0a1vk491r1k1X++mzt0vrYJ7j591hi/GntJPQ==",
                        "model": "torch-jit-export"
                    }
                },
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "97:0e:38:74:25:34",
    "timestamp": "2026-02-10T12:29:01.512Z",
    "debug_timestamp_end": "2026-02-10T12:29:05.236Z",
    "debug_processing_time": 3.723491668701172,
    "rate": 11.286951072899647,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9392824172973633,
                "center_of_mass": {
                    "x": 399,
                    "y": 94,
                    "width": 69.33333333333333,
                    "height": 82.75
                },
                "bounding_box_px": {
                    "x": 331,
                    "y": 12,
                    "width": 208,
                    "height": 331
                },
                "metadata": {
                    "age": {
                        "label": "29",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.8766618371009827,
                        "model": "age_gender"
                    },
                    "reid": {
                        "embedding": "UQ4UP3nU8b6uM2s+fEbiPHP1sD7J3SO+PfvXPoAshT09MME+QPVcv3k1eD5Zywy/bw2IvSvlGjwlJw8//HrXvi8CVr4Zamg/okZ/vYLXpTzbZoI/VPMUvxT0j76lWpg+IsWLv1ovEb7UrCo/JPBpvWLPPj/Jo6c+cTsgPsEmUTzXW1M/wRKzPk/5C7+JGVm/UhmYPbifl72LXPQ+58i5PpLUkz9BFKU9WzVjvy8Ai74jbUi9VzLXPZ+QEL9tDdS+nF6tvhzncL7Mjyy+AguEv3+RPT1CUxS/CpfMPQn1sL67Goe+TGYoPm7+qT+R1am+l4ZVv5URjT0WfXA/HH9DvgPqg75bQ8e+3yS2vgugDr/qkQM+A8Y9P+9k1r3zwJ++4y3TO3sPL77NDCw/ZvhSP3uYSL+iHxE/8F6MPxpoYL9muA0/JQRjvh1heT43aIe95XLhPi67uT4kA+E9zSwhvzGF7L4pP0i/+5apPpyv1L7Vb8C9Rz4pPwtF7z30bRI/RWJsvP5X4r3xtoE+rmU5Pgt7p72QLB4+JPE2PuUZ5b4tB1M/hcIQv8EwAL+eJzk9zAILP6jabr+KOaO+j4o9P9IpC7/z6EG/rctFvzywCr9U/qo+KZBkv3Wpkb5cfAg/R2OLvvbgTL/wrly/RSyHvzzIb7+qRLk+/gcDvjhG3T7Oc4I9p7qzPracEr4ECCu+ZCgAP17hkL/TuAC/++m9vdfuxD5ovnM+hGVzP5vN7D1ukxK+9DQiP8/EhD+oO58+KAiNPvrQSb7SCW2/ZcgzvxJVIr9a5B6/SN+oPi6fmr1hsSw/AOCcPlLpMT63tko+53VYvtDOZr+A73+/hD8uvtCtHL9dHvy+UbLPvdCONL4DsSo/9l2RP9oLYD/GoZM/bEuZPsm0x70d2TK/cFPiOawC2T7cu64+bveePkgtuL0Ie0a/eTQ7v4UlJr2udUk+BYVFvqHIKj9C98y+MtoJvuNkOr91XWU/I0hivkWv+D4ZK9y9OWntuvVx7b5zma6+bRigu25P871hsho+bykVvkTvCr/FRDK/i/boPvOy5D4O/eW8X2TkPfahTb+lVVA/2tkHP6ptlr5xWqU+eCwxvjTjML7L49S+MJd5vgHywb0fPHM+YCguvoX7jT2pdhc/cHiJvSG6jL+646A+tquDPnm3lL4tsXU/nBkRujACkz3mfB6/LEYaP61Ge74/GGe+IZ6dP6bgnb4Sf5I+HpO7vW02aT9a1Og98H84P9E59T1FbIW+V0gyv+8wnr75AFS9OwLIv98IXT2LvFa+6F4Xvz9StL5aNiE9CD8ovUQkAL+9tta+JtXHvgQ/pr1iabK9WjyYvl+fGD9Q7gy/jSdFPA==",
                        "model": "torch-jit-export"
                    }
                },
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
    "debug_mac": "33:81:ce:10:ac:d2",
    "timestamp": "2026-02-10T12:21:30.718Z",
    "debug_timestamp_end": "2026-02-10T12:21:33.440Z",
    "debug_processing_time": 2.721823215484619,
    "rate": 10.62079967995733,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9928065538406372,
                "center_of_mass": {
                    "x": 39,
                    "y": 79,
                    "width": 37.666666666666664,
                    "height": 71.5
                },
                "bounding_box_px": {
                    "x": 2,
                    "y": 8,
                    "width": 114,
                    "height": 286
                },
                "metadata": {
                    "person-attributes": {
                        "label": "M: has_bag has_longpants",
                        "confidence": 0.9290622472763062,
                        "model": "torch-jit-export"
                    }
                },
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "33:81:ce:10:ac:d2",
    "timestamp": "2026-02-10T12:21:30.818Z",
    "debug_timestamp_end": "2026-02-10T12:21:33.541Z",
    "debug_processing_time": 2.723052978515625,
    "rate": 10.62079967995733,
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
                "metadata": {
                    "person-attributes": {
                        "label": "M: has_bag has_longsleeves has_longpants",
                        "confidence": 0.9899972677230835,
                        "model": "torch-jit-export"
                    }
                },
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
    "debug_mac": "b3:2a:e2:c2:25:7a",
    "timestamp": "2026-02-10T12:19:05.090Z",
    "debug_timestamp_end": "2026-02-10T12:19:09.988Z",
    "debug_processing_time": 4.897983551025391,
    "rate": 14.464337542520422,
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
                "metadata": {
                    "person-attributes": {
                        "label": "F: has_bag has_longsleeves has_longpants has_longhair has_coat_jacket",
                        "confidence": 0.6650304794311523,
                        "model": "torch-jit-export"
                    },
                    "reid": {
                        "embedding": "IfANPyX3rT7AypM+DyDSvuf0wztKUqg90RSIvnxWXL9ud2w/yI9+vnslYz87Hae+aM6gv4u2rT7Qw5Q+5XzWPmfHwr5MIYm8vvSSPsAFrz3/bsI/dN1Ov9dXlz4GEZ6+265Cv4Y5Az5yLFi+ur+9uweBez8pV8g+Ad01P4lZMD+JwI8+P8zzPulsNL+wh2W+OsBgv6XL7r3j+iY+eYojv9hPSb6hGAc/CDSgvjVTrL7XczM/lMXLN5EwgL+xg/y+0J8wvvUiwr7C99i+pWscv1xGgD4EvcE+xjGJPcS+Mr6JAhK/fxNOv1VTa7y1DLg+fwsqv5yafr5sDeu+pKRwPkaPA72ICLO+c9FPv4KtLL/QPQc/hL9bP9NSB7+atew+/ifuvV/fBj/ci9S9QsBXPxcsA7/6qYs+yBm3Pn0pDr/XqJ89OC00voTcvT43kvA9RmhEvyO2Az4PufI+vyVSP1HVHr/iICa/pfrGPs0Un74HxCg/mtRTP5SOyb1WDII95YYtvwDQGr/8OCY+HEsQP3VESb/5wwm+YjZWvZRc0r2kkwE/jQq1vqPlxj43cJe/aFSaP8lhjL2i8ek+NhgzP9K3Yj7I2CS/howSv/KgqL5AFZM/84r8vtiHrb1M0e8+QZFhPuN3o751mFW/ADA8v8+oMr7VHo6+XOQ4PO44Yz0l3I4/wFgfPy3DNb43Htq+zy3bPuTgVb9+rYu9wL/svYdy7L3P4Tc/EhUKv/ljwT4Ps5a+NFaDP6ELBz8Bx7i9JZlNvqFzfD2PLDy/i9hWv1Huh74g8AI/2Pu1PpNJk77VqcE96LYZPjz33D6kURq+NvuJP+Dwnr8+uBw982oAv8O0RL2Mugo+Wg1mvhPbvj4iOMQ+bcQGP2+CVz9V304/Ct7WvmfH4j6qjvW849NCPrZqHb/IYCk958wTP2bgsb1vwO++VaNavOZfIb+OM68+3JI5vyTpij2ylMA+z6yXPj1xF79OvM0+MwIiv1QEAj43Okk8aGMcvrNwAj5xHSi/9S9lvmCSQr87voq9Iuvfvirlbr9VbGO/IXqCvvXuED+pypO+CG2Hv3YxHL4MD1Q/O7XoPSQAG79OO1s+tyiwvk2dVz4YKFS/BexxPhYuFz2xqCC/lzeRPihWrb70Iz2+b40fPZXVxb6Tkdw98JB9PrnlmT51Bug+Yeg/v6OEs75zjia/xEsdP/ksWj+EX28+sTVPPvoEvL/fkQQ/8kvrPI5yv70LiOq+trQaPrl7jj81bDW/uy+9ve25Vz70//W+g7yDPjZCHT2Zhw6/Izs5v040NL6F4KS+M5yivo/Dl7yeYQu/vcyFPQaAhT2q25i9BBNWvgLY8L5H1Ou+URyqPQ==",
                        "model": "torch-jit-export"
                    }
                },
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "b3:2a:e2:c2:25:7a",
    "timestamp": "2026-02-10T12:19:05.107Z",
    "debug_timestamp_end": "2026-02-10T12:19:10.101Z",
    "debug_processing_time": 4.9934165477752686,
    "rate": 14.464337542520422,
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
                "metadata": {
                    "person-attributes": {
                        "label": "F: has_bag has_longsleeves has_longpants has_longhair has_coat_jacket",
                        "confidence": 0.9285990595817566,
                        "model": "torch-jit-export"
                    },
                    "reid": {
                        "embedding": "W8YiPzGEqb7ENRi+gsSTPvcY0z7aAdi+Ie2yPnD90b7KP2E8yUlovz47k75zOBe/p5/8PYKzkjz4e5s+ysgePiunm76B8do+gCILvpqG/L3/oVQ/oNYgvxjUv77x6ic9G/PXvrOOt75Cn34+NGyyPqBUgz4PQRw+2C3UPqw6ez6qOXo/gA31Pq1cPr6cWSC/aT6rvgCsHb+SdCM//DVBParJRj8Cb+E9rVSivlSyz777LgM+Q7kBvSujVb8daG2+dfeCvuBgq74CHCk+QjRivzrERT7BA+K+Wh+TPTFMvb1nTqS9XggdPXiIkj80xCy+nC3svsXSjL2V7Jw+KC2SvXHIFb7IWCO+A//hvUCqmL3sJc4+6DoKP0uhsL4Ze5i+LI33PHXtlz086mU+4/Y8Pwxi+r67W9M+4YKmP9UQ9751Vw8/6fWAvkFQNT8FNjq+HhLIPtAMrD3eaWg+Cue5vtCCwr4yoYC/ahcjPeI0Yr45NI8+G9ymPtRIAr7Qgh0/mf2rPSfHJzwWI4M+koqMPq9soLwEcYQ+3qqfvqXY1L4bcQ0/hT44vkcN0r7E6HU+aWJQP/zFRr9ZRCS/soogPxusqL595kO/yMkBvGIHM7/dxfY+oeU1v4OJYr3cGCw/Zm8QPqSbF7/zIS+//zKWv6qEHb+jd16+XR8xPbIi/7x//BM/nCT0vYDey76+byI8xbNYP5V5dL+Urh2/vRAdvpzhkLxu79M+uwXlPv2cUD4Xgb2+M1JnP4ADOj9RPRo/g/UlPuUOF733x1u/ATlgv8C6OL8bwiq/8NGVvgQ3iz4lliE/yO+GPjwmRj+i+L68KHx7Ppz2cL9fLi+/dEOGvr8PFr/8IAa/AWVDviD2q713Xog/nfMhP5x9Ez9OM2c/vMmfPm/ixL2DOCS+W0OcPNaAmT5uqjQ/Yj1PP+ok3r57g3G+Ckkgvwxjnb6Ydrw+Z+57vmVp5T5Ew5m9cvfsPlqU9b6a4y8/gAjHvm2Qqz5qGju/h8F7vtC2oL7q9ri+ZHtRPh5DkL4Iab0+9znqvi8gEr+uWx+/INw6PmA5UD5V3wU+a/drvvnlEL/KiBY/a741PrnTVb77VCg/hR2vPUNLCz7le+e+WzJBvvSdyjy6oXk+wTZQv5s/zD5MeJQ+PVQSvWVZar/UW4k+5Y1fvl5HcL7BRSQ/G/HuvqDu3r573FK/JR4IPyR7Nb62kP69LyuGP1rK3bwtzBM/Bt6JvgzbID/Mlii+KJ4zP4pgMz8O3QK+OQM6v95gdj0Bf0i9a069v0TsBD07ezG++jLDvno5bL5CYC48ZndivrRPyL5LvGK+EBeIvgqqlL1SKtI86Q5IvnaQCz/fKhm/LQC6PQ==",
                        "model": "torch-jit-export"
                    }
                },
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
    "debug_mac": "33:81:ce:10:ac:d2",
    "timestamp": "2026-02-10T12:21:40.718Z",
    "debug_timestamp_end": "2026-02-10T12:21:43.640Z",
    "debug_processing_time": 2.9222302436828613,
    "rate": 10.409417580856887,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9832690954208374,
                "center_of_mass": {
                    "x": 231,
                    "y": 91,
                    "width": 67.0,
                    "height": 88.25
                },
                "bounding_box_px": {
                    "x": 164,
                    "y": 4,
                    "width": 201,
                    "height": 352
                },
                "metadata": {
                    "person-attributes": {
                        "label": "M: has_bag has_longsleeves has_longpants has_coat_jacket",
                        "confidence": 0.9448522329330444,
                        "model": "torch-jit-export"
                    }
                },
                "id": 1
            },
            {
                "category": "person",
                "confidence": 0.6787747740745544,
                "center_of_mass": {
                    "x": 1187,
                    "y": 495,
                    "width": 42.0,
                    "height": 74.75
                },
                "bounding_box_px": {
                    "x": 1145,
                    "y": 422,
                    "width": 126,
                    "height": 298
                },
                "metadata": {
                    "person-attributes": {
                        "label": "F: has_longpants has_longhair",
                        "confidence": 0.6425620913505554,
                        "model": "torch-jit-export"
                    }
                },
                "id": 2
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "33:81:ce:10:ac:d2",
    "timestamp": "2026-02-10T12:21:40.818Z",
    "debug_timestamp_end": "2026-02-10T12:21:43.740Z",
    "debug_processing_time": 2.921823024749756,
    "rate": 10.409417580856887,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9799434542655945,
                "center_of_mass": {
                    "x": 197,
                    "y": 98,
                    "width": 54.666666666666664,
                    "height": 96.25
                },
                "bounding_box_px": {
                    "x": 144,
                    "y": 2,
                    "width": 164,
                    "height": 385
                },
                "metadata": {
                    "person-attributes": {
                        "label": "M: has_bag has_longsleeves has_longpants has_coat_jacket",
                        "confidence": 0.9935144186019897,
                        "model": "torch-jit-export"
                    }
                },
                "id": 1
            },
            {
                "category": "person",
                "confidence": 0.5774734616279602,
                "center_of_mass": {
                    "x": 1196,
                    "y": 450,
                    "width": 37.0,
                    "height": 89.75
                },
                "bounding_box_px": {
                    "x": 1160,
                    "y": 362,
                    "width": 111,
                    "height": 358
                },
                "metadata": {
                    "person-attributes": {
                        "label": "F: has_longhair",
                        "confidence": 0.9247406125068665,
                        "model": "torch-jit-export"
                    }
                },
                "id": 2
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
    "debug_mac": "b3:2a:e2:c2:25:7a",
    "timestamp": "2026-02-10T12:18:55.985Z",
    "debug_timestamp_end": "2026-02-10T12:18:59.900Z",
    "debug_processing_time": 3.9150524139404297,
    "rate": 6.999297444698321,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9953031539916992,
                "center_of_mass": {
                    "x": 199,
                    "y": 92,
                    "width": 83.33333333333333,
                    "height": 92.0
                },
                "bounding_box_px": {
                    "x": 116,
                    "y": 1,
                    "width": 250,
                    "height": 368
                },
                "metadata": {
                    "person-attributes": {
                        "label": "M: has_bag has_longpants",
                        "confidence": 0.9799158573150635,
                        "model": "torch-jit-export"
                    },
                    "reid": {
                        "embedding": "dhyGPmrSZzx77wi/gh6JvdMbaz+nYoK/ObbKPvnk5LxnAaC8u5UIvgoXGbyphDk+cj5jvwED5j4lUUg/4CrEPStDuj6AZSk/W3ubvgXtOj+stxw/5EedviHM+77Lxao9IT4Ovxafbj4avFU+1OJ4PU68sL7D3Sg/a5fEvhbBaj9ytBu/R5vXPgIN7j5sj3W/ymTtvtsBKL/Owkg/uKLtvqwnuD7jLLG+uNe2vs/CQL6Ph9e+nRnWPEAwWb+Iq6O+sPfZPbTft75ejC+9Y4byvsw2cL0uO7e+pnhcvaVd+L1LrgS/IrvdPtwJiT8uEhY/ySOhvi5rAr8sI/W+rMMhPkYM7D3HRB++u1pQPufhaL0eD1Q//PNaPuLHED8vHq6+z+fvvqju8z6qBoS/FhC4PHoTrD6IZ/2+gnvKvPHPtr5UMCY/h7bYvhZoqj4OPRI+/j8DP0S/lD4Igio/xl2OvGFYFz9zhKa+/CkPPxTSfr8HuTq9yJVZvtquiDwM7qi8P8bfPa+vOL6LvA8/rNymPtNekz+/2CQ/K5bzPrrRTL4+n1K+2+brPnIoNL65c5G/gtqLvvtMh75wyA2/cgD3vgvpIT2Y5D6+nbTKPkvjC7/nxb8//+auvuLSm7xz/Ig9JgTTPnrJM77zDLA9q1m3viFQWT2Wv34+F9xLv/eCID51Gco+IQaGv+fEYz6HFiS/8/BZPtujBz/vMBW//LUvPi9zqL5hKo0+1IOqPznqmr2kDSa+afcOP/BMMT/nlVA+Wht9P4M00r7olMs+ityjvVDhg77nSn++G50bP3TKOL+KLEE+8vKQPnWyw7shsY6+N2O9vsQg4j7e1TG/652GvExKOz5g9/u+sOdcv3b5wb62kEY+jVfRPvfnOz/iV/S+LJH/PudjKz+4bTM+J7yDvv22pr4uzp0+UNEaPy1aDj+cNdQ+sSbEPkh3B77M+hK/KP/FvvxWBD/LHba+VNYCv6MSar75ui0/uKnYPlUY/T4XxV0/FPpZv9ZFdL4Ggga/vD5pP+26PL0RmY4+QM96PlZCe78EWCq/u9wdP7kw6T6RF2C+sm0Tv3i8FL4kg/y+ByTTPvOG5z72zNo8AC+sPHRqVj7RnkG+bG5fvtlRCT9Ujge/v3x9v8j7Wj8ryyC/0KmMvwW3KL8tQCs/h5WIP80K1D6zUVY/0snkPqG4476I8Ue7CqslPh08hj4l7yM/hWmEP4OgF7/o2re+8FwDPwI2UTx6eHg9QQ6TP5bRwj5uTJS+SncrP9Lat75rrA8+UygoP8/IDb/jDZ095s8sv0m62L0ChU69Et4aPfy1pT6E5g2+sv2RvphyAL9R+b09geiovqQ0Kj7okBU+q+FLPg==",
                        "model": "torch-jit-export"
                    }
                },
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "b3:2a:e2:c2:25:7a",
    "timestamp": "2026-02-10T12:18:55.987Z",
    "debug_timestamp_end": "2026-02-10T12:18:59.999Z",
    "debug_processing_time": 4.012442350387573,
    "rate": 6.999297444698321,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9960914254188538,
                "center_of_mass": {
                    "x": 183,
                    "y": 91,
                    "width": 88.66666666666667,
                    "height": 86.75
                },
                "bounding_box_px": {
                    "x": 96,
                    "y": 5,
                    "width": 265,
                    "height": 348
                },
                "metadata": {
                    "person-attributes": {
                        "label": "M: has_longpants",
                        "confidence": 0.9835643768310547,
                        "model": "torch-jit-export"
                    },
                    "reid": {
                        "embedding": "yZoqP457m70p2FG/vIiKO+8qjD8EUoa/zEH5PhPHlz10yR293L6uvftmS74XCJa8D25Kv1B6wz6IJGo/1XG+PSjFuD5YqFQ/dbTrvrDZEz/O7OM+/QSKvgQS2L5f9U+87xj0vqNnnj6ppZc8i5wqvoQp+r7euEM/zczaviXKOz+fOh+/g9TXPcKm0D5j2Wm/wTwNv+j9HL9PSmA/WosJv3W1/D7fwau+FZKWvR8aTb5sUAm/bW0tvjFuVr84LLK+ha/FvH6ZEL8FOOG9vqm7vtKSgb01eoC+Gn7ZPZsf272ClQ2/06t4PoTlhT/f6gY/WWBVvsJG575b4aC+/H1EPA50jD4mBrW+EjycPnTDYT1ACYw/uH/JPTZQ9D5xTSm+leLgviP0uD4mAny/h+xBvsudaj4Fzu2+rnqovUW3kL5Ks4A/JZvHvhzIkj7zcRw+X6IKPx+isj6CAbw+qRIwPJ/1Hz+Zsmy+xVApP5nFdL+cMf69D7C9vhcNVbx56AG+zcHBPXllh72i6Bs/A/tPPtVcgD99tnA/hZOVPowKQr4Ak8a9ezEfP+bshr7BUVm/iwiWvreWzL4Eg+u+dnbKvtcjGTzTIYC+F9ADPzJCFr+CD8k//O/gvjRHwj23zSM+auf6Pg40f74LLBA+tROdvl7FE713IWk+ROFqvzDhfT4tdN8+CJaNv+KCmD5fXwK/emiQPvznLz+qs/e+mL1pvUH07b6R6fI9ObW1P0MPmr4gUL2+6DUdP/9M5T6q0Bc+L01vP03KD78WB5E+oYGFva89nL6Lobs7b1YhPx0QVL8rgTs+MRKAPDrjcj4UReO+hqK5vjmazT5pWVm/R9CnvbVcPD62bwW/vPSNv2khBr86dww/Ult8PojkST+AM8C+TyinPsfcFT+CfRM+ZeOIvQWxP76dyys+FsgqP6rzFj+rR+s+qADhPhsYTr4CDxS/IlRgvhVsIj+qy/K+Bf0Svz1KFr1LzDA/MailPnY+IT8cJHA/pZk2v3IvZL5stge/d6c+P1ra/b1C1yI+mRVCPqniWb+TzES/opMCPwaIkD4ufLi9hmL6vrJEdb41lwm+FaJbPlFlcj6s+GE9kWNWPPdrGz7rBCe+Pe6+vTKdFT/KOWm+jtN3v5wwPT9XHCG/KUeDv9TeBL/5Gys/WxOSP/EVmT7jNzw/H0PBPtnvyb4KfQE92MjjPi0OAz8nYKQ+9fCUPzGE1774+VC+u5ICP3bBoL4hNy49jbmTP/25vj42Lx6+Ga4tPwBmuL7Fu4Q+H/wMPxMAFL+68m0+iCofv2kP+r5wMEG+vnzkvGkq4D6yLg++NcFvvszkTL/DAbm9nJO9vrg6uz6TciU+jTCNPg==",
                        "model": "torch-jit-export"
                    }
                },
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
    "debug_mac": "41:65:97:c3:5a:e0",
    "timestamp": "2026-02-10T12:09:19.470Z",
    "debug_timestamp_end": "2026-02-10T12:09:21.931Z",
    "debug_processing_time": 2.460519552230835,
    "rate": 6.604081651768196,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.997582197189331,
                "center_of_mass": {
                    "x": 527,
                    "y": 125,
                    "width": 67.0,
                    "height": 106.75
                },
                "bounding_box_px": {
                    "x": 460,
                    "y": 20,
                    "width": 201,
                    "height": 427
                },
                "metadata": {
                    "age": {
                        "label": "35",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.9521394968032837,
                        "model": "age_gender"
                    },
                    "person-attributes": {
                        "label": "M: has_longpants",
                        "confidence": 0.9166854619979858,
                        "model": "torch-jit-export"
                    },
                    "reid": {
                        "embedding": "VpGuPujDML4O5oa/UxDLvbXp1z7Cn06+Bg8/PsN7Fr6yQSS7Kzujvnvwwb0uRTs+Bc3pPYzbWT8RRxY/3+2XvhARqj5shhA/W9MUv71bcT19jYc+2/GBPkWnrL4aeoG9rN7svo5cuL0WfyY+EuLtvdEqCr8tdOY+R7XWvq4COD+cOTW/h0xdP96UcD/PmtC+BeIwvyDcR758tEc/3wqGvo71Dr34vZO+UlCePZHFWj4UO3G+/2unvoiuAz+uIhC/9D3yvGx8G7/JDvS8hx6aO4oRUrwZRXC+joaePnBdVr5gido9ofFxPpkqmD+7po0+F3+HvhWBLT64bJk+7lP3PujXFr6jaBc+IeQkP1JS3L78op0+wcg5P7Py4D6W4VK+6fXmvTAIjD70bEG/SKLavo2crz6CB6U9CJyuviDJXL52hw4/hao/vqY3AT4mYoS+YUT6PhPFIj97Q40+MJQ+PrmwBT+aioI+FBPuPlo4ur7Tr8s+oXI4vJ9BEz8NKzY96AHNvskO+DvzAcy+hv+RPh2/MT+HvhU/17XwPTYUF72MmYy+o2vzPk7NjD0eq8G/qiYOv/isZz42ML0+5HApvNnX0T3ElPm9FG+HPfl+Db/r658/fWMNv7C3hL4iSSa+Cr5NPshTHb8GWYq+Zsk7v1odor7rxKU+Z8lfv3S4xb5B0No+iNQVvrttmT7knNG+lv8bP9KA0j67fe6+SXDfPvaUpzwlP8g+GyrzPjudgby2McW91yJUPyMcND/lXgq/egFPP6h1JL8IMVE+AqOjPgvFz76q9ru+bYCnP8q8Yb2326s8eD8UP1ey27xY34i+Bdoxvvljrj0oKSa/h4HzvrbUhL0+AQy/+s3RvXJcEr/+/Tk/DEMtPxwkaD9NJy6+BzupPtwh0L5Yu1s9+1pRviCU377/CCE+FvhhPTVSGj2TqVo99bt5P8AlCL+tFSu/Y1h8vGnDKD/Cdpa9aMOhvvoMBr920J4+OF+Nvhw3IT+b6YI/Ve6vvrK6Nb/oYvG+ll9rPqUCSb+2kwW/7TEYPv/dur4DcPC+ttDbPrw+VD+cZ+O94bGavybpwb6VAii+GSkGPyFhzD3xAc89zlVwv6aGRj1kIiG/yl0mPr4/5LsGMzO+cpzRviFWQT/VBqa9q0Ycvzbwg78+Ois/NTprPhmUBz4OrXg/wz9FP8fThb4CnaA+T2EZv4JlpT6PtQQ/pY49P1UYQr8qThK+z3cpP/2Q5D02ga88HI+AP2T8lD46GO89eExoP8ED4T5wtDk+mt6Hvdwnir7q1aC+8BBuPA5rXr4lkPK+WhZZvYTQFz4uVrW+BZE5PHm8Zr53LhU+ahUCvg7N+j7aC66+9k3xvg==",
                        "model": "torch-jit-export"
                    }
                },
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "41:65:97:c3:5a:e0",
    "timestamp": "2026-02-10T12:09:19.494Z",
    "debug_timestamp_end": "2026-02-10T12:09:22.040Z",
    "debug_processing_time": 2.5467610359191895,
    "rate": 6.604081651768196,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9993913173675537,
                "center_of_mass": {
                    "x": 490,
                    "y": 119,
                    "width": 59.0,
                    "height": 105.0
                },
                "bounding_box_px": {
                    "x": 432,
                    "y": 15,
                    "width": 176,
                    "height": 420
                },
                "metadata": {
                    "age": {
                        "label": "29",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.881291389465332,
                        "model": "age_gender"
                    },
                    "person-attributes": {
                        "label": "M: has_bag has_longsleeves has_longpants",
                        "confidence": 0.9961508512496948,
                        "model": "torch-jit-export"
                    },
                    "reid": {
                        "embedding": "FgHDPvThsD391oS/+TtsveKu2j585KK+3dYRPqOSNL4h2EE9+o6svn5EZr1URsk+CcbsvQ663j61EjE/qechvsg/VD69RwY/eLq0vtBftT61N6A+26QHvheQ175kZy2+C0jevuSr7Dxfq1w9ZCj/vn0Gib7ogts+PboKvwFfNj9RnzO/dYU+PywYVT8dHLG+CdQbv/47gr5bYj4/GbSTvrNSEj6K2UG+VP1zvWqoU77aB5q+JcZ0vY7Uwj5Z0i+/RlqTPoiQBb/HA2u9otNMPndTOr5BbwM+TQ7ZvVleML5aXgc/7RfAPkulbj+ASYE+qDgoPSc5QD0yvqI+Ewr9PsSFpj5qQrY+u74fPwHobL65xBM/HCEwP06Wjj5h4uy+TsqFvjRQ0z5SxEu/c5D0vtPSXD4hABs+sjF0vixLPr5Iyfo+5Gw7vhfXXL1OUJu+VYwDPrs7ID8MmQA+ygRdvt6jBT8KvK+99VgrPxIuXb8lCW8+hX32POc1MD8/V9683oqEvtiYsTyKg4a+GLtYPqvQSz8pfFY/dxylvVBimT42CoO+5OzxPlDQ0T2LvKC/Q1DavhYpC77PJ2A+BIQ4Pmj/Ub5QpLS9wHojvtaoAr8P2I4/BRgrvyybGL2ug9+98+ybPTMe+r5KVJm+NZwxvzVu4b4NRhM/VmaGv/xqlL76apE+HppfvRVnuz47cj6+NlVIPz94sj44dfC+xTumPvycID65Pbo+tGEDP6auQDz1r2m+og09P4WoXT+g+Gu+gKU9P3sqEb952oc+EK9dPvumHb+i/qi+aI6sP94DtL794TW9ikzlPlfNIr5WsIa+gvkruz8pVT5W1DO//qDMvpz/gT3T4Re/3iG2vnr2FL8PyoU/1XYuP1EDNz96F8W+fs2/vF8mTb7l1v88P1rNPIkBmL5H45Y+QOP4vfIjdz5w3XI88zoSP3FlDL/hXxa/sI14PukGyz5t3ZC+2CSbvflAEb+rEBI/KXZlvo7MLz/dwGY/+MtmvkghIb9H1i6/dkLhPlDDJL+NpIi+PTFEPgj2p76MxCG/KBjWPtyVET9cGkC+NzA/v0Eq2L7I30G+RzjfPpVm5z34bO69HUhav3PHhz46fRa/UTM/vJGNh72i5729XUxsvstjEj9+Wq6+Tk4xvwYOc78VEks/DLpEPjns9L3hmoY/Hb1SP+HxPz1o0Pg9IUE8vzRJID+O+XU+9iY2P1QXHb9DxRG+D/lIP7vSiTxKyUO9yuKQP05KBz/ZVp48ydN0P0smmD4zPhE+JMe+vOp7NL69zdK+haTgPW5HZL5HgC2+1fygvpghhT5p+F694u4EvkPYhL7sKwU8J3exPT1uFD8GW7m9PjQGvw==",
                        "model": "torch-jit-export"
                    }
                },
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
    "debug_mac": "61:9d:fa:a8:fc:c1",
    "timestamp": "2026-02-10T12:14:10.652Z",
    "debug_timestamp_end": "2026-02-10T12:14:15.120Z",
    "debug_processing_time": 4.468069553375244,
    "rate": 10.723265157886189,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.98388671875,
                "center_of_mass": {
                    "x": 650,
                    "y": 81,
                    "width": 35.333333333333336,
                    "height": 76.75
                },
                "bounding_box_px": {
                    "x": 616,
                    "y": 6,
                    "width": 106,
                    "height": 307
                },
                "metadata": {
                    "age": {
                        "label": "40",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.95361328125,
                        "model": "age_gender"
                    },
                    "person-attributes": {
                        "label": "F: has_bag has_hat has_longsleeves has_longpants has_longhair has_coat_jacket",
                        "confidence": 0.8408203125,
                        "model": "torch-jit-export"
                    },
                    "reid": {
                        "embedding": "G0WOPmNU076x1Zi+TMzCPpQFSj+1YEa/iOKXPpcwSb0fTVw/uL6Bvy1jDr7SUgi/d79dvmgyED7oAZ8+gy0yPpCxfr4Qrv8+VrCfvkjowL44Zz0/WHukvuAe5b7AcPY54Vtbv6EhPz5UJ00+nshePocpFD9vRNq8nCa5Pq1jj73saXI/H0PqPvfrwL68F/K+rpRmvVPhzb5Uat09IBjvPKd3VT9B3Ow+Kb5zvyVa8r5Cg04+6h9QPWMOEr8US+a+m7cHv2zX9L74Wok90JlSv9jWDj4VICO/304EvifYs74b5ZK+CjUAvLSlrT9aWJy+XSEfv1ZLtL2ZAbk+e6JwvpFSpr4rkV2+T+R/vuud4r7sZXw+F3k3P0EaHL/kp6q+pichvlWp0L6Cuys/JVc8P5/CO7/qCq4+iKiZP7dzAr9G2gc/6/6bvh3s4T4McVa+xn/gPij5Uj7s3aQ+0SQRv/aznb2bmXu/XumfPq4Sgj28g6E+X12ePu420r7oFww/6Dy8PeB9ur0qcMg+RO79PiDIjb6oIVI+65I/PXsEj75yY08/sxQtvxY72r44Ank9bFbYPo4bar9GqCC/bAMpP7q75b67RHG/SuCuvqaXDb8gzNI+Qltov/DYeb62HTI/C8sKvtXBLr/90EG/BoWiv9+yAr+pVZK+gdqOPk3uRD6vkIY+D4ZOPt3xe77o/tO8RxBVP9Iaqb9vGAm/+0uhvtjiVz5Q6pg+/ksdPy/vAz+7zEW+Dv1EPzLDlD/6nEM+mpxSPikpar7aIGO/spFIv1Xhtr6n9B2/JBBUvdSOFT62Kg8/hnNMPtMiDz8Eb2k8TPstPlmqU7/+Z0u/IvMlvrazjL7O/j+/GeNDvfIhlb2OJoY/NoxRP5WvKT8qL2M/2JWKPihjY73Ju9W+pwShvTxuHT+XuRM/AoKYPjBDzbw0cG++cTcov7K3Ez5S9vo9vLdCPg72eT70WcK+CHEIPw6C+L6eQxU/wTFkvvsJrz4UhMu+eU0kvj92Fr8U1Yq+bDRePu/zCb4SmSQ/TzejvmWkcr9yUDW/iILSPBgcbT5CbA8+PJR1vOjNFr9SzDI/XS69PpeusD38V80+ouPqvXXwND2ZKCC/IP6AO6CZED0yLow+zOy8vrBdFj5rUZw+1U+xvSkRVb/JIyw/rfoivVlnMb6B73k/OFhXvv4u+j0uRVS/g3DHPvLa8b5u0xa/keqNPz6Hz73HwVE+9dKTvcDPGj+Dd8u+WrxEP4qmjz4seZ6+WbaQvjK1mr6NVpY+XQjvv5i9Pz78lcO+54nyvi0C876aK8m9PeWIvnCwML+aZxy/Xmm9vgCuVD1a2U6+z03hvgUuBD8bHUC+Fc+VPg==",
                        "model": "torch-jit-export"
                    }
                },
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "61:9d:fa:a8:fc:c1",
    "timestamp": "2026-02-10T12:14:10.653Z",
    "debug_timestamp_end": "2026-02-10T12:14:15.225Z",
    "debug_processing_time": 4.5717058181762695,
    "rate": 10.723265157886189,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.984375,
                "center_of_mass": {
                    "x": 621,
                    "y": 83,
                    "width": 45.666666666666664,
                    "height": 78.0
                },
                "bounding_box_px": {
                    "x": 577,
                    "y": 6,
                    "width": 137,
                    "height": 312
                },
                "metadata": {
                    "age": {
                        "label": "39",
                        "model": "age_gender"
                    },
                    "gender": {
                        "label": "Male",
                        "confidence": 0.93505859375,
                        "model": "age_gender"
                    },
                    "person-attributes": {
                        "label": "F: has_bag has_longsleeves has_longpants has_longhair has_coat_jacket",
                        "confidence": 0.7646484375,
                        "model": "torch-jit-export"
                    },
                    "reid": {
                        "embedding": "9ifcPnAYB79AFMY78mC+Phcc5z7T1ja/SOapPsLEpr7e5gg/sKZev5CnvD13HoK9HqFuvpaWA74wl7M+kC+MPk1vmL6axww/8B5BvMZUo75V3To/PoS2vu2P1L59WcM9ewALv/niAT6E+co9qIBqPgBv6j7da3o9M8e7PnH6ML5DWYw/k+fJPtT2Gr50MLa+gW61vO9nB7+FeN490ENKPqjWgj98bi8+5AhRv5dsrr7Mc7k9YhiDPv09TL/+Ure+wpwEv+W5yb7Qjes96kp0v+wPCz4+bUi/Gi85vkW0dr5bqeW+u3lYPQyrqj8b166+4n4Tv2Cz6DyHrC0/6eWovgV/hL7jCuu91Qn4vlsaz77HJ8E+PfgtP56JNb/uJJS+bBVNPddKnr40UQc/4TQ5P7bcH7/2Fqw+0oVxP9d9w75eBMY+G1Dpvu9nxz6D1Lu90h+HPnQPbz6iD4A+vGP8vnOae76XnoS/Jj0aPyAjH75Fgak+3AXAPnLGg754KVE/NoUJvth4Fr79IbE+pwvJPm4jQL16CeE+hD2qPBWFsr5O3iA/2r5Qv6UZi74A6pA6FO0aP0HnPb8ht/e+E1oLP+avlL6jhj+/4K8qvnYi174cM0E+iTHkvjr1p75YH/c+RS+FvQ8sN7/ptYe/61K5vxaOIL/qzKS+49RbPRpWij6yh1k+YDNoPly0h76M5mU9qRUQP3LQhb/TUiS/w0hDvtQwYz7wD/E+JSwGP7lrOj6b3s++ZuZRP2mRfj+0CBk+gHvWPUQ+sb3FimS/WySxvgZEEr8ddgC/wrUMvhbzfj5WqhE/KIKKPuh12z4iCGA9qrCDPo1AS7+4gj6/MhyRvivY6b73dk6/ptGDvlsa3b2cH08/hj4LP5oJBD8fCmo/HYPAPmr+OT6Tj62+KACfPfKtLD/9QxM/mxwoP4rpjb5nEcC+DDE6vzY6FT1hwS8+eH12PgAMqz5SdpG+CVE8PxjPvb7yQNk+oYAVvjBA3z5OFQ++k30Kvz2QF78qFd695xpRvfcy/r0jJi0/7HfMvu5yL79st1+/ExF7vXbwHT5GDjo+eYPlvR+jDr+AyVo/DrLvPic1jb3tiE4+Ai58vmcq3j0+pRW/LOt8PSWlTT3MIeM90FPlvm3EvT7GYn0+x2m0vVPwQ79XvAU/KdebvmR0WbxRb4I/rSZovnh0Fj0Utii/OwPePjbA6L5JQ0K+yLiKPw/3+b7gqPo9IBiKO9icSz998+y+ZmAnPx5XCz9xScy+In7zvlT/E7/m5jq9rgbkv+iiGj7oz/K+pfaQvm1jpL3focW9ed27vsiuNb8kpmO/4AoJvw7bbz4sdXa+Cn3FvlQ05D5FnKW+RlKcPg==",
                        "model": "torch-jit-export"
                    }
                },
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

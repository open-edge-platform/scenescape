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

```json
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

```json
{
    "id": "atag-qcam1",
    "debug_mac": "47:e6:77:25:3b:f9",
    "timestamp": "2026-02-06T10:55:31.749Z",
    "debug_timestamp_end": "2026-02-06T10:55:34.172Z",
    "debug_processing_time": 2.422764778137207,
    "rate": 9.499186626193884,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.987617552280426,
                "center_of_mass": {
                    "x": 321,
                    "y": 89,
                    "width": 56.0,
                    "height": 88.0
                },
                "bounding_box_px": {
                    "x": 265,
                    "y": 2,
                    "width": 168,
                    "height": 351
                },
                "age": "22",
                "gender": "Female",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "47:e6:77:25:3b:f9",
    "timestamp": "2026-02-06T10:55:31.849Z",
    "debug_timestamp_end": "2026-02-06T10:55:34.272Z",
    "debug_processing_time": 2.422588586807251,
    "rate": 9.499186626193884,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9945145845413208,
                "center_of_mass": {
                    "x": 296,
                    "y": 90,
                    "width": 64.66666666666667,
                    "height": 89.0
                },
                "bounding_box_px": {
                    "x": 232,
                    "y": 1,
                    "width": 195,
                    "height": 356
                },
                "age": "32",
                "gender": "Male",
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

[See JSON](./example_output/agegender_reid_cpu_raw.json)


**Example SceneScape output metadata:**

```json
{
    "id": "atag-qcam1",
    "debug_mac": "09:91:b4:33:31:d0",
    "timestamp": "2026-02-06T11:37:26.077Z",
    "debug_timestamp_end": "2026-02-06T11:37:30.922Z",
    "debug_processing_time": 4.845034122467041,
    "rate": 13.856813149734855,
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
                "reid": "IfANPyX3rT7AypM+DyDSvuf0wztKUqg90RSIvnxWXL9ud2w/yI9+vnslYz87Hae+aM6gv4u2rT7Qw5Q+5XzWPmfHwr5MIYm8vvSSPsAFrz3/bsI/dN1Ov9dXlz4GEZ6+265Cv4Y5Az5yLFi+ur+9uweBez8pV8g+Ad01P4lZMD+JwI8+P8zzPulsNL+wh2W+OsBgv6XL7r3j+iY+eYojv9hPSb6hGAc/CDSgvjVTrL7XczM/lMXLN5EwgL+xg/y+0J8wvvUiwr7C99i+pWscv1xGgD4EvcE+xjGJPcS+Mr6JAhK/fxNOv1VTa7y1DLg+fwsqv5yafr5sDeu+pKRwPkaPA72ICLO+c9FPv4KtLL/QPQc/hL9bP9NSB7+atew+/ifuvV/fBj/ci9S9QsBXPxcsA7/6qYs+yBm3Pn0pDr/XqJ89OC00voTcvT43kvA9RmhEvyO2Az4PufI+vyVSP1HVHr/iICa/pfrGPs0Un74HxCg/mtRTP5SOyb1WDII95YYtvwDQGr/8OCY+HEsQP3VESb/5wwm+YjZWvZRc0r2kkwE/jQq1vqPlxj43cJe/aFSaP8lhjL2i8ek+NhgzP9K3Yj7I2CS/howSv/KgqL5AFZM/84r8vtiHrb1M0e8+QZFhPuN3o751mFW/ADA8v8+oMr7VHo6+XOQ4PO44Yz0l3I4/wFgfPy3DNb43Htq+zy3bPuTgVb9+rYu9wL/svYdy7L3P4Tc/EhUKv/ljwT4Ps5a+NFaDP6ELBz8Bx7i9JZlNvqFzfD2PLDy/i9hWv1Huh74g8AI/2Pu1PpNJk77VqcE96LYZPjz33D6kURq+NvuJP+Dwnr8+uBw982oAv8O0RL2Mugo+Wg1mvhPbvj4iOMQ+bcQGP2+CVz9V304/Ct7WvmfH4j6qjvW849NCPrZqHb/IYCk958wTP2bgsb1vwO++VaNavOZfIb+OM68+3JI5vyTpij2ylMA+z6yXPj1xF79OvM0+MwIiv1QEAj43Okk8aGMcvrNwAj5xHSi/9S9lvmCSQr87voq9Iuvfvirlbr9VbGO/IXqCvvXuED+pypO+CG2Hv3YxHL4MD1Q/O7XoPSQAG79OO1s+tyiwvk2dVz4YKFS/BexxPhYuFz2xqCC/lzeRPihWrb70Iz2+b40fPZXVxb6Tkdw98JB9PrnlmT51Bug+Yeg/v6OEs75zjia/xEsdP/ksWj+EX28+sTVPPvoEvL/fkQQ/8kvrPI5yv70LiOq+trQaPrl7jj81bDW/uy+9ve25Vz70//W+g7yDPjZCHT2Zhw6/Izs5v040NL6F4KS+M5yivo/Dl7yeYQu/vcyFPQaAhT2q25i9BBNWvgLY8L5H1Ou+URyqPQ==",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "09:91:b4:33:31:d0",
    "timestamp": "2026-02-06T11:37:26.093Z",
    "debug_timestamp_end": "2026-02-06T11:37:31.008Z",
    "debug_processing_time": 4.915539026260376,
    "rate": 13.856813149734855,
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
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw(memory:VAMemory) ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.xml model_proc=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! vapostproc ! video/x-raw,format=BGRA ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

**Example raw output metadata:**

```json
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

```json
{
    "id": "atag-qcam1",
    "debug_mac": "7d:f1:0e:d7:43:8f",
    "timestamp": "2026-02-06T11:06:28.534Z",
    "debug_timestamp_end": "2026-02-06T11:06:30.739Z",
    "debug_processing_time": 2.2046027183532715,
    "rate": 10.256629226842627,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9453125,
                "center_of_mass": {
                    "x": 355,
                    "y": 87,
                    "width": 49.333333333333336,
                    "height": 87.75
                },
                "bounding_box_px": {
                    "x": 306,
                    "y": 0,
                    "width": 149,
                    "height": 351
                },
                "age": "21",
                "gender": "Female",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "7d:f1:0e:d7:43:8f",
    "timestamp": "2026-02-06T11:06:28.628Z",
    "debug_timestamp_end": "2026-02-06T11:06:30.838Z",
    "debug_processing_time": 2.210261583328247,
    "rate": 10.256629226842627,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9853515625,
                "center_of_mass": {
                    "x": 321,
                    "y": 90,
                    "width": 55.666666666666664,
                    "height": 87.5
                },
                "bounding_box_px": {
                    "x": 266,
                    "y": 3,
                    "width": 167,
                    "height": 351
                },
                "age": "21",
                "gender": "Female",
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

[See JSON](./example_output/agegender_reid_gpu_raw.json)



**Example SceneScape output metadata:**

```json
{
    "id": "atag-qcam1",
    "debug_mac": "2b:c5:9f:65:27:84",
    "timestamp": "2026-02-06T11:31:12.820Z",
    "debug_timestamp_end": "2026-02-06T11:31:16.124Z",
    "debug_processing_time": 3.304636001586914,
    "rate": 10.94028770022226,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.998046875,
                "center_of_mass": {
                    "x": 700,
                    "y": 81,
                    "width": 61.333333333333336,
                    "height": 80.25
                },
                "bounding_box_px": {
                    "x": 639,
                    "y": 1,
                    "width": 185,
                    "height": 321
                },
                "reid": "ogOvPvuQvr46r7G8wAQzPoQpKj/74+W+8FLfPn7cPbzJbzw/lLVlvxsc5r3YoRO/o+ewvjqCxj52nRw/sITPPRBL5b3pji0/uWlvvtTnbL53xiQ/58LBvnOBhb6Ilwk+Wo+av/k7Zr2McuQ9BINRPs+tOj/gjDs9HmPjPnKPID6iIC8/lzDiPgvMM74Pj2+/avXiPWW9lL7GS8M9ABy8u6sLFT+aA9I+VKpCv3z8qL78ypO8ItCIvtSGGL8k7hG/TZq/vq7skL1tygW7YvAcvzwcXT65Fy2/RqkavgAOkr50XkG+zcIxPlb+sT8RJdG+jt4Vv27tCb5jhOk+CDbwPUkN+L7qJkO+XehDvhamub704s0+HQsYP1F62b4B+8O+1issvfqAHL2MBis/1BmBP+bsHL90XlU+sDZ7P7YAyb7wtSQ/9uKPvsSTED/7w2Q+7ilwPoTN3T2KgTg/0fbjvhbrgr6VFVG/NCy3PvV2J76AuzQ8V8EUPzYke76YLvs+OPs2Pm3O8b322w8/zOvCPgewzLwibXI+mLDKPbEEjb6ksTw/SWIYv/bUrL516yq9AHAvPgTrhL+ir+W+wIvpPqsqF7/hczu/W2/2vjS0zb7lR5M+BRRKvy5tc72R1FM/iG1DPfck7r4TUSy/tU6fv9104r4B4AQ+Sx6pPT/4gj5/moC9rIrNPQtcGr7D/Km+xRg8P41Djb+/jMO++8Uuvshqiz1pFdY+oha0Pq4/+D1h6qK9LNAnP966pD+jo7w+2B+ePmIIQz3AnjK/Np88vwCjuL4qYVK/UUeDvgpZrbx9pN4+eqNpPooEwz7/puE+tbPfvTqZEL8sdDm/Db8ivgtEPb4Fvzq/TZiBvmV6oL1QAh0/dXFLPwT9OD/HvGw/hNINP84xfr0rygi/sJtvPJ8b/D7LZBg/kMAFP5u2Hr7FH1y+17KTvsI0Rz15gNW9RtiQvVpyrj7Ty8y+2c7HPhV+d77njpg+NkoUv9FYvj6g3r+9m82TveV0tr5JUI6+xvySPqX3A76/2Gs+AdapviS9Sb92pWi/QLB4PuRJQL3q7cA+SUhjvYgOxL5rNxc/1869Pjt57z3cewo/sZQYvmJ2jj5aOIy+RqZOPti9HD1Q6xE+EvE+uzBbgz32ULo+iraOvsmtTb9lK8c+fBFkPiIF173sjIw/gNj6PJBpZjyT9DS/mhboPmQTur1nTfG+IdwwP6FIQ7698EU/r5Hpu662GD+Bm9S+U61xP078BD88Egi+W5TeviRIV74I66Y9oKTFv+BsmTxGrK2+cY6rvpXjWb6HoEe84k4MvdRWzr48oD2//ERLPg9ZybyVnL29pmjuOuxK9j73N86+iiD9vA==",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "2b:c5:9f:65:27:84",
    "timestamp": "2026-02-06T11:31:12.919Z",
    "debug_timestamp_end": "2026-02-06T11:31:16.220Z",
    "debug_processing_time": 3.3012702465057373,
    "rate": 10.94028770022226,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.98388671875,
                "center_of_mass": {
                    "x": 696,
                    "y": 80,
                    "width": 56.666666666666664,
                    "height": 80.0
                },
                "bounding_box_px": {
                    "x": 641,
                    "y": 0,
                    "width": 170,
                    "height": 320
                },
                "reid": "EirAPrr7Zr4TDJm+QMm9PSWJgT99wAK/XLjrPnYYzj28/SM/NUx8v2sDUb3YgOq+AFcqvhf/Jj98ceM+LqBkPtDZc74dkM8+ufc8vnQoH75SWCk/M7TIvkDhD7+cGx0+eFBwvwA2ij0sJaQ+X9+xvTKuLj+IGq08GnmIPhrpA70sRHg/3qLVPmnDor73ADm/8emmvV4P2r4ATT8+oLvrPfxaUj8TGLk+BSZbv0M4br6s1dA903WKviucSb+XmjW/A0UMv0h+074DDgG+Y/M8vzSltj4OUEC/HOYMPbEPFL4jO8+9+biePqVKvj+YSo6++Zkgv9yvoD0E0SI/SeqHvkYw4L6WwHi+ClMtvo4bib4TWck+njAeP6iW5b5D1fu+2TUhve8tWb5F7yo/opOJP0F6/L6MhFU+Vp2UP7GHv75RF2U/Z7KOvnsPCD8AtWY635G1PkZhgT42DDA/gDtDvzTl074B/0e/OOQCP0l09r3A1Xc8G8mQPmeWmb5g4vk+hEOpPey3Hr2nRZY+VBwcPzapKb66+sY+8ZqePQtol75Eunw/7BpCv8WXqr2Pa3W+4BG3Ptw3Zr+u7+C+WR0/P0pBk743BWS/9hfnvuprHb8WaOw+Fnk5v96Hub0lWCo/wJEGPFp2NL+aGC+/humZv4AOA78sWnA9o+FhvbQ/lj40zKU9TTyLPozQhL0H1yW+QE5RP10Itb9CWr6+Nf66voAqZT3KGpI+v//qPsQhpLy/EJO+1i1ZP16dqz9+VK8+hKBMPng6T70RsWO/uK0Xv9lIWr6wAkS/fx8nvRI6LT70ENs++ql2Poh45z6jnKo+eZ6pvBRQR7+Z8Rq//EMivkfmh74xJD2/bTxCvlgSAD1c/E4/gzh0P4+WHD/KsEI/bOuDPn1UOb5KkO++Eu/EvdiIFT8JjR4/i3jSPqgEm77Dflq+4ubvvk/sbT6q/vg9BAkLPXr3Ej8fYVS+sD3cPr6Mpr7MmBA/0tUjv3BWuD6Yop6+oisevnPNnr4h7bK+Ej2PPscICr3OJIU+6ynivv00ar/OvD2/tKuNPQ5E8D5oHoM+C7NmvjaAEL++gEE/Bg7zPqm4Wbyy/Qk/10pkvqmXXz4jE9u+4prUPu0n/z0IvFs+pLiZvkSzhD02faE+fbvovRveU7+0CRM/YNejPYBkRDxJop8/+nKlvhwOBz4wLjG/hreePkXAg74ZO/q9WqN5P0qurr6v3xM/mAarPLKfGj9xnYu+yrCCP2oszz6c6Ha+IaSpvksPrb7pZwc+ZpTav2bYWL3MWZe+BWG+vi0ijb75JO69VhENvpnXE7+VN0O/M/GvvQyLmj188xu+dThqvvpNLz/3P7y+8Ed5PA==",
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

```json
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

```json
{
    "id": "atag-qcam1",
    "debug_mac": "81:e0:ec:b0:ac:49",
    "timestamp": "2026-02-06T11:43:15.722Z",
    "debug_timestamp_end": "2026-02-06T11:43:18.745Z",
    "debug_processing_time": 3.022975444793701,
    "rate": 11.65819912160486,
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
                "person-attributes": "F: has_bag has_longsleeves has_longpants has_longhair has_coat_jacket",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "81:e0:ec:b0:ac:49",
    "timestamp": "2026-02-06T11:43:15.822Z",
    "debug_timestamp_end": "2026-02-06T11:43:18.846Z",
    "debug_processing_time": 3.0240232944488525,
    "rate": 11.65819912160486,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.971470296382904,
                "center_of_mass": {
                    "x": 533,
                    "y": 81,
                    "width": 42.333333333333336,
                    "height": 77.25
                },
                "bounding_box_px": {
                    "x": 491,
                    "y": 4,
                    "width": 128,
                    "height": 310
                },
                "person-attributes": "F: has_bag has_longsleeves has_longpants has_longhair has_coat_jacket",
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

[See JSON](./example_output/personattr_reid_cpu_raw.json)


**Example SceneScape output metadata:**

```json
{
    "id": "atag-qcam1",
    "debug_mac": "c5:70:aa:ae:e4:03",
    "timestamp": "2026-02-06T11:49:14.595Z",
    "debug_timestamp_end": "2026-02-06T11:49:19.755Z",
    "debug_processing_time": 5.160121202468872,
    "rate": 13.881287541836151,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9784737229347229,
                "center_of_mass": {
                    "x": 516,
                    "y": 84,
                    "width": 40.0,
                    "height": 77.75
                },
                "bounding_box_px": {
                    "x": 477,
                    "y": 8,
                    "width": 120,
                    "height": 311
                },
                "reid": "6qYjP8BEPr+saV2+Cc66PXjoCz+v0vG+t9oTP2Zo0b6OjAs/iFxdv5A1Sb6tb7m+eowJPzdIUD5Ay0A/lFUavZf5ub5J754+swtMvjx6ib7ZqBg/+Sgxv1gPTr4tBMs95WgAv6DPAz6jD1U++whYPvqU9D4f0hA+ErvDPeBRZz5gYIs/mIroPpGvp72czAu/gAQWvxnZer9Ou4s+GQ1TPupNIT+DrwU/ta0Nvhk6w74GGgK+PcCmOwwp/L4ThQY+eWIXv5bo5r50kAO9Ai9zv0xqU76W4WC/POH9PFJEj75KQfw9/OnKvbUzoT80coK8O6O2vq4lvr5wK88+5K+IPR9n2L6P3YS+hr1avq97tb54GrI+0f2xPkEzmr4yfpW9Vxn+PlF08r3KKQE/8/40P/PoDL/EUQs/+F2cPxRMAL+blQI/dv+Nvs1QkD5EbM6+hCLjPaHozj0aBq8+3GYvv5js+L7RGHG/4pSBPVauyr770gg+lziuPhSDkr40Lkw/e1lwvry0bT5JWJk+ErQzPmCRHD45V9A+TvHevaGJfj0+TTA/1h0hvtXizb6ltBU9VKsKP3yDL7/HNhC/PSdnP6A4UL6uf0C/3ObFvohm7r4QLNo+Jz4cv045j77ImG8+UGe4PcQP+76yiBy/9cGNv4YOOL8PXCC+iV9fvPVdhz5VCCI/l12MvqorcL6Sriw+YNRrP3I6jr9GpS+/IA6yPHK9LL26e4w+NgEiPxToIT4Wvom+MCxNP1s+IT8Vheg+OpG6Pvf4r775ZEi/hgiJv6XAw74/qom/m8jSvb+1v70bGCI/VUyjPrIe+D6URjU+sZqAPgeAcb82npC/xZk0vn71mr5jP7m+Cai9vruNtL5xSmo/zOrMPpVOGD8DBow/XADLPvQqIT7ClRG/+V/JvC0BFj5Qd8A+pIjdPoWVkL6fTzS+v3oOvzp8h77nvpA+ZK9+Pf/UCj9bD76+Ym/UPQXPKb+R55A/94Rpvugjsz4DC9G+U4jZvXyw/L749Wq+BJJCPCM217tqpwA/ZURkvulEcr8IwjK/MSNiPjFP1T10Z2k+B3cfvvMoL7+47ng+mBZHPhiUXb5/Jz0/bEaCvVM/U72K6uy+/JcmvnfNGD33UkG+gsdov5AZoT7H9HA9ZxvHvTBr3r7DvEI+leguvt1/eb5Gvh4/RfGDvpED/b7pdEK/C6QFP/DVA74BIU2+h+tcP49hxr24UZ8+kCervtAMMj+LHQ+/N1M7P4PBJT+Ggt2+7Gj2vjrVWL4zvS09C2yavzJ4UT54L2i+k8yivhNlI76dUls65t0TvhSLBL8WvBC/DKkjvzimjL0Ix80+IshDvDWVST8Lu2y/ZJjYvQ==",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "c5:70:aa:ae:e4:03",
    "timestamp": "2026-02-06T11:49:14.601Z",
    "debug_timestamp_end": "2026-02-06T11:49:19.828Z",
    "debug_processing_time": 5.227355241775513,
    "rate": 13.881287541836151,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9801545739173889,
                "center_of_mass": {
                    "x": 502,
                    "y": 88,
                    "width": 38.333333333333336,
                    "height": 83.75
                },
                "bounding_box_px": {
                    "x": 465,
                    "y": 6,
                    "width": 115,
                    "height": 334
                },
                "reid": "vgCAP1OqR78lf/I9honDvqwrlL6cAQa/AaRIvtdKoT4cFPw6r9+2vqwFTz7qYIG/rYUVv4pVZb3G7LE9kBNHPgKGAr+5hlA//0VUvow/CrwyoJU/vsVCv72hhz56Pw6/rZBUv9ZcVb0JJjc+tAjEvO9ESD93cs0+DUXzPooLED4JJOw+F7szP/lYF79UaQG//6ZSv/Gw2L6ccQM/WilsvVy8lz9I2wM/3wmjvXpPAb9XuAA/0QCVPnH9Vb8h5oO9AmCGPrv9fL6Zlz6+eRnBvxBwnz76t4i+oixTvpEi1rzvVJW+/+MEvlNSPj+MmIm+GqwSv4QWWDx7Vtc9WYDuvY10Ar5CJHS+pInUvkn7G769OyU/0GEVP12T6L43Ev09hzypPsreEj3pmZ8+AhQJP6Q6FL92nd89bbw8P6H+K763VfM+WlW0vo1CHD8bO8a+774jPtsGgz3uCoc+JSjOPiR0NL/5ilG/kWKXPnIbiz6oCpk+UZr5Ps0e1L0cMzw8JkZOvi7xXz7r5Gs/lQZbPmCLB7/VEGA8ybMSvy/SQb1ZSdc+1d6Zvg0HRT9/kE2/XSpjP5BG974q5DS/lbUuP9ERDT6xyQm/Cnb2vnpyqr6ejp8/TzpgvsOxTr7WxiA/GqtgPkVFKT0GfBa/6Xxdv3Rkjb/drRq/v1SUvrRAC77nFzg/GEkFPzQtAT/Xah2+FIAHP7qiJ79Rr6C+nlDkPdsdkL7Ys2s+MdO/PvtcA7+hDL2+mSGvP+vBiT9MsqY+59UOvWPMML8G7Ly9THcxv9k+jb79EdG9Vx0Bv1h+xL2us90+R2eEPpvZlT4ePpW92LWrPpTDdr9lWt2+QGSBvqlBzLyd1uK+xEUcPqLIhD0rYT8/3ezzPkVqoz+b1PA+TqzgPZfSyz6OAf+9AQ7sPQIYbT5vWe8+2PGFP0NPo75FD+a+dyAEPzttw74QJuA+LRvzvZVKqD6V9aw+WyGHPoPeF782ueq8ywkNvjmQQj6Gnd2+EANuPqIWyz45tB+/nNTHvuiamb6DHS4+0A8Tv3BlW7+HWUq/hdBovvtJoT58+2Y+DeQzv5MKOD6ztZA+bvipvQzZUL/GAH4+uf2JPUnHZj28auC+KVtxPVD7cr5LjQM+1a4tv8EXHD6zO4s9/JdKvve1tr28EYg+VssavaNQoT7ZEuW+QLCOPixNdb/Xs0a/Iui0PNqNRT914/49iA9NP0PjhL4v9xE+saqQPKhbvj4z9wi/DGqEPntMHD+HWKa/pkGEvrqrEL42huK+rSuLvx101b5Fj7W+DW+LvpUj2b48odW+vIRIvuNNCb8Jmge/xIlCvhvImj5xkcw+onwhPgdSpj2ykEu+qFbpvQ==",
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
```json
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw(memory:VAMemory) ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.xml model_proc=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! vapostproc ! video/x-raw,format=BGRA ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

**Example raw output metadata:**

```json
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

```json
{
    "id": "atag-qcam1",
    "debug_mac": "17:cf:36:77:a4:e0",
    "timestamp": "2026-02-06T11:43:56.882Z",
    "debug_timestamp_end": "2026-02-06T11:43:59.188Z",
    "debug_processing_time": 2.305920124053955,
    "rate": 10.048692255989547,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.9453125,
                "center_of_mass": {
                    "x": 355,
                    "y": 87,
                    "width": 49.333333333333336,
                    "height": 87.75
                },
                "bounding_box_px": {
                    "x": 306,
                    "y": 0,
                    "width": 149,
                    "height": 351
                },
                "person-attributes": "F: has_bag has_longsleeves has_longpants has_longhair has_coat_jacket",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "17:cf:36:77:a4:e0",
    "timestamp": "2026-02-06T11:43:56.978Z",
    "debug_timestamp_end": "2026-02-06T11:43:59.286Z",
    "debug_processing_time": 2.307368755340576,
    "rate": 10.048692255989547,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.97900390625,
                "center_of_mass": {
                    "x": 339,
                    "y": 87,
                    "width": 48.0,
                    "height": 87.5
                },
                "bounding_box_px": {
                    "x": 291,
                    "y": 0,
                    "width": 144,
                    "height": 350
                },
                "person-attributes": "M: has_bag has_longsleeves has_longpants has_coat_jacket",
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

[See JSON](./example_output/)

**Example SceneScape output metadata:**

```json
{
    "id": "atag-qcam1",
    "debug_mac": "f5:1c:fa:de:fd:45",
    "timestamp": "2026-02-06T11:52:25.263Z",
    "debug_timestamp_end": "2026-02-06T11:52:28.572Z",
    "debug_processing_time": 3.3082544803619385,
    "rate": 10.743678940586664,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.998046875,
                "center_of_mass": {
                    "x": 700,
                    "y": 81,
                    "width": 61.333333333333336,
                    "height": 80.25
                },
                "bounding_box_px": {
                    "x": 639,
                    "y": 1,
                    "width": 185,
                    "height": 321
                },
                "reid": "tuhvPmHL374wG3i9zF/JPh1Pej+FFRu/5oLLPtIbCb7XkEc/hsA2v7ikAL3pEUG/fiIzv65CyT7DihU/taOKPrhtgD3apg0/a4znvimIs72E+Sc/JsIEv/JEFb83IsS8Qcdrv61iE74YqdE9NipVPoKMYz9aJDy+Vl4dPx5B9T4JyzQ/R2npPv01hb4gg4O/tmugPTxSQL58ygK9A/FXvvy/Mj97cgA/RpNFvz38Pr7GM7s+0zwnv9qZ6b6LhzK/PzLWvr85ML5kbXe+DWdNv2aK+z5BE8O+tCrYPGdjtb6c87a9PrUdPlhkoz/2aym+Xd8vv1lKkb7A2RQ9YjofPm16kb54eES+NQhDvmke675HHY8+CA7cPpQGNb+KPS+/4i+AvoaU3brmTAM/+8eHP8M4Db/k6+w8El6rP1XCwb4S6FQ/waa1vvm80z4stFk+wCwGPbz2rD5kkkw/JRu7vjhtFz21rQy/XJCMPjJ3gz3c7rU+jswrP+9CHr8C+ck+LEvKPoLKD770LSA/qqj+PjyHCr7ksuU9nsGQPkyWLT6rt2M/1xS/vjFvsL42Z6O+ACnSOg6inL+mR4q+Xn3iPmO1uL6r5TO/Zx/3vhDbEr+mDfA+HRCGv0/6pr5wtJI/Hu2oPjEgFb5g2DS/LQXEv2Krp74GXrk97iAsPsS7ID44tYA9s4hHPvGEBD6yRMe+R9koP6jkkL9BXma+AbitvmgWZb0MtAQ/hpkXPZUtgj4gOWk9yb6OPxhRrz8WOog+/JTRPvn0ZT4cSSW/qN6Cv0xAlL79fIW/wSvhvuAO4ztWQKI+hXSwvFCa6D2HExM+MNQkvtBvNr+DETi/98w7vpqRsr1Kw+K+enJwvjQTjbw+YSA/wrR3P9SfWT/65wo/hX10Pi52zD1WTxW/lUi6vkuiST/1DCo/QpseP4JWIL4YbsC+zls9vtMqxb6CoM++ouU1PhjFuj5ODq++7CQAP3055r73gu89YhsQv6GilD5R6lS+WK+gPHZ6zL75PSi+ENAFPwmO9r2UnMw+vTXsvN7ncr/a8Rm/6LgAPlo2tD5Mlwo/wNVLPHd9yb6mRqs+w4GMPvqFCz0BoS0/XV6QvaGwmj6ptNG+q9EWP+5Trz6S/2U+j10JPmgr0D0FRzo+6XAavaVgP79eOS0/R0+kPvCaDT1o8UE/1g5dvefeET+LrUm/9OoOPgiveT6Uj+S+ccQyPzBdML8/WY8/8Jg3vrOFGj/XhAm/oR1MP/TMJT9LB4S+y1aivvjoJz7OOs69m22av95nQb7RudG+UHSqvuEsEL8isU89c2vhvgjVFb9G7gC/mKWuPgrnFT7CpoO9LNuCPkadXj5A7f69dME3Pg==",
                "id": 1
            }
        ]
    }
}
{
    "id": "atag-qcam1",
    "debug_mac": "f5:1c:fa:de:fd:45",
    "timestamp": "2026-02-06T11:52:25.365Z",
    "debug_timestamp_end": "2026-02-06T11:52:28.673Z",
    "debug_processing_time": 3.3077921867370605,
    "rate": 10.743678940586664,
    "objects": {
        "person": [
            {
                "category": "person",
                "confidence": 0.98388671875,
                "center_of_mass": {
                    "x": 696,
                    "y": 80,
                    "width": 56.666666666666664,
                    "height": 80.0
                },
                "bounding_box_px": {
                    "x": 641,
                    "y": 0,
                    "width": 170,
                    "height": 320
                },
                "reid": "zCHkPgW5fL4KUDG9FPxXPt7GVz8/IwW/XJbdPm9C3L2j7RA/wI1Zv1GD0r3lBQa+zhqcvToOGD+s98Y+jCHsPUYpQ74A8Lc+Go4mvutjgr7yzyE/b5HvvtKZRL9Uirk9rzhXv2xclL3qwYQ+1Zi1vS6f/T6J8dM95oOYPjSRGD24ZFk/IOKRPp7oS776c1m/ot4svv33Db/oG4A+0DBcPc1GbT/v+ps+B4CHv47pgr4gvio+gTwPvZBo+r5DeB2/OZkTv24OMr+jGTe+xGNsv8p4XD7SKTG/yg/GvYxgg74MWE2+nQquPf+Euj/c+IO++ZrhvthnID6pDAQ/aIKmvZJzK76pZKK+hvzSvq2vw72ppwE/7JX2PuoB6b50BYu+zKB8vs1OUL7L8hU/IsxoPzIHBL/ii8U982VxP7O00r4zHCU/yrq4vpWyyD4D3ka+EKLtPvBmdz6U6CA/dBPyvpmO0b6o21q/mrSdPu9H4r2G2ic+945cPp0Smr6O6c8+5qQvPgC7GTvkgWU+DdDEPrZ/lb6CJ30+J81CvauKRb67sz4/2H0jv+ZgxL5eLiC9QnS1PuibJb/mw/e+Qo9vP+vZRb7cpmq/BWjkvq91Fb9ogXU++bshvxDqAT1f3Tw/m8fyvcGlJr/ppSq/FbOGv5GR7b4exru9mpS+vWTa0D5+oXI+AFBAOsmVc74lZ+S+kiMgP7zDl7/Y6aS+C5SbvvarpD5KbrY+WPmgPu2jJT4Fi+e9zATtPsTWpj8YhQs/prUsPnmy2b33CW+/1CYEv149s77ddB+/xL8DvmqrLj7dAfc+KjwZvchD1z4sYfA95d31uwA/Tb+5ZUW/9o2/vt9Xhr5WiBC/o06TvadY8r22TFo/IQBoP4J5BT+ikT8/oOASPqTvTr1o9Ra/XxjBvHPTxT7GLDM/bhXrPihCn7531Z++f6OQvuSKsL6+kAo+ELfSPfHdCj+gqJ6+mWrmPsK6A7942iY/UJcjv4yb0z5Pw2G+yw4/voQutL6usBG+APx8O6AdaD1Ldzw/ryFSvjYUHr/QXGu/sFlfPowPPj78s3E+lGisvIXZB78u/7Y+PxsKP8bURz28FfA+LF+LvnCF0j3Kz4G+EgF2Pmjrkj17DhS9IXp+vsIykT4PS9k+AKt2PNMEKL/sKR0/oNWSvhLYdb2mp40/DlnhvtrDYz2lr+2+glgEP+z9ir0Bxbu+MPBpP2h5cb422U4/6DDfPJGCFD+lt0W+zK6JP063FD90s32+NlyKvuxVmr4Qet48Eo3Lv8CLfTzxfpG+9rjKvjOSjb648028cemmvoBkFr/KkRy/gpqYvrP1ET6kUuC8JHiQvpeuAj8DQQG/iK05PQ==",
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

[See JSON](./example_output/person_metadata_cpu_raw.json)

**Example SceneScape output metadata:**

```json
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

<details>
<summary>GPU</summary>

**Pipeline:**
```bash
multifilesrc loop=TRUE location=/home/pipeline-server/videos/qcam1.ts name=source ! decodebin3 ! video/x-raw(memory:VAMemory) ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model_proc=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=0 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.xml model_proc=/home/pipeline-server/models/intel/age-gender-recognition-retail-0013/FP32/age-gender-recognition-retail-0013.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvaclassify scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.xml model_proc=/home/pipeline-server/models/intel/person-attributes-recognition-crossroad-0238/FP32/person-attributes-recognition-crossroad-0238.json device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvainference scheduling-policy=latency batch-size=1 inference-interval=1 model=/home/pipeline-server/models/intel/person-reidentification-retail-0277/FP32/person-reidentification-retail-0277.xml device=GPU pre-process-backend=va-surface-sharing inference-region=1 ! queue ! gvametaconvert add-tensor-data=true name=metaconvert ! vapostproc ! video/x-raw,format=BGRA ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! appsink sync=true
```

**Example raw output metadata:**

[See JSON](./example_output/person_metadata_gpu_raw.json)

**Example SceneScape output metadata:**

```json
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

---

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

```json
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

```json
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

```json
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

```json
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

### GPU Optimization

For GPU pipelines, ensure VA-API surface sharing is enabled:
```bash
pre-process-backend=va-surface-sharing
```

This eliminates memory copies between CPU and GPU, significantly improving performance.

---

## Performance Considerations

### CPU vs GPU

- **CPU**: Lower latency, suitable for single-stream or low-resolution scenarios
- **GPU**: Higher throughput, ideal for multiple streams or high-resolution video

### Memory Usage

ReID embeddings are 256-dimensional float32 vectors (1KB per object). Monitor memory when tracking many objects over time.

### Inference Interval

For scenarios where real-time tracking isn't critical, increase `inference-interval` to reduce computational load:
- `inference-interval=1`: Every frame (highest accuracy, highest cost)
- `inference-interval=5`: Every 5th frame (balanced)
- `inference-interval=10`: Every 10th frame (lowest cost)

---

## Metadata Format

### Raw Metadata

Raw metadata includes:
- Detection bounding boxes and confidence scores
- Classification results with labels and confidence
- Tensor data for all inference outputs
- ReID embeddings as base64-encoded vectors

### SceneScape Metadata

Processed metadata includes:
- Object tracking IDs
- Simplified classification results
- Performance metrics (processing time, frame rate)
- Optional model confidence scores (e.g., `age_model_confidence`, `gender_model_confidence`)

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

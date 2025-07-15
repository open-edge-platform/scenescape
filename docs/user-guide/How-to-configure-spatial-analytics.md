# How to Configure Spatial Analytics in Intel® SceneScape

This guide provides step-by-step instructions to set up and use Regions of Interest (ROIs) and Tripwires in Intel® SceneScape. By completing this guide, you will:

- Understand the differences between Regions of Interest and Tripwires
- Learn how to configure ROIs and Tripwires through the UI
- Verify that events are properly triggered when objects interact with your defined analytics

---

## Prerequisites

Follow the steps in [Getting-Started-Guide.md](./Getting-Started-Guide.md) to bring up an instance of SceneScape with out-of-box demo scenes.

## Steps to Configure Regions of Interest

### 1. Understand Analytic Types

**Regions of Interest (ROIs)** are defined areas within a scene where you want to monitor object presence, count, and dwell time.
**Tripwires** are virtual lines that trigger events when objects cross them in either direction.

---

### 2. Configure and Use a Region of Interest

#### Create a Region of Interest

1. Log in to Intel® SceneScape.
2. Click on a scene.
3. Click on the `Regions` tab below the scene map view.
4. Click `New Region` button to create a region.
5. Draw the region on the scene by clicking points on the scene map to form a polygon. Be sure to click on the starting point to close the polygon.
6. **Optional**: Add a user-defined name for the ROI in the text box.
7. Click `Save Regions and Tripwires` to save the newly created region.

#### Modify a Region of Interest

1. Click on `Regions` at the bottom of the page.
2. Find your region in the Scene and double click on the polygon to edit its shape. Drag the vertices to refine their positions.
3. Click `Save Regions and Tripwires` to persist your changes.

#### Verify the Results

1. Use a tool like [MQTT Explorer](https://mqtt-explorer.com/) to monitor the topic right under the region name text box. For example: /scenescape/event/region/${scene_uuid}/${region_uuid}/count
2. When the center of the object enters or exits the Region of Interest, observe that a message is received on the region event topic. Here is an example:

```
{
    "timestamp": "2025-07-11T06:27:53.880Z",
    "scene_id": "302cf49a-97ec-402d-a324-c5077b280b7b",
    "scene_name": "Queuing",
    "region_id": "79c9e88c-6b26-482a-9a58-2f0c1b79bb05",
    "region_name": "roi_79c9e88c-6b26-482a-9a58-2f0c1b79bb05",
    "counts": {
        "person": 1
    },
    "objects": [
        {
            "category": "person",
            "confidence": 0.9964306950569153,
            "center_of_mass": {
                "x": 873.1902567545573,
                "y": 98.25730884776397,
                "width": 53.51023356119788,
                "height": 91.01821394527661
            },
            "id": "67c4eee3-7e5e-4bd7-ac5c-559cb41f2338",
            "type": "person",
            "translation": [
                3.0463823772090572,
                3.6136200341276368,
                -2.416780078615621e-17
            ],
            "size": [
                0.5,
                0.5,
                1.85
            ],
            "velocity": [
                -0.7110168771449774,
                0.18551042958887443,
                0.0
            ],
            "rotation": [
                0,
                0,
                0,
                1
            ],
            "visibility": [ //Which cameras is this object visible from
                "atag-qcam1",
                "atag-qcam2"
            ],
            "regions": { //List of all the regions that the object is in
                "79c9e88c-6b26-482a-9a58-2f0c1b79bb05": {
                    "entered": "2025-07-11T06:27:53.880Z"
                }
            },
            "similarity": null,
            "first_seen": "2025-07-11T06:27:49.379Z" // when was the object first seen in the Scene
        }
    ],
    "entered": [ //List of all objects that entered the region
        {
            "category": "person",
            "confidence": 0.9964306950569153,
            "center_of_mass": {
                "x": 873.1902567545573,
                "y": 98.25730884776397,
                "width": 53.51023356119788,
                "height": 91.01821394527661
            },
            "id": "67c4eee3-7e5e-4bd7-ac5c-559cb41f2338",
            "type": "person",
            "translation": [
                3.0463823772090572,
                3.6136200341276368,
                -2.416780078615621e-17
            ],
            "size": [
                0.5,
                0.5,
                1.85
            ],
            "velocity": [
                -0.7110168771449774,
                0.18551042958887443,
                0.0
            ],
            "rotation": [
                0,
                0,
                0,
                1
            ],
            "visibility": [
                "atag-qcam1",
                "atag-qcam2"
            ],
            "regions": {
                "79c9e88c-6b26-482a-9a58-2f0c1b79bb05": {
                    "entered": "2025-07-11T06:27:53.880Z"
                }
            },
            "similarity": null,
            "first_seen": "2025-07-11T06:27:49.379Z"
        }
    ],
    "exited": [ //List of all objects that just exited this region
        {
            "object": {
                "category": "person",
                "confidence": 0.9963177442550659,
                "center_of_mass": {
                    "x": 486.91266377766925,
                    "y": 167.66232883228977,
                    "width": 38.757527669270814,
                    "height": 103.58497395234949
                },
                "id": "adf2932f-979e-4bd7-91b2-7909f355fbcb",
                "type": "person",
                "translation": [
                    1.2290083442950077,
                    5.053712379915115,
                    -2.7154344421259052e-19
                ],
                "size": [
                    0.5,
                    0.5,
                    1.85
                ],
                "velocity": [
                    -0.1824836416851012,
                    0.0915883684787472,
                    0.0
                ],
                "rotation": [
                    0,
                    0,
                    0,
                    1
                ],
                "visibility": [
                    "atag-qcam1",
                    "atag-qcam2"
                ],
                "regions": {},
                "similarity": null,
                "first_seen": "2025-07-11T06:29:02.378Z"
            },
            "dwell": 2.799999952316284 //What is the amount of time spent by the object in the ROI (in seconds)
        }
    ],
    "metadata": {
        "points": [
            [
                0.6242038216560509,
                4.617834394904459
            ],
            [
                1.7452229299363058,
                3.050955414012739
            ],
            [
                3.859872611464968,
                3.9426751592356686
            ],
            [
                2.2229299363057327,
                5.777070063694268
            ]
        ],
        "title": "roi_79c9e88c-6b26-482a-9a58-2f0c1b79bb05",
        "uuid": "79c9e88c-6b26-482a-9a58-2f0c1b79bb05",
        "area": "poly",
        "fromSensor": false
    }
}
```

![Configure and Verify Region of Interest](images/create-roi.gif)
Figure 1: Region of Interest creation flow

---

#### Enable Volumetric Intersection for Region of Interest

By default, Regions of Interest trigger events when the center point of each object enters or leaves the bounds of the polygon. However, for detecting an event like a collision, computing a volumetric intersection is necessary.

1. Follow the instructions in [How-to-define-object-properties.md](./How-to-define-object-properties.md) to create an entry for the object category of interest.
1. Click on the `Regions` tab tab below the scene map view.
1. Find the specific region in the list and click on "volumetric" checkbox to enable intersection detection.
1. **Optional**: you can add a uniform buffer around the region and vary the height of the region.
1. Click `Save Regions and Tripwires` to persist your changes.

#### Verify the Results

1. Use a tool like [MQTT Explorer](https://mqtt-explorer.com/) to monitor the topic right under the region name text box. For example: /scenescape/event/region/${scene_uuid}/${region_uuid}/count
2. Navigate to the 3D UI view of the Scene.
3. When an object first intersects or last intersects with the region of interest, observe a message is received on the event topic for that region. Here is an example:

```
{
    "timestamp": "2025-07-11T06:27:53.880Z",
    "scene_id": "302cf49a-97ec-402d-a324-c5077b280b7b",
    "scene_name": "Queuing",
    "region_id": "79c9e88c-6b26-482a-9a58-2f0c1b79bb05",
    "region_name": "roi_79c9e88c-6b26-482a-9a58-2f0c1b79bb05",
    "counts": {
        "person": 1
    },
    "objects": [
        {
            "category": "person",
            "confidence": 0.9964306950569153,
            "center_of_mass": {
                "x": 873.1902567545573,
                "y": 98.25730884776397,
                "width": 53.51023356119788,
                "height": 91.01821394527661
            },
            "id": "67c4eee3-7e5e-4bd7-ac5c-559cb41f2338",
            "type": "person",
            "translation": [
                3.0463823772090572,
                3.6136200341276368,
                -2.416780078615621e-17
            ],
            "size": [
                0.5,
                0.5,
                1.85
            ],
            "velocity": [
                -0.7110168771449774,
                0.18551042958887443,
                0.0
            ],
            "rotation": [
                0,
                0,
                0,
                1
            ],
            "visibility": [ //Which cameras is this object visible from
                "atag-qcam1",
                "atag-qcam2"
            ],
            "regions": { //List of all the regions that the object is in
                "79c9e88c-6b26-482a-9a58-2f0c1b79bb05": {
                    "entered": "2025-07-11T06:27:53.880Z"
                }
            },
            "similarity": null,
            "first_seen": "2025-07-11T06:27:49.379Z" // when was the object first seen in the Scene
        }
    ],
    "entered": [ //List of all objects that entered the region
        {
            "category": "person",
            "confidence": 0.9964306950569153,
            "center_of_mass": {
                "x": 873.1902567545573,
                "y": 98.25730884776397,
                "width": 53.51023356119788,
                "height": 91.01821394527661
            },
            "id": "67c4eee3-7e5e-4bd7-ac5c-559cb41f2338",
            "type": "person",
            "translation": [
                3.0463823772090572,
                3.6136200341276368,
                -2.416780078615621e-17
            ],
            "size": [
                0.5,
                0.5,
                1.85
            ],
            "velocity": [
                -0.7110168771449774,
                0.18551042958887443,
                0.0
            ],
            "rotation": [
                0,
                0,
                0,
                1
            ],
            "visibility": [
                "atag-qcam1",
                "atag-qcam2"
            ],
            "regions": {
                "79c9e88c-6b26-482a-9a58-2f0c1b79bb05": {
                    "entered": "2025-07-11T06:27:53.880Z"
                }
            },
            "similarity": null,
            "first_seen": "2025-07-11T06:27:49.379Z"
        }
    ],
    "exited": [ //List of all objects that just exited this region
        {
            "object": {
                "category": "person",
                "confidence": 0.9963177442550659,
                "center_of_mass": {
                    "x": 486.91266377766925,
                    "y": 167.66232883228977,
                    "width": 38.757527669270814,
                    "height": 103.58497395234949
                },
                "id": "adf2932f-979e-4bd7-91b2-7909f355fbcb",
                "type": "person",
                "translation": [
                    1.2290083442950077,
                    5.053712379915115,
                    -2.7154344421259052e-19
                ],
                "size": [
                    0.5,
                    0.5,
                    1.85
                ],
                "velocity": [
                    -0.1824836416851012,
                    0.0915883684787472,
                    0.0
                ],
                "rotation": [
                    0,
                    0,
                    0,
                    1
                ],
                "visibility": [
                    "atag-qcam1",
                    "atag-qcam2"
                ],
                "regions": {},
                "similarity": null,
                "first_seen": "2025-07-11T06:29:02.378Z"
            },
            "dwell": 2.799999952316284 //What is the amount of time spent by the object in the ROI (in seconds)
        }
    ],
    "metadata": {
        "points": [
            [
                0.6242038216560509,
                4.617834394904459
            ],
            [
                1.7452229299363058,
                3.050955414012739
            ],
            [
                3.859872611464968,
                3.9426751592356686
            ],
            [
                2.2229299363057327,
                5.777070063694268
            ]
        ],
        "title": "roi_79c9e88c-6b26-482a-9a58-2f0c1b79bb05",
        "uuid": "79c9e88c-6b26-482a-9a58-2f0c1b79bb05",
        "area": "poly",
        "fromSensor": false
    }
}
```

### 3. Configure and Use a Tripwire

#### Create a Tripwire

1. Log in to Intel® SceneScape.
2. Click on a scene.
3. Click on the `Tripwires` tab below the scene map view.
4. Click `New Tripwire` to create a tripwire.
5. Click on the Scene and a green line with two moveable endpoints will appear.
6. Click and drag each endpoint to get the right orientation and position for the tripwire (the flag line indicates the direction of positive flow)..
7. **Optional**: Add a user-defined name for the tripwire in the textbox
8. Click `Save Regions and Tripwires` to create the tripwire.

#### Modify a Tripwire

1. Click on the `Tripwires` tab below the scene map view.
2. Double click on the tripwire to edit on the scene.
3. Click and drag to change position and orientation.
4. Click `Save Regions and Tripwires` to persist your changes.

#### Verify the Results

1. Use a tool like [MQTT Explorer](https://mqtt-explorer.com/) to monitor the topic right under the tripwire name text box. For example: /scenescape/event/tripwire/${scene_uuid}/${tripwire_uuid}/objects
2. When an object walks through a tripwire, observe a message is received on that topic and it contains the following data:

```
{
    "timestamp": "2025-07-11T06:46:21.205Z",
    "scene_id": "97781c36-b53a-4749-87e6-8815da99bac7",
    "scene_name": "Intersection-Demo",
    "tripwire_id": "92652a52-a6d5-4920-b292-0e868208a0c8",
    "tripwire_name": "northwest-tripwire",
    "counts": {
        "vehicle": 1
    },
    "objects": [
        {
            "category": "vehicle",
            "confidence": 0.9130859375,
            "center_of_mass": {
                "x": 1150,
                "y": 291,
                "width": 65.0,
                "height": 37.0
            },
            "id": "5559c880-2b13-4d43-b856-8be8d8eac43a",
            "type": "vehicle",
            "translation": [
                87.89656932138013,
                73.997183861969,
                -1.4970315844207517e-16
            ],
            "size": [
                2.5,
                1.5,
                1.5
            ],
            "velocity": [
                -5.0083541472629864,
                -5.053219441313509,
                0.0
            ],
            "rotation": [
                0.0,
                -0.0,
                -0.9230240359425683,
                0.3847422891654783
            ],
            "visibility": [
                "camera2"
            ],
            "regions": {
                "e9f0981d-8535-4782-8e85-a04cb2605db5": {
                    "entered": "2025-07-11T06:46:19.004Z"
                }
            },
            "similarity": null,
            "first_seen": "2025-07-11T06:46:18.783Z",
            "camera_bounds": {},
            "direction": 1 //in which direction was the tripwire triggered
        }
    ],
    "entered": [],
    "exited": [],
    "metadata": {
        "title": "northwest-tripwire",
        "points": [
            [
                86.55407287208759,
                105.45893940982072
            ],
            [
                87.94171331893469,
                73.54320913233751
            ]
        ],
        "uuid": "92652a52-a6d5-4920-b292-0e868208a0c8"
    }
}
```

![Configure and Verify Tripwire](images/create-tripwire.gif)
Figure 2: Tripwire creation flow

---

## Supporting Resources

- [How to visualize regions](How-to-visualize-regions.md)
- [Intel® SceneScape README](https://github.com/open-edge-platform/scenescape/blob/main/README.md)

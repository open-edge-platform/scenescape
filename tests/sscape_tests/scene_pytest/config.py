# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

frame = {"timestamp": "2021-10-13T20:32:34.655Z", "id": "camera1", "objects": {"person": [{"id": 1, "category": "person", "confidence": 0.9959450364112854, "bounding_box": {"x": 394, "y": 89, "width": 70, "height": 262}}, {"id": 2, "category": "person", "confidence": 0.6066580414772034, "bounding_box": {"x": 407, "y": 68, "width": 59, "height": 176}, "center_of_mass": {"x": 426, "y": 112, "width": 19.666666666666668, "height": 44.0}}]}, "rate": 1.1, "scene_id": 1, "scene_name": "Demo"}
overlap = 85.08281972265023
person_obj = {"id": 1, "category": "person", "confidence": 0.9997454285621643, "bounding_box": {"x": 336, "y": 148, "width": 128, "height": 296}}
when = 1654078116.573
expected_mobj = "Person: None/1 (628.799, 638.212, 0.000) None vectors: [Vector: (266.513, 542.244, 260.386) (628.799, 638.212, 0.000) 1654078116.573]"
jdata = {"timestamp": "2023-05-16T21:22:58.388Z", "timestamp_end": "2023-05-16T21:22:58.798Z", "processing_time": 0.41015076637268066, "mac": "02:42:ac:16:00:05", "id": "camera1", "objects": {"person": [{"id": 1, "category": "person", "confidence": 0.999774158000946, "bounding_box": {"x": 0.1995591483897673, "y": -0.3168439110398937, "width": 0.287085090665981, "height": 0.5076504652020396}, "center_of_mass": {"x": 488, "y": 131, "width": 54.666666666666664, "height": 72.5}, "bounding_box_px": {"x": 434, "y": 59, "width": 164.0, "height": 290.0}}]}, "rate": 6.4}
thing_type = "person"

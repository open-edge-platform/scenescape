# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from gstgva import VideoFrame
import json
import io
import sys
import os
import numpy as np
import openvino as ov
from scipy.spatial.transform import Rotation

from deepscenario_utils import preprocess, postprocess, decrypt

MODEL_PATH="/home/pipeline-server/user_scripts/model.enc"
DEFAULT_INTRINSICS_PATH = "/home/pipeline-server/user_scripts/intrinsics.json"
CATEGORIES_PATH="/home/pipeline-server/user_scripts/categories.json"
PASWORD_PATH="/home/pipeline-server/user_scripts/password.txt"

SCORE_THRESHOLD = 0.7
NMS_THRESHOLD = 0.65


def project_to_image(pts_3d: np.ndarray, intrinsics: np.ndarray) -> np.ndarray:
    # Convert pts_3d to homogeneous coordinates
    pts_3d_homogeneous = np.hstack((pts_3d, np.ones((pts_3d.shape[0], 1))))

    # Perform matrix multiplication with intrinsic matrix
    pts_img_homogeneous = intrinsics @ pts_3d_homogeneous.T

    # Normalize to get 2D image coordinates
    pts_img = pts_img_homogeneous[:2] / pts_img_homogeneous[2]
    return pts_img.T

def compute_2d_bbox_closest_surface(corners_3d: np.ndarray, intrinsics: np.ndarray) -> tuple:
    # Project 3D corners to 2D image plane
    corners_2d = project_to_image(corners_3d, intrinsics)

    # Define faces using corner indices
    faces = [
        [0, 1, 2, 3],  # Front face
        [4, 5, 6, 7],  # Back face
        [0, 1, 5, 4],  # Bottom face
        [2, 3, 7, 6],  # Top face
        [0, 3, 7, 4],  # Left face
        [1, 2, 6, 5]   # Right face
    ]

    # Calculate average z-coordinate for each face
    face_distances = [np.mean(corners_3d[face, 2]) for face in faces]

    # Find the closest face
    closest_face_index = np.argmin(face_distances)
    closest_face = faces[closest_face_index]

    # Calculate 2D bounding box for the closest face
    surface_corners_2d = corners_2d[closest_face]
    x_min, y_min = np.min(surface_corners_2d, axis=0)
    x_max, y_max = np.max(surface_corners_2d, axis=0)
    width = x_max - x_min
    height = y_max - y_min

    return x_min, y_min, width, height

def get_box_corners(annotation: dict) -> np.ndarray:
    # Extract dimensions and calculate local corners
    l, w, h = annotation['dimension']
    corners_x = [l / 2, l / 2, -l / 2, -l / 2, l / 2, l / 2, -l / 2, -l / 2]
    corners_y = [w / 2, -w / 2, -w / 2, w / 2, w / 2, -w / 2, -w / 2, w / 2]
    corners_z = [0, 0, 0, 0, h, h, h, h]

    # Rotate and translate corners to global coordinates
    transform = np.eye(4)
    transform[:3, :3] = Rotation.from_quat(annotation['rotation']).as_matrix()
    transform[:3, 3] = annotation['translation']

    # Calculate corners in homogeneous coordinates
    corners_homogeneous = np.dot(transform, np.vstack((corners_x, corners_y, corners_z, np.ones(8))))
    corners_3d = corners_homogeneous[:3].T  # Extract x, y, z coordinates
    return corners_3d

def load_json(json_path: str) -> dict:
    with open(json_path) as file:
        return json.load(file)

def load_model(path_to_model: str, password: str, device: str = 'GPU'):
    assert device in ['CPU', 'GPU']
    core = ov.Core()
    model_bytes = decrypt(password, path_to_model)
    model_raw = core.read_model(model=io.BytesIO(model_bytes))
    return core.compile_model(model=model_raw, device_name=device)

def read_passwd(file_path):
    try:
        with open(file_path, 'r') as file:
            line = file.readline()
            return line if line else None
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        return None
    except IOError:
        print(f"Error: Could not read the file '{file_path}'.")
        return None

def infer_from_img(img, model, intrinsics, categories):

    class_ids = [category['id'] for category in categories]
    input_height = model.input().shape[3]
    input_width = model.input().shape[4]
    input_size = (input_height, input_width)

    network_input, intrinsics_scaled = preprocess(img, intrinsics, input_size)
    network_output = model(network_input)
    anns = postprocess(
        network_output,
        intrinsics_scaled,
        input_size,
        class_ids,
        score_threshold=SCORE_THRESHOLD, # 0.3,
        nms_threshold=NMS_THRESHOLD #0.65,
    )

    return anns

class DeepScenario:
    def __init__(self, *args, **kwargs):
        if args and args[0]:
            intrinsics_path = args[0]
        else:
            intrinsics_path = DEFAULT_INTRINSICS_PATH
        self.intrinsics = load_json(intrinsics_path)['intrinsic_matrix']
        self.intrinsics = np.dot(np.array(self.intrinsics), np.eye(4)[:3, :])
        self.categories = load_json(CATEGORIES_PATH)
        self.category_dict = {category["id"]: category["name"] for category in self.categories}
        self.password = read_passwd(PASWORD_PATH)
        self.model = load_model(MODEL_PATH, self.password, "CPU")

    def process_frame(self, frame: VideoFrame) -> bool:
        with frame.data() as frame_data:
            annotations = infer_from_img(frame_data, self.model, self.intrinsics, self.categories)
            for annotation in annotations:
                if (annotation["category_id"] not in (2,3)) and (annotation["score"] > SCORE_THRESHOLD):
                    corners_3d = get_box_corners(annotation)
                    x, y, w, h = compute_2d_bbox_closest_surface(corners_3d, self.intrinsics)
                    label = self.category_dict.get(annotation["category_id"], "")
                    roi = frame.add_region(x, y, w, h, label, annotation["score"], False, annotation)
        return True

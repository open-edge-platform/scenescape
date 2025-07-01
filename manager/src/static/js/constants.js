// SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

export const APP_NAME = "scenescape";
export const REST_URL = "/api/v1";
export const SUCCESS = 200;

// Scene settings
export const SCENE_MAX_TEXTURE_SIZE = 4096;
export const SCENE_MESH_NAMES = ["mesh_0", "3d_scene", "floor"];

// Camera settings
export const CAMERA_FOV = 40;
export const CAMERA_ASPECT = 16 / 9;
export const CAMERA_NEAR = 0.1;
export const CAMERA_FAR = 2000;
export const CAMERA_SCALE_FACTOR = 1;
export const INITIAL_PROJECTION_OPACITY = 90;
export const [FX, FY, CX, CY] = [0, 4, 2, 5];
export const [K1, K2, P1, P2, K3] = [0, 1, 2, 3, 4];
export const MAX_COPLANAR_DETERMINANT = 0.1;
export const MAX_INTRINSICS_UPDATE_WAIT_TIME = 5000;

// Draw settings
export const CALIBRATION_BACKGROUND_COLOR = "#808080"; // Gray
export const CALIBRATION_POINT_COLORS = [
  "#ff0000", // Red
  "#00ff00", // Green
  "#0000ff", // Blue
  "#ffff00", // Yellow
  "#ff00ff", // Magenta (Fuchsia)
  "#00ffff", // Cyan (Aqua)
  "#ffa500", // Orange
  "#800080"  // Purple
];
export const CALIBRATION_POINT_SCALE = 0.015;
export const CALIBRATION_SCALE_FACTOR = 200;
export const CALIBRATION_TEXT_SIZE = 0.1;
export const MAX_CALIBRATION_POINTS = 50;
export const SPHERE_NUM_SEGMENTS = 15;
export const SPHERE_RADIUS = 0.05;
export const TEXT_FONT = "/static/examples/fonts/helvetiker_regular.typeface.json";
export const TEXT_SIZE = 0.2;

// Mqtt topics
export const CMD_CAMERA = "/cmd/camera/";
export const CMD_AUTOCALIB_SCENE = "/cmd/autocalibration/scene/";
export const CMD_DATABASE = "/cmd/database";
export const DATA_AUTOCALIB_CAM_POSE = "/autocalibration/camera/pose/";
export const DATA_REGULATED = "/regulated/scene/";
export const DATA_CAMERA = "/data/camera/";
export const IMAGE_CAMERA = "/image/camera/";
export const IMAGE_CALIBRATE = "/image/calibration/camera/";
export const SYS_AUTOCALIB_STATUS = "/sys/autocalibration/status";
export const SYS_CHILDSCENE_STATUS = "/sys/child/status";
export const SYS_PERCEBRO_STATUS = "/sys/percebro/status/";
export const EVENT = "/event"

// Model directory
export const MODEL_DIRECTORY_API = `${REST_URL}/model-directory/`;
export const DIRECTORY_LEFT_INDENT = 32;

// Error message constants

import numpy as np
from scipy.spatial.transform import Rotation as R
from .read_write_model import qvec2rotmat
from typing import Dict, Sequence


def to_sp_rotation(qwxyz):
    return R.from_quat((*qwxyz[1:], qwxyz[0]))


def pose_distance(pose1, pose2):
    if isinstance(pose1, tuple):  # (R,t) or (qwxyz, tvec)
        R1, t1 = pose1[0], pose1[1]
        R2, t2 = pose2[0], pose2[1]
        if R1.size == 4:  # quaternion qwxyz
            R1 = to_sp_rotation(R1)
            R2 = to_sp_rotation(R2)
        distance = np.linalg.norm(-R1.inv().apply(t1) + R2.inv().apply(t2))
        angle = (R1.inv() * R2).magnitude()
        return distance, angle
    if isinstance(pose1, np.ndarray):  # 4x4 homogenous matrix
        return pose_distance(
            (pose1[:3, :3], pose1[:3, 3:]), (pose2[:3, :3], pose2[:3, 3:])
        )
    return pose_distance((pose1.qvec, pose1.tvec), (pose2.qvec, pose2.tvec))


def find_nearest_pose(query_poses: Dict, dataset_poses: Dict):
    """Get nearest pose from a dataset to a query pose.

    Args:
        query_poses (dict): List of query poses. Pose is the camera extrinsic tuple
        (q_xyzw, tvec).
        dataset_poses (dict): List of dataset poses.

    Returns:
        (dict[str, str], dict[str, (float, float)]): dataset_poses that are
        closest to the query_poses and min distances.
    """
    min_dset = {}
    min_d_a = {}
    for qpath, qpose in query_poses.items():
        min_d_a[qpath] = (np.inf, np.inf)
        for dpath, dpose in dataset_poses.items():
            # prevent sorting order errors due to rounding errors
            d_a = tuple(round(x, 6) for x in pose_distance(qpose, dpose))
            if d_a < min_d_a[qpath]:
                min_dset[qpath] = dpath
                min_d_a[qpath] = d_a
    return min_dset, min_d_a


def evaluate(
    poses_predicted: Dict[str, Dict],
    poses_gt: Dict[str, Dict],
    thresholds_tRdeg: Sequence = ((0.01, 1.0), (0.02, 2.0), (0.05, 5.0), (0.1, 10.0)),
    error_basis=None,
    only_localized: bool = False,
    logs=None,
):
    """Compute median translation and rotation errors, as well as ratio of
    images localizaed to within the given thresholds.

    Args:
        poses_predicted (Dict[str, Dict]): Dictionary of estimated camera
            extrinsic parameters in terms of pairs of quaternion rotation and
            translation for query images.
        poses_gt (Dict[str, Dict]): Dictionary with ground truth poses, similar
            to poses_predicted.
        thresholds_tRdeg [Sequence]: Sequence of pairs of (distance,
            angle_degrees) thresholds.
        only_localized (bool): Ignore localization failures.
        logs [Dict]: If provided, computed errors are aded to the logs.

    Returns:
        median translation error, median rotation (degrees) error, sequence of
            ratios of images with error less than thresholds.
    """
    if error_basis is not None:
        assert len(error_basis) == len(poses_predicted)
    errors = np.empty((len(poses_gt), 3))
    for idx, name in enumerate(poses_gt):
        if name not in poses_predicted:
            if only_localized:
                continue
            e_t = np.inf
            e_R = 180.0
        else:
            R_gt, t_gt = qvec2rotmat(poses_gt[name][0]), poses_gt[name][1]
            R, t = qvec2rotmat(poses_predicted[name][0]), poses_gt[name][1]
            e_t = np.linalg.norm(-R_gt.T @ t_gt + R.T @ t, axis=0)
            cos = np.clip((np.trace(np.dot(R_gt.T, R)) - 1) / 2, -1.0, 1.0)
            e_R = np.rad2deg(np.abs(np.arccos(cos)))

        errors[idx] = (
            e_t,
            1.0 if error_basis is None else e_t / error_basis[name][0],
            e_R,
        )
        if logs is not None:
            logs["loc"][name]["e_t"] = e_t
            logs["loc"][name]["e_t_rel"] = errors[idx, 1]
            logs["loc"][name]["e_R"] = e_R

    med_t = np.median(errors[:, 0])
    med_R = np.median(errors[:, 2])

    ratio_localized = np.fromiter(
        (
            np.mean((errors[:, 0] < th_t) & (errors[:, 2] < th_R))
            for th_t, th_R in thresholds_tRdeg
        ),
        dtype=float,
    )

    return med_t, med_R, ratio_localized

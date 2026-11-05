# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Vendored from scenescape-v2-architecture/algorithms/amodalreasoner.
# See NOTICE in this package for provenance requirements.

"""Per Camera Amodal Reasoning"""
import open3d as o3d
import numpy as np
from scipy.stats import truncnorm
from .constants import PLANE_DECISION_NML_WEIGHT
from .intersection_map import DepthMap

class AmodalReasoner:
  """Class for bayesian projection and intersection into a triangualar mesh for a single-camera (i.e one instantiation per-camera)"""
  debug = False   # class-level default so instances built without __init__ (e.g. tests) are safe
  # TODO: Potential redesign to factory pattern, where we are producing gaus_objects of somesort.
  # Lots of reuse of gaus_rays but not appropiate to solidify as a object attribute.
  def __init__(self, mesh: o3d.geometry.TriangleMesh, rwc_z_up: np.ndarray, camera_intrinsics: np.ndarray, camera_extrinsics: np.ndarray, width: int, height: int, num_layers: int = 4):
    self.rwc_z_up = rwc_z_up
    self.mesh = mesh
    # Layered so query() can peel: first layer is the front hit, deeper layers the floor.
    self.depth_map = DepthMap(camera_intrinsics, camera_extrinsics, mesh, width, height, num_layers=num_layers)
    self.depth_map.populate()
    self.debug = False   # when True, generate() records intermediate rays/points into self.trace
    self.trace: dict = {}

  def _get_centroid_points(self, gaus_rays: dict[str, np.ndarray]): 
    # Result in (N,3) matrix
    p_cs = gaus_rays['ray'] * gaus_rays['depth_est'][:, None] + gaus_rays['mu']
    return p_cs

  def _build_orthonorm_frame(self, gaus_rays: dict[str, np.ndarray]):
    #  Should return (N, 3, 3)
    e1 = gaus_rays['ray'] / np.linalg.norm(gaus_rays['ray'], axis=1, keepdims=True)
    z = self.rwc_z_up / np.linalg.norm(self.rwc_z_up)
    # e_h = r x z_up; fall back to r x X where r is (near) parallel to z_up (degenerate cross).
    cross = np.cross(e1, z)
    norm_c = np.linalg.norm(cross, axis=1, keepdims=True)
    cross = np.where(norm_c < 1e-6, np.cross(e1, np.array([1.0, 0.0, 0.0])), cross)
    e2 = cross / np.linalg.norm(cross, axis=1, keepdims=True)
    # e_v = r x e_h, unit since e1 and e2 are orthonormal.
    e3 = np.cross(e1, e2)
    # Columns are [r, e_h, e_v] -> (N, 3, 3)
    frame = np.stack((e1, e2, e3), axis=2)
    return frame

  def _deconstruct_cov(self, frame: np.ndarray, gaus_rays: dict[str, np.ndarray]):
    """
    Frame should be (N, 3, 3)
    Returns [ray (depth) variance, horizontal variance, vertical variance]
    """
    # (N, 3, 3) @ (N, 3, 3) @ (N, 3, 3)
    lam = frame.mT @ gaus_rays['Sigma'] @ frame
    return lam

  def  _create_probe_points(self, dir_variance: np.ndarray, frame: np.ndarray, centroid_points: np.ndarray, devs: float = 2.0):
    sig_h = np.sqrt(dir_variance[:, 1, 1])[:, None]
    sig_v = np.sqrt(dir_variance[:, 2, 2])[:, None]
    # e3 = e1 x e2 has an arbitrary sign; orient it toward world-up so v_no drops to the floor.
    z = self.rwc_z_up / np.linalg.norm(self.rwc_z_up)
    e_v = frame[:, :, 2] * np.where(frame[:, :, 2] @ z < 0, -1.0, 1.0)[:, None]
    p_h_po = centroid_points + (devs * sig_h) * frame[:, :, 1]
    p_h_no = centroid_points - (devs * sig_h) * frame[:, :, 1]
    p_v_po = centroid_points + (devs * sig_v) * e_v
    p_v_no = centroid_points - (devs * sig_v) * e_v
    # Block layout (5N, 3): [h_po, h_no, v_po(top), v_no(lower), centroid]; probe k = [k*N:(k+1)*N].
    return np.vstack((p_h_po, p_h_no, p_v_po, p_v_no, centroid_points)) 

  def _get_free_3d_mask(self, at_prem_depths: np.ndarray, over_prem_depths: np.ndarray, depth_hi: np.ndarray):
    """Uses probe intersect #4
      Doe this work? 
      OR will the angular extend put the item so far back that a ray shot at its bottom will intersect near d_Est
        ---- *Verify* the size of a ray is agnostic to where it is on the ground ( I believe ) - meaning the elongated gaussian does 
            not have any understanding of the surface it exists on, only the size of the bb.
            Meaning it places teh gaussian in an affine space.
    """
    n = depth_hi.shape[0]
    v_no = slice(3 * n, 4 * n)  # lower-vertical probe block
    at_v = at_prem_depths[v_no]
    over_v = over_prem_depths[v_no]
    if at_v.ndim > 1:  # peeled layers -> front hit
      at_v, over_v = at_v[..., 0], over_v[..., 0]
    on_prem_mask = at_v > depth_hi
    over_prem_mask = over_v > depth_hi
    free3d_mask = np.logical_and(on_prem_mask, over_prem_mask)
    return free3d_mask

  def _get_avg_local_ground_plane(self, origins: np.ndarray, frame: np.ndarray, start_depths: np.ndarray, end_depths: np.ndarray, num_pins: int):
    """Pin-dropping along -world-up to estimate a local averaged ground plane (normal, point)."""
    # TODO: Optimization, remove pins that hit high points that vary outside normal range (1 std)
    z = self.rwc_z_up / np.linalg.norm(self.rwc_z_up)
    spaced_pin_depths = np.linspace(start_depths, end_depths, num_pins, axis=1)          # (N, num_pins)
    spaced_pin_rays = frame[:, :, 0].reshape(-1, 1, 3) * spaced_pin_depths[..., None]     # (N, num_pins, 3)
    spaced_pin_points = np.repeat(origins, num_pins, axis=0) + spaced_pin_rays.reshape(-1, 3)
    down = np.broadcast_to(-z, spaced_pin_points.shape)
    normals, depths = self.depth_map.cast_np(down, spaced_pin_points)
    # Average only pins that hit the mesh (missed pins are inf depth / nan normal).
    normals = normals.reshape(-1, num_pins, 3)
    t_safe = np.where(np.isfinite(depths), depths, 0.0)                                   # avoid inf*0 on misses
    hits = (spaced_pin_points + t_safe[:, None] * down).reshape(-1, num_pins, 3)
    valid = np.isfinite(depths).reshape(-1, num_pins)[..., None]
    count = np.maximum(valid.sum(axis=1), 1)
    average_normals = np.where(valid, normals, 0.0).sum(axis=1) / count
    average_points = np.where(valid, hits, 0.0).sum(axis=1) / count
    if self.debug:
      self.trace["pin_drop"] = {"origins": spaced_pin_points.reshape(-1, num_pins, 3), "hits": hits,
                                      "valid": valid[..., 0], "normals": normals,
                                      "avg_point": average_points, "avg_normal": average_normals}
    return average_normals, average_points

  def _cosine_similarity(self, n_one: np.ndarray, n_two: np.ndarray):
    # Row-wise angular distance (arccos of cosine); used as a cost so lower = more aligned.
    dot = np.einsum('ij,ij->i', n_one, n_two)
    denom = np.linalg.norm(n_one, axis=1) * np.linalg.norm(n_two, axis=1)
    return np.arccos(np.clip(dot / np.maximum(denom, 1e-12), -1.0, 1.0))

  def _calculate_height_from_depth(self, origin_points: np.ndarray, depths: np.ndarray, dir_rays: np.ndarray): 
    # World-up height of the ray hit (o3d: hit = origin + t_hit * dir).
    z = self.rwc_z_up / np.linalg.norm(self.rwc_z_up)
    hits = origin_points + depths[:, None] * dir_rays
    return hits @ z

  def _hit_points_from_query(self, probe_points: np.ndarray, depths: np.ndarray):
    """World hit points for the camera-ray t_hit values returned by query()."""
    if depths.ndim > 1:
      depths = depths[..., 0]  # front layer
    cam_origin = self.depth_map.camera_extrinsics[:3, 3]
    dirs = probe_points - cam_origin
    dirs = dirs / np.linalg.norm(dirs, axis=1, keepdims=True)
    return cam_origin + depths[:, None] * dirs

  def _signed_wall_angle(self, cand_normals: np.ndarray, rays: np.ndarray):
    """Signed angle (deg) between candidate normal and world-up, in the plane about e_h."""
    z = self.rwc_z_up / np.linalg.norm(self.rwc_z_up)
    n_c = cand_normals / np.linalg.norm(cand_normals, axis=1, keepdims=True)
    r = rays / np.linalg.norm(rays, axis=1, keepdims=True)
    # e_h = z x r; fall back to z x X when r is (near) parallel to z_up (degenerate cross).
    cross = np.cross(z, r)
    norm_c = np.linalg.norm(cross, axis=1, keepdims=True)
    cross = np.where(norm_c < 1e-6, np.cross(z, np.array([1.0, 0.0, 0.0])), cross)
    e_h = cross / np.linalg.norm(cross, axis=1, keepdims=True)
    y = np.einsum('ij,ij->i', np.cross(z, n_c), e_h)
    x = n_c @ z
    return np.degrees(np.arctan2(y, x))

  def _wall_spectrum(self, mu: np.ndarray, p_c: np.ndarray, p_top: np.ndarray,
                       l_v: float = 75.0, num_rays: int = 8):
    """Occluded fallback: fan num_rays from the camera between the centroid and top targets.

    Returns (wall_spec, spectrum_depth): per-object vertical-hit-or-rising-backing flag and a
    wall depth (nearest vertical hit, else mean distance over rising horizontal supports).
    """
    z = self.rwc_z_up / np.linalg.norm(self.rwc_z_up)
    t = np.linspace(0.0, 1.0, num_rays)
    # Target points between centroid and top, then unit rays from the camera through them.
    q = (1 - t)[None, :, None] * p_c[:, None, :] + t[None, :, None] * p_top[:, None, :]
    dirs = q - mu[:, None, :]
    dirs = dirs / np.linalg.norm(dirs, axis=-1, keepdims=True)          # (N, M, 3)
    origins = np.broadcast_to(mu[:, None, :], dirs.shape)
    # query() looks the targets up in the prebuilt depth map; peeled maps return layers, so
    # keep the front hit, then reshape back to the per-object fan of num_rays.
    t_hit, normals = self.depth_map.query(q.reshape(-1, 3))
    if t_hit.ndim > 1:
      t_hit, normals = t_hit[..., 0], normals[..., 0, :]
    t_hit = t_hit.reshape(-1, num_rays)
    normals = normals.reshape(-1, num_rays, 3)
    finite = np.isfinite(t_hit)
    # Vertical (wall-like) by the unsigned angle of the hit normal to world-up.
    a = np.degrees(np.arccos(np.clip(np.abs(normals @ z), 0.0, 1.0)))   # (N, M)
    v = (a >= l_v) & finite
    # Nearest vertical hit distance per object (inf where none).
    nearest_vert = np.where(v, t_hit, np.inf).min(axis=1)
    # Rising horizontal supports: a higher non-vertical hit than the previous ray.
    t_safe = np.where(finite, t_hit, 0.0)                              # avoid inf*0 on misses
    heights = (origins + t_safe[..., None] * dirs) @ z                # (N, M)
    rising = np.zeros_like(v)
    rising[:, 1:] = (~v[:, 1:]) & finite[:, 1:] & finite[:, :-1] & (heights[:, 1:] > heights[:, :-1]) & (heights[:, 1:] - heights[:, :-1] > .1)  # TODO: Need to add a way to determine if the rate of change is high enough, is the hieght change enough..?
    # TODO: Create best fit plane (min-OLS); determine gradient of plane - if magnituide of gradient is less than some value simply call noise (random bumps in ground) and not actual increase
    support_sum = rising.sum(axis=1)  # TODO: Recheck: odd thing to be summing mask
    d_wall = np.where(support_sum > 0,
                          np.sum(np.where(rising, t_hit, 0.0), axis=1) / np.maximum(support_sum, 1),   # TODO: Recheck: odd thing to be dividng by mask..
                          np.nan) # averaged wall
    spectrum_depth = np.where(np.isfinite(nearest_vert), nearest_vert, d_wall)
    if self.debug:
      self.trace["spectrum"] = {"origins": np.array(origins), "dirs": dirs,
                                      "hits": origins + t_safe[..., None] * dirs,
                                      "finite": finite, "vertical": v, "support_sum": rising}
    return v.any(axis=1) | (support_sum > 0), spectrum_depth

  def _get_occlusion_depth(self, ray_var: np.ndarray, 
                             lo_vert_at_prem_depths: np.ndarray, 
                             lo_vert_over_prem_depths: np.ndarray, 
                             prior_depth_est: np.ndarray, 
                             free_3d_mask: np.ndarray, 
                             origins: np.ndarray | None = None,
                             frame: np.ndarray | None = None, 
                             over_prem_probe_points: np.ndarray | None = None,
                             num_pins: int = 4,
                             non_naive: bool = True, eps:float=.1):
    
    """If no occlusion, depth is set to np.nan (masked at use-time)"""
    # Base Naive checks (thresholds in std units: sqrt(ray_var) is sigma_d).
    sigma_d = np.sqrt(ray_var)
    at_edge_closer_than_exp = np.where(prior_depth_est - lo_vert_at_prem_depths > sigma_d * eps, lo_vert_at_prem_depths, np.nan) #np.nan does not play nice typically, need to find better sentinel val
    hits_dist_too_far = np.where(lo_vert_over_prem_depths - lo_vert_at_prem_depths > sigma_d * eps, lo_vert_over_prem_depths, np.nan)
    # Nearest applicable occluder; nan (no occlusion) where neither side fired. fmin skips nan.
    occlusion_depth = np.where(free_3d_mask, np.nan, np.fmin(at_edge_closer_than_exp, hits_dist_too_far))
    if non_naive and frame is not None and origins is not None and over_prem_probe_points is not None:
      # TODO: Further Research: We can put start depth as .1sigma before and end_depth as .1sigma after 
      # TODO: Use the above naive checks as masks that pass onto here
      z = self.rwc_z_up / np.linalg.norm(self.rwc_z_up)
      average_normals, average_points = self._get_avg_local_ground_plane(origins, frame, prior_depth_est - sigma_d*eps, prior_depth_est + sigma_d*eps, num_pins)
      average_heights = average_points @ z
      fpj_normals, fpj_depths = self.depth_map.cast_np(frame[:,:,0], over_prem_probe_points)
      bpj_normals, bpj_depths = self.depth_map.cast_np(-frame[:,:,0], over_prem_probe_points)
      fpj_heights= self._calculate_height_from_depth(over_prem_probe_points, fpj_depths,frame[:,:,0])
      bpj_heights= self._calculate_height_from_depth(over_prem_probe_points, bpj_depths, -frame[:,:,0])
      fpj_height_dif= np.abs(fpj_heights - average_heights)
      bpj_height_dif= np.abs(bpj_heights - average_heights)
      nmlzd_height_denom = fpj_height_dif + bpj_height_dif
      fpj_nmlzd_height = fpj_height_dif / nmlzd_height_denom
      bpj_nmlzd_height = bpj_height_dif / nmlzd_height_denom
      fpj_normal_similarity = self._cosine_similarity(average_normals, fpj_normals)
      bpj_normal_similarity = self._cosine_similarity(average_normals, bpj_normals)
      nmlzd_sim_denom = fpj_normal_similarity + bpj_normal_similarity
      fpj_nmlzd_sim = fpj_normal_similarity / nmlzd_sim_denom
      bpj_nmlzd_sim = bpj_normal_similarity / nmlzd_sim_denom
      cost_fpj = PLANE_DECISION_NML_WEIGHT * fpj_nmlzd_sim + (1 - PLANE_DECISION_NML_WEIGHT) * fpj_nmlzd_height
      cost_bpj = PLANE_DECISION_NML_WEIGHT * bpj_nmlzd_sim + (1 - PLANE_DECISION_NML_WEIGHT) * bpj_nmlzd_height
      # Vectorized pick: per row keep the projection (fpj/bpj) with the lower cost.
      choose_fpj = cost_fpj < cost_bpj
      trusted_depths = np.where(choose_fpj, fpj_depths, bpj_depths)
      trusted_dirs = np.where(choose_fpj[:, None], frame[:, :, 0], -frame[:, :, 0])
      # fpj/bpj t_hit is measured from the over-premise probe point along the frame axis,
      # but query()'s lo_vert depths are measured from the camera. Recover the world hit
      # point, then re-express it as a camera range so both live on the same ruler.
      trusted_points = over_prem_probe_points + trusted_depths[:, None] * trusted_dirs
      cam_origin = self.depth_map.camera_extrinsics[:3, 3]
      trusted_cam_depths = np.linalg.norm(trusted_points - cam_origin, axis=-1)

      # Occlusion: a nearer actual hit means a closer surface occludes the expected floor.
      at_prem_occluded = np.abs(lo_vert_at_prem_depths - trusted_cam_depths) > eps
      over_prem_occluded = np.abs(lo_vert_over_prem_depths - trusted_cam_depths) > eps

      # Per-side occluder depth (nan where that side didn't fire); naive checks store a
      # value/nan, so ~isnan turns them back into masks.
      over_depth = np.where(over_prem_occluded | ~np.isnan(hits_dist_too_far), lo_vert_over_prem_depths, np.nan)
      at_depth = np.where(at_prem_occluded | ~np.isnan(at_edge_closer_than_exp), lo_vert_at_prem_depths, np.nan)
      # Nearest applicable occluder; nan (no occlusion) where neither side fired. fmin skips nan.
      occlusion_depth = np.where(free_3d_mask, np.nan, np.fmin(at_depth, over_depth))
      return occlusion_depth
    return occlusion_depth


  def _get_wall_depth(self, mu: np.ndarray, ray: np.ndarray, depth_est: np.ndarray,
            depth_lo: np.ndarray, depth_hi: np.ndarray, frame: np.ndarray,
            at_prem_probe_points: np.ndarray, at_prem_depths: np.ndarray, at_prem_normals: np.ndarray,
            centroid_points: np.ndarray, occlusion_depth: np.ndarray,
            l_v: float = 75.0, u_v: float = 115.0, height_eps: float = .1):
    """Wall depth per object; np.nan where no wall (masked at use-time).

    Step 9: signed-angle test is primary; a higher horizontal surface counts as backing
    only when the pin-dropped ground is trustworthy (not occluded) and it is not ground.
    Occluded objects fall back to the centroid-to-top ray spectrum.
    """
    n = depth_est.shape[0]
    # Blocks: v_po (top) [2n:3n], v_no (lower) [3n:4n], centroid [4n:5n].
    top_s, lov_s, cen_s = slice(2 * n, 3 * n), slice(3 * n, 4 * n), slice(4 * n, 5 * n)
    cand_normals = at_prem_normals[cen_s]
    if cand_normals.ndim > 2:  # peeled layers -> keep the front hit
      cand_normals = cand_normals[:, 0, :]
    cand_depths = at_prem_depths[cen_s]
    cand_depths = cand_depths[..., 0] if cand_depths.ndim > 1 else cand_depths
    cand_points = self._hit_points_from_query(at_prem_probe_points[cen_s], at_prem_depths[cen_s])
    lo_vert_points = self._hit_points_from_query(at_prem_probe_points[lov_s], at_prem_depths[lov_s])
    top_points = self._hit_points_from_query(at_prem_probe_points[top_s], at_prem_depths[top_s])

    # Pin-dropped averaged ground plane over the object's depth band [depth_lo, depth_hi] along
    # the centroid ray, so the pins fan across the floor footprint (not clustered at the centroid).
    avg_ground_normals, avg_ground_points = self._get_avg_local_ground_plane(
      mu, frame, depth_lo, depth_hi, num_pins=4)

    occluded_mask = ~np.isnan(occlusion_depth)
    if occluded_mask.ndim > 1:
      occluded_mask = occluded_mask.any(axis=tuple(range(1, occluded_mask.ndim)))

    z = self.rwc_z_up / np.linalg.norm(self.rwc_z_up)
    # Primary: candidate normal is vertical (wall) by the signed test.
    a_s = self._signed_wall_angle(cand_normals, ray)
    is_vertical = (a_s >= l_v) & (a_s < u_v)
    # Height ordering; differences cancel the world-up origin offset.
    # h_v = lo_vert_points @ z
    # f1 = (cand_points @ z) > h_v
    # f2 = (top_points @ z) > h_v
    # Pin-dropped averaged ground plane (point + normal): signed distance of a query point.
    n_g = avg_ground_normals / np.maximum(np.linalg.norm(avg_ground_normals, axis=1, keepdims=True), 1e-12)  
    s_pc = np.einsum('ij,ij->i', centroid_points - avg_ground_points, n_g)
    s_pt = np.einsum('ij,ij->i', top_points - avg_ground_points, n_g)
    ground = (s_pc <= 0) & (s_pt <= 0) # If both heights are less than a small error we indicate ground
    # Higher-than-floor surface is backing only on a trustworthy (unoccluded) floor.
    # backing = (f1 | f2) & ~ground & ~occluded_mask #TODO: This doesn't work because ground is often sloped/bumpy/uneven in hieght
    # TODO: To fix this we can create a OLS-fit plane; get gradient of plane and determien if gradients slipe is closer to noise or wall
    # The reason for this is we were getting false positives of wall-determination on ground where the ground was bumpy
    #naive_wall = is_vertical | backing
    # Occluded objects (untrustworthy floor) fall back to the centroid-to-top ray spectrum.
    spec_wall, spec_depth = self._wall_spectrum(mu, centroid_points, at_prem_probe_points[top_s], l_v)
    spec_only =  ~is_vertical & spec_wall
    is_wall = is_vertical | spec_wall
    wall_depth = np.where(is_vertical, cand_depths, np.nan)
    wall_depth = np.where(spec_only, spec_depth, wall_depth)
    if self.debug:
      self.trace["wall"] = {"cand_points": cand_points, "is_vertical": is_vertical,
                                  "is_wall": is_wall, "wall_depth": wall_depth,
                                  "ground_point": avg_ground_points, "ground_normal": avg_ground_normals}
    return wall_depth

  def _total_occlusion(self, probe_points: np.ndarray, n: int,
                         num_rays: int = 9, occ_frac: float = 0.9, eps: float = 0.1):
    """Fraction-based total-occlusion test over the object's vertical 2-sigma extent.

    Fans num_rays targets from the lower-vertical (v_no) up to the top (v_po) probe and marks
    each blocked when scene geometry sits nearer than the target. 'Fully occluded' means at
    least occ_frac of that column is blocked - a graded, noise-tolerant replacement for an
    all-or-nothing lo/centroid/top test. A detection with a meaningful visible fraction is a
    real occluder (keep it back); only a near-zero visible fraction flips it to a wall
    (pull forward). Returns (mask, nearest_blocker_depth).
    """
    cam = self.depth_map.camera_extrinsics[:3, 3]
    lo_pts, top_pts = probe_points[3 * n:4 * n], probe_points[2 * n:3 * n]
    s = np.linspace(0.0, 1.0, num_rays)
    targets = (1 - s)[None, :, None] * lo_pts[:, None, :] + s[None, :, None] * top_pts[:, None, :]
    t_hit, _ = self.depth_map.query(targets.reshape(-1, 3))
    t_hit = t_hit[..., 0] if t_hit.ndim > 1 else t_hit
    t_hit = t_hit.reshape(n, num_rays)
    dist = np.linalg.norm(targets - cam, axis=-1)
    blocked = np.isfinite(t_hit) & (t_hit < dist - eps)   # scene surface in front of each target
    frac = blocked.mean(axis=1)
    nearest = np.where(blocked, t_hit, np.inf).min(axis=1)
    if self.debug:
      self.trace["total_occ_frac"] = frac
    return frac >= occ_frac, nearest

  def _update_depth_gaussian(self, depth_est: np.ndarray, sigma_d_sq: np.ndarray,
                               occlusion_depth: np.ndarray, wall_depth: np.ndarray,
                               free_3d_mask: np.ndarray, k: float = 2.0, r_occ: float = 0.0,
                               eps: float = 0.1):
    """Step 10: re-bound the depth Gaussian from occlusion/wall hits (moment-matched).

    No-op for free-3D objects or when neither bound fired. Occlusion inflates (adaptive
    Kalman) then lower-truncates at d_occ; a wall alone upper-truncates at d_wall (shrinks).
    Returns (mu, var) along the depth axis.
    """
    occluded = np.isfinite(occlusion_depth)   # a bound is present only if finite (misses are inf/nan)
    walled = np.isfinite(wall_depth)
    # A wall is a far-side backing; when it coincides with the occluder (within eps) it is the
    # occluder's own face, not a surface behind the hidden object - a surface can't be both.
    # Drop it so an occluded object gets an occlusion-only update (expands) instead of collapsing
    # onto the occluder.
    walled &= ~(occluded & (wall_depth <= occlusion_depth + eps))
    update = ~free_3d_mask & (occluded | walled)

    # Adaptive inflation from the part of the occluder innovation the prior can't explain.
    occ_d = np.where(occluded, occlusion_depth, depth_est)
    delta_sq = (depth_est - occ_d) ** 2
    inflation = np.where(occluded, np.maximum(0.0, delta_sq - (sigma_d_sq + r_occ)) / k, 0.0)
    var_pre = sigma_d_sq + inflation
    sigma_pre = np.sqrt(var_pre)

    # Truncate to [a, b]: the occluder is a lower bound, the wall an upper bound.
    a = np.where(occluded, occ_d, -np.inf)
    b = np.where(walled, wall_depth, np.inf)
    alpha = (a - depth_est) / sigma_pre
    beta = (b - depth_est) / sigma_pre
    # Conflicting bounds (occluder behind the wall) make [a, b] empty, where the truncated
    # normal is undefined and the closed-form moments blow up; fall back to the midpoint of
    # the two crossed bounds (documented weak heuristic) with the inflated prior variance.
    empty = a >= b
    beta_safe = np.where(empty, alpha + 1.0, beta)  # dummy valid interval; overwritten below
    mu_t, var_t = truncnorm.stats(alpha, beta_safe, loc=depth_est, scale=sigma_pre, moments="mv")
    mu_t = np.where(empty, 0.5 * (a + b), mu_t)
    var_t = np.where(empty, var_pre, var_t)

    mu_new = np.where(update, mu_t, depth_est)
    var_new = np.where(update, np.maximum(var_t, 0.0), sigma_d_sq)
    return mu_new, var_new

  def generate(self, gaus_rays: dict[str, np.ndarray]):
    """Condition each object's depth Gaussian on the scene geometry; returns (depth, var).

    gaus_rays holds parallel per-object arrays in the world frame (mu = camera origin):
      "mu":        float32, (N, 3)     camera world position (shared ray origin)
      "Sigma":     float32, (N, 3, 3)  world covariance (depth variance drives sigma_d)
      "ray":       float32, (N, 3)     unit world direction to the centroid
      "depth_est": float32, (N,)       along-ray distance to the centroid
      "depth_lo":  float32, (N,)
      "depth_hi":  float32, (N,)
    depth_sigma / score / edge_valid may be present but are not read here. Returns
    (updated_depth, updated_var), each (N,), along the ray (depth) axis.
    """
    n = gaus_rays['depth_hi'].shape[0]
    centroid_points = self._get_centroid_points(gaus_rays)
    frame = self._build_orthonorm_frame(gaus_rays)
    decons_cov = self._deconstruct_cov(frame, gaus_rays)
    at_prem_probe_points = self._create_probe_points(decons_cov, frame, centroid_points)
    over_prem_probe_points = self._create_probe_points(decons_cov, frame, centroid_points, 2.1)
    at_prem_depths, at_prem_normals = self.depth_map.query(at_prem_probe_points)
    over_prem_depths, over_prem_normals = self.depth_map.query(over_prem_probe_points)
    free3d_mask = self._get_free_3d_mask(at_prem_depths, over_prem_depths, gaus_rays['depth_hi']) 
    # Lower-vertical (v_no) block, front layer, for the naive occlusion checks.
    lo_at = at_prem_depths[3*n:4*n]
    lo_over = over_prem_depths[3*n:4*n]
    if lo_at.ndim > 1:
      lo_at, lo_over = lo_at[..., 0], lo_over[..., 0]
    occlusion_depth = self._get_occlusion_depth(decons_cov[:, 0, 0], lo_at, lo_over, gaus_rays['depth_est'], free3d_mask)

    wall_depth = self._get_wall_depth(gaus_rays['mu'], gaus_rays['ray'], gaus_rays['depth_est'],
                                          gaus_rays['depth_lo'], gaus_rays['depth_hi'], frame,
                                          at_prem_probe_points, at_prem_depths, at_prem_normals,
                                          centroid_points, occlusion_depth)

    total_occ, nearest_block = self._total_occlusion(at_prem_probe_points, n)
    # A fully-occluded detection cannot lie behind the surface (nothing would be visible), so the
    # depth prior is wrong: drop the occluder (lower bound) and treat the nearest blocker as a
    # wall (upper bound) that pulls the object in front of it.
    occlusion_depth = np.where(total_occ, np.nan, occlusion_depth)
    wall_depth = np.where(total_occ, nearest_block, wall_depth)

    updated_depth, updated_var = self._update_depth_gaussian(
      gaus_rays['depth_est'], decons_cov[:, 0, 0], occlusion_depth, wall_depth, free3d_mask)

    if self.debug:
      lov = slice(3 * n, 4 * n)
      self.trace["camera"] = self.depth_map.camera_extrinsics[:3, 3]
      self.trace["centroids"] = centroid_points
      self.trace["total_occ"] = total_occ
      self.trace["occlusion"] = {
        "at_probe": at_prem_probe_points[lov], "over_probe": over_prem_probe_points[lov],
        "at_hit": self._hit_points_from_query(at_prem_probe_points[lov], at_prem_depths[lov]),
        "over_hit": self._hit_points_from_query(over_prem_probe_points[lov], over_prem_depths[lov]),
        "occluded": np.isfinite(occlusion_depth)}
      # Camera-ray hit points for the lower-vertical (v_no), centroid and top (v_po) probes.
      top_b, cen_b = slice(2 * n, 3 * n), slice(4 * n, 5 * n)
      self.trace["probe_rays"] = {
        "lo_hit": self._hit_points_from_query(at_prem_probe_points[lov], at_prem_depths[lov]),
        "cen_hit": self._hit_points_from_query(at_prem_probe_points[cen_b], at_prem_depths[cen_b]),
        "top_hit": self._hit_points_from_query(at_prem_probe_points[top_b], at_prem_depths[top_b])}
      # Prior/updated 3D Gaussian ellipsoids: world cov = frame @ Lambda @ frameᵀ, so the
      # updated ellipsoid swaps the frame-space depth variance for updated_var and re-centres.
      lam_updated = decons_cov.copy()
      lam_updated[:, 0, 0] = updated_var
      cov_updated = frame @ lam_updated @ frame.mT
      updated_centroids = gaus_rays['mu'] + gaus_rays['ray'] * updated_depth[:, None]
      self.trace["gaussian"] = {
        "centroids": centroid_points, "cov": gaus_rays['Sigma'],
        "updated_centroids": updated_centroids, "updated_cov": cov_updated,
        "prior_depth": gaus_rays['depth_est'], "updated_depth": updated_depth}
    return updated_depth, updated_var
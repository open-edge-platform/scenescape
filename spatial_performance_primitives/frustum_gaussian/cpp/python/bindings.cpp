// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include "frustum_gaussian/frustum.hpp"

#include <stdexcept>
#include <vector>
#include <string>

namespace py = pybind11;
using namespace fg;

// ---------------------------------------------------------------------------
// Numpy array type aliases
// ---------------------------------------------------------------------------
using F32Array  = py::array_t<float,   py::array::c_style | py::array::forcecast>;
using U8Array   = py::array_t<uint8_t, py::array::c_style | py::array::forcecast>;

// ---------------------------------------------------------------------------
// Helper: require shape
// ---------------------------------------------------------------------------
static void require_shape(const py::buffer_info& info,
                          std::initializer_list<ssize_t> expected,
                          const char* name) {
    if ((ssize_t)info.ndim != (ssize_t)expected.size())
        throw std::invalid_argument(
            std::string(name) + ": expected " +
            std::to_string(expected.size()) + "D array, got " +
            std::to_string(info.ndim) + "D");

    ssize_t i = 0;
    for (auto e : expected) {
        if (e >= 0 && info.shape[i] != e)
            throw std::invalid_argument(
                std::string(name) + ": dimension " + std::to_string(i) +
                " expected " + std::to_string(e) +
                ", got " + std::to_string(info.shape[i]));
        ++i;
    }
}

// ---------------------------------------------------------------------------
// project_frustum_batch — numpy interface (dict-based API)
//
// Parameters
// ----------
// obs_dict     : dict with keys:
//   'boxes'    (N, 4) float32  [u_min, v_min, u_max, v_max]    REQUIRED
//   'priors'   (N, 6) float32  [mu_x, mu_y, mu_z, σx, σy, σz]  REQUIRED
//   'ranges'   (N,)   float32  slant-range (m); NaN = no measurement  OPTIONAL
//   'clipped'  (N,)   uint8    edge bitmask; 0xFF = auto-detect        OPTIONAL
// intrinsics   : (4,)   float32  [fx, fy, cx, cy]
// img_size     : (2,)   float32  [width, height]
// sigma_px     : float  detector edge-localization noise (default 2.0)
// sensor       : RangeSensorConfig or None  (default None = angular-only)
//
// Returns
// -------
// dict with keys:
//   'mu'          (N, 3)    float32  — position in camera frame (m)
//   'Sigma'       (N, 3, 3) float32  — covariance (m²)
//   'ray'         (N, 3)    float32  — unit ray direction
//   'depth_est'   (N,)      float32  — MAP depth (m)
//   'depth_sigma' (N,)      float32  — 1-σ depth uncertainty (m)
//   'depth_lo'    (N,)      float32  — geometric lower bound (m)
//   'depth_hi'    (N,)      float32  — geometric upper bound (m)
//   'score'       (N,)      float32  — depth quality ∈ [0,1]
//   'edge_valid'  (N,)      uint8    — unclipped edge flags
// ---------------------------------------------------------------------------
static py::dict batch_numpy(
    const py::dict& obs_dict,
    const F32Array& intrinsics_arr,
    const F32Array& img_size_arr,
    float           sigma_px   = 2.0f,
    py::object      sensor_obj = py::none())
{
    // ---- Required inputs -----------------------------------------------
    if (!obs_dict.contains("boxes"))
        throw std::invalid_argument("obs_dict must contain 'boxes'");
    if (!obs_dict.contains("priors"))
        throw std::invalid_argument("obs_dict must contain 'priors'");

    F32Array boxes_arr  = obs_dict["boxes"].cast<F32Array>();
    F32Array priors_arr = obs_dict["priors"].cast<F32Array>();

    auto bi = boxes_arr.request();
    auto pi = priors_arr.request();
    auto ii = intrinsics_arr.request();
    auto si = img_size_arr.request();

    if (bi.ndim != 2 || bi.shape[1] != 4)
        throw std::invalid_argument("obs_dict['boxes'] must be (N, 4)");
    if (pi.ndim != 2 || pi.shape[1] != 6)
        throw std::invalid_argument("obs_dict['priors'] must be (N, 6)");
    if (bi.shape[0] != pi.shape[0])
        throw std::invalid_argument("'boxes' and 'priors' must have the same N");
    if (ii.ndim != 1 || ii.shape[0] != 4)
        throw std::invalid_argument("intrinsics must be (4,): [fx,fy,cx,cy]");
    if (si.ndim != 1 || si.shape[0] != 2)
        throw std::invalid_argument("img_size must be (2,): [width,height]");

    const ssize_t N = bi.shape[0];

    const float* bptr = static_cast<const float*>(bi.ptr);
    const float* iptr = static_cast<const float*>(ii.ptr);
    const float* sptr = static_cast<const float*>(si.ptr);
    const float* pptr = static_cast<const float*>(pi.ptr);

    // ---- Optional clipped array ----------------------------------------
    const uint8_t* clip_ptr = nullptr;
    U8Array clipped_arr;
    if (obs_dict.contains("clipped") && !obs_dict["clipped"].is_none()) {
        clipped_arr = obs_dict["clipped"].cast<U8Array>();
        auto ci = clipped_arr.request();
        if (ci.ndim != 1 || ci.shape[0] != N)
            throw std::invalid_argument("obs_dict['clipped'] must be (N,) uint8");
        clip_ptr = static_cast<const uint8_t*>(ci.ptr);
    }

    // ---- Optional ranges array -----------------------------------------
    const float* ranges_ptr = nullptr;
    F32Array ranges_arr;
    if (obs_dict.contains("ranges") && !obs_dict["ranges"].is_none()) {
        ranges_arr = obs_dict["ranges"].cast<F32Array>();
        auto ri = ranges_arr.request();
        if (ri.ndim != 1 || ri.shape[0] != N)
            throw std::invalid_argument("obs_dict['ranges'] must be (N,) float32");
        ranges_ptr = static_cast<const float*>(ri.ptr);
    }

    // ---- Optional per-detection axis_aware array -------------------------
    const uint8_t* axis_aware_ptr = nullptr;
    U8Array axis_aware_arr;
    if (obs_dict.contains("axis_aware") && !obs_dict["axis_aware"].is_none()) {
        axis_aware_arr = obs_dict["axis_aware"].cast<U8Array>();
        auto ai = axis_aware_arr.request();
        if (ai.ndim != 1 || ai.shape[0] != N)
            throw std::invalid_argument("obs_dict['axis_aware'] must be (N,) bool/uint8");
        axis_aware_ptr = static_cast<const uint8_t*>(ai.ptr);
    }

    // ---- RangeSensorConfig (optional) ----------------------------------
    RangeSensorConfig sensor{};
    if (!sensor_obj.is_none())
        sensor = sensor_obj.cast<RangeSensorConfig>();

    // ---- Build C++ input arrays ----------------------------------------
    const Intrinsics K(iptr[0], iptr[1], iptr[2], iptr[3], sptr[0], sptr[1]);
    const DetectorNoise noise(sigma_px);

    std::vector<BoundingBox> boxes_c(N);
    std::vector<ShapePrior>  priors_c(N);

    for (ssize_t i = 0; i < N; ++i) {
        const float* b = bptr + i * 4;
        boxes_c[i].u_min   = b[0];
        boxes_c[i].v_min   = b[1];
        boxes_c[i].u_max   = b[2];
        boxes_c[i].v_max   = b[3];
        boxes_c[i].clipped = clip_ptr ? clip_ptr[i] : BoundingBox::CLIPPED_AUTO;

        const float* p = pptr + i * 6;
        priors_c[i].mu_x    = p[0];
        priors_c[i].mu_y    = p[1];
        priors_c[i].mu_z    = p[2];
        priors_c[i].sigma_x = p[3];
        priors_c[i].sigma_y = p[4];
        priors_c[i].sigma_z = p[5];
        if (axis_aware_ptr)
            priors_c[i].axis_aware = axis_aware_ptr[i] != 0;
    }

    // ---- Call C++ batch kernel -----------------------------------------
    std::vector<FrustumObservation> out_c(N);
    {
        py::gil_scoped_release release;
        project_frustum_batch(
            boxes_c.data(), K, priors_c.data(), noise, out_c.data(),
            static_cast<size_t>(N),
            ranges_ptr, sensor);
    }

    // ---- Build numpy output arrays -------------------------------------
    auto mu_out          = py::array_t<float>({N, (ssize_t)3});
    auto Sigma_out       = py::array_t<float>({N, (ssize_t)3, (ssize_t)3});
    auto ray_out         = py::array_t<float>({N, (ssize_t)3});
    auto depth_est_out   = py::array_t<float>(N);
    auto depth_sigma_out = py::array_t<float>(N);
    auto depth_lo_out    = py::array_t<float>(N);
    auto depth_hi_out    = py::array_t<float>(N);
    auto score_out       = py::array_t<float>(N);
    auto edge_valid_out  = py::array_t<uint8_t>(N);

    float*   mu_p  = mu_out.mutable_data();
    float*   Sg_p  = Sigma_out.mutable_data();
    float*   ray_p = ray_out.mutable_data();
    float*   de_p  = depth_est_out.mutable_data();
    float*   ds_p  = depth_sigma_out.mutable_data();
    float*   dlo_p = depth_lo_out.mutable_data();
    float*   dhi_p = depth_hi_out.mutable_data();
    float*   sc_p  = score_out.mutable_data();
    uint8_t* ev_p  = edge_valid_out.mutable_data();

    for (ssize_t i = 0; i < N; ++i) {
        const auto& o = out_c[i];
        mu_p[i*3+0] = o.mu[0]; mu_p[i*3+1] = o.mu[1]; mu_p[i*3+2] = o.mu[2];
        for (int k = 0; k < 9; ++k) Sg_p[i*9+k] = o.Sigma[k];
        ray_p[i*3+0] = o.ray[0]; ray_p[i*3+1] = o.ray[1]; ray_p[i*3+2] = o.ray[2];
        de_p[i]  = o.depth_est;
        ds_p[i]  = o.depth_sigma;
        dlo_p[i] = o.depth_lo;
        dhi_p[i] = o.depth_hi;
        sc_p[i]  = o.score;
        ev_p[i]  = o.edge_valid;
    }

    py::dict result;
    result["mu"]          = mu_out;
    result["Sigma"]       = Sigma_out;
    result["ray"]         = ray_out;
    result["depth_est"]   = depth_est_out;
    result["depth_sigma"] = depth_sigma_out;
    result["depth_lo"]    = depth_lo_out;
    result["depth_hi"]    = depth_hi_out;
    result["score"]       = score_out;
    result["edge_valid"]  = edge_valid_out;
    return result;
}

// ---------------------------------------------------------------------------
// transform_to_world_batch — numpy interface
//
// Parameters
// ----------
// mu       : (N, 3) float32 — camera-frame positions
// Sigma    : (N, 3, 3) float32 — camera-frame covariances
// ray      : (N, 3) float32 — camera-frame rays
// pose_mat : (4, 4) float32 — camera-to-world pose matrix (row-major)
//
// Returns dict with mu, Sigma, ray, and depth quantities in the world frame;
// score and edge_valid are copied unchanged.
// ---------------------------------------------------------------------------
static py::dict transform_world_batch(
    const py::dict& obs_dict,
    const F32Array& pose_arr)
{
    auto pi = pose_arr.request();
    if (pi.ndim != 2 || pi.shape[0] != 4 || pi.shape[1] != 4)
        throw std::invalid_argument("pose_mat must be (4, 4) float32");
    const float* pose_ptr = static_cast<const float*>(pi.ptr);

    F32Array mu_in    = obs_dict["mu"].cast<F32Array>();
    F32Array Sigma_in = obs_dict["Sigma"].cast<F32Array>();
    F32Array ray_in   = obs_dict["ray"].cast<F32Array>();
    F32Array depth_est_in = obs_dict["depth_est"].cast<F32Array>();
    F32Array depth_sigma_in = obs_dict["depth_sigma"].cast<F32Array>();
    F32Array depth_lo_in = obs_dict["depth_lo"].cast<F32Array>();
    F32Array depth_hi_in = obs_dict["depth_hi"].cast<F32Array>();

    auto mui = mu_in.request();
    const ssize_t N = mui.shape[0];

    const float* mu_p  = static_cast<const float*>(mui.ptr);
    const float* Sg_p  = static_cast<const float*>(Sigma_in.request().ptr);
    const float* ray_p = static_cast<const float*>(ray_in.request().ptr);
    const float* depth_est_p = static_cast<const float*>(depth_est_in.request().ptr);
    const float* depth_sigma_p = static_cast<const float*>(depth_sigma_in.request().ptr);
    const float* depth_lo_p = static_cast<const float*>(depth_lo_in.request().ptr);
    const float* depth_hi_p = static_cast<const float*>(depth_hi_in.request().ptr);

    auto mu_out    = py::array_t<float>({N, (ssize_t)3});
    auto Sigma_out = py::array_t<float>({N, (ssize_t)3, (ssize_t)3});
    auto ray_out   = py::array_t<float>({N, (ssize_t)3});
    auto depth_est_out = py::array_t<float>(N);
    auto depth_sigma_out = py::array_t<float>(N);
    auto depth_lo_out = py::array_t<float>(N);
    auto depth_hi_out = py::array_t<float>(N);

    float* mu_op  = mu_out.mutable_data();
    float* Sg_op  = Sigma_out.mutable_data();
    float* ray_op = ray_out.mutable_data();
    float* depth_est_op = depth_est_out.mutable_data();
    float* depth_sigma_op = depth_sigma_out.mutable_data();
    float* depth_lo_op = depth_lo_out.mutable_data();
    float* depth_hi_op = depth_hi_out.mutable_data();

    {
        py::gil_scoped_release release;
        for (ssize_t i = 0; i < N; ++i) {
            FrustumObservation obs{};
            obs.mu[0] = mu_p[i*3+0]; obs.mu[1] = mu_p[i*3+1]; obs.mu[2] = mu_p[i*3+2];
            for (int k = 0; k < 9; ++k) obs.Sigma[k] = Sg_p[i*9+k];
            obs.ray[0] = ray_p[i*3+0]; obs.ray[1] = ray_p[i*3+1]; obs.ray[2] = ray_p[i*3+2];
            obs.depth_est = depth_est_p[i];
            obs.depth_sigma = depth_sigma_p[i];
            obs.depth_lo = depth_lo_p[i];
            obs.depth_hi = depth_hi_p[i];

            const FrustumObservation out_obs = transform_to_world(obs, pose_ptr);

            mu_op[i*3+0] = out_obs.mu[0]; mu_op[i*3+1] = out_obs.mu[1]; mu_op[i*3+2] = out_obs.mu[2];
            for (int k = 0; k < 9; ++k) Sg_op[i*9+k] = out_obs.Sigma[k];
            ray_op[i*3+0] = out_obs.ray[0]; ray_op[i*3+1] = out_obs.ray[1]; ray_op[i*3+2] = out_obs.ray[2];
            depth_est_op[i] = out_obs.depth_est;
            depth_sigma_op[i] = out_obs.depth_sigma;
            depth_lo_op[i] = out_obs.depth_lo;
            depth_hi_op[i] = out_obs.depth_hi;
        }
    }

    // Build result: copy non-spatial fields from input, replace mu/Sigma/ray
    py::dict result;
    for (auto item : obs_dict)
        result[item.first] = item.second;
    result["mu"]    = mu_out;
    result["Sigma"] = Sigma_out;
    result["ray"]   = ray_out;
    result["depth_est"] = depth_est_out;
    result["depth_sigma"] = depth_sigma_out;
    result["depth_lo"] = depth_lo_out;
    result["depth_hi"] = depth_hi_out;
    return result;
}

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------
PYBIND11_MODULE(_frustum_gaussian_cpp, m) {
    m.doc() = "Gaussian frustum projection — C++/TBB core";

    // --- Edge flag constants -------------------------------------------
    m.attr("EDGE_LEFT")   = py::int_(EDGE_LEFT);
    m.attr("EDGE_RIGHT")  = py::int_(EDGE_RIGHT);
    m.attr("EDGE_TOP")    = py::int_(EDGE_TOP);
    m.attr("EDGE_BOTTOM") = py::int_(EDGE_BOTTOM);
    m.attr("EDGE_ALL")    = py::int_(EDGE_ALL);

    // --- BoundingBox ---------------------------------------------------
    py::class_<BoundingBox>(m, "BoundingBox")
        .def(py::init<float, float, float, float>(),
             py::arg("u_min"), py::arg("v_min"),
             py::arg("u_max"), py::arg("v_max"),
             "Bounding box in pixel coordinates (auto edge-clip detection).")
        .def(py::init<>())
        .def_readwrite("u_min",   &BoundingBox::u_min)
        .def_readwrite("v_min",   &BoundingBox::v_min)
        .def_readwrite("u_max",   &BoundingBox::u_max)
        .def_readwrite("v_max",   &BoundingBox::v_max)
        .def_readwrite("clipped", &BoundingBox::clipped,
             "Clipped-edge bitmask (0xFF = auto-detect).")
        .def("__repr__", [](const BoundingBox& b) {
            return "<BoundingBox [" + std::to_string(b.u_min) + "," +
                   std::to_string(b.v_min) + "," + std::to_string(b.u_max) +
                   "," + std::to_string(b.v_max) + "]>";
        });

    // --- Intrinsics ----------------------------------------------------
    py::class_<Intrinsics>(m, "Intrinsics")
        .def(py::init<float, float, float, float, float, float>(),
             py::arg("fx"), py::arg("fy"),
             py::arg("cx"), py::arg("cy"),
             py::arg("width"), py::arg("height"))
        .def(py::init<>())
        .def_readwrite("fx",     &Intrinsics::fx)
        .def_readwrite("fy",     &Intrinsics::fy)
        .def_readwrite("cx",     &Intrinsics::cx)
        .def_readwrite("cy",     &Intrinsics::cy)
        .def_readwrite("width",  &Intrinsics::width)
        .def_readwrite("height", &Intrinsics::height);

    // --- ShapePrior ----------------------------------------------------
    py::class_<ShapePrior>(m, "ShapePrior")
        .def(py::init<float,float,float,float,float,float,bool>(),
             py::arg("mu_x"),    py::arg("mu_y"),    py::arg("mu_z"),
             py::arg("sigma_x"), py::arg("sigma_y"), py::arg("sigma_z"),
             py::arg("axis_aware") = true)
        .def(py::init<>())
        .def_readwrite("mu_x",    &ShapePrior::mu_x)
        .def_readwrite("mu_y",    &ShapePrior::mu_y)
        .def_readwrite("mu_z",    &ShapePrior::mu_z)
        .def_readwrite("sigma_x", &ShapePrior::sigma_x)
        .def_readwrite("sigma_y", &ShapePrior::sigma_y)
        .def_readwrite("sigma_z", &ShapePrior::sigma_z)
        .def_readwrite("axis_aware", &ShapePrior::axis_aware);

    // --- DetectorNoise -------------------------------------------------
    py::class_<DetectorNoise>(m, "DetectorNoise")
        .def(py::init<float>(), py::arg("sigma_px") = 2.0f)
        .def(py::init<>())
        .def_readwrite("sigma_px", &DetectorNoise::sigma_px);

    // --- RangeSensorConfig --------------------------------------------
    py::enum_<RangeConvention>(m, "RangeConvention",
         "How a ranging sensor reports distance to a surface.")
        .value("SLANT_RANGE",     RangeConvention::SLANT_RANGE,
               "Distance along the line of sight (hypotenuse). Most LiDAR/radar/ToF.")
        .value("CARTESIAN_DEPTH", RangeConvention::CARTESIAN_DEPTH,
               "Perpendicular distance to the image plane (z-depth). Intel RealSense, stereo.");

    py::class_<RangeSensorConfig>(m, "RangeSensorConfig",
         "Per-sensor calibration for ranging modalities (ToF, LiDAR, radar, etc.).")
        .def(py::init<>())
        .def(py::init<float, float, float, RangeConvention>(),
             py::arg("sigma_m"), py::arg("range_min_m") = 0.0f,
             py::arg("range_max_m") = 1.0e6f,
             py::arg("convention") = RangeConvention::CARTESIAN_DEPTH)
        .def_readwrite("sigma_m",     &RangeSensorConfig::sigma_m,
             "1-σ range measurement noise (m).")
        .def_readwrite("range_min_m", &RangeSensorConfig::range_min_m,
             "Measurements at or below this are discarded (m).")
        .def_readwrite("range_max_m", &RangeSensorConfig::range_max_m,
             "Measurements above this are discarded (m).")
        .def_readwrite("convention",  &RangeSensorConfig::convention,
             "Distance convention: CARTESIAN_DEPTH (default, z-depth) or SLANT_RANGE.")
        .def("__repr__", [](const RangeSensorConfig& s) {
            const char* conv = (s.convention == RangeConvention::CARTESIAN_DEPTH)
                             ? "cartesian" : "slant";
            return "<RangeSensorConfig sigma=" + std::to_string(s.sigma_m) +
                   "m range=[" + std::to_string(s.range_min_m) + "," +
                   std::to_string(s.range_max_m) + "] " + conv + ">";
        });

    // --- FrustumObservation --------------------------------------------
    py::class_<FrustumObservation>(m, "FrustumObservation")
        .def(py::init<>())
        .def_property("mu", [](const FrustumObservation& o) {
                return py::array_t<float>(3, o.mu);
            }, nullptr)
        .def_property("Sigma", [](const FrustumObservation& o) {
                return py::array_t<float>({3, 3}, o.Sigma);
            }, nullptr)
        .def_property("ray", [](const FrustumObservation& o) {
                return py::array_t<float>(3, o.ray);
            }, nullptr)
        .def_readonly("depth_est",   &FrustumObservation::depth_est)
        .def_readonly("depth_sigma", &FrustumObservation::depth_sigma)
        .def_readonly("depth_lo",    &FrustumObservation::depth_lo,
             "Geometric lower bound on depth (m); object can't be closer.")
        .def_readonly("depth_hi",    &FrustumObservation::depth_hi,
             "Geometric upper bound on depth (m); object can't be farther.")
        .def_readonly("score",       &FrustumObservation::score)
        .def_readonly("edge_valid",  &FrustumObservation::edge_valid)
        .def("__repr__", [](const FrustumObservation& o) {
            return "<FrustumObservation depth=" + std::to_string(o.depth_est) +
                   "m score=" + std::to_string(o.score) + ">";
        });

    // --- Single-detection API ------------------------------------------
    m.def("project_frustum",
          [](const BoundingBox& bb, const Intrinsics& K,
             const ShapePrior& prior, const DetectorNoise& noise) {
              return project_frustum(bb, K, prior, noise);
          },
          py::arg("bb"), py::arg("intrinsics"),
          py::arg("shape_prior"), py::arg("noise") = DetectorNoise{},
          "Project one bounding box to a camera-frame Gaussian frustum observation.");

    m.def("project_frustum",
          [](const BoundingBox& bb, const Intrinsics& K,
             const ShapePrior& prior, const DetectorNoise& noise,
             float range_m, const RangeSensorConfig& sensor) {
              return project_frustum(bb, K, prior, noise, range_m, sensor);
          },
          py::arg("bb"), py::arg("intrinsics"),
          py::arg("shape_prior"), py::arg("noise"),
          py::arg("range_m"), py::arg("sensor") = RangeSensorConfig{},
          "Project one bounding box with a range measurement to a Gaussian frustum observation.");

    m.def("transform_to_world",
          [](const FrustumObservation& obs, const F32Array& pose_arr) {
              auto info = pose_arr.request();
              if (info.ndim != 2 || info.shape[0] != 4 || info.shape[1] != 4)
                  throw std::invalid_argument("pose_mat must be (4,4) float32");
              return transform_to_world(obs, static_cast<const float*>(info.ptr));
          },
          py::arg("obs"), py::arg("pose_mat"),
          "Transform a FrustumObservation from camera frame to world frame.");

    // --- Batch numpy API -----------------------------------------------
    m.def("project_frustum_batch",
          &batch_numpy,
          py::arg("obs"),
          py::arg("intrinsics"),
          py::arg("img_size"),
          py::arg("sigma_px") = 2.0f,
          py::arg("sensor")   = py::none(),
          R"doc(
Project N bounding boxes to camera-frame Gaussian frustums (TBB parallel).

Parameters
----------
obs         : dict with keys:
  'boxes'   (N, 4) float32  [u_min, v_min, u_max, v_max]             REQUIRED
  'priors'  (N, 6) float32  [mu_x, mu_y, mu_z, sigma_x, sigma_y, sigma_z]  REQUIRED
  'ranges'  (N,)   float32  slant-range (m); NaN = no measurement     optional
  'clipped' (N,)   uint8    edge bitmask; 0xFF = auto-detect           optional
  'axis_aware' (N,) bool    per-detection axis-aware sizing            optional
intrinsics  : (4,)   float32  [fx, fy, cx, cy]
img_size    : (2,)   float32  [width, height]
sigma_px    : float  detector edge-localization noise (default 2.0)
sensor      : RangeSensorConfig or None (default None = angular-only)

Returns
-------
dict with keys:
  mu (N,3), Sigma (N,3,3), ray (N,3),
  depth_est (N,), depth_sigma (N,),
  depth_lo (N,), depth_hi (N,),   <- hard geometric bounds
  score (N,), edge_valid (N,)
          )doc");

    m.def("transform_to_world_batch",
          &transform_world_batch,
          py::arg("obs_dict"), py::arg("pose_mat"),
          "Transform a batch-result dict from camera frame to world frame.");

    // --- 3D oriented bounding-box API ----------------------------------
    //
    // project_frustum_3d(translation, half_extents, rotation, intrinsics,
    //                    body_sigmas=None, range_sigma_m=0.5)
    //
    // translation  : (3,) float32   object center in camera frame (m)
    // half_extents : (3,) float32   [a, b, c] half-sizes in body frame (m)
    // rotation     : (3,3) or (9,)  R_body_to_cam, row-major
    // intrinsics   : Intrinsics
    // body_sigmas  : (3,) float32   [σx, σy, σz] in body frame (m)
    //                               None → use range_sigma_m isotropically
    // range_sigma_m: float          fallback isotropic noise (m)
    m.def("project_frustum_3d",
          [](const F32Array&  trans_arr,
             const F32Array&  he_arr,
             const F32Array&  rot_arr,
             const Intrinsics& K,
             py::object        body_sigmas_obj,
             float             range_sigma_m) -> FrustumObservation
          {
              // translation (3,)
              auto ti = trans_arr.request();
              if (ti.size != 3)
                  throw std::invalid_argument("translation must have 3 elements");
              const float* t = static_cast<const float*>(ti.ptr);

              // half_extents (3,)
              auto hi = he_arr.request();
              if (hi.size != 3)
                  throw std::invalid_argument("half_extents must have 3 elements");
              const float* he = static_cast<const float*>(hi.ptr);

              // rotation (3,3) or (9,) — row-major
              auto ri = rot_arr.request();
              if (ri.size != 9)
                  throw std::invalid_argument("rotation must be (3,3) or (9,) with 9 elements");
              const float* rot = static_cast<const float*>(ri.ptr);

              if (body_sigmas_obj.is_none()) {
                  return project_frustum_3d(t, he, rot, K, range_sigma_m);
              } else {
                  F32Array bs_arr = body_sigmas_obj.cast<F32Array>();
                  auto bi2 = bs_arr.request();
                  if (bi2.size != 3)
                      throw std::invalid_argument("body_sigmas must have 3 elements");
                  const float* bs = static_cast<const float*>(bi2.ptr);
                  return project_frustum_3d(t, he, rot, K, bs);
              }
          },
          py::arg("translation"),
          py::arg("half_extents"),
          py::arg("rotation"),
          py::arg("intrinsics"),
          py::arg("body_sigmas")   = py::none(),
          py::arg("range_sigma_m") = 0.5f,
          R"doc(
Convert an oriented 3D bounding box to a FrustumObservation Gaussian.

Works with any 3D detector: LiDAR, radar, stereo, monocular-3D DNN, or
foundation models that produce oriented 3D bounding boxes.

Center convention
-----------------
``translation`` must be the **geometric center** of the box (nuScenes /
Waymo / OpenPCDet convention: corners symmetric about center).

KITTI-convention monocular detectors (SMOKE, MonoCon, PGD, CenterNet3D,
KITTI-convention monocular detectors (SMOKE, MonoCon, PGD, CenterNet3D, …)
output the **bottom-center** instead.  Convert first::

    center_cam = bottom_center + R @ [0, 0, h/2]

or use ``fg.from_3d_annotation(…, center_is_bottom=True)`` which handles
this automatically.

Parameters
----------
translation   : (3,) float32   Geometric center of the 3D BB in camera frame (m)
half_extents  : (3,) float32   [a, b, c] half-sizes in body frame (m)
rotation      : (3,3) or (9,)  R_body_to_cam row-major (body axes in camera frame)
intrinsics    : Intrinsics      Camera K (for ray computation)
body_sigmas   : (3,) float32   [σx, σy, σz] 1-σ position uncertainty in body frame.
                                None → use range_sigma_m isotropically.
range_sigma_m : float           Isotropic fallback noise when body_sigmas is None.

Returns
-------
FrustumObservation where:
  mu          = translation (camera-frame geometric center)
  Sigma       = R * diag(σx², σy², σz²) * Rᵀ  (anisotropic, camera-frame)
  depth_est   = ‖translation‖
  depth_sigma = 1-σ uncertainty along the camera ray
  depth_lo/hi = box extent ± sigma along ray
  score       = tightness (close to 1 for precise 3D detectors)
  edge_valid  = EDGE_ALL (image edges don't constrain 3D detectors)
          )doc");
}


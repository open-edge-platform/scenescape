// SPDX-FileCopyrightText: (C) 2015 OpenCV Foundation, all rights reserved.
// SPDX-FileCopyrightText: (C) 2019 - 2023 Intel Corp.
// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

#pragma once

#include <opencv2/core.hpp>
#include <opencv2/core/hal/hal.hpp>
#include <opencv2/core/utility.hpp>
#include <opencv2/tracking.hpp>
#include <opencv2/tracking/kalman_filters.hpp>
#include <typeinfo>

namespace cv {
namespace detail {
namespace tracking {
template <typename _Tp> bool inline callHalCholesky(_Tp *L, size_t lstep, int lsize);

template <> bool inline callHalCholesky<float>(float *L, size_t lstep, int lsize)
{
  return hal::Cholesky32f(L, lstep, lsize, NULL, 0, 0);
}

template <> bool inline callHalCholesky<double>(double *L, size_t lstep, int lsize)
{
  return hal::Cholesky64f(L, lstep, lsize, NULL, 0, 0);
}

template <typename _Tp> bool inline choleskyDecomposition(const _Tp *A, size_t astep, int asize, _Tp *L, size_t lstep)
{
  bool success = false;

  astep /= sizeof(_Tp);
  lstep /= sizeof(_Tp);

  for (int i = 0; i < asize; i++)
    for (int j = 0; j <= i; j++)
      L[i * lstep + j] = A[i * astep + j];

  success = callHalCholesky(L, lstep * sizeof(_Tp), asize);

  if (success)
  {
    for (int i = 0; i < asize; i++)
      for (int j = i + 1; j < asize; j++)
        L[i * lstep + j] = 0.0;
  }

  return success;
}

class UnscentedKalmanFilterMod : public UnscentedKalmanFilter
{
  int DP;       // dimensionality of the state vector
  int MP;       // dimensionality of the measurement vector
  int CP;       // dimensionality of the control vector
  int dataType; // type of elements of vectors and matrices

  Mat state;    // estimate of the system state (x*), DP x 1
  Mat errorCov; // estimate of the state cross-covariance matrix (P), DP x DP

  Mat processNoiseCov;     // process noise cross-covariance matrix (Q), DP x DP
  Mat measurementNoiseCov; // measurement noise cross-covariance matrix (R), MP x MP

  Ptr<UkfSystemModel>
    model; // object of the class containing functions for computing the next state and the measurement.

  // Parameters of algorithm
  double alpha; // parameter, default is 1e-3
  double k;     // parameter, default is 0
  double beta;  // parameter, default is 2.0

  double lambda;    // internal parameter, lambda = alpha*alpha*( DP + k ) - DP;
  double tmpLambda; // internal parameter, tmpLambda = alpha*alpha*( DP + k );

  // Auxillary members
  Mat measurementEstimate; // estimate of current measurement (y*), MP x 1

  Mat sigmaPoints; // set of sigma points ( x_i, i = 1..2*DP+1 ), DP x 2*DP+1

  Mat transitionSPFuncVals;  // set of state function values at sigma points ( f_i, i = 1..2*DP+1 ), DP x 2*DP+1
  Mat measurementSPFuncVals; // set of measurement function values at sigma points ( h_i, i = 1..2*DP+1 ), MP x 2*DP+1

  Mat transitionSPFuncValsCenter;  // set of state function values at sigma points minus estimate of state ( fc_i, i =
                                   // 1..2*DP+1 ), DP x 2*DP+1
  Mat measurementSPFuncValsCenter; // set of measurement function values at sigma points minus estimate of measurement (
                                   // hc_i, i = 1..2*DP+1 ), MP x 2*DP+1

  Mat Wm; // vector of weights for estimate mean, 2*DP+1 x 1
  Mat Wc; // matrix of weights for estimate covariance, 2*DP+1 x 2*DP+1

  Mat gain;  // Kalman gain matrix (K), DP x MP
  Mat xyCov; // estimate of the covariance between x* and y* (Sxy), DP x MP
  Mat yyCov; // estimate of the y* cross-covariance matrix (Syy), MP x MP

  Mat r; // zero vector of process noise for getting transitionSPFuncVals,
  Mat q; // zero vector of measurement noise for getting measurementSPFuncVals

  Mat getSigmaPoints(const Mat &mean, const Mat &covMatrix, double coef);

public:
  UnscentedKalmanFilterMod(const UnscentedKalmanFilterParams &params);
  ~UnscentedKalmanFilterMod();

  // perform prediction step
  // control - the optional control vector, CP x 1
  Mat predict(InputArray control = noArray()) override;

  // perform correction step
  // measurement - current measurement vector, MP x 1
  Mat correct(InputArray measurement) override;

  //  Get system parameters
  Mat getProcessNoiseCov() const override;
  Mat getMeasurementNoiseCov() const override;
  Mat getErrorCov() const override;
  Mat getMeasurementCov() const;

  void setStateAndCovariance(cv::Mat state, cv::Mat errorCov)
  {
    state = state.clone();
    errorCov = errorCov.clone();
  }

  //  Get the state estimate
  Mat getState() const override;
};

Ptr<UnscentedKalmanFilterMod> inline createUnscentedKalmanFilterMod(const UnscentedKalmanFilterParams &params)
{
  Ptr<UnscentedKalmanFilterMod> kfu(new UnscentedKalmanFilterMod(params));
  return kfu;
}
}
}
}

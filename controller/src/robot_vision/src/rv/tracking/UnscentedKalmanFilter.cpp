// SPDX-FileCopyrightText: (C) 2015 OpenCV Foundation, all rights reserved.
// SPDX-FileCopyrightText: (C) 2019 - 2023 Intel Corp.
// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/UnscentedKalmanFilter.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <mutex>

#include <opencv2/core.hpp>
#include <opencv2/tracking/kalman_filters.hpp>

namespace cv {
namespace detail {
namespace tracking {

namespace {

// Smallest eigenvalue a repaired covariance keeps; far above double rounding and the Cholesky pivot threshold.
constexpr double kMinEigenvalue = 1e-9;

// Lower Cholesky factor of covMatrix; false if it is not positive definite.
bool choleskyFactor(const Mat &covMatrix, Mat &covMatrixL)
{
  covMatrixL = covMatrix.clone();
  return choleskyDecomposition<double>(
    covMatrix.ptr<double>(), covMatrix.step, covMatrix.rows, covMatrixL.ptr<double>(), covMatrixL.step);
}

// Nearest symmetric positive definite matrix: symmetrize and raise the eigenvalues to a small floor.
Mat repairCovariance(const Mat &covMatrix)
{
  const Mat symmetric = 0.5 * (covMatrix + covMatrix.t());
  Mat eigenvalues;
  Mat eigenvectors; // one eigenvector per row
  eigen(symmetric, eigenvalues, eigenvectors);
  double largest = 0.0;
  minMaxLoc(eigenvalues, nullptr, &largest);
  const Mat raised = max(eigenvalues, std::max(kMinEigenvalue, largest * 1e-12));
  return eigenvectors.t() * Mat::diag(raised) * eigenvectors;
}

// Diagonal Cholesky factor from the covariance diagonal; non-finite or tiny entries use kMinEigenvalue.
// Rewrites covMatrix to that finite diagonal so the caller's P is not left half-factorised or non-finite.
Mat diagonalFactor(Mat &covMatrix)
{
  Mat deviations(covMatrix.rows, 1, CV_64F);
  for (int i = 0; i < covMatrix.rows; ++i)
  {
    const double entry = covMatrix.at<double>(i, i);
    const double variance = (std::isfinite(entry) && entry > kMinEigenvalue) ? entry : kMinEigenvalue;
    deviations.at<double>(i) = std::sqrt(variance);
  }
  Mat variances;
  multiply(deviations, deviations, variances);
  covMatrix = Mat::diag(variances);
  return Mat::diag(deviations);
}

} // namespace

UnscentedKalmanFilterMod::UnscentedKalmanFilterMod(const UnscentedKalmanFilterParams &params)
{
  alpha = params.alpha;
  beta = params.beta;
  k = params.k;

  CV_Assert(params.DP > 0 && params.MP > 0);
  // Double precision only: float32 rounding would lose the eigenvalue floor of the covariance repair.
  CV_Assert(params.dataType == CV_64F);
  DP = params.DP;
  MP = params.MP;
  CP = std::max(params.CP, 0);
  dataType = params.dataType;

  model = params.model;

  CV_Assert(params.stateInit.cols == 1 && params.stateInit.rows == DP);
  CV_Assert(params.errorCovInit.cols == DP && params.errorCovInit.rows == DP);
  state = params.stateInit.clone();
  errorCov = params.errorCovInit.clone();

  CV_Assert(params.processNoiseCov.cols == DP && params.processNoiseCov.rows == DP);
  CV_Assert(params.measurementNoiseCov.cols == MP && params.measurementNoiseCov.rows == MP);
  processNoiseCov = params.processNoiseCov.clone();
  measurementNoiseCov = params.measurementNoiseCov.clone();

  measurementEstimate = Mat::zeros(MP, 1, dataType);

  q = Mat::zeros(DP, 1, dataType);
  r = Mat::zeros(MP, 1, dataType);

  gain = Mat::zeros(DP, DP, dataType);

  transitionSPFuncVals = Mat::zeros(DP, 2 * DP + 1, dataType);
  measurementSPFuncVals = Mat::zeros(MP, 2 * DP + 1, dataType);

  transitionSPFuncValsCenter = Mat::zeros(DP, 2 * DP + 1, dataType);
  measurementSPFuncValsCenter = Mat::zeros(MP, 2 * DP + 1, dataType);

  lambda = alpha * alpha * (DP + k) - DP;
  tmpLambda = lambda + DP;

  double tmp2Lambda = 0.5 / tmpLambda;

  Wm = tmp2Lambda * Mat::ones(2 * DP + 1, 1, dataType);
  Wc = tmp2Lambda * Mat::eye(2 * DP + 1, 2 * DP + 1, dataType);

  Wm.at<double>(0, 0) = lambda / tmpLambda;
  Wc.at<double>(0, 0) = lambda / tmpLambda + 1.0 - alpha * alpha + beta;
}

UnscentedKalmanFilterMod::~UnscentedKalmanFilterMod()
{
  state.release();
  errorCov.release();

  processNoiseCov.release();
  measurementNoiseCov.release();

  measurementEstimate.release();

  sigmaPoints.release();

  transitionSPFuncVals.release();
  measurementSPFuncVals.release();

  transitionSPFuncValsCenter.release();
  measurementSPFuncValsCenter.release();

  Wm.release();
  Wc.release();

  gain.release();
  xyCov.release();
  yyCov.release();

  r.release();
  q.release();
}

Mat UnscentedKalmanFilterMod::getSigmaPoints(const Mat &mean, Mat &covMatrix, double coef)
{
  // x_0 = mean
  // x_i = mean + coef * cholesky( covMatrix ), i = 1..n
  // x_(i+n) = mean - coef * cholesky( covMatrix ), i = 1..n

  int n = mean.rows;
  Mat points = repeat(mean, 1, 2 * n + 1);

  // covMatrixL = cholesky( covMatrix ). A failed factorisation leaves a half-factorised matrix; non-finite P can
  // also make Cholesky look successful with NaN entries. Repair finite indefinite P, else fall back to a diagonal
  // factor — never draw sigma points from a bad factor.
  Mat covMatrixL;
  const bool finite = checkRange(covMatrix);
  if (!finite || !choleskyFactor(covMatrix, covMatrixL))
  {
    static std::once_flag warned;
    std::call_once(warned, [] {
      std::cerr << "UnscentedKalmanFilterMod: covariance not positive definite, repaired before drawing sigma points\n";
    });
    if (finite)
    {
      covMatrix = repairCovariance(covMatrix);
      if (!choleskyFactor(covMatrix, covMatrixL))
      {
        covMatrixL = diagonalFactor(covMatrix);
      }
    }
    else
    {
      covMatrixL = diagonalFactor(covMatrix);
    }
  }

  covMatrixL = coef * covMatrixL;

  Mat p_plus = points(Rect(1, 0, n, n));
  Mat p_minus = points(Rect(n + 1, 0, n, n));

  add(p_plus, covMatrixL, p_plus);
  subtract(p_minus, covMatrixL, p_minus);

  return points;
}

Mat UnscentedKalmanFilterMod::predict(InputArray _control)
{
  Mat control = _control.getMat();
  // get sigma points from x* and P
  sigmaPoints = getSigmaPoints(state, errorCov, sqrt(tmpLambda));

  // compute f-function values at sigma points
  // f_i = f(x_i, control, 0), i = 0..2*DP
  Mat x, fx;
  for (int i = 0; i < 2 * DP + 1; i++)
  {
    x = sigmaPoints(Rect(i, 0, 1, DP));
    fx = transitionSPFuncVals(Rect(i, 0, 1, DP));
    model->stateConversionFunction(x, control, q, fx);
  }
  // compute the estimate of state as mean f-function value at sigma point
  // x* = SUM_{i=0}^{2*DP}( Wm[i]*f_i )
  state = transitionSPFuncVals * Wm;

  // compute f-function values at sigma points minus estimate of state
  // fc_i = f_i - x*, i = 0..2*DP
  subtract(transitionSPFuncVals, repeat(state, 1, 2 * DP + 1), transitionSPFuncValsCenter);

  // compute the estimate of the state cross-covariance matrix
  // P = SUM_{i=0}^{2*DP}( Wc[i]*fc_i*fc_i.t ) + Q
  errorCov = transitionSPFuncValsCenter * Wc * transitionSPFuncValsCenter.t() + processNoiseCov;

  // This poart has been moved from the predict function to allow the calculation of the yyCov matrix (measurement covariance)
  // get sigma points from x* and P
  sigmaPoints = getSigmaPoints(state, errorCov, sqrt(tmpLambda));

  // compute h-function values at sigma points
  // h_i = h(x_i, 0), i = 0..2*DP
  Mat hx;
  for (int i = 0; i < 2 * DP + 1; i++)
  {
    x = sigmaPoints(Rect(i, 0, 1, DP));
    hx = measurementSPFuncVals(Rect(i, 0, 1, MP));
    model->measurementFunction(x, r, hx);
  }

  // compute the estimate of measurement as mean h-function value at sigma point
  // y* = SUM_{i=0}^{2*DP}( Wm[i]*h_i )
  measurementEstimate = measurementSPFuncVals * Wm;

  // compute h-function values at sigma points minus estimate of state
  // hc_i = h_i - y*, i = 0..2*DP
  subtract(measurementSPFuncVals, repeat(measurementEstimate, 1, 2 * DP + 1), measurementSPFuncValsCenter);

  // compute the estimate of the y* cross-covariance matrix
  // Syy = SUM_{i=0}^{2*DP}( Wc[i]*hc_i*hc_i.t ) + R
  yyCov = measurementSPFuncValsCenter * Wc * measurementSPFuncValsCenter.t() + measurementNoiseCov;


  return state.clone();
}

Mat UnscentedKalmanFilterMod::correct(InputArray _measurement)
{
  Mat measurement = _measurement.getMat();
  // Cross-covariance must use the same predicted-state sigma points as Syy.
  // Using transitionSPFuncValsCenter (prior→predict) here left velocity weakly
  // observable and kept P_v stuck near its isotropic init.
  Mat predictedStateSPCenter;
  subtract(sigmaPoints, repeat(state, 1, 2 * DP + 1), predictedStateSPCenter);
  xyCov = predictedStateSPCenter * Wc * measurementSPFuncValsCenter.t();

  // compute the Kalman gain matrix
  // K = Sxy * Syy^(-1)
  gain = xyCov * yyCov.inv(DECOMP_SVD);

  // compute the corrected estimate of state
  // x* = x* + K*(y - y*), y - current measurement
  state = state + gain * (measurement - measurementEstimate);

  // compute the corrected estimate of the state cross-covariance matrix
  // P = P - K*Sxy.t
  errorCov = errorCov - gain * xyCov.t();

  return state.clone();
}

Mat UnscentedKalmanFilterMod::correct(InputArray _measurement, const std::vector<int> &observedRows)
{
  if (static_cast<int>(observedRows.size()) == MP)
  {
    return correct(_measurement);
  }

  // Same update as correct(measurement), restricted to the observed rows of y, y* and Syy.
  Mat measurement = _measurement.getMat();
  Mat predictedStateSPCenter;
  subtract(sigmaPoints, repeat(state, 1, 2 * DP + 1), predictedStateSPCenter);
  xyCov = predictedStateSPCenter * Wc * selectRows(measurementSPFuncValsCenter, observedRows).t();

  gain = xyCov * selectBlock(yyCov, observedRows).inv(DECOMP_SVD);
  state = state + gain * (selectRows(measurement, observedRows) - selectRows(measurementEstimate, observedRows));
  errorCov = errorCov - gain * xyCov.t();

  return state.clone();
}

Mat UnscentedKalmanFilterMod::getProcessNoiseCov() const
{
  return processNoiseCov.clone();
}

Mat UnscentedKalmanFilterMod::getMeasurementNoiseCov() const
{
  return measurementNoiseCov.clone();
}

Mat UnscentedKalmanFilterMod::getMeasurementCov() const
{
  return yyCov.clone();
}

Mat UnscentedKalmanFilterMod::getErrorCov() const
{
  return errorCov.clone();
}

Mat UnscentedKalmanFilterMod::getState() const
{
  return state.clone();
}

} // tracking
} // cv
}

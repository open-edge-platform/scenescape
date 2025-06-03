/*M///////////////////////////////////////////////////////////////////////////////////////
 //
 //  IMPORTANT: READ BEFORE DOWNLOADING, COPYING, INSTALLING OR USING.
 //
 //  By downloading, copying, installing or using the software you agree to this license.
 //  If you do not agree to this license, do not download, install,
 //  copy or use the software.
 //
 //
 //                           License Agreement
 //                For Open Source Computer Vision Library
 //
.// Copyright (C) 2019-2023 Intel Corp.
 // Copyright (C) 2015, OpenCV Foundation, all rights reserved.
 // Third party copyrights are property of their respective owners.
 //
 // Redistribution and use in source and binary forms, with or without modification,
 // are permitted provided that the following conditions are met:
 //
 //   * Redistribution's of source code must retain the above copyright notice,
 //     this list of conditions and the following disclaimer.
 //
 //   * Redistribution's in binary form must reproduce the above copyright notice,
 //     this list of conditions and the following disclaimer in the documentation
 //     and/or other materials provided with the distribution.
 //
 //   * The name of the copyright holders may not be used to endorse or promote products
 //     derived from this software without specific prior written permission.
 //
 // This software is provided by the copyright holders and contributors "as is" and
 // any express or implied warranties, including, but not limited to, the implied
 // warranties of merchantability and fitness for a particular purpose are disclaimed.
 // In no event shall the Intel Corporation or contributors be liable for any direct,
 // indirect, incidental, special, exemplary, or consequential damages
 // (including, but not limited to, procurement of substitute goods or services;
 // loss of use, data, or profits; or business interruption) however caused
 // and on any theory of liability, whether in contract, strict liability,
 // or tort (including negligence or otherwise) arising in any way out of
 // the use of this software, even if advised of the possibility of such damage.
 //
 //M*/

#include "rv/tracking/UnscentedKalmanFilter.hpp"

#include <opencv2/core.hpp>
#include <opencv2/tracking/kalman_filters.hpp>

namespace cv {
namespace detail {
namespace tracking {

UnscentedKalmanFilterMod::UnscentedKalmanFilterMod(const UnscentedKalmanFilterParams &params)
{
  alpha = params.alpha;
  beta = params.beta;
  k = params.k;

  CV_Assert(params.DP > 0 && params.MP > 0);
  CV_Assert(params.dataType == CV_32F || params.dataType == CV_64F);
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

  if (dataType == CV_64F)
  {
    Wm.at<double>(0, 0) = lambda / tmpLambda;
    Wc.at<double>(0, 0) = lambda / tmpLambda + 1.0 - alpha * alpha + beta;
  }
  else
  {
    Wm.at<float>(0, 0) = (float)(lambda / tmpLambda);
    Wc.at<float>(0, 0) = (float)(lambda / tmpLambda + 1.0 - alpha * alpha + beta);
  }
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

Mat UnscentedKalmanFilterMod::getSigmaPoints(const Mat &mean, const Mat &covMatrix, double coef)
{
  // x_0 = mean
  // x_i = mean + coef * cholesky( covMatrix ), i = 1..n
  // x_(i+n) = mean - coef * cholesky( covMatrix ), i = 1..n

  int n = mean.rows;
  Mat points = repeat(mean, 1, 2 * n + 1);

  Mat covMatrixL = covMatrix.clone();

  // covMatrixL = cholesky( covMatrix )
  if (dataType == CV_64F)
    choleskyDecomposition<double>(
      covMatrix.ptr<double>(), covMatrix.step, covMatrix.rows, covMatrixL.ptr<double>(), covMatrixL.step);
  else if (dataType == CV_32F)
    choleskyDecomposition<float>(
      covMatrix.ptr<float>(), covMatrix.step, covMatrix.rows, covMatrixL.ptr<float>(), covMatrixL.step);

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
  // compute the estimate of the covariance between x* and y*
  // Sxy = SUM_{i=0}^{2*DP}( Wc[i]*fc_i*hc_i.t )
  xyCov = transitionSPFuncValsCenter * Wc * measurementSPFuncValsCenter.t();

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

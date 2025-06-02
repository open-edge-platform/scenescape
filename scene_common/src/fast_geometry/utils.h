
/*
 * Copyright (C) 2024 Intel Corporation
 *
 * This software and the related documents are Intel copyrighted materials,
 * and your use of them is governed by the express license under which they
 * were provided to you ("License"). Unless the License provides otherwise,
 * you may not use, modify, copy, publish, distribute, disclose or transmit
 * this software or the related documents without Intel's prior written permission.
 *
 * This software and the related documents are provided as is, with no express
 * or implied warranties, other than those that are expressly stated in the License.
 */

#ifndef UTILS_H
#define UTILS_H

#include <cmath>

template<class T>
  inline T magnitude(T a, T b, T c)
{
    double sum;
    sum = (a*a) + (b*b) + (c*c);
    return (T) sqrt(sum);
}
template<class T>
  inline T magnitude(T a, T b)
{
    double sum;
    sum = (a*a) + (b*b);
    return (T) sqrt(sum);
}

#endif

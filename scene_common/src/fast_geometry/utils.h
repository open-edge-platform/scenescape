/*
 * SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
 * SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
 * This file is licensed under the Limited Edge Software Distribution License Agreement.
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

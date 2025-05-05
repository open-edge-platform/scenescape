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

#ifndef REGION_H
#define REGION_H

#include <string>
#include <map>
#include <vector>

class Polygon
{
  public:

    Polygon(const std::vector<std::pair<double, double>>& vertices);

    std::vector<std::pair<double, double>> getVertices() const ;

    // Method to check if a point is inside the region
    bool isPointInside(double px, double py) const ;

  private:
    std::vector<std::pair<double, double>> vertices;
    int region_type;
};


#endif

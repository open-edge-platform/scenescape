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

#include <stdexcept>
#include <sstream>

#include "polygon.h"

Polygon::Polygon(const std::vector<std::pair<double, double>>& vertices)
    : vertices(vertices)
{
}
std::vector<std::pair<double, double>> Polygon::getVertices() const
{
    return this->vertices;
}
bool Polygon::isPointInside(double px, double py) const
{
    int n = this->vertices.size();
    bool inside = false;

    for (int i = 0, j = n - 1; i < n; j = i++)
    {
        double xi = this->vertices[i].first;
        double yi = this->vertices[i].second;
        double xj = this->vertices[j].first;
        double yj = this->vertices[j].second;

        bool intersect = ((yi > py) != (yj > py))
                          && px < ((xj - xi) * (py - yi) / (yj - yi) + xi);
        if (intersect)
        {
            inside = !inside;
        }
    }
    return inside;
}


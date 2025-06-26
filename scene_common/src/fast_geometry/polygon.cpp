// SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

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


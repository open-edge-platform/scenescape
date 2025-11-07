#pragma once
#include <ostream>
#include <string>

struct CenterOfMass {
    double x, y, width, height;
};

struct BoundingBoxPx {
    int x, y, width, height;
};

struct Person {
    std::string category;
    double confidence;
    CenterOfMass center_of_mass;
    BoundingBoxPx bounding_box_px;
    int id;
};

// Stream output operators
std::ostream& operator<<(std::ostream& os, const CenterOfMass& com);
std::ostream& operator<<(std::ostream& os, const BoundingBoxPx& bbox);
std::ostream& operator<<(std::ostream& os, const Person& person);

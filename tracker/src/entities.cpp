#include "entities.h"
#include <iomanip>

std::ostream& operator<<(std::ostream& os, const CenterOfMass& com) {
    os << "CenterOfMass(x=" << com.x << ", y=" << com.y << ", w=" << com.width
       << ", h=" << com.height << ")";
    return os;
}

std::ostream& operator<<(std::ostream& os, const BoundingBoxPx& bbox) {
    os << "BoundingBox[x=" << bbox.x << ", y=" << bbox.y << ", w=" << bbox.width
       << ", h=" << bbox.height << "]";
    return os;
}

std::ostream& operator<<(std::ostream& os, const Person& person) {
    os << "Person{\n"
       << "  id: " << person.id << "\n"
       << "  category: " << person.category << "\n"
       << "  confidence: " << std::fixed << std::setprecision(4) << person.confidence << "\n"
       << "  center_of_mass: " << person.center_of_mass << "\n"
       << "  bounding_box_px: " << person.bounding_box_px << "\n"
       << "}";
    return os;
}

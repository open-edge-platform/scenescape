// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <string>
#include <unordered_map>

namespace rv {
namespace tracking {
namespace metadata_fusion {

inline constexpr char ValuePrefix[] = "metadata.";
inline constexpr char ConfidencePrefix[] = "metadata_confidence.";
inline constexpr char ProvenancePrefix[] = "metadata_provenance.";
inline constexpr char TransientPrefix[] = "metadata_transient.";

inline void clearTransientMetadata(std::unordered_map<std::string, std::string> &attributes)
{
  for (auto attribute = attributes.begin(); attribute != attributes.end();)
  {
    if (attribute->first.rfind(TransientPrefix, 0) != 0)
    {
      ++attribute;
      continue;
    }
    const auto field = attribute->first.substr(std::char_traits<char>::length(TransientPrefix));
    attributes.erase(ValuePrefix + field);
    attributes.erase(ConfidencePrefix + field);
    attributes.erase(ProvenancePrefix + field);
    attribute = attributes.erase(attribute);
  }
}

} // namespace metadata_fusion
} // namespace tracking
} // namespace rv
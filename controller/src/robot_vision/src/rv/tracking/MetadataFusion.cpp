// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "rv/tracking/MetadataFusion.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <string_view>

namespace rv {
namespace tracking {
namespace metadata_fusion {
namespace {

constexpr std::array<const char *, 4> MetadataPrefixes
  = {ValuePrefix, ConfidencePrefix, ProvenancePrefix, TransientPrefix};
constexpr std::array<const char *, 2> CompanionPrefixes = {ProvenancePrefix, TransientPrefix};

bool startsWith(const std::string &value, std::string_view prefix)
{
  return value.compare(0, prefix.size(), prefix) == 0;
}

bool hasCompanions(const TrackedObject &object)
{
  return std::any_of(object.attributes.begin(), object.attributes.end(), [](const auto &attribute) {
    return std::any_of(CompanionPrefixes.begin(), CompanionPrefixes.end(), [&](const auto prefix) {
      return startsWith(attribute.first, prefix);
    });
  });
}

std::optional<double> metadataConfidence(const TrackedObject &object, const std::string &field)
{
  const auto confidence = object.attributes.find(ConfidencePrefix + field);
  if (confidence == object.attributes.end())
  {
    return std::nullopt;
  }
  double value{};
  const auto *begin = confidence->second.data();
  const auto *end = begin + confidence->second.size();
  const auto [ptr, error] = std::from_chars(begin, end, value);
  if (error != std::errc{} || ptr != end || !std::isfinite(value))
  {
    return std::nullopt;
  }
  return value;
}

void copyMetadataCompanions(const TrackedObject &source,
                            const std::string &field,
                            TrackedObject &destination,
                            bool companionsPresent)
{
  if (!companionsPresent)
  {
    return;
  }
  for (const auto prefix : CompanionPrefixes)
  {
    const std::string key = prefix + field;
    const auto value = source.attributes.find(key);
    if (value != source.attributes.end())
    {
      destination.attributes[key] = value->second;
    }
    else
    {
      destination.attributes.erase(key);
    }
  }
}

void clearMetadataAttributes(TrackedObject &object)
{
  for (auto attribute = object.attributes.begin(); attribute != object.attributes.end();)
  {
    const bool metadata = std::any_of(MetadataPrefixes.begin(), MetadataPrefixes.end(), [&](const auto prefix) {
      return startsWith(attribute->first, prefix);
    });
    if (metadata)
    {
      attribute = object.attributes.erase(attribute);
    }
    else
    {
      ++attribute;
    }
  }
}

} // namespace

bool shouldReplace(bool winnerExists,
                   const std::optional<double> &candidateConfidence,
                   size_t candidateCameraIndex,
                   const std::optional<double> &winnerConfidence,
                   size_t winnerCameraIndex)
{
  if (!winnerExists)
  {
    return true;
  }
  if (candidateConfidence && !winnerConfidence)
  {
    return true;
  }
  if (!candidateConfidence && winnerConfidence)
  {
    return false;
  }
  if (candidateConfidence && winnerConfidence)
  {
    return *candidateConfidence > *winnerConfidence
      || (*candidateConfidence == *winnerConfidence && candidateCameraIndex > winnerCameraIndex);
  }
  return candidateCameraIndex > winnerCameraIndex;
}

void clearTransientMetadata(std::unordered_map<std::string, std::string> &attributes)
{
  for (auto attribute = attributes.begin(); attribute != attributes.end();)
  {
    if (!startsWith(attribute->first, TransientPrefix))
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

void fuseMetadata(const std::vector<std::pair<size_t, size_t>> &matches,
                  const std::vector<std::vector<TrackedObject>> &objectsPerCamera,
                  TrackedObject &measurement)
{
  struct Winner
  {
    std::optional<double> confidence;
    size_t cameraIndex;
  };
  std::unordered_map<std::string, Winner> winners;
  clearMetadataAttributes(measurement);
  bool destinationHasCompanions = false;
  for (const auto &[cameraIndex, objectIndex] : matches)
  {
    const auto &object = objectsPerCamera[cameraIndex][objectIndex];
    const bool sourceHasCompanions = hasCompanions(object);
    for (const auto &[key, value] : object.attributes)
    {
      if (!startsWith(key, ValuePrefix))
      {
        continue;
      }
      const std::string field = key.substr(std::char_traits<char>::length(ValuePrefix));
      const auto confidence = metadataConfidence(object, field);
      const auto winner = winners.find(field);
      const bool winnerExists = winner != winners.end();
      const std::optional<double> winnerConfidence = winnerExists ? winner->second.confidence : std::optional<double>{};
      const size_t winnerCameraIndex = winnerExists ? winner->second.cameraIndex : 0;
      if (!shouldReplace(winnerExists, confidence, cameraIndex, winnerConfidence, winnerCameraIndex))
      {
        continue;
      }
      measurement.attributes[key] = value;
      copyMetadataCompanions(object, field, measurement, sourceHasCompanions || destinationHasCompanions);
      const std::string confidenceKey = ConfidencePrefix + field;
      if (confidence)
      {
        measurement.attributes[confidenceKey] = object.attributes.at(confidenceKey);
      }
      else
      {
        measurement.attributes.erase(confidenceKey);
      }
      winners[field] = Winner{confidence, cameraIndex};
    }
    destinationHasCompanions = destinationHasCompanions || sourceHasCompanions;
  }
}

void mergeHistoricalMetadata(const TrackedObject &track, TrackedObject &measurement)
{
  const bool companionsPresent = hasCompanions(track) || hasCompanions(measurement);
  for (const auto &[key, value] : track.attributes)
  {
    if (!startsWith(key, ValuePrefix))
    {
      continue;
    }
    const std::string field = key.substr(std::char_traits<char>::length(ValuePrefix));
    const std::string transientKey = TransientPrefix + field;
    if (track.attributes.find(transientKey) != track.attributes.end()
        || measurement.attributes.find(transientKey) != measurement.attributes.end())
    {
      continue;
    }
    const auto storedConfidence = metadataConfidence(track, field);
    const auto currentValue = measurement.attributes.find(key);
    const auto currentConfidence = metadataConfidence(measurement, field);
    const bool currentIsHigher = currentValue != measurement.attributes.end() && currentConfidence
      && (!storedConfidence || *currentConfidence > *storedConfidence);
    if (currentIsHigher)
    {
      continue;
    }
    measurement.attributes[key] = value;
    copyMetadataCompanions(track, field, measurement, companionsPresent);
    const std::string confidenceKey = ConfidencePrefix + field;
    if (storedConfidence)
    {
      measurement.attributes[confidenceKey] = track.attributes.at(confidenceKey);
    }
    else
    {
      measurement.attributes.erase(confidenceKey);
    }
  }
}

} // namespace metadata_fusion
} // namespace tracking
} // namespace rv

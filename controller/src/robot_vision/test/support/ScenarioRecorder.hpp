// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <gtest/gtest.h>
#include <opencv2/core.hpp>

#include <rv/tracking/CAModel.hpp>
#include <rv/tracking/CPModel.hpp>
#include <rv/tracking/CTRVModel.hpp>
#include <rv/tracking/CVModel.hpp>

#include "Scenario.hpp"

namespace rv::tracking::test {

// Compact JSON for the scenario files: shortest round-trip doubles, NaN and infinity as null.
class JsonWriter
{
public:
  JsonWriter &beginObject()
  {
    return open('{');
  }
  JsonWriter &endObject()
  {
    return close('}');
  }
  JsonWriter &beginArray()
  {
    return open('[');
  }
  JsonWriter &endArray()
  {
    return close(']');
  }

  JsonWriter &key(std::string_view name)
  {
    separate();
    writeString(name);
    mOut += ':';
    mAfterKey = true;
    return *this;
  }

  JsonWriter &value(double number)
  {
    separate();
    if (!std::isfinite(number))
    {
      mOut += "null";
      return *this;
    }
    std::array<char, 32> buffer{};
    const auto result = std::to_chars(buffer.data(), buffer.data() + buffer.size(), number);
    mOut.append(buffer.data(), result.ptr);
    return *this;
  }

  JsonWriter &value(int number)
  {
    separate();
    mOut += std::to_string(number);
    return *this;
  }

  JsonWriter &value(std::string_view text)
  {
    separate();
    writeString(text);
    return *this;
  }

  JsonWriter &value(const char *text)
  {
    return value(std::string_view(text));
  }

  JsonWriter &null()
  {
    separate();
    mOut += "null";
    return *this;
  }

  // Column vectors as a flat array, other matrices as an array of rows; empty matrices as null.
  JsonWriter &value(const cv::Mat &matrix)
  {
    if (matrix.empty())
    {
      return null();
    }
    cv::Mat values;
    matrix.convertTo(values, CV_64F);
    if (values.cols == 1)
    {
      beginArray();
      for (int row = 0; row < values.rows; ++row)
      {
        value(values.at<double>(row, 0));
      }
      return endArray();
    }
    beginArray();
    for (int row = 0; row < values.rows; ++row)
    {
      beginArray();
      for (int col = 0; col < values.cols; ++col)
      {
        value(values.at<double>(row, col));
      }
      endArray();
    }
    return endArray();
  }

  template <int Rows, int Cols> JsonWriter &value(const cv::Matx<double, Rows, Cols> &matrix)
  {
    return value(cv::Mat(matrix));
  }

  template <std::size_t N> JsonWriter &value(const std::array<double, N> &numbers)
  {
    beginArray();
    for (double number : numbers)
    {
      value(number);
    }
    return endArray();
  }

  // Inserts an already serialized JSON value.
  JsonWriter &raw(std::string_view json)
  {
    separate();
    mOut += json;
    return *this;
  }

  const std::string &str() const
  {
    return mOut;
  }

private:
  JsonWriter &open(char bracket)
  {
    separate();
    mOut += bracket;
    mFirst.push_back(true);
    return *this;
  }

  JsonWriter &close(char bracket)
  {
    mOut += bracket;
    mFirst.pop_back();
    return *this;
  }

  void separate()
  {
    if (mAfterKey)
    {
      mAfterKey = false;
      return;
    }
    if (!mFirst.empty())
    {
      if (!mFirst.back())
      {
        mOut += ',';
      }
      mFirst.back() = false;
    }
  }

  void writeString(std::string_view text)
  {
    mOut += '"';
    for (const char c : text)
    {
      switch (c)
      {
        case '"':
          mOut += "\\\"";
          break;
        case '\\':
          mOut += "\\\\";
          break;
        case '\n':
          mOut += "\\n";
          break;
        case '\r':
          mOut += "\\r";
          break;
        case '\t':
          mOut += "\\t";
          break;
        default:
          if (static_cast<unsigned char>(c) < 0x20)
          {
            std::array<char, 8> escaped{};
            std::snprintf(escaped.data(), escaped.size(), "\\u%04x", static_cast<unsigned>(c));
            mOut += escaped.data();
          }
          else
          {
            mOut += c;
          }
      }
    }
    mOut += '"';
  }

  std::string mOut;
  std::vector<bool> mFirst;
  bool mAfterKey = false;
};

inline std::int64_t toMicroseconds(double seconds)
{
  return std::llround(seconds * 1e6);
}

// ISO 8601 UTC with microseconds, counted from the system_clock epoch like atSeconds().
inline std::string isoTimestamp(std::int64_t microsecondsSinceEpoch)
{
  using namespace std::chrono;
  const sys_time<microseconds> time{microseconds{microsecondsSinceEpoch}};
  const auto day = floor<days>(time);
  const year_month_day date{day};
  const hh_mm_ss clock{time - day};
  std::array<char, 40> buffer{};
  std::snprintf(buffer.data(),
                buffer.size(),
                "%04d-%02u-%02uT%02d:%02d:%02d.%06ldZ",
                static_cast<int>(date.year()),
                static_cast<unsigned>(date.month()),
                static_cast<unsigned>(date.day()),
                static_cast<int>(clock.hours().count()),
                static_cast<int>(clock.minutes().count()),
                static_cast<int>(clock.seconds().count()),
                static_cast<long>(clock.subseconds().count()));
  return buffer.data();
}

// Rotation about z as a quaternion [x, y, z, w].
inline std::array<double, 4> yawQuaternion(double yaw)
{
  return {0.0, 0.0, std::sin(0.5 * yaw), std::cos(0.5 * yaw)};
}

// Writes one scenario as JSONL files for tools/tracker/evaluation/visualization:
//   groundtruth.jsonl  canonical ground truth with size, rotation, velocity and a "truth" object
//   detections.jsonl   canonical camera-data frames with the 3D detections fed to FilterRun, one frame per sensor id
//   tracks.jsonl       canonical tracker output with the estimate after every FilterRun step
//   estimator.jsonl    one "config" line per track, then one "step" line per FilterRun step
// Records only when RV_SCENARIO_DIR is set. Files go to $RV_SCENARIO_DIR/<Suite>.<Test>/<caseName>/ and are written
// on destruction. Detection ids are the FilterRun track id. Reads private estimator members (tests build with
// -fno-access-control).
class ScenarioRecorder : public FilterRunObserver
{
public:
  static constexpr const char *kEnvironmentVariable = "RV_SCENARIO_DIR";

  explicit ScenarioRecorder(std::string_view caseName = {})
    : ScenarioRecorder(caseName, rootFromEnvironment())
  {
  }

  // An empty root disables recording.
  ScenarioRecorder(std::string_view caseName, const std::filesystem::path &root)
  {
    if (root.empty())
    {
      return;
    }
    mSceneName = currentTestName();
    mDirectory = root / mSceneName;
    if (!caseName.empty())
    {
      mDirectory /= sanitize(caseName);
      mSceneName += "/" + sanitize(caseName);
    }
  }

  ~ScenarioRecorder() override
  {
    write();
  }

  ScenarioRecorder(const ScenarioRecorder &) = delete;
  ScenarioRecorder &operator=(const ScenarioRecorder &) = delete;

  bool enabled() const
  {
    return !mDirectory.empty();
  }

  const std::filesystem::path &directory() const
  {
    return mDirectory;
  }

  void truth(const std::vector<TruthSample> &samples, int objectId = 1)
  {
    if (!enabled() || samples.empty())
    {
      return;
    }
    mCategories[objectId] = std::string(samples.front().box.category);
    for (const auto &sample : samples)
    {
      JsonWriter json;
      json.beginObject();
      json.key("id").value(objectId);
      json.key("category").value(sample.box.category);
      json.key("translation").value(std::array{sample.x, sample.y, 0.0});
      json.key("size").value(std::array{sample.box.length, sample.box.width, sample.box.height});
      json.key("rotation").value(yawQuaternion(sample.heading));
      json.key("velocity").value(std::array{sample.vx(), sample.vy(), 0.0});
      json.key("truth").beginObject();
      json.key("speed").value(sample.speed);
      json.key("yaw_rate").value(sample.yawRate);
      json.key("acceleration").value(sample.acceleration);
      json.endObject();
      json.endObject();
      mTruth[toMicroseconds(sample.t)].push_back(json.str());
    }
    mDirty = true;
  }

  void filterStep(const FilterRun &run, const std::optional<Observation> &observation) override
  {
    if (!enabled())
    {
      return;
    }
    if (observation)
    {
      recordDetection(*observation, run.trackId());
    }
    const auto &estimator = run.estimator;
    const auto time
      = std::chrono::round<std::chrono::microseconds>(estimator.mLastTimestamp.time_since_epoch()).count();
    const bool initStep = !mEstimatorConfigs.contains(run.trackId());
    if (initStep)
    {
      mEstimatorConfigs[run.trackId()] = configLine(run);
    }
    mTracks[{time, run.trackId()}] = estimator.currentState();
    mEstimatorSteps.push_back(stepLine(run, time, initStep));
    mDirty = true;
  }

  // Writes all files, also called by the destructor. A write error is reported as a test failure.
  void write()
  {
    if (!enabled() || !mDirty)
    {
      return;
    }
    mDirty = false;
    std::error_code error;
    std::filesystem::create_directories(mDirectory, error);
    if (error)
    {
      ADD_FAILURE() << "ScenarioRecorder: cannot create " << mDirectory << ": " << error.message();
      return;
    }
    writeLines("groundtruth.jsonl", groundTruthLines());
    writeLines("detections.jsonl", detectionLines());
    writeLines("tracks.jsonl", trackLines());
    std::vector<std::string> estimatorLines;
    for (const auto &[trackId, line] : mEstimatorConfigs)
    {
      estimatorLines.push_back(line);
    }
    estimatorLines.insert(estimatorLines.end(), mEstimatorSteps.begin(), mEstimatorSteps.end());
    writeLines("estimator.jsonl", estimatorLines);
  }

private:
  struct DetectionEntry
  {
    int objectId;
    std::string json;
  };

  void recordDetection(const Observation &observation, int objectId)
  {
    const auto &detection = observation.detection;
    JsonWriter json;
    json.beginObject();
    json.key("id").value(objectId);
    json.key("translation").value(std::array{detection.x, detection.y, detection.z});
    json.key("size").value(std::array{detection.length, detection.width, detection.height});
    if (orientation::hasOrientation(detection))
    {
      json.key("rotation").value(yawQuaternion(detection.yaw));
    }
    json.endObject();
    mDetections[{toMicroseconds(observation.t), observation.sensorId}].push_back({objectId, json.str()});
  }

  static std::filesystem::path rootFromEnvironment()
  {
    const char *root = std::getenv(kEnvironmentVariable);
    return root != nullptr ? std::filesystem::path(root) : std::filesystem::path();
  }

  // Letters, digits, '-' and '_' only, so names cannot leave the output directory.
  static std::string sanitize(std::string_view name)
  {
    std::string result;
    for (const char c : name)
    {
      const bool allowed
        = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_';
      result += allowed ? c : '_';
    }
    return result.empty() ? "_" : result;
  }

  static std::string currentTestName()
  {
    const auto *info = ::testing::UnitTest::GetInstance()->current_test_info();
    if (info == nullptr)
    {
      return "scenario";
    }
    return sanitize(info->test_suite_name()) + "." + sanitize(info->name());
  }

  static std::string_view modelName(const cv::Ptr<cv::detail::tracking::UkfSystemModel> &model)
  {
    if (dynamic_cast<const CVModel *>(model.get()) != nullptr)
    {
      return "CV";
    }
    if (dynamic_cast<const CAModel *>(model.get()) != nullptr)
    {
      return "CA";
    }
    if (dynamic_cast<const CPModel *>(model.get()) != nullptr)
    {
      return "CP";
    }
    if (dynamic_cast<const CTRVModel *>(model.get()) != nullptr)
    {
      return "CTRV";
    }
    return "unknown";
  }

  std::string category(int objectId) const
  {
    const auto found = mCategories.find(objectId);
    return found != mCategories.end() && !found->second.empty() ? found->second : "unknown";
  }

  static std::string configLine(const FilterRun &run)
  {
    const auto &estimator = run.estimator;
    const auto &config = run.config();
    JsonWriter json;
    json.beginObject();
    json.key("type").value("config");
    json.key("track_id").value(std::to_string(run.trackId()));
    json.key("motion_models").beginArray();
    for (const auto &model : estimator.mSystemModels)
    {
      json.value(modelName(model));
    }
    json.endArray();
    json.key("process_noise").value(config.mDefaultProcessNoise);
    json.key("measurement_noise").value(config.mDefaultMeasurementNoise);
    json.key("init_state_covariance").value(config.mInitStateCovariance);
    json.key("ukf").beginObject();
    json.key("alpha").value(estimator.mAlpha);
    json.key("beta").value(estimator.mBeta);
    json.key("kappa").value(estimator.mKappa);
    json.endObject();
    json.key("transition_probability").value(estimator.getTransitionProbability());
    json.key("min_probability").value(estimator.mMinProbability);
    json.key("max_probability").value(estimator.mMaxProbability);
    json.key("state_names").beginArray();
    for (const char *name : {"x", "y", "vx", "vy", "ax", "ay", "z", "length", "width", "height", "yaw", "yaw_rate"})
    {
      json.value(name);
    }
    json.endArray();
    json.key("measurement_names").beginArray();
    for (const char *name : {"x", "y", "z", "length", "width", "height", "yaw"})
    {
      json.value(name);
    }
    json.endArray();
    json.endObject();
    return json.str();
  }

  static std::string stepLine(const FilterRun &run, std::int64_t time, bool initStep)
  {
    const auto &estimator = run.estimator;
    const auto &state = estimator.currentState();
    JsonWriter json;
    json.beginObject();
    json.key("type").value("step");
    json.key("track_id").value(std::to_string(run.trackId()));
    json.key("timestamp").value(isoTimestamp(time));
    json.key("mu").value(estimator.getModelProbability());
    json.key("x").value(state.stateVector());
    if (initStep)
    {
      // initialize() sets no combined covariance and no prediction; every model starts from the same P0.
      json.key("P").value(estimator.getKalmanFilterErrorCovariance(0));
      json.key("z_pred").null();
      json.key("S").null();
    }
    else
    {
      json.key("P").value(state.errorCovariance);
      // From the predict step; correct() leaves them unchanged.
      json.key("z_pred").value(state.predictedMeasurementMean);
      json.key("S").value(state.predictedMeasurementCov);
    }
    json.endObject();
    return json.str();
  }

  std::vector<std::string> groundTruthLines() const
  {
    std::vector<std::string> lines;
    for (const auto &[time, objects] : mTruth)
    {
      JsonWriter json;
      json.beginObject();
      json.key("timestamp").value(isoTimestamp(time));
      json.key("objects").beginArray();
      for (const auto &object : objects)
      {
        json.raw(object);
      }
      json.endArray();
      json.endObject();
      lines.push_back(json.str());
    }
    return lines;
  }

  std::vector<std::string> detectionLines() const
  {
    std::vector<std::string> lines;
    for (const auto &[frame, entries] : mDetections)
    {
      std::map<std::string, std::vector<std::string>> byCategory;
      for (const auto &entry : entries)
      {
        byCategory[category(entry.objectId)].push_back(entry.json);
      }
      JsonWriter json;
      json.beginObject();
      json.key("id").value(frame.second);
      json.key("timestamp").value(isoTimestamp(frame.first));
      json.key("objects").beginObject();
      for (const auto &[name, objects] : byCategory)
      {
        json.key(name).beginArray();
        for (const auto &object : objects)
        {
          json.raw(object);
        }
        json.endArray();
      }
      json.endObject();
      json.endObject();
      lines.push_back(json.str());
    }
    return lines;
  }

  std::vector<std::string> trackLines() const
  {
    std::vector<std::string> lines;
    auto frame = mTracks.begin();
    while (frame != mTracks.end())
    {
      const std::int64_t time = frame->first.first;
      JsonWriter json;
      json.beginObject();
      json.key("id").value(mSceneName);
      json.key("name").value(mSceneName);
      json.key("timestamp").value(isoTimestamp(time));
      json.key("objects").beginArray();
      for (; frame != mTracks.end() && frame->first.first == time; ++frame)
      {
        const int trackId = frame->first.second;
        const auto &state = frame->second;
        json.beginObject();
        json.key("id").value(std::to_string(trackId));
        json.key("category").value(category(trackId));
        json.key("translation").value(std::array{state.x, state.y, state.z});
        json.key("velocity").value(std::array{state.vx, state.vy, 0.0});
        json.key("size").value(std::array{state.length, state.width, state.height});
        json.key("rotation").value(yawQuaternion(state.yaw));
        json.endObject();
      }
      json.endArray();
      json.endObject();
      lines.push_back(json.str());
    }
    return lines;
  }

  void writeLines(std::string_view fileName, const std::vector<std::string> &lines) const
  {
    const auto path = mDirectory / fileName;
    std::ofstream file(path, std::ios::trunc);
    for (const auto &line : lines)
    {
      file << line << '\n';
    }
    file.close();
    if (!file)
    {
      ADD_FAILURE() << "ScenarioRecorder: cannot write " << path;
    }
  }

  std::filesystem::path mDirectory;
  std::string mSceneName;
  bool mDirty = false;
  std::map<int, std::string> mCategories;
  std::map<std::int64_t, std::vector<std::string>> mTruth;
  std::map<std::pair<std::int64_t, std::string>, std::vector<DetectionEntry>> mDetections;
  std::map<std::pair<std::int64_t, int>, TrackedObject> mTracks;
  std::map<int, std::string> mEstimatorConfigs;
  std::vector<std::string> mEstimatorSteps;
};

} // namespace rv::tracking::test

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Optional ReID telemetry initialization and failure isolation."""

import os
import unittest
from unittest import mock

from reid import observability


RECORDERS = (
  (observability.record_decision_latency, "_decision_latency", {"category": "person"}),
  (observability.record_backend_query_duration, "_backend_query_duration", {"backend": "VDMS"}),
  (observability.record_backend_write_duration, "_backend_write_duration", {"backend": "VDMS"}),
)


class TestObservability(unittest.TestCase):

  def setUp(self):
    self.enterContext(mock.patch.dict(os.environ, {
      "REID_ENABLE_METRICS": "true",
      "REID_METRICS_ENDPOINT": "http://localhost:4317",
    }, clear=True))
    self.enterContext(mock.patch.multiple(
      observability, _provider=None, _decision_latency=None,
      _backend_query_duration=None, _backend_write_duration=None))
    self.exporter = self.enterContext(mock.patch.object(observability, "OTLPMetricExporter"))
    self.reader = self.enterContext(mock.patch.object(observability, "PeriodicExportingMetricReader"))
    self.provider_factory = self.enterContext(mock.patch.object(observability, "MeterProvider"))
    self.warning = self.enterContext(mock.patch.object(observability.log, "warning"))
    self.provider = self.provider_factory.return_value
    self.meter = self.provider.get_meter.return_value

  def assert_metrics_disabled(self):
    self.assertIsNone(observability._provider)
    for _, attribute, _ in RECORDERS:
      self.assertIsNone(getattr(observability, attribute))

  def test_disabled_metrics_do_not_create_exporter_or_provider(self):
    for enabled in (None, "false", "0", "no", "invalid"):
      with self.subTest(enabled=enabled):
        if enabled is None:
          os.environ.pop("REID_ENABLE_METRICS", None)
        else:
          os.environ["REID_ENABLE_METRICS"] = enabled
        self.assertIsNone(observability.init())
        self.assert_metrics_disabled()
    self.exporter.assert_not_called()
    self.reader.assert_not_called()
    self.provider_factory.assert_not_called()

  def test_missing_endpoint_disables_metrics(self):
    del os.environ["REID_METRICS_ENDPOINT"]

    self.assertIsNone(observability.init())

    self.assert_metrics_disabled()
    self.exporter.assert_not_called()
    self.provider_factory.assert_not_called()
    self.warning.assert_called_once_with("REID_METRICS_ENDPOINT not set; disabling ReID metrics")

  def test_enabled_metrics_create_service_resource_and_histograms(self):
    histograms = [mock.Mock() for _ in RECORDERS]
    self.meter.create_histogram.side_effect = histograms

    self.assertIs(observability.init(), self.provider)

    self.exporter.assert_called_once_with(endpoint="http://localhost:4317", insecure=True)
    self.reader.assert_called_once_with(self.exporter.return_value, export_interval_millis=60000)
    self.provider_factory.assert_called_once()
    provider_kwargs = self.provider_factory.call_args.kwargs
    self.assertEqual(provider_kwargs["resource"].attributes["service.name"], "reid-service")
    self.assertEqual(provider_kwargs["metric_readers"], [self.reader.return_value])
    self.provider.get_meter.assert_called_once_with(observability.__name__)
    self.assertEqual(self.meter.create_histogram.call_args_list, [
      mock.call("scenescape_reid_decision_latency", unit="s",
                description="Track first observation to completed ReID decision",
                explicit_bucket_boundaries_advisory=observability.DECISION_LATENCY_BUCKETS),
      mock.call("scenescape_reid_backend_query_duration", unit="s",
                description="Duration of a ReID backend similarity query",
                explicit_bucket_boundaries_advisory=observability.BACKEND_DURATION_BUCKETS),
      mock.call("scenescape_reid_backend_write_duration", unit="s",
                description="Duration of a ReID backend descriptor write",
                explicit_bucket_boundaries_advisory=observability.BACKEND_DURATION_BUCKETS),
    ])
    self.assertIs(observability._provider, self.provider)
    for (_, attribute, _), histogram in zip(RECORDERS, histograms):
      self.assertIs(getattr(observability, attribute), histogram)
    self.provider.shutdown.assert_not_called()
    self.warning.assert_not_called()

  def test_enabled_values_and_custom_export_interval(self):
    os.environ["REID_METRICS_EXPORT_INTERVAL_S"] = "7"
    for enabled in ("1", "TRUE", "Yes"):
      with self.subTest(enabled=enabled):
        os.environ["REID_ENABLE_METRICS"] = enabled
        self.assertIs(observability.init(), self.provider)
        self.reader.assert_called_with(self.exporter.return_value, export_interval_millis=7000)
    self.warning.assert_not_called()

  def test_invalid_export_intervals_fall_back_to_default(self):
    for interval in ("invalid", "", "0", "-1", "1.5"):
      with self.subTest(interval=interval):
        os.environ["REID_METRICS_EXPORT_INTERVAL_S"] = interval
        self.warning.reset_mock()

        self.assertIs(observability.init(), self.provider)

        self.reader.assert_called_with(self.exporter.return_value, export_interval_millis=60000)
        self.warning.assert_called_once_with("Invalid REID_METRICS_EXPORT_INTERVAL_S; using default of 60s")

  def test_initialization_failures_are_isolated(self):
    stages = (
      (self.exporter, False),
      (self.reader, False),
      (self.provider_factory, False),
      (self.provider.get_meter, True),
      (self.meter.create_histogram, True),
    )
    for failing_mock, provider_created in stages:
      with self.subTest(stage=failing_mock):
        self.provider.shutdown.reset_mock()
        self.warning.reset_mock()
        failing_mock.side_effect = RuntimeError("initialization failed")
        try:
          self.assertIsNone(observability.init())
        finally:
          failing_mock.side_effect = None
        self.assert_metrics_disabled()
        self.assertEqual(self.provider.shutdown.call_count, int(provider_created))
        self.warning.assert_called_once_with(
          "Could not initialize ReID metrics; disabling export: initialization failed")

  def test_partial_histogram_initialization_does_not_publish_globals(self):
    self.meter.create_histogram.side_effect = [mock.Mock(), RuntimeError("histogram failed")]

    self.assertIsNone(observability.init())

    self.assert_metrics_disabled()
    self.provider.shutdown.assert_called_once_with()
    self.warning.assert_called_once()

  def test_recording_without_initialized_metrics_is_a_noop(self):
    for record, _, attributes in RECORDERS:
      with self.subTest(record=record.__name__):
        record(object(), next(iter(attributes.values())))
    self.warning.assert_not_called()

  def test_recording_preserves_labels_and_clamps_negative_durations(self):
    for record, attribute, attributes in RECORDERS:
      with self.subTest(record=record.__name__):
        histogram = mock.Mock()
        with mock.patch.object(observability, attribute, histogram):
          record("0.25", next(iter(attributes.values())))
          record(-1.0, next(iter(attributes.values())))
        self.assertEqual(histogram.record.call_args_list, [
          mock.call(0.25, attributes=attributes),
          mock.call(0.0, attributes=attributes),
        ])
    self.warning.assert_not_called()

  def test_recording_failures_are_isolated(self):
    for record, attribute, attributes in RECORDERS:
      for value, error in (("invalid", None), (object(), None), (0.1, RuntimeError("record failed"))):
        with self.subTest(record=record.__name__, value=value):
          histogram = mock.Mock()
          histogram.record.side_effect = error
          self.warning.reset_mock()
          with mock.patch.object(observability, attribute, histogram):
            record(value, next(iter(attributes.values())))
          self.warning.assert_called_once()
          self.assertTrue(self.warning.call_args.args[0].startswith("ReID metric recording failed:"))
          if error is None:
            histogram.record.assert_not_called()

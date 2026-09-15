# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit Tests for Model Download Retry Logic
Tests the retry_with_exponential_backoff utility and model loader error handling.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

# Mock scene_common before importing model_utils; restored by the fixture below
# so this doesn't leak into other test modules in the same pytest session.
_ORIGINAL_SCENE_COMMON = sys.modules.get('scene_common')
sys.modules['scene_common'] = MagicMock()

# Add tools directory to path
tools_path = Path(__file__).parent.parent / 'tools'
sys.path.insert(0, str(tools_path))

from model_utils import (
    retry_with_exponential_backoff,
    DEFAULT_MAX_RETRY_ATTEMPTS,
    DEFAULT_RETRY_INITIAL_WAIT_SECONDS,
)


@pytest.fixture(scope="module", autouse=True)
def _restore_scene_common_module():
  yield
  if _ORIGINAL_SCENE_COMMON is not None:
    sys.modules['scene_common'] = _ORIGINAL_SCENE_COMMON
  else:
    sys.modules.pop('scene_common', None)


# Test constants derived from the production defaults, so tests validate real
# behavior instead of independently-guessed values.
TEST_DEFAULT_MAX_ATTEMPTS = DEFAULT_MAX_RETRY_ATTEMPTS
TEST_DEFAULT_INITIAL_WAIT = DEFAULT_RETRY_INITIAL_WAIT_SECONDS
TEST_CUSTOM_MAX_ATTEMPTS = TEST_DEFAULT_MAX_ATTEMPTS + 2
TEST_CUSTOM_WAIT = 1
TEST_SINGLE_ATTEMPT = 1



class TestRetryLogic:
  """Test cases for retry_with_exponential_backoff function"""

  def test_succeeds_on_first_attempt(self, mocker):
    """Test that function succeeds immediately when no error occurs"""
    mock_func = MagicMock(return_value="success")
    mock_sleep = mocker.patch('model_utils.time.sleep')

    result = retry_with_exponential_backoff(
        mock_func,
        max_attempts=TEST_DEFAULT_MAX_ATTEMPTS,
        initial_wait_seconds=TEST_DEFAULT_INITIAL_WAIT
    )

    assert result == "success"
    assert mock_func.call_count == 1
    # No sleep should occur on first success
    mock_sleep.assert_not_called()

  def test_succeeds_on_second_attempt_with_backoff(self, mocker):
    """Test retry succeeds on second attempt after initial failure"""
    # First call raises, second succeeds
    mock_func = MagicMock(side_effect=[
        RuntimeError("Network timeout"),
        "success"
    ])
    mock_sleep = mocker.patch('model_utils.time.sleep')

    result = retry_with_exponential_backoff(
        mock_func,
        max_attempts=TEST_DEFAULT_MAX_ATTEMPTS,
        initial_wait_seconds=TEST_DEFAULT_INITIAL_WAIT
    )

    assert result == "success"
    assert mock_func.call_count == 2
    # Should sleep once between attempts with default wait
    mock_sleep.assert_called_once_with(TEST_DEFAULT_INITIAL_WAIT)

  def test_exponential_backoff_timing(self, mocker):
    """Test exponential backoff uses correct timing: 2s, 4s, 8s"""
    # Fail all attempts to force all retries
    mock_func = MagicMock(side_effect=RuntimeError("Always fails"))
    mock_sleep = mocker.patch('model_utils.time.sleep')

    with pytest.raises(RuntimeError):
      retry_with_exponential_backoff(
          mock_func,
          max_attempts=TEST_DEFAULT_MAX_ATTEMPTS,
          initial_wait_seconds=TEST_DEFAULT_INITIAL_WAIT
      )

    # Should have 2 sleeps (between 3 attempts)
    assert mock_sleep.call_count == 2
    # Verify exponential backoff: 2s then 4s
    sleep_calls = [call(TEST_DEFAULT_INITIAL_WAIT), call(TEST_DEFAULT_INITIAL_WAIT * 2)]
    mock_sleep.assert_has_calls(sleep_calls)

  def test_fails_after_max_attempts(self, mocker):
    """Test exception is raised after exhausting all retry attempts"""
    mock_func = MagicMock(side_effect=ValueError("Persistent failure"))
    mock_sleep = mocker.patch('model_utils.time.sleep')

    with pytest.raises(ValueError) as exc_info:
      retry_with_exponential_backoff(
          mock_func,
          max_attempts=TEST_DEFAULT_MAX_ATTEMPTS,
          initial_wait_seconds=TEST_CUSTOM_WAIT
      )

    assert "Persistent failure" in str(exc_info.value)
    assert mock_func.call_count == TEST_DEFAULT_MAX_ATTEMPTS

  def test_custom_max_attempts(self, mocker):
    """Test custom max_attempts parameter is respected"""
    mock_func = MagicMock(side_effect=RuntimeError("Fails"))
    mock_sleep = mocker.patch('model_utils.time.sleep')

    with pytest.raises(RuntimeError):
      retry_with_exponential_backoff(
          mock_func,
          max_attempts=TEST_CUSTOM_MAX_ATTEMPTS,
          initial_wait_seconds=TEST_CUSTOM_WAIT
      )

    # Should attempt 5 times
    assert mock_func.call_count == TEST_CUSTOM_MAX_ATTEMPTS

  def test_succeeds_on_third_attempt(self, mocker):
    """Test retry succeeds on third attempt after two failures"""
    mock_func = MagicMock(side_effect=[
        RuntimeError("First failure"),
        RuntimeError("Second failure"),
        "success"
    ])
    mock_sleep = mocker.patch('model_utils.time.sleep')

    result = retry_with_exponential_backoff(
        mock_func,
        max_attempts=TEST_DEFAULT_MAX_ATTEMPTS,
        initial_wait_seconds=TEST_DEFAULT_INITIAL_WAIT
    )

    assert result == "success"
    assert mock_func.call_count == TEST_DEFAULT_MAX_ATTEMPTS
    # Should sleep twice (between 3 attempts): 2s, then 4s
    assert mock_sleep.call_count == 2
    sleep_calls = [call(TEST_DEFAULT_INITIAL_WAIT), call(TEST_DEFAULT_INITIAL_WAIT * 2)]
    mock_sleep.assert_has_calls(sleep_calls)

  def test_logging_on_retry_attempts(self, mocker):
    """Test logging messages for each retry attempt"""
    mock_func = MagicMock(side_effect=[
        RuntimeError("Network error"),
        "success"
    ])
    mock_sleep = mocker.patch('model_utils.time.sleep')
    mock_log = mocker.patch('model_utils.log')

    result = retry_with_exponential_backoff(
        mock_func,
        max_attempts=TEST_DEFAULT_MAX_ATTEMPTS,
        initial_wait_seconds=TEST_DEFAULT_INITIAL_WAIT
    )

    # Verify logging calls include attempt numbers
    info_calls = [call for call in mock_log.info.call_args_list]
    warning_calls = [call for call in mock_log.warning.call_args_list]

    # Verify attempt numbers logged match the max_attempts actually passed in
    assert any(f"Attempt 1/{TEST_DEFAULT_MAX_ATTEMPTS}" in str(call) for call in info_calls)
    assert any(f"Attempt 2/{TEST_DEFAULT_MAX_ATTEMPTS}" in str(call) for call in info_calls)
    # Should have warning about retry
    assert any("Retrying" in str(call) for call in warning_calls)

  def test_single_attempt_mode(self, mocker):
    """Test with max_attempts=1 (no retries)"""
    mock_func = MagicMock(side_effect=RuntimeError("Failed"))
    mock_sleep = mocker.patch('model_utils.time.sleep')

    with pytest.raises(RuntimeError):
      retry_with_exponential_backoff(
          mock_func,
          max_attempts=TEST_SINGLE_ATTEMPT,
          initial_wait_seconds=TEST_DEFAULT_INITIAL_WAIT
      )

    # Should only attempt once
    assert mock_func.call_count == TEST_SINGLE_ATTEMPT
    # No sleep when max_attempts=1
    mock_sleep.assert_not_called()


class TestDownloadFunctionWithRetry:
  """Integration tests verifying download functions use retry logic"""

  def test_mapanything_download_attempts_retry_on_failure(self, mocker):
    """Test that download_mapanything_model uses retry logic"""
    # Mock dependencies
    mocker.patch('download_mapanything.ensure_cache_directories')
    mocker.patch('download_mapanything.check_model_exists', return_value=False)
    mock_retry = mocker.patch('download_mapanything.retry_with_exponential_backoff')

    # Simulate retry raising exception (all attempts failed)
    mock_retry.side_effect = RuntimeError("Download failed after retries")

    from download_mapanything import download_mapanything_model

    result = download_mapanything_model()

    # Should return False instead of raising
    assert result is False
    # Should have called retry_with_exponential_backoff with the download function,
    # relying on model_utils' own defaults rather than passing duplicated values
    mock_retry.assert_called_once()
    assert callable(mock_retry.call_args[0][0])

  def test_vggt_download_attempts_retry_on_failure(self, mocker):
    """Test that download_vggt_model uses retry logic"""
    # Mock dependencies
    mocker.patch('download_vggt.ensure_cache_directories')
    mocker.patch('download_vggt.check_model_exists', return_value=False)
    mock_retry = mocker.patch('download_vggt.retry_with_exponential_backoff')

    # Simulate retry raising exception
    mock_retry.side_effect = RuntimeError("Download failed after retries")

    from download_vggt import download_vggt_model

    result = download_vggt_model()

    # Should return False instead of raising
    assert result is False
    # Should have called retry_with_exponential_backoff with the download function,
    # relying on model_utils' own defaults rather than passing duplicated values
    mock_retry.assert_called_once()
    assert callable(mock_retry.call_args[0][0])

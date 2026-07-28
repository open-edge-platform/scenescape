#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Download Scenescape demo models via Intel model_downloader REST API."""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib import error, request


_JOB_POLL_INTERVAL_S = 5.0
_PROGRESS_UPDATE_INTERVAL_S = 30.0
_DEFAULT_MODELS_CONFIG_FILE = Path(__file__).resolve().parents[1] / 'models.json'


def _parse_bool(value: str) -> bool:
  normalized = str(value).strip().lower()
  return normalized in {'1', 'true', 'yes', 'on'}


def _get_job_ids(response_body: str) -> list[str]:
  data = json.loads(response_body)
  job_ids = data.get('job_ids', [])

  if not isinstance(job_ids, list):
    raise TypeError('job_ids must be a list')

  for job_id in job_ids:
    if not isinstance(job_id, str):
      raise TypeError('Each job_id must be a string')

  return job_ids


def _get_tracked_jobs(response_body: str, job_ids: list[str]) -> dict[str, dict[str, object]]:
  """
  Extracts and returns a dictionary of tracked jobs from the API response.
  The keys are job IDs and the values are the corresponding job objects.
  """
  data = json.loads(response_body)
  jobs = data.get('jobs', [])
  if not isinstance(jobs, list):
    raise TypeError('jobs must be a list')

  tracked_job_ids = set(job_ids)
  tracked_jobs = {}
  for job in jobs:
    if not isinstance(job, dict):
      raise TypeError('Each job entry must be an object')

    job_id = job.get('id')
    if not isinstance(job_id, str):
      raise ValueError('Each job entry must include a string id')

    if job_id in tracked_job_ids:
      tracked_jobs[job_id] = job

  return tracked_jobs


def _get_job_outcome(job: dict[str, object]) -> str:
  """
  Determines the outcome of a job based on its status and result.
  Returns one of the following strings:
  - 'completed' if the job completed successfully
  - 'failed' if the job failed or was canceled
  - 'pending' if the job is still in progress or its outcome is unknown
  """
  status = str(job.get('status', '')).strip().lower()
  result = job.get('result')
  success = None

  if isinstance(result, dict) and 'success' in result:
    success = result['success']
    if not isinstance(success, bool):
      raise ValueError('Job result success flag must be a boolean value')

  if status in {'failed', 'canceled'}:
    return 'failed'

  if status == 'completed':
    return 'completed' if success is not False else 'failed'

  if success is False:
    return 'failed'

  return 'pending'


def _wait_for_jobs(
    api_url: str,
    job_ids: list[str],
    wait_timeout_s: int,
    poll_interval_s: float = _JOB_POLL_INTERVAL_S,
) -> None:
  """
  Waits for the specified download jobs to complete by polling the downloader API.
  Raises a RuntimeError if any job fails or if the wait times out.
  """
  if not job_ids:
    raise ValueError('No job ids returned by downloader API')

  endpoint = f"{api_url.rstrip('/')}/api/v1/jobs"
  req = request.Request(endpoint, method='GET')
  deadline = time.time() + wait_timeout_s
  last_error = ''
  display_time = time.time()
  print('Waiting for model download jobs', end='', flush=True)

  while time.time() < deadline:
    try:
      with request.urlopen(req, timeout=1800) as response:
        output = response.read().decode('utf-8', errors='replace')
    except error.HTTPError as exc:
      body = exc.read().decode('utf-8', errors='replace')
      raise RuntimeError(f'Download job status request failed: HTTP {exc.code} - {body}') from exc
    except error.URLError as exc:
      last_error = f'Download job status request failed: {exc.reason}'
    except ConnectionResetError:
      last_error = 'Download job status request failed: connection reset by peer'
    else:
      tracked_jobs = _get_tracked_jobs(output, job_ids)
      missing_job_ids = sorted(set(job_ids) - set(tracked_jobs))
      failed_job_ids = []
      pending_job_ids = missing_job_ids.copy()

      for job_id, job in tracked_jobs.items():
        outcome = _get_job_outcome(job)
        if outcome == 'failed':
          failed_job_ids.append(job_id)
        elif outcome == 'pending':
          pending_job_ids.append(job_id)

      if failed_job_ids:
        print()
        raise RuntimeError(f'Download jobs failed: {", ".join(sorted(failed_job_ids))}')

      if not pending_job_ids:
        print()
        return

      last_error = (
        'Timeout waiting for download jobs to finish: '
        f'{", ".join(sorted(pending_job_ids))}'
      )

    if time.time() - display_time >= _PROGRESS_UPDATE_INTERVAL_S:
      print('.', end='', flush=True)
      display_time = time.time()

    time.sleep(min(poll_interval_s, max(0.0, deadline - time.time())))

  print()
  raise RuntimeError(last_error)


def _post_download_request(
    api_url: str,
    models: list[dict[str, object]],
    parallel_downloads: bool,
    wait_timeout_s: int,
) -> list[str]:
  """
  Posts a download request to the downloader API and returns the list of IDs of jobs used by
  model downloader to download models.
  Raises a RuntimeError if the request fails or if the wait times out.
  """
  endpoint = (
    f"{api_url.rstrip('/')}/api/v1/models/download"
    f"?download_path=."
  )
  payload = {
    'models': models,
    'parallel_downloads': parallel_downloads,
  }
  encoded_payload = json.dumps(payload).encode("utf-8")
  req = request.Request(
    endpoint,
    data=encoded_payload,
    headers={'Content-Type': 'application/json'},
    method='POST',
  )

  deadline = time.time() + wait_timeout_s
  last_error = ''
  display_time = time.time()
  print('Downloading models', end='', flush=True)

  while time.time() < deadline:
    try:
      with request.urlopen(req, timeout=1800) as response:
        output = response.read().decode('utf-8', errors='replace')
        print()
        return _get_job_ids(output)
    except error.HTTPError as exc:
      body = exc.read().decode('utf-8', errors='replace')
      raise RuntimeError(f'Download request failed: HTTP {exc.code} - {body}') from exc
    except error.URLError as exc:
      last_error = f'Download request failed: {exc.reason}'
    except ConnectionResetError:
      last_error = 'Download request failed: connection reset by peer'

    if time.time() - display_time >= _PROGRESS_UPDATE_INTERVAL_S:
      print('.', end='', flush=True)
      display_time = time.time()

    time.sleep(min(_JOB_POLL_INTERVAL_S, max(0.0, deadline - time.time())))

  print()
  raise RuntimeError(last_error or 'Timeout waiting for model download request acceptance')


def _build_arg_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser()
  parser.add_argument('--api-url', type=str, default=os.getenv('MODEL_DOWNLOADER_URL', 'http://127.0.0.1:8200'))
  parser.add_argument(
    '--models-config',
    type=str,
    default=os.getenv('MODEL_CONFIG_FILE', str(_DEFAULT_MODELS_CONFIG_FILE)),
    help='Path to JSON config containing descriptions of models which should be downloaded.',
  )
  parser.add_argument(
    "--destination-path",
    type=str,
    default=os.getenv("MODEL_DESTINATION_PATH", ""),
    help="Optional path to copy downloaded models to after download.",
  )
  parser.add_argument(
    '--parallel-downloads',
    type=str,
    default=os.getenv('PARALLEL_DOWNLOADS', 'false'),
    help='Boolean value: true/false',
  )
  parser.add_argument(
    '--initial-wait-timeout',
    type=int,
    default=int(os.getenv('MODEL_DOWNLOADER_INITIAL_WAIT_TIMEOUT', '720')),
    help='Initial wait timeout in seconds for the download request to be accepted by the downloader API'
  )
  parser.add_argument(
    '--wait-timeout',
    type=int,
    default=int(os.getenv('MODEL_DOWNLOADER_WAIT_TIMEOUT', '720')),
    help='Wait timeout in seconds for the download jobs to complete'
  )
  return parser


def _validate_downloader_models(models: object) -> list[dict[str, object]]:
  if not isinstance(models, list):
    raise ValueError('models must be a JSON array')

  if not models:
    raise ValueError('models must not be empty')

  validated_models = []
  for index, model in enumerate(models):
    if not isinstance(model, dict):
      raise ValueError(f'models[{index}] must be an object')

    name = model.get('name')
    if not isinstance(name, str) or not name:
      raise ValueError(f'models[{index}].name must be a non-empty string')

    validated_models.append(model)

  return validated_models


def _extract_downloader_models(config_models: object) -> list[dict[str, object]]:
  if not isinstance(config_models, list):
    raise ValueError('models must be a JSON array')

  downloader_models = []
  for index, model in enumerate(config_models):
    if not isinstance(model, dict):
      raise ValueError(f'models[{index}] must be an object')

    downloader_model = model.get('model_downloader')
    if not isinstance(downloader_model, dict):
      raise ValueError(f'models[{index}].model_downloader must be an object')
    downloader_models.append(downloader_model)

  return _validate_downloader_models(downloader_models)


def _load_models_from_config(config_file: str) -> list[dict[str, object]]:
  with open(config_file, 'r', encoding='utf-8') as handle:
    config = json.load(handle)

  if not isinstance(config, dict):
    raise ValueError('models config must be a JSON object')

  return _extract_downloader_models(config.get('models'))


def main() -> int:
  parser = _build_arg_parser()
  args = parser.parse_args()

  try:
    models = _load_models_from_config(args.models_config)
    parallel_downloads = _parse_bool(args.parallel_downloads)
  except (OSError, ValueError, json.JSONDecodeError) as exc:
    print(f'Invalid input: {exc}', file=sys.stderr)
    return 2

  try:
    job_ids = _post_download_request(
      api_url=args.api_url,
      models=models,
      parallel_downloads=parallel_downloads,
      wait_timeout_s=args.initial_wait_timeout,
    )
    _wait_for_jobs(
      api_url=args.api_url,
      job_ids=job_ids,
      wait_timeout_s=args.wait_timeout,
    )
  except (RuntimeError, TimeoutError, ValueError) as exc:
    print(str(exc), file=sys.stderr)
    return 1

  print('Model download request completed.')
  return 0


if __name__ == '__main__':
  sys.exit(main())

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import time
from datetime import datetime
from pytz import timezone

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
TIMEZONE = "UTC"

def get_iso_time(timestamp: float=None) -> str:
  """! Returns ISO 8601 timestamp in UTC as string.

  @param      timestamp    Time in seconds as float type.
  @return     Time as string.
  """
  if timestamp is None:
    timestamp = time.time()

  utc_time = datetime.fromtimestamp(timestamp, tz=timezone(TIMEZONE))
  return f"{utc_time.strftime(DATETIME_FORMAT)[:-3]}Z"

def get_epoch_time(timestamp: str=None) -> float:
  """! Returns Epoch/POSIX timestamp in UTC as float.

  @param      timestamp    Time as string type.
  @return     Time as float.
  """
  if not timestamp:
    return time.time()

  utc_time = datetime.strptime(timestamp, f"{DATETIME_FORMAT}Z")
  return utc_time.replace(tzinfo=timezone(TIMEZONE)).timestamp()

def adjust_time(now, server, client, lastTimeSync, timeOffset, exception):
  if server is not None and (not lastTimeSync or now - lastTimeSync > 300):
    try:
      response = client.request(server, timeout=1)
      timeOffset = response.offset
      lastTimeSync = now
    except exception:
      print("Failed to connect to time server. Using old offset")
  return timeOffset, lastTimeSync

def get_datetime_from_string(date_string: str) -> datetime:
  """! Returns datetime object from string.

  @param      date_string    Date in string format.
  @return     Date as datetime object.
  """
  return datetime.strptime(date_string, f"{DATETIME_FORMAT}Z").replace(tzinfo=timezone(TIMEZONE))

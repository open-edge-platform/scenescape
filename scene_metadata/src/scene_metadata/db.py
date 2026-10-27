# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Timescale/PostgreSQL access."""

from pathlib import Path
import os

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from scene_common import log

def schema_sql_path() -> Path:
  env_path = os.environ.get('SCENE_METADATA_SQL_PATH')
  if env_path:
    return Path(env_path)
  root = Path(__file__).resolve().parents[2]
  docker_path = Path('/app/sql/001_init.sql')
  if docker_path.is_file():
    return docker_path
  return root / 'sql' / '001_init.sql'


def database_url() -> str:
  return os.environ.get(
    'SCENE_METADATA_DATABASE_URL',
    'postgresql://scenescape:scenescape@localhost:5432/scene_metadata',
  )


class Database:
  """Connection pool and schema bootstrap."""

  def __init__(self, url: str | None = None, sql_path: Path | None = None):
    self._url = url or database_url()
    self._sql_path = sql_path or schema_sql_path()
    self._pool: ConnectionPool | None = None

  def open(self) -> None:
    if self._pool is not None:
      return
    self._pool = ConnectionPool(self._url, kwargs={'row_factory': dict_row}, open=True)
    self._apply_schema()

  def close(self) -> None:
    if self._pool is not None:
      self._pool.close()
      self._pool = None

  def _apply_schema(self) -> None:
    if not self._sql_path.is_file():
      log.warning(f"scene-metadata schema file missing: {self._sql_path}")
      return
    sql = self._sql_path.read_text(encoding='utf-8')
    with self.connection() as conn:
      conn.execute(sql)
      self._apply_retention(conn)
      conn.commit()

  def _apply_retention(self, conn) -> None:
    days = os.environ.get('SCENE_METADATA_RETENTION_DAYS')
    if not days:
      return
    try:
      interval_days = int(days)
    except ValueError:
      log.warning(f'invalid SCENE_METADATA_RETENTION_DAYS={days!r}')
      return
    if interval_days <= 0:
      return
    conn.execute(
      """
      SELECT add_retention_policy(
        'scenescape_events',
        drop_after => (%s || ' days')::interval,
        if_not_exists => TRUE
      )
      """,
      (interval_days,),
    )

  def connection(self) -> Connection:
    if self._pool is None:
      raise RuntimeError('Database pool is not open')
    return self._pool.connection()

import pytest
import json
import os
import zipfile
import tempfile
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from scene_common.rest_client import RESTClient

#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0




class TestImportSceneInit:
  def test_init_creates_instance(self):
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
      zip_path = tmp.name
    try:
      with patch.object(RESTClient.importScene, 'extractZip'):
        scene = RESTClient.importScene(zip_path, 'test_token')
        assert scene.zip_path == zip_path
        assert scene.rest.token == 'test_token'
        assert scene.badZipfile is False
    finally:
      os.unlink(zip_path)

  def test_init_sets_resturl_from_env(self):
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
      zip_path = tmp.name
    try:
      with patch.dict(os.environ, {'WEBSERVER_URL': 'https://custom.url'}):
        with patch.object(RESTClient.importScene, 'extractZip'):
          scene = RESTClient.importScene(zip_path, 'token')
          assert 'custom.url/api/v1' in scene.restUrl
    finally:
      os.unlink(zip_path)


class TestExtractZip:
  def test_extract_valid_zip(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      zip_path = os.path.join(tmpdir, 'test.zip')
      json_path = os.path.join(tmpdir, 'scene.json')
      
      with open(json_path, 'w') as f:
        json.dump({'name': 'test'}, f)
      
      with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.write(json_path, arcname='scene.json')
      
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.zip_path = zip_path
        result = scene.extractZip()
        
        assert result is True
        assert os.path.exists(scene.extract_dir)

  def test_extract_bad_zipfile(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      zip_path = os.path.join(tmpdir, 'bad.zip')
      
      with open(zip_path, 'w') as f:
        f.write('not a zip file')
      
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.zip_path = zip_path
        scene.extractZip()
        
        assert scene.badZipfile is True

  def test_extract_empty_zip(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      zip_path = os.path.join(tmpdir, 'empty.zip')
      
      with zipfile.ZipFile(zip_path, 'w') as zf:
        pass
      
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.zip_path = zip_path
        scene.extractZip()
        
        assert scene.badZipfile is True


class TestCreateSceneMap:
  def test_create_scene_map_success(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      resource_file = os.path.join(tmpdir, 'map.bin')
      with open(resource_file, 'wb') as f:
        f.write(b'test_data')
      
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.rest = Mock()
        scene.rest.createScene = Mock(return_value={'uid': 'scene123'})
        
        json_data = {'name': 'TestScene', 'scale': 1.0}
        result = scene.createSceneMap(json_data, resource_file)
        
        scene.rest.createScene.assert_called_once()
        call_args = scene.rest.createScene.call_args[0][0]
        assert call_args['name'] == 'TestScene'
        assert call_args['scale'] == 1.0


class TestLoadScene:
  @pytest.mark.asyncio
  async def test_load_scene_no_json_file(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.extract_dir = tmpdir
        scene.badZipfile = False
        
        errors = await scene.loadScene()
        
        assert errors['scene'] is not None
        assert 'No JSON file found' in str(errors['scene'])

  @pytest.mark.asyncio
  async def test_load_scene_multiple_json_files(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      open(os.path.join(tmpdir, 'scene1.json'), 'w').close()
      open(os.path.join(tmpdir, 'scene2.json'), 'w').close()
      
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.extract_dir = tmpdir
        scene.badZipfile = False
        
        errors = await scene.loadScene()
        
        assert errors['scene'] is not None
        assert 'Multiple JSON files found' in str(errors['scene'])

  @pytest.mark.asyncio
  async def test_load_scene_bad_zipfile(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      open(os.path.join(tmpdir, 'scene.json'), 'w').close()
      
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.extract_dir = tmpdir
        scene.badZipfile = True
        
        errors = await scene.loadScene()
        
        assert errors['scene'] is not None

  @pytest.mark.asyncio
  async def test_load_scene_invalid_json(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      json_file = os.path.join(tmpdir, 'scene.json')
      with open(json_file, 'w') as f:
        f.write('invalid json {')
      
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.extract_dir = tmpdir
        scene.badZipfile = False
        
        errors = await scene.loadScene()
        
        assert errors['scene'] is not None
        assert 'Failed to parse JSON' in str(errors['scene'])

  @pytest.mark.asyncio
  async def test_load_scene_no_resource_files(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      json_file = os.path.join(tmpdir, 'scene.json')
      with open(json_file, 'w') as f:
        json.dump({'name': 'TestScene'}, f)
      
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.extract_dir = tmpdir
        scene.badZipfile = False
        
        errors = await scene.loadScene()
        
        assert errors['scene'] is not None
        assert 'No resource files found' in str(errors['scene'])

  @pytest.mark.asyncio
  async def test_load_scene_no_matching_resource(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      json_file = os.path.join(tmpdir, 'scene.json')
      with open(json_file, 'w') as f:
        json.dump({'name': 'TestScene'}, f)
      
      open(os.path.join(tmpdir, 'otherscene.bin'), 'w').close()
      
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.extract_dir = tmpdir
        scene.badZipfile = False
        
        errors = await scene.loadScene()
        
        assert errors['scene'] is not None
        assert 'No matching resource file' in str(errors['scene'])

  @pytest.mark.asyncio
  async def test_load_scene_success(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      json_file = os.path.join(tmpdir, 'scene.json')
      scene_data = {
        'name': 'TestScene',
        'scale': 1.0,
        'cameras': [],
        'regions': [],
        'tripwires': [],
        'sensors': []
      }
      with open(json_file, 'w') as f:
        json.dump(scene_data, f)
      
      resource_file = os.path.join(tmpdir, 'TestScene.bin')
      with open(resource_file, 'wb') as f:
        f.write(b'data')
      
      with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
        scene = RESTClient.importScene.__new__(RESTClient.importScene)
        scene.extract_dir = tmpdir
        scene.badZipfile = False
        scene.rest = Mock()
        scene.rest.createScene = Mock(return_value={'uid': 'scene123'})
        scene.rest.updateScene = Mock(return_value=Mock(content={'uid': 'scene123'}))
        scene.bulk_create = AsyncMock(return_value=None)
        
        errors = await scene.loadScene()
        
        assert errors['scene'] is None


class TestBulkCreate:
  @pytest.mark.asyncio
  async def test_bulk_create_success(self):
    with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
      scene = RESTClient.importScene.__new__(RESTClient.importScene)
      
      mock_fn = AsyncMock()
      mock_response = Mock()
      mock_response.errors = None
      mock_fn.return_value = mock_response
      
      items = [{'name': 'item1'}, {'name': 'item2'}]
      errors = await scene.bulk_create(items, 'scene123', mock_fn)
      
      assert errors is None

  @pytest.mark.asyncio
  async def test_bulk_create_with_errors(self):
    with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
      scene = RESTClient.importScene.__new__(RESTClient.importScene)
      
      mock_fn = AsyncMock()
      mock_response = Mock()
      mock_response.errors = {'field': ['error message']}
      mock_fn.return_value = mock_response
      
      items = [{'name': 'item1'}]
      errors = await scene.bulk_create(items, 'scene123', mock_fn)
      
      assert errors is not None
      assert len(errors) == 1

  @pytest.mark.asyncio
  async def test_bulk_create_empty_items(self):
    with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
      scene = RESTClient.importScene.__new__(RESTClient.importScene)
      
      mock_fn = AsyncMock()
      
      errors = await scene.bulk_create([], 'scene123', mock_fn)
      
      assert errors is None

  @pytest.mark.asyncio
  async def test_bulk_create_exception_handling(self):
    with patch.object(RESTClient.importScene, '__init__', lambda x, y, z: None):
      scene = RESTClient.importScene.__new__(RESTClient.importScene)
      
      mock_fn = AsyncMock(side_effect=Exception('Test error'))
      
      items = [{'name': 'item1'}]
      errors = await scene.bulk_create(items, 'scene123', mock_fn)
      
      assert errors is not None
      assert len(errors) == 1
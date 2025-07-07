# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import json
import re
import requests
import sys
from http import HTTPStatus
from urllib.parse import urljoin

class RESTResult(dict):
  def __init__(self, statusCode, errors=None):
    super().__init__()
    self.statusCode = statusCode
    self.errors = errors
    return

class RESTClient:
  def __init__(self, url, rootcert=None, auth=None):
    self.url = url
    self.rootcert = rootcert
    if not self.url.endswith("/"):
      self.url = self.url + "/"
    self.session = requests.session()
    if auth:
      self._parseAuth(auth)
    return

  def _parseAuth(self, auth):
    """Parses auth file or string and uses the result to authenticate
    @param      auth            path to auth file or a user:password string
    """
    user = pw = None
    if os.path.exists(auth):
      with open(auth, encoding='utf-8') as json_file:
        data = json.load(json_file)
      user = data['user']
      pw = data['password']
    else:
      sep = auth.find(':')
      if sep < 0:
        raise ValueError("Invalid user/password")
      user = auth[:sep]
      pw = auth[sep + 1:]
    res = self.authenticate(user, pw)
    if not res:
      error_message = (
        f"Failed to authenticate\n"
        f"  URL: {self.url}\n"
        f"  status: {res.statusCode}\n"
        f"  errors: {res.errors}"
      )
      raise RuntimeError(error_message)
    return

  @property
  def isAuthenticated(self):
    return hasattr(self, 'token') and self.token is not None

  def decodeReply(self, reply, expectedStatus, successContent=None):
    result = RESTResult(statusCode=reply.status_code)
    decoded = False
    if 'Content-Type' in reply.headers and reply.headers['Content-Type'] == "application/json":
      try:
        content = json.loads(reply.content)
        decoded = True
      except json.JSONDecodeError:
        content = reply.content
    else:
      content = {
        'data': reply.content,
      }
      if 'Content-Disposition' in reply.headers:
        fname = re.findall("filename=(.+)", reply.headers['Content-Disposition'])[0]
        content['filename'] = fname
      decoded = True

    if reply.status_code == expectedStatus:
      if successContent:
        content = successContent
        decoded = True
      if decoded:
        result.update(content)

    if not decoded or reply.status_code != expectedStatus:
      result.errors = content

    return result

  def authenticate(self, user, password):
    """Authenticates against REST server and sets up session

    @param      user            user to authenticate as
    @param      password        user's password
    @return                     RESTResult with 'authenticated': True upon success,
                                or empty with `errors` set.
    """
    auth_url = urljoin(self.url, "auth")
    try:
      reply = self.session.post(auth_url, data={'username': user, 'password': password},
                                verify=self.rootcert)
    except requests.exceptions.ConnectionError as err:
      result = RESTResult("ConnectionError", errors=("Connection error", str(err)))
    else:
      result = self.decodeReply(reply, HTTPStatus.OK, successContent={'authenticated': True})
      if reply.status_code == HTTPStatus.OK:
        data = json.loads(reply.content)
        self.token = data['token']
    return result

  def dataIsNested(self, data):
    for key in data:
      if isinstance(data[key], dict):
        return True
    return False

  def prepareDataArgs(self, data, files):
    data_args = {'data': data}
    if not files:
      data_args = {'json': data}
    elif self.dataIsNested(data):
      raise ValueError("requests library can't combine files and nested dictionaries")
    return data_args

  def _create(self, endpoint, data, files=None):
    """Private method to create a new object, used by public object specific calls.

    @param      endpoint        object specific endpoint on REST server
    @param      data            dict with key/value pairs of new object
    @param      files           dict with file data, as binary blobs
                                or open file pointers
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    full_path = urljoin(self.url, endpoint)
    headers = {'Authorization': f"Token {self.token}"}
    data_args = self.prepareDataArgs(data, files)
    reply = self.session.post(full_path, **data_args, files=files,
                              headers=headers, verify=self.rootcert)
    return self.decodeReply(reply, HTTPStatus.CREATED)

  def _get(self, endpoint, parameters):
    """Private method to get an object, used by public object specific calls.

    @param      endpoint        object specific endpoint on REST server
    @param      parameters      dictionary of key/value pairs appended to GET request,
                                used by server to filter out objects
    @return                     RESTResult with decoded object(s) on success,
                                empty with `errors` set on failure
    """
    full_path = urljoin(self.url, endpoint)
    headers = {'Authorization': f"Token {self.token}"}
    reply = self.session.get(full_path, params=parameters, headers=headers,
                             verify=self.rootcert)
    return self.decodeReply(reply, HTTPStatus.OK)

  def _update(self, endpoint, data, files=None):
    """Private method to update an object, used by public object specific calls.

    @param      endpoint        object specific endpoint on REST server
    @param      data            dictionary with key/value pairs to update
    @param      files           dictionary with file data, as binary blobs
                                or open file pointers
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    full_path = urljoin(self.url, endpoint)
    headers = {'Authorization': f"Token {self.token}"}
    data_args = self.prepareDataArgs(data, files)
    reply = self.session.post(full_path, **data_args, files=files,
                              headers=headers, verify=self.rootcert)
    return self.decodeReply(reply, HTTPStatus.OK)

  def _delete(self, endpoint):
    """Private method to delete an object, used by public object specific calls.

    @param      endpoint        object specific endpoint on REST server
    @return                     RESTResult with deleted object's uid on success,
                                empty with `errors` set on failure
    """
    full_path = urljoin(self.url, endpoint)
    headers = {'Authorization': f"Token {self.token}"}
    reply = self.session.delete(full_path, headers=headers, verify=self.rootcert)
    return self.decodeReply(reply, HTTPStatus.OK)

  def _separateFiles(self, data, fields):
    files = None
    for fileField in fields:
      if fileField in data and not isinstance(data[fileField], str):
        data = data.copy()
        files = {fileField: data[fileField]}
        data.pop(fileField)
    return data, files

  # Scene
  def getScenes(self, filter):
    """Gets all scenes matching filter. If filter is None returns all scenes.

    @param      filter          dict with key/value pairs to filter matching objects
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._get("scenes", filter)

  def createScene(self, data):
    """Creates a new scene

    @param      data            dict with key/value pairs of new object. `map`
                                field accepts binary data or open file pointer.
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    data, files = self._separateFiles(data, ['map', 'thumbnail'])
    return self._create("scene", data, files)

  def getScene(self, uid):
    """Gets scene with `uid`

    @param      uid             uid of scene to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._get(f"scene/{uid}", None)

  def updateScene(self, uid, data):
    """Updates scene with `uid`

    @param      uid             uid of scene to update
    @param      data            dict with key/value pairs of new object. `map`
                                field accepts binary data or open file pointer.
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    data, files = self._separateFiles(data, ['map', 'thumbnail'])
    return self._update(f"scene/{uid}", data, files)

  def deleteScene(self, uid):
    """Deletes scene with `uid`

    @param      uid             uid of scene to delete
    @return                     RESTResult with deleted object's uid on success,
                                empty with `errors` set on failure
    """
    return self._delete(f"scene/{uid}")

  # Camera
  def getCameras(self, filter):
    """Gets all cameras matching filter. If filter is None returns all cameras.

    @param      filter          dict with key/value pairs to filter matching objects
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._get("cameras", filter)

  def createCamera(self, data):
    """Creates a new camera

    @param      data            dict with key/value pairs of new object.
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._create("camera", data)

  def getCamera(self, uid):
    """Gets camera with `uid`

    @param      uid             uid of camera to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._get(f"camera/{uid}", None)

  def updateCamera(self, uid, data):
    """Updates camera with `uid`

    @param      uid             uid of camera to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._update(f"camera/{uid}", data)

  def deleteCamera(self, uid):
    """Deletes camera with `uid`

    @param      uid             uid of camera to delete
    @return                     RESTResult with deleted object's uid on success,
                                empty with `errors` set on failure
    """
    return self._delete(f"camera/{uid}")

  def frame(self, uid, timestamp):
    """Gets frame from camera with `uid` which is near `timestamp`

    @param      uid             uid of camera to get frame from
    @param      timestamp       timestamp in ISO 8601 format
    """
    return self._get(f"frame", {'camera': uid, 'timestamp': timestamp})

  # Sensor
  def getSensors(self, filter):
    """Gets all sensors matching filter. If filter is None returns all sensors.

    @param      filter          dict with key/value pairs to filter matching objects
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._get("sensors", filter)

  def createSensor(self, data):
    """Creates a new sensor

    @param      data            dict with key/value pairs of new object. `map`
                                field accepts binary data or open file pointer.
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._create("sensor", data)

  def getSensor(self, uid):
    """Gets sensor with `uid`

    @param      uid             uid of sensor to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._get(f"sensor/{uid}", None)

  def updateSensor(self, uid, data):
    """Updates sensor with `uid`

    @param      uid             uid of sensor to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._update(f"sensor/{uid}", data)

  def deleteSensor(self, uid):
    """Deletes sensor with `uid`

    @param      uid             uid of sensor to delete
    @return                     RESTResult with deleted object's uid on success,
                                empty with `errors` set on failure
    """
    return self._delete(f"sensor/{uid}")

  # Region
  def getRegions(self, filter):
    """Gets all regions matching filter. If filter is None returns all regions.

    @param      filter          dict with key/value pairs to filter matching objects
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._get("regions", filter)

  def createRegion(self, data):
    """Creates a new region

    @param      data            dict with key/value pairs of new object. `map`
                                field accepts binary data or open file pointer.
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._create("region", data)

  def getRegion(self, uid):
    """Gets region with `uid`

    @param      uid             uid of region to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._get(f"region/{uid}", None)

  def updateRegion(self, uid, data):
    """Updates region with `uid`

    @param      uid             uid of region to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._update(f"region/{uid}", data)

  def deleteRegion(self, uid):
    """Deletes region with `uid`

    @param      uid             uid of region to delete
    @return                     RESTResult with deleted object's uid on success,
                                empty with `errors` set on failure
    """
    return self._delete(f"region/{uid}")

  # Tripwire
  def getTripwires(self, filter):
    """Gets all tripwires matching filter. If filter is None returns all tripwires.

    @param      filter          dict with key/value pairs to filter matching objects
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._get("tripwires", filter)

  def createTripwire(self, data):
    """Creates a new tripwire

    @param      data            dict with key/value pairs of new object. `map`
                                field accepts binary data or open file pointer.
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._create("tripwire", data)

  def getTripwire(self, uid):
    """Gets tripwire with `uid`

    @param      uid             uid of tripwire to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._get(f"tripwire/{uid}", None)

  def updateTripwire(self, uid, data):
    """Updates tripwire with `uid`

    @param      uid             uid of tripwire to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._update(f"tripwire/{uid}", data)

  def deleteTripwire(self, uid):
    """Deletes tripwire with `uid`

    @param      uid             uid of tripwire to delete
    @return                     RESTResult with deleted object's uid on success,
                                empty with `errors` set on failure
    """
    return self._delete(f"tripwire/{uid}")

  # Assets
  def getAssets(self, filter):
    """Gets all assets matching filter. If filter is None returns all assets.

    @param      filter          dict with key/value pairs to filter matching objects
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._get("assets", filter)

  def createAsset(self, data):
    """Creates a new asset

    @param      data            dict with key/value pairs of new object. `map`
                                field accepts binary data or open file pointer.
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._create("asset", data)

  def getAsset(self, uid):
    """Gets asset with `uid`

    @param      uid             uid of asset to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._get(f"asset/{uid}", None)

  def updateAsset(self, uid, data):
    """Updates asset with `uid`

    @param      uid             uid of asset to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._update(f"asset/{uid}", data)

  def deleteAsset(self, uid):
    """Deletes asset with `uid`

    @param      uid             uid of asset to delete
    @return                     RESTResult with deleted object's uid on success,
                                empty with `errors` set on failure
    """
    return self._delete(f"asset/{uid}")

  # child
  def getChildScene(self, filter):
    """Gets all child scenes matching filter. If filter is None returns all child scenes.

    @param      filter          dict with key/value pairs to filter matching objects
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._get("scenes/child", filter)

  # Users
  def getUsers(self, filter):
    """Gets all users matching filter. If filter is None returns all users.

    @param      filter          dict with key/value pairs to filter matching objects
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._get("users", filter)

  def createUser(self, data):
    """Creates a new user

    @param      data            dict with key/value pairs of new object.
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._create("user", data)

  def getUser(self, username):
    """Gets user with `username`

    @param      username        username of user to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._get(f"user/{username}", None)

  def updateUser(self, username, data):
    """Updates user with `username`

    @param      username        username of user to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._update(f"user/{username}", data)

  def deleteUser(self, username):
    """Deletes user with `username`

    @param      username        username of user to delete
    @return                     RESTResult with deleted object's uid on success,
                                empty with `errors` set on failure
    """
    return self._delete(f"user/{username}")

  # CalibrationMarker
  def getCalibrationMarkers(self, filter):
    """Gets all calibration markers matching filter. If filter is None returns all calibration markers.

    @param      filter          dict with key/value pairs to filter matching objects
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._get("calibrationmarkers", filter)

  def getCalibrationMarker(self, marker_id):
    """Gets calibration marker with `marker_id`

    @param      marker_id          marker_id of calibration marker to get
    @return                        RESTResult with decoded object on success,
                                   empty with `errors` set on failure
    """
    return self._get(f"calibrationmarker/{marker_id}", None)

  def createCalibrationMarker(self, data):
    """Creates a new calibration marker

    @param      data            dict with key/value pairs of new object.
    @return                     RESTResult with decoded objects on success,
                                empty with `errors` set on failure
    """
    return self._create("calibrationmarker", data)

  def updateCalibrationMarker(self, uid, data):
    """Updates calibration marker with `uid`

    @param      uid             uid of calibration marker to get
    @return                     RESTResult with decoded object on success,
                                empty with `errors` set on failure
    """
    return self._update(f"calibrationmarker/{uid}", data)

  def deleteCalibrationMarker(self, uid):
    """Deletes calibration marker with `uid`

    @param      uid             uid of calibration marker to delete
    @return                     RESTResult with deleted object's uid on success,
                                empty with `errors` set on failure
    """
    return self._delete(f"calibrationmarker/{uid}")

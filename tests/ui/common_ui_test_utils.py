#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import cv2
import json
import time
import random
import filecmp
import tempfile
import functools
import subprocess
import numpy as np

from PIL import Image
from io import BytesIO
from typing import Dict
from urllib.parse import urlparse
from pyvirtualdisplay import Display
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from tests.common_test_utils import record_test_result
from tests.ui.browser import Browser, By, NoSuchElementException

# FIXME - APP_PROPER_NAME is not the right way to validate correct page load
APP_PROPER_NAME = 'Intel® SceneScape'
# from manager.settings import APP_PROPER_NAME

TEST_SCENE_NAME = "Demo"
TEST_SCENE_ID = "3bc091c7-e449-46a0-9540-29c499bca18c"
TEST_MEDIA_PATH = os.path.dirname(os.path.realpath(__file__)) + "/test_media/"

DEFAULT_IMAGE_MSE_THRESHOLD = 0.2

# Constants values to indicate the height, length and the upper left point of
# the triangular sensor for the function create_triangle_sensor()
DEFAULT_SENSOR_TRIANGLE_HEIGHT = 600
DEFAULT_SENSOR_TRIANGLE_LENGTH = 800
DEFAULT_SENSOR_TRIANGLE_UPPER_LEFT_POINT = (-400, -300)

def check_page_login(browser, params):
  """! Logs into the Scenescape web UI.
  @param    browser                    Object wrapping the Selenium driver.
  @param    params                     Dict of test parameters.
  @return   bool                       Boolean representing success.
  """
  logged_in = False
  if browser.getPage(params['weburl'], APP_PROPER_NAME):
    print("Logging in")
    logged_in = browser.login(params['user'], params['password'], params['weburl'])
    print("Logged in: ", logged_in)
  return logged_in

def create_object_library(browser, object_name, max_radius=None, tracking_radius=None,
                          max_height=None, mark_color=None, model_file=None):
  """! Adds an Object to the Object Library.
  @param    browser                    Object wrapping the Selenium driver.
  @param    object_name                Class of the tracked Object.
  @param    max_radius                 Max Object Radius (meters).
  @param    tracking_radius            Tracking radius (meters).
  @param    max_height                 Max Object Height (meters).
  @param    mark_color                 Mark Color used for representation.
  @param    model_file                 Path to file to upload.
  @return   bool                       Boolean representing success.
  """
  browser.find_element(By.ID, "nav-object-library").click()
  obj_record = browser.find_elements(By.XPATH, "//td[text()='{0}']".format(object_name))
  if len(obj_record) > 0:
    print("3D object already exists, deleting it before proceeding ...")
    if not delete_object_library(browser, object_name):
      return False
  browser.find_element(By.CSS_SELECTOR, "a[href^=\"/asset/create/\"]").click()
  # Fill in the form
  browser.find_element(By.ID, 'id_name').send_keys(object_name)
  if max_radius:
    browser.find_element(By.ID, "id_max_radius").clear()
    browser.find_element(By.ID, "id_max_radius").send_keys(max_radius)
  if tracking_radius:
    browser.find_element(By.ID, "id_tracking_radius").clear()
    browser.find_element(By.ID, "id_tracking_radius").send_keys(tracking_radius)
  if max_height:
    browser.find_element(By.ID, "id_max_height").clear()
    browser.find_element(By.ID, "id_max_height").send_keys(max_height)
  if mark_color:
    browser.find_element(By.ID, "id_mark_color").clear()
    browser.find_element(By.ID, "id_mark_color").send_keys(mark_color)
  if model_file:
    browser.find_element(By.ID, "id_model_3d").send_keys(model_file)
  browser.find_element(By.CSS_SELECTOR, "input[value=\"Add New Object\"]").click()
  # Verify object is shown in list
  obj_record = browser.find_elements(By.XPATH, "//td[text()='{0}']".format(object_name))
  if len(obj_record) == 0:
    return False
  print('Object Library asset "{0}" created!'.format(object_name))
  return True

def delete_object_library(browser, object_name):
  """! Deletes an Object from the Object Library.
  @param    browser                    Object wrapping the Selenium driver.
  @param    object_name                Name of the Object.
  @return   bool                       Boolean representing success.
  """
  # navigate to 3D Assets page
  browser.find_element(By.ID, "nav-object-library").click()
  browser.find_element(By.XPATH, "//td[text()='{0}']/parent::tr//i[contains(@class, 'bi-trash')]/parent::a".format(object_name)).click()
  # click on delete confirmation button
  browser.find_element(By.CSS_SELECTOR, "input[value^=\"Yes, Delete the Object!\"]").click()
  obj_record = browser.find_elements(By.XPATH, "//td[text()='{0}']".format(object_name))
  if len(obj_record) > 0:
    return False
  print('Object Library asset "{0}" deleted!'.format(object_name))
  return True

def delete_scene(browser, scene_name):
  """! Delete named Scenescape scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    scene_name                 Name of the scene to be deleted.
  @return   bool                       Boolean representing success.
  """
  browser.find_element(By.ID, "nav-scenes").click()
  time.sleep(1)
  browser.find_element(By.NAME, scene_name).find_element(By.NAME, "Delete",).click()
  time.sleep(1)
  print("Confirmation appeared: " + str(browser.find_element(By.XPATH, "//*[@type = 'submit']").get_attribute("value")))
  browser.find_element(By.XPATH, "//*[@type = 'submit']").click()
  time.sleep(1)
  if scene_name not in browser.page_source:
    print(scene_name + " deleted")
    return True
  return False

def take_screenshot(browser, element, path):
  """! Function to take a screenshot of the requested element.
  @param    browser                    The browser used in the test.
  @param    element                    Element to screen shot.
  @param    path                       Path used to save the screenshot.
  @return   screenshot                 Base64 encoded screenshot.
  """
  #Adding viewport-adjustment snip to handle out of bounds error
  # minimum window size required: {'width': 1550, 'height': 838}
  min_viewport_width = 1920
  min_viewport_height = 1080
  viewport_dimensions = browser.execute_script("return [window.innerWidth, window.innerHeight];")
  viewport_width = viewport_dimensions[0]
  viewport_height = viewport_dimensions[1]
  if viewport_width < min_viewport_width or viewport_height < min_viewport_height:
    browser.setViewportSize( min_viewport_width, min_viewport_height )
    print("Viewport size set to:", browser.execute_script("return [window.innerWidth, window.innerHeight];"))
  return element.screenshot(path)

def read_images(img_array, file_path):
  """! Function to read array of images.
  @param    img_array                  Array to store images.
  @param    file_path                  Array of paths to read.
  @return   array                      Updated array of images.
  """
  for file in file_path:
    image = cv2.imread(file)
    img_array.append(image)
  return img_array

def add_child_scene(browser, parent, child):
  """! Function to link child scene to parent scene
  @param    parent                  The name of the parent scene.
  @param    child                   The name of the child scene.
  @return   bool                    Boolean representing success.
  """
  browser.find_element(By.ID, "nav-scenes").click()
  if child not in browser.page_source or parent \
    not in browser.page_source:
    print("scenes {} and {} do not exist!".format(child, parent))
    return False

  parent = "scene-manage-{}".format(parent)
  browser.find_element(By.ID, parent).click()
  browser.find_element(By.ID, "children-tab").click()
  browser.find_element(By.ID, "new-child").click()
  select = Select(browser.find_element(By.ID, "id_child"))
  select.select_by_visible_text(child)
  browser.find_element(By.ID, "add-child-scene").click()
  return True

def update_child_scene(browser, parent, child, transform):
  """! Function to update child scene with pose information
  @param    parent                  The name of the parent scene.
  @param    child                   The name of the child scene.
  @return   transform               Euler angle transform with pose information.
  @return   bool                    Boolean representing success.
  """
  browser.find_element(By.ID, "nav-scenes").click()
  if child not in browser.page_source or parent \
    not in browser.page_source:
    print("scenes {} and {} do not exist!".format(child, parent))
    return False

  parent = "scene-manage-{}".format(parent)
  browser.find_element(By.ID, parent).click()
  browser.find_element(By.ID, "children-tab").click()
  update_element = "child-update-{}".format(child)
  browser.find_element(By.ID, update_element).click()
  select = Select(browser.find_element(By.ID, "id_transform_type"))
  select.select_by_visible_text(transform['transform'])

  for id in range(1, 4):
    translation_field = browser.find_element(By.ID, "id_transform{}".format(id))
    translation_field.clear()
    translation_field.send_keys(transform['pose']['translation'][id - 1])

  for id in range(4, 7):
    rotation_field = browser.find_element(By.ID, "id_transform{}".format(id))
    rotation_field.clear()
    rotation_field.send_keys(transform['pose']['rotation'][id - 4])

  scale = browser.find_element(By.ID, "id_transform7")
  scale.clear()
  scale.send_keys(transform['pose']['scale'][0])
  browser.find_element(By.ID, "update-child").click()
  return True

def delete_child_scene(browser, parent, child):
  """! Function to delete link child from parent scene
  @param    parent                  The name of the parent scene.
  @param    child                   The name of the child scene.
  @return   bool                    Boolean representing success.
  """
  browser.find_element(By.ID, "nav-scenes").click()
  if child not in browser.page_source or parent \
    not in browser.page_source:
    print("scenes {} and {} do not exist!".format(child, parent))
    return False

  parent = "scene-manage-{}".format(parent)
  browser.find_element(By.ID, parent).click()
  browser.find_element(By.ID, "children-tab").click()
  delete_element = "child-delete-{}".format(child)
  browser.find_element(By.ID, delete_element).click()
  confirm_delete_element = "confirm-delete"
  browser.find_element(By.ID, confirm_delete_element).click()
  return True

def create_scene(browser, scene_name, scale, map_image):
  """! Create a Scenescape scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    scene_name                 Name of the scene to be created.
  @param    scale                      Scale of the scene map relative to reality in pixels per meter.
  @param    map_image                  Path to the scene map.
  @return   bool                       Boolean representing success.
  """
  browser.find_element(By.ID, "nav-scenes").click()
  if scene_name in browser.page_source:
    print("Scene already exists, deleting it before proceeding ...")
    if not delete_scene(browser, scene_name):
      return False

  browser.find_element(By.ID, "new_scene").click()
  browser.find_element(By.ID, "id_name").click()
  browser.find_element(By.ID, "id_name").send_keys(scene_name)
  time.sleep(1)
  browser.find_element(By.ID, "id_map").send_keys(map_image)
  browser.find_element(By.ID, "id_scale").click()
  browser.find_element(By.ID, "id_scale").send_keys(scale)
  browser.find_element(By.ID, "save").click()
  time.sleep(1)
  browser.find_element(By.NAME, scene_name)
  return True

def inject_json(input_text, browser, element, form_id):
  """! This function takes a serialized json object, fills a given form
  and submits
  @param    input_text                 Serialized json object.
  @param    browser                    Object wrapping the Selenium driver.
  @param    element                    The component of the html form.
  @return   None
  """
  input = browser.find_element(By.ID, element)
  browser.execute_script("document.getElementById('id_rois').type='text'")
  input.clear()
  input.send_keys(input_text)
  script = "document.getElementById({}).submit()".format(form_id)
  browser.execute_script(script)
  return

def create_tripwire_by_ratio(browser, tripwire_name, x_ratio):
  """! This function creates a tripwire by filling in the tripwire
  form and submitting it directly.
  @param    browser                    Object wrapping the Selenium driver.
  @param    tripwire_name              Name of the created tripwire.
  @param    x_ratio                    Ratio of scene width.
  @return   points                     List of tripwire points.
  """
  # Unhide hidden fields so Selenium can access them
  browser.execute_script("document.getElementById('scale').type='text'")
  browser.execute_script("document.getElementById('tripwires').type='text'")
  # Move controls out of the way
  browser.execute_script("document.getElementById('scene-controls').removeAttribute('id')")

  scale_field = browser.find_element(By.ID, "scale")
  scale = float(scale_field.get_attribute("value"))

  # Create tripwire across the center point (origin is bottom left in meters)
  svg = browser.find_element(By.ID, "svgout")
  cx = svg.size['width'] / (2 * scale)
  cy = svg.size['height'] / (2 * scale)
  form_id = '"roi-form"'

  tripwires = []
  points = []
  dx = cx * x_ratio
  points.append([ cx - dx, cy ])
  points.append([ cx + dx, cy ])
  tripwires.append({"title": tripwire_name, "points": points})
  tripwires_text = json.dumps(tripwires)

  inject_json(tripwires_text, browser, "tripwires", form_id)
  time.sleep(2)
  return points

def create_tripwire(browser, tw_name):
  """! Creates a tripwire in the scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    tw_name                    Name of the tripwire to be created.
  @return   bool                       Boolean representing success.
  """
  tripwire_points = None
  try:
    browser.find_element(By.ID, "tripwires-tab").click()
    print("Clicked on the 'Tripwires' tab")
    browser.find_element(By.ID,"new-tripwire").click()
    browser.find_element(By.ID,"svgout").click()
    print("Tripwire Appeared")

    tripwire = browser.find_element(By.ID,"tripwire_0")
    points_0 = browser.find_elements(By.CLASS_NAME,"point_0")
    points_1 = browser.find_elements(By.CLASS_NAME,"point_1")
    point_0 = points_0[-1]
    point_1 = points_1[-1]
    action = browser.actionChains()
    action.drag_and_drop_by_offset(point_0,-400,0).perform()
    action.drag_and_drop_by_offset(point_1,400,0).perform()

    tripwires = browser.find_element(By.ID, "tripwires")
    tripwire_points = tripwires.get_attribute('value')
    tripwire_points = json.loads(tripwire_points)[0]['points']
    tripwire_points[0] = [float(point) for point in tripwire_points[0]]
    tripwire_points[1] = [float(point) for point in tripwire_points[1]]

    tripwire_titles = browser.find_elements(By.CSS_SELECTOR,".card-body .tripwire-title")
    tripwire_name = tripwire_titles[-1]
    tripwire_name.click()
    tripwire_name.clear()
    tripwire_name.send_keys(tw_name)
    print("Updated name of the tripwire to ", tw_name)
    browser.find_element(By.ID,"save-trips").click()
    print("clicked 'Save Regions and Tripwires'")
    return tripwire_points
  except Exception as e:
    print("Failed creating and saving new tripwire!!!, error: ", e)
  return tripwire_points

def modify_tripwire(browser):
  """! Modifies a tripwire in the scene.
  @param    browser                    Object wrapping the Selenium driver.
  @return   bool                       Boolean representing success.
  """
  try:
    # creating a long horizontal tripwire
    points_0 = browser.find_elements(By.CLASS_NAME, "point_0")
    points_1 = browser.find_elements(By.CLASS_NAME, "point_1")
    point_0 = points_0[-1]
    point_1 = points_1[-1]

    action = browser.actionChains()
    action.drag_and_drop_by_offset(point_0, -100, 0).perform()
    action.drag_and_drop_by_offset(point_1, 200, 0).perform()
    print("Moved the ends of tripwire")

    browser.find_element(By.ID,"save-trips").click()
    print("clicked 'Save Regions and Tripwires'")

  except Exception as e:
    print("Failed modifying tripwire!, error: ", e)
    return False
  return True

def delete_tripwire(browser, tw_uuid):
  browser.find_element(By.ID, "tripwires-tab").click()
  print("Click on the 'Tripwires' tab")
  browser.find_element(By.ID, f"form-tripwire_{tw_uuid}").find_element(By.CLASS_NAME, "tripwire-remove").click()
  browser.switch_to.alert.accept()
  print("Tripwire deleted!")
  return

def verify_tripwire_persistence(browser, tw_name):
  """! Checks that tripwire name is in the scene tripwire tab.
  @param    browser                    Object wrapping the Selenium driver.
  @param    tw_name                    Name of the tripwire to be created.
  @return   bool                       Boolean representing success.
  """
  try:
    browser.find_element(By.ID, "tripwires-tab").click()
    print("Verifying persistence of tripwire after saving...")
    tripwire_titles = browser.find_elements(By.CSS_SELECTOR,".card-body .tripwire-title")
    if not tripwire_titles:
      print(f"No tripwires were found!")
      return False
    tripwire_name = tripwire_titles[-1]
    if tripwire_name.get_attribute('value') != tw_name:
      print(f"Expected name: {tw_name} - Returned name: {tripwire_name.get_attribute('value')}")
      return False
    print(f"Tripwire '{tw_name}' is persistent")
    return True
  except Exception as e:
    print("Error in verifying tripwire persistence", e)
  return False

def move_tripwire(browser):
  """! Moves tripwire randomly.
  @param    browser                    Object wrapping the Selenium driver.
  @return   bool                       Boolean representing success.
  """
  try:
    tripwire = browser.find_element(By.ID,"tripwire_0")
    if tripwire == None:
      return False
    points_0 = browser.find_elements(By.CLASS_NAME,"point_0")
    points_1 = browser.find_elements(By.CLASS_NAME,"point_1")
    point_0 = points_0[-1]
    point_1 = points_1[-1]

    action = browser.actionChains()
    action.drag_and_drop_by_offset(point_0,0,random.randint(30,80)).perform()
    action.drag_and_drop_by_offset(point_1,random.randint(30,80),0).perform()
    print("Moved the ends of tripwire")
    return True
  except Exception as e:
    print("Error in moving tripwire:",e)
  return False

def change_cam_calibration(browser, dragdropPoint, scrollPoint, save_calibration=True):
  """! Changes the camera calibration by moving a point in the camera view and scene view.
  @param    browser                    Object wrapping the Selenium driver.
  @param    dragdropPoint              Location to where we drag and drop camera calibration point
  @param    scrollPoint                Location to which we scroll the page
  @param    save_calibration           If True: save the calibration changes permanently.
                                       If False: apply calibration changes temporarily
                                       without saving them. Changes will be discarded upon
                                       session termination or Reset Points button.
  @return   bool                       Boolean representing success.
  """
  browser.find_element(By.ID,'cam_calibrate_1').click()
  camera_canvas = browser.find_elements(By.ID,"camera_canvas")
  map_canvas = browser.find_elements(By.ID,"map_canvas")
  if camera_canvas and map_canvas == None:
    return False
  cam_draggable = browser.find_elements(By.CSS_SELECTOR,"#camera .draggable.p1")
  map_draggable = browser.find_elements(By.CSS_SELECTOR,"#map .draggable.p1")
  cam_p1 = cam_draggable[-1]
  map_p1 = map_draggable[-1]

  action = browser.actionChains()
  action.drag_and_drop_by_offset(cam_p1,dragdropPoint[0],dragdropPoint[1]).perform()
  time.sleep(1)
  browser.execute_script("window.scrollTo({},{});".format(scrollPoint[0], scrollPoint[1]))
  action.drag_and_drop_by_offset(map_p1,dragdropPoint[0],dragdropPoint[1]).perform()
  print("Changed the Camera Perspective")
  if save_calibration:
    browser.find_element(By.NAME,"calibrate_save").click()
    print("clicked 'Save Calibration'")
  else:
    print("It has been chosen not to save the calibration changes.")
  return True

def check_cam_calibration(browser, not_expected_cam=(0, 0), not_expected_map=(0, 0)):
  """! Checks whether the camera calibration has moved the points in the camera view and scene view
  to a point that differs from the passed parameter.
  @param    browser                    Object wrapping the Selenium driver.
  @param    not_expected_point         Not expected cooridinates for a saved calibration point
  @return   bool                       Boolean representing success.
  """
  try:
    browser.find_element(By.ID,'cam_calibrate_1').click()
    cam_values_init = get_calibration_points(browser, 'camera')
    map_values_init = get_calibration_points(browser, 'map')
    if (cam_values_init[0] != not_expected_cam) and (map_values_init[0] != not_expected_map):
      print(f"Perspective changed to: Cam coord1: '{cam_values_init[0]}' Map coord1: '{map_values_init[0]}'")
      return True
    else:
      print("Perspective has not changed!")
  except Exception as e:
    print("Error in verifying perspective persistence: ",e)
  return False

def check_calibration_initialization(browser, expected_cam_values, expected_map_values):
  """! Checks whether the camera calibration has moved the points in the camera view and scene view
  to the point passed as expected_points parameters.
  @param    browser                    Object wrapping the Selenium driver.
  @param    expected_cam_values        Expected camera cooridinates for a saved calibration point or points
  @param    expected_map_values        Expected map cooridinates for a saved calibration point or points
  @return   bool                       Boolean representing success.
  """
  calibration = True
  try:
    browser.find_element(By.ID,'cam_calibrate_1').click()
    cam_values_init = get_calibration_points(browser, 'camera')
    map_values_init = get_calibration_points(browser, 'map')
    for index in range(len(expected_cam_values)):
      if (cam_values_init[index] == expected_cam_values[index]) and (map_values_init[index] == expected_map_values[index]):
        print(f"Calibration persists: Cam coord {index}: '{cam_values_init[index]}', Map coord {index}: '{map_values_init[index]}'")
      else:
        print(f"Calibration for point {index} not as expected:")
        print(f"Cam coord {index} is: '{cam_values_init[index]}', expected: '{expected_cam_values[index]}'")
        print(f"Map coord {index} is: '{map_values_init[index]}', expected: '{expected_map_values[index]}'")
        calibration = False
  except Exception as e:
    print("Error in verifying perspective persistence: ",e)
    calibration = False
  return calibration

def get_calibration_points(browser, calibration_type, initial_transforms=True):
  """! Return initial values of calibration points for camera or map.
  @param    browser                    Object wrapping the Selenium driver.
  @param    calibration_type           String to specify 'camera' or 'map' calibration points
  @param    initial_transforms         If True: return initial calibration transform stored in database.
                                       If False: return temporary calibration changes before save.
  @return   list                       List of calibration points represented as four pairs of float x, y values.
  """
  try:
    browser.execute_script("document.querySelectorAll('.display-none').forEach(e => {e.style.display = 'block';})")
    transforms_type = 'initial-id_transforms' if initial_transforms else 'id_transforms'
    init_id_transforms = browser.find_element(By.ID, transforms_type).get_attribute('value')
    init_id_list = init_id_transforms.strip().split(",")
    init_id_pairs = list(zip(map(float, init_id_list[::2]), map(float, init_id_list[1::2])))
    if calibration_type == 'camera':
      calibration_values_init = init_id_pairs[:4]
      print(f"Camera coordinate points: {calibration_values_init}")
    elif calibration_type == 'map':
      calibration_values_init = init_id_pairs[4:8]
      print(f"Map coordinate points: {calibration_values_init}")
    else:
      raise ValueError("Invalid calibration type specified. Use 'camera' or 'map'.")
    return calibration_values_init
  except (ValueError, Exception) as e:
    print("Error in getting camera calibration points: ", e)
  return None

def change_map_perspective(browser):
  """! Change map perspective. """
  MAP_POINT_X_OFFSET = -400
  MAP_POINT_Y_OFFSET = 0
  try:
    map_point = browser.find_element(By.ID, "scene")
    action = browser.actionChains()
    action.drag_and_drop_by_offset(map_point, MAP_POINT_X_OFFSET, MAP_POINT_Y_OFFSET).perform()
    return True
  except Exception as e:
    print("Error in changing map perspective:",e)
  return False

def validate_scene_data(browser, scene_name, scale, map_image):
  """! Checks the scene data is the same as expected.
  @param    browser                    Object wrapping the Selenium driver.
  @param    scene_name                 Name of the scene being checked.
  @param    scale                      Scale of the scene map relative to reality in pixels per meter.
  @param    map_image                  Path to the scene map.
  @return   bool                       :w
  Boolean representing success.
  """
  try:
    if scene_name in browser.page_source:
      print("Scene is accessible from the list of scenes")
      browser.find_element(By.NAME, scene_name).find_element(By.NAME, "Edit").click()
      print(browser.page_source)
      get_name = browser.find_element(By.ID, "id_name").get_attribute("value")
      get_scale = browser.find_element(By.ID, "id_scale").get_attribute("value")
      get_image_text = browser.find_element(By.CSS_SELECTOR, "#map_wrapper a").get_attribute('text')
      if get_name == scene_name and float(get_scale) == float(scale) and get_image_text.split('_')[0] in map_image:
        print("scene_name: " + get_name)
        print("scale_value: " + get_scale)
        print("map: " + get_image_text)
        return True
    return False
  except Exception as e:
    print("Exception occurred while adding additional maps: " + str(e))
  return False

def add_camera_to_scene(browser, scene_name, camera_id, camera_name):
  """! Adds a camera to the named scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    scene_name                 Name of the scene being checked.
  @param    camera_id                  ID of the camera to be added.
  @param    camera_name                Name of the camera to be added.
  @return   bool                       Boolean representing success.
  """
  try:
    if scene_name in browser.page_source:
      browser.find_element(By.XPATH, "//*[text()='" + scene_name + "']/parent::*/div[2]/div/a[1]").click()
      browser.find_element(By.ID, "new-camera").click()
      browser.find_element(By.ID, "id_sensor_id").send_keys(camera_id)
      browser.find_element(By.ID, "id_name").send_keys(camera_name)
      browser.find_element(By.ID, "id_scene").click()
      dropdown = browser.find_element(By.ID, "id_scene")
      dropdown.find_element(By.XPATH, "//option[. = '"+scene_name+"']").click()
      browser.find_element(By.CSS_SELECTOR, ".btn:nth-child(1)").click()
      print("Camera " + camera_name + " added to scene " + scene_name)
      return True
  except Exception as e:
    print("Exception occurred while adding additional maps: " + str(e))
  return False

def delete_camera(browser, camera_name):
  """! Delete named camera from the scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    camera_name                Name of the camera to be added.
  @return   bool                       Boolean representing success.
  """
  browser.find_element(By.LINK_TEXT, "Cameras").click()
  rows_to_delete = browser.find_elements(By.XPATH, "//td[text()='"+ camera_name +"']/parent::tr")
  for r in rows_to_delete:
    browser.find_element(By.XPATH, "//td[text()='"+ camera_name +"']/parent::tr//a[contains(@href,'cam/delete/')]").click()
    browser.find_element(By.XPATH, "//*[@type = 'submit']").click()
    browser.find_element(By.LINK_TEXT, "Cameras").click()

  # Page is redirected to respective scene page verify the absence of the camera in that page
  if camera_name not in browser.page_source:
    print(f"Deleted {camera_name} from Cameras page")
    return True
  print("Error while deleting camera:", camera_name)
  return False

def create_sensor(browser, sensor_id, sensor_name, scene_name):
  """! Creates a default sensor covering the entire scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    sensor_id                  ID of the sensor to be added.
  @param    sensor_name                Name of the sensor to be added.
  @param    scene_name                 Name of the scene being checked.
  @return   None
  """
  browser.find_element(By.ID, "id_sensor_id").send_keys(sensor_id)
  browser.find_element(By.ID, "id_name").send_keys(sensor_name)
  browser.find_element(By.ID, "id_scene").click()
  dropdown = browser.find_element(By.ID, "id_scene")
  dropdown.find_element(By.XPATH, "//option[. = '" + scene_name + "']").click()
  add_button_xpath = "//input[@value = 'Add New Sensor']"
  browser.find_element(By.XPATH, add_button_xpath).click()
  return

def create_sensor_from_scene(browser, sensor_id, sensor_name, scene_name):
  """! From the scene page creates a default sensor covering the entire scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    sensor_id                  ID of the sensor to be added.
  @param    sensor_name                Name of the sensor to be added.
  @param    scene_name                 Name of the scene being checked.
  @return   bool                       Boolean representing success.
  """
  assert navigate_to_scene(browser, scene_name)
  browser.find_element(By.ID, "sensors-tab").click()
  browser.find_element(By.ID, "new-sensor").click()
  create_sensor(browser, sensor_id, sensor_name, scene_name)
  assert navigate_to_scene(browser, scene_name)

  # Page is redirected to respective scene page verify the presence of the sensor in that page
  if sensor_name in browser.page_source:
    print(f"Added {sensor_name} to the scene {scene_name}")
    return True
  print("Error while creating sensor:", sensor_name)
  return False

def create_sensor_from_sensors_page(browser, sensor_id, sensor_name, scene_name):
  """! From the sensor calibration page creates a default sensor covering the entire scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    sensor_id                  ID of the sensor to be added.
  @param    sensor_name                Name of the sensor to be added.
  @param    scene_name                 Name of the scene being checked.
  @return   bool                       Boolean representing success.
  """
  browser.find_element(By.LINK_TEXT, "Sensors").click()
  browser.find_element(By.LINK_TEXT, '+ New Sensor').click()
  create_sensor(browser, sensor_id, sensor_name, scene_name)

  # Page is redirected to respective scene page verify the presence of the sensor in that page
  if sensor_name in browser.page_source:
    print(f"Added {sensor_name} to the scene {scene_name}")
    return True
  print("Error while creating sensor:", sensor_name)
  return False

def open_scene_manage_sensors_tab(browser):
  """! Opens Manage Sensor tab from the Scene page.
  @param    browser                    Object wrapping the Selenium driver.
  @return   True                       Returns True if the action is successful.
  """
  try:
    browser.find_element(By.ID, "sensors-tab").click()
    browser.find_element(By.CSS_SELECTOR, "#sensors > div > div > div > div > div > a:nth-child(1)").click()
    return True
  except:
    return False

def save_sensor_calibration(browser):
  """! Saves sensor calibration in the Manage Sensor tab.
  @param    browser                    Object wrapping the Selenium driver.
  @return   True                       Returns True if the action is successful.
  """
  try:
    browser.find_element(By.NAME, "save").click()
    return True
  except:
    return False

def create_circle_sensor(browser, radius=250):
  """! Creates a sensor that covers a circular area.
  @param    browser                    Object wrapping the Selenium driver.
  @param    radius                     Radius of the circular area covered by the sensor.
  @return   True                       Returns True if the action is successful.
  """
  browser.find_element(By.CSS_SELECTOR, "#id_area_1").click()
  slider = browser.find_element(By.ID, "id_sensor_r")
  circle_action = browser.actionChains()
  circle_action.click_and_hold(slider).move_by_offset(radius, 0).release().perform()
  return save_sensor_calibration(browser)

def create_triangle_sensor(browser, triangle_height=DEFAULT_SENSOR_TRIANGLE_HEIGHT, triangle_length=DEFAULT_SENSOR_TRIANGLE_LENGTH, upper_left_point=DEFAULT_SENSOR_TRIANGLE_UPPER_LEFT_POINT):
  """! Creates a sensor that covers a triangular area.
  @param    browser                    Object wrapping the Selenium driver.
  @param    triangle_height            Height of the triangular area.
  @param    triangle_length            Length of the triangular area.
  @param    upper_left_point           Location of the triangular areas upper left point relative to the center of element svgout.
  @return   True                       Returns True if the action is successful.
  """
  browser.find_element(By.CSS_SELECTOR, "#id_area_2").click()
  svg = browser.find_element(By.ID, "svgout")
  action_chain = browser.actionChains()
  action_chain.move_to_element_with_offset(svg, upper_left_point[0], upper_left_point[1]).click().perform()
  action_chain.move_by_offset(0, triangle_height).click().perform()
  action_chain.move_by_offset(triangle_length, 0).click().perform()
  action_chain.move_by_offset(-triangle_length, -triangle_height).click().perform()
  return save_sensor_calibration(browser)

def delete_sensor(browser, sensor_name):
  """! Deletes named sensor from the scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    sensor_name                Name of the sensor to be added.
  @return   bool                       Boolean representing a success.
  """
  browser.find_element(By.LINK_TEXT, "Sensors").click()
  browser.find_element(By.XPATH, "//td[text()='" + sensor_name
                       + "']/parent::tr/td[5]/a").click()
  browser.find_element(By.XPATH, "//*[@type = 'submit']").click()

  # verify the absence of the sensor
  if sensor_name not in browser.page_source:
    print(f"Deleted {sensor_name} from Sensors page")
    return True
  print("Error while deleting sensor:", sensor_name)
  return False

def verify_sensor_list(browser, sensor_names):
  """! Navigates to sensor page via the navigation bar and checks that the
  names in sensor_names are listed on the sensor page.
  @param    browser                    Object wrapping the Selenium driver.
  @param    sensor_names               List of the sensors to be checked.
  @return   bool                       Boolean representing a success.
  """
  try:
    browser.find_element(By.CSS_SELECTOR, ".navbar-nav > .nav-item:nth-child(3) > .nav-link").click()
    time.sleep(1)
    for sensor_name in sensor_names:
      browser.find_element(By.XPATH, "//td[text()='" + sensor_name + "']")
    return True
  except:
    return False

def verify_sensor_under_scene(browser, sensor_names):
  """! Navigates to sensor tab in the scene page and checks that the names in sensor_names are listed there.
  @param    browser                    Object wrapping the Selenium driver.
  @param    sensor_names               List of the sensors to be checked.
  @return   bool                       Boolean representing a success.
  """
  try:
    browser.find_element(By.ID, "sensors-tab").click()
    time.sleep(1)
    for sensor_name in sensor_names:
      browser.find_element(By.XPATH, "//*/h5[contains(text(), '"+ sensor_name +"')]")
    return True
  except:
    return False

def create_roi_by_ratio(browser, polygon_name, x_ratio, y_ratio, sensor=False):
  """! This function creates an ROI by filling in the ROI form
  and submitting it directly.
  @param    browser                    Object wrapping the Selenium driver
  @param    polygon_name               Name of the created roi
  @param    x_ratio                    Ratio of scene width
  @param    y_ratio                    Ratio of scene height
  @return   points                     List of roi points
  """
  # Unhide hidden fields so Selenium can access them
  browser.execute_script("document.getElementById('scale').type='text'")
  browser.execute_script("document.getElementById('id_rois').type='text'")
  # Move controls out of the way
  browser.execute_script("document.getElementById('scene-controls').removeAttribute('id')")

  scale_field = browser.find_element(By.ID, "scale")
  scale = float(scale_field.get_attribute("value"))
  form_id = '"roi-form"'
  polygon_id = polygon_name

  svg = browser.find_element(By.ID, "svgout")

  # Create ROI about the center point (origin is bottom left in meters)
  cx = svg.size['width'] / (2 * scale)
  cy = svg.size['height'] / (2 * scale)

  if sensor:
    create_sensor_from_scene(browser, polygon_id, polygon_name, TEST_SCENE_NAME)
    open_sensor_tab(browser)
    open_scene_manage_sensors_tab(browser)
    browser.find_element(By.CSS_SELECTOR, "#id_area_2").click()
    form_id = '"roi-form-calibrate"'

  dx = cx * x_ratio
  dy = cy * y_ratio

  rois = []
  points = []

  points.append([ cx - dx, cy + dy ])
  points.append([ cx - dx, cy - dy ])
  points.append([ cx + dx, cy - dy ])
  points.append([ cx + dx, cy + dy ])

  rois.append({"title": polygon_name, "points": points})
  rois_text = json.dumps(rois)

  inject_json(rois_text, browser, "id_rois", form_id)

  time.sleep(2)

  return points

def create_roi(browser, polygon_name, x, y, side_length = 250):
  """! This function creates triangular ROI where the first point is positioned at (x,y)
  relative to the center of element svgout which spans the scene map.
  @param    browser                    Object wrapping the Selenium driver.
  @param    polygon_name               Name of the polygon to be created.
  @param    x                          X-coordinate of the first point.
  @param    y                          Y-coordinate of the first point.
  @param    side_length                Side length of the triangle.
  @param    sensor_names               List of the sensors to be checked.
  @return   bool                       Boolean representing success.
  """
  #Adding viewport-adjustment snip to handle out of bounds error
  # minimum window size required: {'width': 1550, 'height': 838}
  roi_points = None
  min_viewport_width = 1920
  min_viewport_height = 1080
  viewport_dimensions = browser.execute_script("return [window.innerWidth, window.innerHeight];")
  viewport_width = viewport_dimensions[0]
  viewport_height = viewport_dimensions[1]
  if viewport_width < min_viewport_width or viewport_height < min_viewport_height:
    browser.setViewportSize( min_viewport_width, min_viewport_height )
    print("Viewport size set to:", browser.execute_script("return [window.innerWidth, window.innerHeight];"))

  browser.find_element(By.ID, "regions-tab").click()
  browser.find_element(By.ID,"new-roi").click()
  svg = browser.find_element(By.ID, "svgout")

  time.sleep(1)
  action = browser.actionChains()
  action.drag_and_drop_by_offset(svg, x, y)
  action.perform()
  action.click()

  action2 = browser.actionChains()
  action2.move_by_offset(0, side_length).perform()
  time.sleep(1)
  action2.click()

  action2.move_by_offset(side_length, 0).perform()
  time.sleep(1)
  action2.click()

  action2.move_by_offset(0, -side_length).perform()
  time.sleep(1)
  action2.click()
  polygon_list = browser.find_elements(By.TAG_NAME,"polygon")

  #Get the latest polygon which was created
  polygon_points = polygon_list[-1].get_attribute("points")
  p_list = list(map(float,polygon_points.split(","))) # has the list of vertices of the polygon created

  #Get all the available vertices
  all_points = browser.find_elements(By.CLASS_NAME,"vertex")
  polygon_created = False
  for point in all_points:
    #find the origin point of the above polygon to complete the polygon which are first and the second element in the p_list
    if float(point.get_attribute("cx")) == p_list[0] and float(point.get_attribute("cy")) == p_list[1]:
      point.click()
      print(f"{polygon_name} created")
      polygon_created = True
      time.sleep(1)
      break

  polygon_name_updated = False
  roi_titles = browser.find_elements(By.CSS_SELECTOR,".card-body .roi-title")
  roi_name = roi_titles[-1]
  roi_name.click()
  roi_name.clear()
  roi_name.send_keys(polygon_name)
  #Verifying that name is updated successfully
  if roi_name.get_attribute('value') == polygon_name:
    print(f"ROI Name(Text box) updated successfully to {roi_name.get_attribute('value')}")
    polygon_name_updated = True
  else:
    print("Failed to update polygon name")

  if polygon_created and polygon_name_updated:
    roi = browser.find_element(By.ID, "id_rois")
    roi_points = roi.get_attribute('value')
    roi_points = json.loads(roi_points)[0]['points']
    roi_points[0] = [float(point) for point in roi_points[0]]
    roi_points[1] = [float(point) for point in roi_points[1]]
    roi_points[2] = [float(point) for point in roi_points[2]]

  browser.find_element(By.ID,"save-rois").click()
  print("Saved ROI successfully")

  return roi_points

def verify_roi(browser, rois_list):
  """! Function to verify if a given ROI list is present in UI.
  @param    browser                    The browser used in the test.
  @param    rois_list                  List of ROIs to verify in UI
  @return   bool                       True if all ROI is present, False if otherwise.
  """
  print("Navigating to ROI tab ...")
  browser.find_element(By.ID, "regions-tab").click()
  # roi_titles are roi_names which are in the roi_list
  roi_titles = browser.find_elements(By.CSS_SELECTOR, ".card-body .roi-title")

  persistent_roi_list = []
  # get all the names of the available ROIs
  for roi in roi_titles:
    persistent_roi_list.append(roi.get_attribute('value'))
  count = 0
  for roi_name in rois_list:
    if roi_name in persistent_roi_list:
      print(f"{roi_name} is persistent")
      count += 1
    else:
      print(f"{roi_name} is NOT persistent")

  if count == len(rois_list):
    return True
  return False

def delete_roi(browser, roi):
  """! Function used to delete a given ROI.
  @param    browser                    The browser used in the test.
  @param    roi                        ROI to be deleted.
  @return   bool                       True if ROI is deleted from UI, False if otherwise.
  """
  print("Navigating to ROI tab ...")
  browser.find_element(By.ID, "regions-tab").click()
  print("Deleting ...")
  roi_titles = browser.find_elements(By.CSS_SELECTOR, ".card-body .roi-title")
  roi_name = roi_titles[-1]
  time.sleep(2)

  if roi_name.get_attribute('value') == roi:
    trash_buttons = browser.find_elements(By.CSS_SELECTOR, ".card-body .roi-remove")
    remove_button = trash_buttons[-1]
    time.sleep(2)
    remove_button.click()
    print("Clicked on the trash icon")

    prompt_obj = browser.switch_to.alert
    msg = prompt_obj.text
    print("Alert message: " + msg)
    prompt_obj.accept()
    print("Clicked on the OK button to delete")
    return True
  else:
    print("Unable to delete ROI")
    return False

def create_camera(browser, camera_name, camera_id, scene_name):
  """! Creates camera from the camera list accessed via the navigation bar.
  @param    browser                    Object wrapping the Selenium driver.
  @param    camera_name                Name of the camera to be added.
  @param    camera_id                  ID of the camera to be added.
  @param    scene_name                 Name of the scene being checked.
  @return   bool                       Boolean representing success.
  """
  #Navigate to camera menu
  camera_menu_xpath = "//a[@href = '/cam/list/']"
  browser.find_element(By.XPATH, camera_menu_xpath).click()

  # New camera button
  new_camera_xpath = "//a[@href = '/cam/create/']"
  browser.find_element(By.XPATH, new_camera_xpath).click()

  # Update the Camera details
  browser.find_element(By.ID, "id_sensor_id").click()
  browser.find_element(By.ID, "id_sensor_id").send_keys(camera_id)
  browser.find_element(By.ID, "id_name").click()
  browser.find_element(By.ID, "id_name").send_keys(camera_name)
  browser.find_element(By.ID, "id_scene").click()
  select = Select(browser.find_element(By.ID, "id_scene"))
  select.select_by_visible_text(scene_name)

  add_button_xpath = "//input[@value = 'Add New Camera']"
  browser.find_element(By.XPATH, add_button_xpath).click()

  # Page is redirected to respective scene page verify the presence of the camera in that page
  if camera_name in browser.page_source:
    print(f"Added {camera_name} to the scene {scene_name}")
    return True
  print("Error while creating camera:",camera_name)
  return False

def check_db_status(browser):
  """! The purpose of this function is to make sure database is
  up before running the tests. This function will return true if
  it's able to navigate to the 'Demo' scene page.
  @param    browser                    Object wrapping the Selenium driver.
  @return   bool                       Boolean representing success.
  """
  return navigate_to_scene(browser, TEST_SCENE_NAME)

def navigate_to_scene(browser, scene_name):
  """! This function navigates to the 'Scenes' page, then waits for the Scene 'scene_name'
  to become available, and navigates to it.
  @param    browser                    Object wrapping the Selenium driver.
  @param    scene_name                 Name of the scene to be navigated to.
  @return   bool                       Boolean representing success.
  """
  # This clicks on the 'Scenes' entry in the banner at the top
  scenes_xpath = "//a[@href = '/']"
  browser.find_element(By.XPATH, scenes_xpath).click()
  time.sleep(1)

  # This element is only shown when there is at least one scene available
  card_header_xpath = "//h5[@class='card-header' and text()='" + scene_name + "']"
  found = wait_for_elements(browser, card_header_xpath, text=scene_name, findBy=By.XPATH)

  if found:
    card_header_element = browser.find_element(By.XPATH, card_header_xpath)
    print( "Card Header Element: {}".format(card_header_element.text))
    card_header_element.find_element(By.XPATH, "./..//a[1]").click()
    time.sleep(1)
    scene_name_xpath = "//h2[@id='scene_name' and text()='" + scene_name + "']"
    browser.find_element(By.XPATH, scene_name_xpath)
  else:
    print( "Unable to find {} scene!".format(scene_name))
  return found

def wait_for_elements(browser, search_phrase, text=None, findBy=By.XPATH, maxWait=120, refreshPage=True):
  """! This function waits for elements to be available in the browser, for a duration of maxWait.
  @param    browser                    Object wrapping the Selenium driver.
  @param    search_phrase              Search phrase to use in locating the web element.
  @param    text                       Expected text value of the located web element.
  @params   findBy                     The type of search to use in locating the search_phrase.
  @params   maxWait                    How much time to wait for.
  @params   refreshPage                Refresh the page before checking for the element.
  @return   bool                       Boolean representing success.
  """
  startTime = time.time()
  elapsedTime = 0
  intervalSeconds = 1 # Time to wait between operations

  while elapsedTime < maxWait:
    try:
      elements = browser.find_elements(findBy, search_phrase)
      for element in elements:
        if not text or text == element.text:
          return True
      # If we didnt return, then we either got empty array
      # or desired element is not found
      raise NoSuchElementException
    except NoSuchElementException:
      if refreshPage:
        browser.refresh()
    time.sleep(intervalSeconds)
    elapsedTime = time.time() - startTime
  print( "Failed finding element with [{}]:'{}'".format(findBy, search_phrase))
  return False

def selenium_wait_for_elements(browser, search_phrase, timeout=20):
  """
  This function waits for elements to be available in the browser by using expected_conditions
  from selenium webdriver, for a duration specified in timeout param.
  @params     browser                  The browser being used in the test.
  @params     search_phrase            The search_element object from webdriver.
  @params     timeout                  How much time to wait for
  @returns    bool                     Boolean which is true if element loaded before timeout.
  """
  return WebDriverWait(browser, timeout).until(EC.visibility_of_element_located(search_phrase))

def create_orphan_camera(browser, camera_name, camera_id):
  """! Creates camera in a scene then deletes the scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    camera_name                Name of the camera to be added.
  @param    camera_id                  ID of the camera to be added.
  @return   bool                       Boolean representing success.
  """
  scene_name = "Selenium Camera test scene"
  scale = 1000
  map_image = os.path.join(TEST_MEDIA_PATH, "HazardZoneScene.png")

  is_scene_created = create_scene(browser, scene_name, scale, map_image)
  if not is_scene_created:
    return False
  print("Created scene ", scene_name)

  is_camera_created = create_camera(browser, camera_name, camera_id, scene_name)
  if not is_camera_created:
    return False
  print(f"Added {camera_name} ID : {camera_id} to the scene {scene_name}")

  is_scene_deleted = delete_scene(browser, scene_name)
  if not is_scene_deleted:
    return False
  print(f"Orphan camera created")
  return True

def save_sensor_calibration(browser):
  """! Saves sensor calibration in the Manage Sensor tab.
  @param    browser                    Object wrapping the Selenium driver.
  @return   True                       Returns True if the action is successful.
  """
  try:
    browser.find_element(By.NAME, "save").click()
    return True
  except:
    return False

def create_circle_sensor(browser, radius=250):
  """! Creates a sensor that covers a circular area.
  @param    browser                    Object wrapping the Selenium driver.
  @param    radius                     Radius of the circular area covered by the sensor.
  @return   True                       Returns True if the action is successful.
  """
  browser.find_element(By.CSS_SELECTOR, "#id_area_1").click()
  slider = browser.find_element(By.ID, "id_sensor_r")
  circle_action = browser.actionChains()
  circle_action.click_and_hold(slider).move_by_offset(radius, 0).release().perform()
  return save_sensor_calibration(browser)

def create_triangle_sensor(browser, triangle_height=600, triangle_length=800, upper_left_point=(-400, -300)):
  """! Creates a sensor that covers a triangular area.
  @param    browser                    Object wrapping the Selenium driver.
  @param    triangle_height            Height of the triangular area.
  @param    triangle_length            Length of the triangular area.
  @param    upper_left_point           Location of the triangular areas upper left point relative to the center of element svgout.
  @return   True                       Returns True if the action is successful.
  """
  browser.find_element(By.CSS_SELECTOR, "#id_area_2").click()
  svg = browser.find_element(By.ID, "svgout")
  action_chain = browser.actionChains()
  action_chain.move_to_element_with_offset(svg, upper_left_point[0], upper_left_point[1]).click().perform()
  action_chain.move_by_offset(0, triangle_height).click().perform()
  action_chain.move_by_offset(triangle_length, 0).click().perform()
  action_chain.move_by_offset(-triangle_length, -triangle_height).click().perform()
  return save_sensor_calibration(browser)

def open_sensor_tab(browser):
  """! Opens Sensor tab.
  @param    browser                    Object wrapping the Selenium driver.
  @return   True                       Returns True if the action is successful.
  """
  browser.find_element(By.ID, "sensors-tab").click()
  return True

def open_scene_manage_sensors_tab(browser):
  """! Opens Manage Sensor tab from the Scene page.
  @param    browser                    Object wrapping the Selenium driver.
  @return   True                       Returns True if the action is successful.
  """
  browser.find_element(By.ID, "sensors-tab").click()
  browser.find_element(By.CSS_SELECTOR, "#sensors > div > div > div > div > div > a:nth-child(1)").click()
  return True

def mse(mat1, mat2):
  """! Mean Squared Error between two numpy arrays.
  @param    mat1                       The first numpy array.
  @param    mat2                       The second numpy array.
  @return   FLOAT                      MSE between the first and second numpy array.
  """
  dmat = mat1 - mat2
  smat = np.square(dmat)
  return np.mean(smat)

def read_image(file_path):
  """! Read image from path with OpenCV
  @param    file_path                  Image file path to be read.
  @return   np.ndarray                 Image in NumPy array.
  """
  return cv2.imread(file_path)

def compare_images(base_image: np.ndarray, image: np.ndarray, comparison_threshold: float = DEFAULT_IMAGE_MSE_THRESHOLD) -> bool:
  """! Compare the mean squared error between to images represented as numpy arrays.
  @param    base_image                 Baseline image to be compared against.
  @param    image                      Image to be compared against the baseline image.
  @param    comparison_threshold       Threshold of the mse comparison.
  @return   bool                       True if the mse between the two images is greater than the comparison threshold.
  """
  mse_value = mse(base_image, image)
  if mse_value > comparison_threshold:
    return True
  return False

def get_images_difference(base_image: np.ndarray, image: np.ndarray) -> float:
  """! Return the mean squared error between two images represented as numpy arrays.
  Identical images should return 0.0 value. Different images should return a value > 0
  @param    base_image                 Baseline image to be compared against.
  @param    image                      Image to be compared against the baseline image.
  @return   float                      The mse comparison result.
  """
  mse_value = mse(base_image, image)
  return mse_value

def check_current_address(browser: Browser, expected_address: str) -> bool:
  """! Checks that the current pages URL is the same as the expected URL.
  @param    browser                    Object wrapping the Selenium driver.
  @param    expected_address           Expected current page address.
  @return   bool                       Boolean representing success.
  """
  if expected_address == urlparse(browser.current_url).path:
    return True
  return False

def navigate_directly_to_page(browser: Browser, page_path: str) -> bool:
  """! Navigates to page via a URL.
  @param    browser                    Object wrapping the Selenium driver.
  @param    page_path                  Expected path of the page.
  @return   bool                       Boolean representing success.
  """
  parsed_url = urlparse(browser.current_url)
  address = parsed_url._replace(path=page_path)
  browser.getPage(address.geturl(), APP_PROPER_NAME)
  return check_current_address(browser, page_path)

def check_filename_in_page(browser, page_path, selector_type, file):
  """! Checks that filename exists in any of the elements from element list.
  @param    browser                    Object wrapping the Selenium driver.
  @param    page_path                  Expected path of the page.
  @param    selector_type              Method used to access location.
  @param    file                       File object.
  @return   True if the filename matches with an element, False otherwise.
  """
  assert navigate_directly_to_page(browser, page_path)
  elements = browser.find_elements(selector_type, file.expected_location)

  for element in elements:
    if element.text == file.filename:
      return True

  return False

def upload_scene_file(browser, scene_name, file):
  """! Upload the scene file to a scene.
  @param    browser                    Object wrapping the Selenium driver.
  @param    scene_name                 Name of the scene to upload files.
  @param    file                       File object
  @return   bool                       Boolean representing successful upload.
  """
  assert scene_name in browser.page_source
  browser.find_element(By.ID, file.upload_element_id).send_keys(file.file_path)

  # Saves uploaded images and goes back to the page listing all the scenes
  browser.find_element(By.ID, "save").click()

  page_path = f"/scene/update/{TEST_SCENE_ID}/"
  selector_type = By.CSS_SELECTOR
  return check_filename_in_page(browser, page_path, selector_type, file)

def get_element_screenshot(element) -> np.ndarray:
  """! Uses the selenium driver to take a screenshot of an element and returns a numpy array.
  @return   img_array slice            Screenshot as a numpy array.
  """
  img_bytes_raw = element.screenshot_as_png
  img_bytes = BytesIO(img_bytes_raw)
  img = Image.open(img_bytes, formats=["PNG"])
  img_array = np.asarray(img)
  # drop alpha channel, bgr to rbg
  img_array = img_array[:, :, 0:3]
  return img_array[:, :, ::-1]

def is_within_rectangle(bl, tr, curr_point):
  """! Determines if a point lies within a rectangle or not.
  @param    bl          Bottom Left of the rectangle.
  @param    tr          Top Right of the rectangle.
  @param    curr_point  Point being check.
  @return   bool        True/False if point is in rectangle.
  """
  if (curr_point[0] > bl[0] and curr_point[0] < tr[0] and
    curr_point[1] > bl[1] and curr_point[1] < tr[1]):
    return True
  else:
    return False

######################################################################################
# Decorators
######################################################################################
def mock_display(func):
  """! Run func with a mock display.
  @param    func                       Function to be wrapped.
  @return   wrapper_mock_display       Wrapped function mocking a display.
  """
  @functools.wraps(func)
  def wrapper_mock_display(*args, **kwargs):
    display = Display(visible=0, size=(1920, 1080))
    display.start()

    return_val = func(*args, **kwargs)

    display.stop()
    return return_val
  return wrapper_mock_display

def scenescape_login_headed(func):
  """! Run func after logging into Scenescape.
  @param    func                       Function to be wrapped.
  @return   wrapper_scenescape_login   Wrapped function logged into Scenescape.
  """
  @functools.wraps(func)
  def wrapper_scenescape_login(*args, **kwargs):
    browser = Browser(headless=False)
    params = args[0]
    assert check_page_login(browser, params)
    assert check_db_status(browser)

    return_val = func(browser, *args[1:], **kwargs)

    browser.close()
    return return_val
  return wrapper_scenescape_login

######################################################################################
# Parameters
######################################################################################
@dataclass
class File():
  """! Parameters for uploading a file which is simpler than UploadParams.
  @param    file_path                  Path to uploaded file.
  @param    upload_element_id          HTML ID of upload field.
  @param    expected_location          Expected location of the uploaded files filename.
  """
  file_path: str
  upload_element_id: str
  expected_location: str

  @property
  def filename(self):
    return self.file_path.split("/")[-1]

@dataclass
class InteractionParams:
  """! Parameters for uploading a file.
  @param    file_name                  Name of uploaded file.
  @param    file_path                  Path to uploaded file.
  @param    page_path                  Address of page to upload file.
  @param    field_name                 Name of the html file upload field.
  @param    field_selector             Selection string for html upload field.
  @param    element_location           Location in page of file name once uploaded.
  @param    element_type               Type of attribute the holding the file name.
  @param    screenshot_threshold       Threshold defining screenshot difference.
  @param    debug                      Flag to run test in debug mode.
  """
  file_name: str
  file_path: str
  page_path: str
  field_name: str
  field_selector: str
  element_location: str
  element_type: str="text"
  screenshot_threshold: float=-1.0
  debug: bool=False

  _screenshots: Dict = field(default_factory=dict)
  _screenshot_count: int=0

  @property
  def screenshots(self):
    """! Return added screenshots.
    @return   _screenshots             Dictionary of added screenshots.
    """
    return self._screenshots

  @screenshots.setter
  def screenshots(self, new_shots):
    """! Set screenshots dictionary value.
    @param   new_shots                 New dictionary of screenshots.
    """
    self._screenshots = new_shots

  def add_screenshot(self, screenshot):
    """! Add screenshot to the dictionary of screenshots.
    @param    screenshot               Screenshot to be added to the screenshots dictionary.
    @return   None
    """
    self._screenshot_count += 1
    self._screenshots[self._screenshot_count] = screenshot
    return

@dataclass
class CheckInteraction:
  """! Collection of page interaction checks.
  @param    file_name_in_page          If true check that the file name is in the page.
  @param    file_on_server             If true check that the file is on the server.
  @param    screenshots_differ         If true check that screenshots differ.
  """
  file_name_in_page: bool=False
  file_on_server: bool=False
  screenshots_differ: bool=False

######################################################################################
# Page Interactions
######################################################################################
class InteractWithPage(ABC):
  """! Base class for interacting with a page. """
  def __init__(self, browser: Browser, interaction_params: InteractionParams=None):
    """! Initiate class.
    @param    browser                  Object wrapping the Selenium driver.
    @param    interaction_params       InteractionParams object.
    @return   None
    """
    self.browser = browser
    self.interaction_params = interaction_params
    return

  @abstractmethod
  def navigate_to_page(self, expected_path: str) -> bool:
    """! Navigates to page via the web interface.
    @param    expected_path            Expected path of the page.
    @return   bool                     Boolean representing success.
    """
    raise NotImplementedError("Method not implemented.")

  @abstractmethod
  def check_successful_interaction(self, params: InteractionParams, checks: CheckInteraction) -> bool:
    """! Checks that an interaction with a page is successful.
    @return   bool                     Boolean representing success.
    """
    raise NotImplementedError("Method not implemented.")

  def upload_file(self) -> bool:
    """! Uploads file based on the classes upload_params.
    @return   correct_address          Address of the upload page.
    """
    correct_address = self.navigate_to_page(self.interaction_params.page_path)
    self.browser.find_element(By.CSS_SELECTOR, self.interaction_params.field_selector).send_keys(self.interaction_params.file_path)
    self.browser.find_element(By.CSS_SELECTOR, self.interaction_params.field_selector).submit()
    self.browser.find_element(By.CSS_SELECTOR, "input[value=\"Save Scene Updates\"]").click()
    if correct_address:
      success_str = "Submitting upload {fname} succeeded: {fpath}".format(fname=self.interaction_params.field_name, \
                                                                          fpath=self.interaction_params.file_path)
      print(success_str)
    return correct_address

  def click_element_css_selector(self, selector: str) -> None:
    """! Clicks on html element picked out by the a CSS selector.
    @param    selector                 CSS selector picking out the element.
    @return   None.
    """
    self.browser.find_element(By.CSS_SELECTOR, selector).click()
    return

  def get_page_screenshot(self) -> np.ndarray:
    """! Uses the selenium driver to take screenshot and returns a numpy array.
    @return   img_array slice          Screenshot as a numpy array.
    """
    img_bytes_raw = self.browser.get_screenshot_as_png()
    img_bytes = BytesIO(img_bytes_raw)
    img = Image.open(img_bytes, formats=["PNG"])
    img_array = np.asarray(img)
    # drop alpha channel, bgr to rbg
    img_array = img_array[:, :, 0:3]
    return img_array[:, :, ::-1]

  def check_file_uploaded_is_on_server(self) -> bool:
    """! Check that uploaded file is on the server.
    @return   upload_success           Boolean which is true if the file is on the server.
    """
    check_str_root = "Check Uploaded File On Server: "
    upload_success = False
    tmp_dir_path = tempfile.mkdtemp()
    file_output_path = tmp_dir_path + "/" + self.interaction_params.file_name
    parsed_url = urlparse(self.browser.current_url)
    file_url = parsed_url._replace(path=f"/media/{self.interaction_params.file_name}").geturl()

    curl_str = ["curl", file_url, "-k", "-o", file_output_path, "-v"]
    sessionid = None
    csrftoken = None

    for item in self.browser.get_cookies():
      if item['name'] == "sessionid":
        sessionid = f"{item['name']}={item['value']}"
      elif item['name'] == "csrftoken":
        csrftoken = f"{item['name']}={item['value']}"

    assert sessionid is not None
    assert csrftoken is not None
    curl_str.extend(["-b", f"{sessionid};{csrftoken}"])
    subprocess.run(curl_str, capture_output=True, text=True)

    tmp_files = os.listdir(tmp_dir_path)
    if (self.interaction_params.file_name in tmp_files) and filecmp.cmp(file_output_path, self.interaction_params.file_path):
      upload_success = True
      print(check_str_root + "Passed")
    else:
      print(check_str_root + "Failed")
    return upload_success

  def check_screenshots_differ(self) -> bool:
    """! Tests that screenshot 1 differs from screenshot 2 by a given MSE threshold.
    @return   bool                     Boolean which is True if the screenshots differ more than the MSE threshold.
    """
    navigate_directly_to_page(self.browser, self.interaction_params.page_path)
    time.sleep(5)
    screenshot = self.get_page_screenshot()
    self.interaction_params.add_screenshot(screenshot)
    if self.interaction_params.debug:
      fname = self.interaction_params.file_name.replace(".", "_")
      fname = fname.split("/")[-1]
      cv2.imwrite("screenshot_" + fname + ".png", screenshot)

    return compare_images(self.interaction_params.screenshots[1],
                          self.interaction_params.screenshots[2],
                          self.interaction_params.screenshot_threshold)

  def check_file_uploaded_name(self) -> bool:
    """! Check that uploaded filename is in the expected html page at the expected location.
    @return   upload_success           Boolean which is true if the file name is where it is expected.
    """
    check_str_root = "Check Uploaded File Name: "
    upload_success = False
    navigate_success = navigate_directly_to_page(self.browser, self.interaction_params.page_path)
    element = self.browser.find_element(By.CSS_SELECTOR, self.interaction_params.element_location)
    page_file_name = None
    if self.interaction_params.element_type == "text":
      page_file_name = element.text
    elif self.interaction_params.element_type == "attribute":
      page_file_name = element.get_attribute("value")

    if(page_file_name == self.interaction_params.file_name) and navigate_success:
      upload_success = True
      print(check_str_root + "Passed")
    else:
      print(check_str_root + "Failed")
    return upload_success

  def check_successful_interaction(self, checks: CheckInteraction) -> bool:
    """! Check that the page interaction is successful using one or more checks.
    @param    checks                   The types of interaction checks to use.
    @return   passes                   Boolean which is true if the interaction passes the checks.
    """
    passes = True
    if checks.file_name_in_page:
      passes = (passes and self.check_file_uploaded_name())
      print("CHECK: file_name_in_page: ", passes)

    if checks.file_on_server:
      passes = (passes and self.check_file_uploaded_is_on_server())
      print("CHECK: file_on_server: ", passes)

    if checks.screenshots_differ:
      passes = (passes and self.check_screenshots_differ())
      print("CHECK: screenshots_differ: ", passes)
    print()
    return passes

############################################################################

class InteractWith3DScene(InteractWithPage):
  """! Class for interacting with the 3d scene page. """

  def __init__(self, browser: Browser, interaction_params: InteractionParams=None):
    """! Initiate class.
    @param    browser                  Object wrapping the Selenium driver.
    @param    interaction_params       InteractionParams object.
    @return   None
    """
    InteractWithPage.__init__(self, browser, interaction_params)
    return

  def navigate_to_page(self, expected_path: str) -> bool:
    """! Place holder to satisfy the abstract method. """
    return False

  def get_3D_scene_screenshot(self) -> np.ndarray:
    """! Take screenshot of current 3D scene.
    @return   screenshot               Numpy array representing a screenshot.
    """
    navigate_directly_to_page(self.browser, f"/scene/detail/{TEST_SCENE_ID}/")
    time.sleep(1)
    return self.get_page_screenshot()

  def check_3D_asset_visible(self) -> bool:
    """! Checks 3d asset visibility by checking that the expected filename is in the page source
    and that the current screenshot differs from the baseline screenshot.
    @return   object_visible_success   Boolean which is true if both checks pass.
    """
    object_visible_checks = CheckInteraction(file_name_in_page=True, screenshots_differ=True)
    return self.check_successful_interaction(object_visible_checks)

  def hide_stats(self) -> bool:
    """! Hides the stats graph so that the graph doesn't affect the MSE during screenshot tests.
    @return   bool                     Boolean representing success.
    """
    self.browser.execute_script("document.getElementsByClassName('stats')[0].style.display = 'none';")
    return True

  def hide_control_panels(self) -> bool:
    """! Hides the 3D scene and camera control panels.
    @return  panels_hidden_success     Boolean which is true if both panels are hidden.
    """
    WAIT_SEC = 1
    camera_3d_controls = self.browser.find_element(By.ID, "panel-3d-controls")
    scene_3d_controls = self.browser.find_element(By.ID, "scene-controls-3d")

    # Hide 3d panels
    self.browser.execute_script("arguments[0].style.display = 'none';", camera_3d_controls)
    self.browser.execute_script("arguments[0].style.display = 'none';", scene_3d_controls)
    time.sleep(WAIT_SEC)

    # Check if panels are hidden successfully
    if camera_3d_controls.is_displayed() or scene_3d_controls.is_displayed():
      return False

    return True

  def unhide_control_panels(self) -> bool:
    """! Unhides the 3D scene and camera control panels.
    @return   panels_displayed_success        Boolean representing success.
    """
    WAIT_SEC = 1
    camera_3d_controls = self.browser.find_element(By.ID, "panel-3d-controls")
    scene_3d_controls = self.browser.find_element(By.ID, "scene-controls-3d")

    #Unhide 3d panels
    time.sleep(WAIT_SEC)
    self.browser.execute_script("arguments[0].style.display = 'block';", camera_3d_controls)
    self.browser.execute_script("arguments[0].style.display = 'block';", scene_3d_controls)

    # Check if panels are unhidden successfully
    if not camera_3d_controls.is_displayed() or not scene_3d_controls.is_displayed():
      return False

    return True

class InteractWithSceneUpdate(InteractWithPage):
  """! Class for interacting with the scene update page. """

  def __init__(self, browser: Browser, interaction_params: InteractionParams=None):
    """! Initiate the class.
    @param    browser                  Object wrapping the Selenium driver.
    @param    interaction_params       InteractionParams object.
    @return   None
    """
    InteractWithPage.__init__(self, browser, interaction_params)
    return

  def navigate_to_page(self, expected_path: str) -> bool:
    """! Navigates to page via the web interface.
    @param    expected_path            Expected path of the page.
    @return   bool                     Boolean representing success.
    """
    self.click_element_css_selector("#home")
    self.click_element_css_selector(f"#scene-edit-{TEST_SCENE_ID}")
    return check_current_address(self.browser, expected_path)

  def upload_scene_file(self, checks: CheckInteraction) -> bool:
    """! Upload a scene map file.
    @return   bool                     Boolean representing success.
    """
    upload_success = False
    correct_address = self.upload_file()

    # Wait for redirect to resolve back to the Scenes page
    selenium_wait_for_elements(self.browser, (By.LINK_TEXT, "+ New Scene"), 5)
    successful_checks = self.check_successful_interaction(checks)
    if successful_checks and correct_address:
      upload_success = True
    return upload_success

  def upload_scene_3D_map(self, checks: CheckInteraction) -> bool:
    """! Upload a 3d scene map file.
    @return   bool                     Boolean representing success.
    """
    upload_checks = replace(checks, screenshots_differ=False)
    upload_success = self.upload_scene_file(upload_checks)
    assert upload_success
    return upload_success

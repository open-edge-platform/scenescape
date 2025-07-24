# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import time

import numpy as np
from PIL import Image
from io import BytesIO
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from tests.diagnostic import Diagnostic
from .browser import Browser

# FIXME - Incorporate common into this class after migrating older tests to classes
import tests.ui.common_ui_test_utils as common

class UserInterfaceTest(Diagnostic):
  from selenium.webdriver.common.by import By

  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.browser = Browser()
    return

  def buildArgparser(self):
    parser = self.argumentParser()
    parser.add_argument("--user", required=True, help="user to log into web server")
    parser.add_argument("--password", required=True, help="password to log into web server")
    parser.add_argument("--auth", default="/run/secrets/percebro.auth",
                        help="user:password or JSON file for MQTT authentication")
    parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                        help="path to ca certificate")
    parser.add_argument("--broker_url", default="broker.scenescape.intel.com",
                        help="hostname or IP of the broker")
    parser.add_argument("--broker_port", default=1883, help="broker port")
    parser.add_argument("--weburl", default="https://web.scenescape.intel.com",
                        help="Web URL of the server")
    parser.add_argument("--resturl", default="https://web.scenescape.intel.com/api/v1",
                        help="URL of REST server")
    parser.add_argument("--scene", default="Demo", help="name of scene to test against")
    parser.add_argument("--scene_id", default="3bc091c7-e449-46a0-9540-29c499bca18c", help="id of scene to test against")
    return parser

  # Wrappers to use common_ui_test_utils until all of that can be moved here

  def login(self):
    log_params = {
      'weburl': self.params['weburl'],
      'user': self.params['user'],
      'password': self.params['password'],
    }
    return common.check_page_login(self.browser, log_params)

  def checkDbStatus(self):
    return common.check_db_status(self.browser)

  def clickOnElement(self, elementId: str, waitTime: int = 1, delay: int = 0) -> None:
    """! Toggles the specified slider in the 3D UI control panel
    @param    slider_label    Label to search for to locate the slider
    @param    waitTime        Length of time to wait after performing action
    @param    delay           Length of time to wait for element before performing action
    """
    if delay > 0:
      WebDriverWait(self.browser, delay).until(
        EC.element_to_be_clickable((self.By.ID, elementId)))
    self.browser.find_element(self.By.ID, elementId).click()
    self.browser.actionChains().pause(waitTime).perform()

  def compareImages(self, baseImage, Image, comparisonThreshold):
    return common.compare_images(baseImage, Image, comparisonThreshold)

  def getPageScreenshot(self) -> np.ndarray:
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

  def navigateDirectlyToPage(self, pagePath):
    return common.navigate_directly_to_page(self.browser, pagePath)

  def navigateToScene(self, sceneName):
    return common.navigate_to_scene(self.browser, sceneName)

  def findElement(self, by, value):
    return self.browser.find_element(by, value)

  def executeScript(self, script, *args):
    return self.browser.execute_script(script, *args)

  def toggleElementDisplay(self, element_class: str, display: bool, waitTime: int = 1) -> None:
    """! Toggles the display of the first element of a class
    @param    element_class    The class of the element to show/hide
    @param    display          True if displaying the element, False if hiding
    """
    if display:
      self.browser.execute_script(
        f"document.getElementsByClassName('{element_class}')[0].style"
        ".removeProperty('display');")
    else:
      self.browser.execute_script(
        f"document.getElementsByClassName('{element_class}')[0].style.display = 'none';")
    time.sleep(waitTime)

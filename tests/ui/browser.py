#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import time
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

MAX_RETRIES = 5
RETRY_DELAY = 30

class Browser(Firefox):
  def __init__(self, headless=True):
    # Must remove proxy settings from environment otherwise Jenkins testing fails
    for key in os.environ:
      if 'proxy' in key or 'PROXY' in key:
        del os.environ[key]

    options = Options()
    if headless:
      options.add_argument('--headless')

    options.add_argument("--window-size=1080,1920")
    s = Service("/usr/local/bin/geckodriver")
    super().__init__(options=options, service=s)
    return

  def getPage(self, url, expected_title, retries=MAX_RETRIES, delay=RETRY_DELAY):
    '''
    Will load the page at <url> and check to see if the title
    matches. Returns True/False.
    '''

    print("Fetching page")
    retry = 0
    success = False
    while True:
      try:
        self.get(url)
        print(self.title)
        if self.title == expected_title:
          success = True
          break
      except WebDriverException as e:
        print("Fetch error")

      retry += 1
      if retry >= retries:
        print(f"Failed to get page from server after {retry} tries")
        break
      time.sleep(delay)

    return success

  def login(self, user, password, weburl, retries=MAX_RETRIES, delay=RETRY_DELAY):
    '''
    Tries to log in using the provided user & password. Returns
    True/False. If unable to find form fields or error message,
    raises an exception.
    '''
    success = False
    retry = 0
    while True:
      try:
        self.get(weburl)
      except WebDriverException as e:
        print("Fetch error")
      else:
        try:
          field = self.find_element(By.ID, "username")
        except NoSuchElementException:
          pass
        else:
          field.clear()
          field.send_keys(user)
          field = self.find_element(By.ID, "password")
          field.clear()
          field.send_keys(password)

          button = self.find_element(By.CSS_SELECTOR, "button.btn-primary")
          button.click()

          try:
            self.find_element(By.CSS_SELECTOR, "ul.navbar-nav")
            success = True
            break
          except NoSuchElementException:
            try:
              self.find_element(By.CSS_SELECTOR, "ul.errorlist")
              print("Invalid user/password")
            except NoSuchElementException:
              print("Couldn't find login status")

      retry += 1
      if retry >= retries:
        print("Failed to login after", retry, "tries")
        break
      time.sleep(delay)

    return success

  def setViewportSize(self, width, height):
    window_size = self.execute_script("""
        return [window.outerWidth - window.innerWidth + arguments[0],
          window.outerHeight - window.innerHeight + arguments[1]];
        """, width, height)
    return self.set_window_size(*window_size)

  def actionChains(self):
    return ActionChains(self)

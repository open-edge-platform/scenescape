#!/usr/bin/env python3

import os
import shutil
import time
import geckodriver_autoinstaller
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from pathlib import Path
from shutil import which
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
import subprocess

def _validate_firefox(binary):
    result = subprocess.run([binary, "--version"], capture_output=True, text=True)
    if result.returncode != 0 or "Firefox" not in result.stdout + result.stderr:
        raise RuntimeError(f"Invalid Firefox binary: {binary}")

def _find_firefox_binary():
    candidates = [
        which("firefox"),
        which("firefox-esr"),
        "/usr/bin/firefox",
        "/usr/bin/firefox-esr",
        "/snap/bin/firefox",
    ]

    for candidate in candidates:
        if not candidate:
            continue
        p = Path(candidate)
        if p.is_file() and p.stat().st_mode & 0o111:
            return str(p)

    raise RuntimeError(
        "No valid Firefox executable found. Checked firefox/firefox-esr in PATH "
        "and common system locations."
    )

class Browser(Firefox):
  def __init__(self, headless=True):
    # Remove proxy settings safely
    for key in list(os.environ):
      if 'proxy' in key.lower():
        os.environ.pop(key, None)

    # Make headless explicit for Firefox in CI
    if headless:
      os.environ["MOZ_HEADLESS"] = "1"

    options = Options()
    if headless:
      options.add_argument("--headless")

    options.add_argument("--width=1080")
    options.add_argument("--height=1920")
    options.set_preference("webgl.disabled", True)
    options.set_preference("media.hardware-video-decoding.enabled", False)
    options.set_preference("gfx.webrender.software", True)
    options.set_preference("network.proxy.type", 0)

    binary = _find_firefox_binary()
    _validate_firefox(binary)
    options.binary_location = binary

    geckodriver_path = shutil.which("geckodriver") or geckodriver_autoinstaller.install()
    service = Service(geckodriver_path)

    super().__init__(options=options, service=service)

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

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import time
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from pathlib import Path
from shutil import which
import subprocess

MAX_RETRIES = 5
RETRY_DELAY = 30

def _validate_firefox(binary):
  result = subprocess.run([binary, "--version"], capture_output=True, text=True)
  if result.returncode != 0 or "Firefox" not in result.stdout + result.stderr:
    raise RuntimeError(f"Invalid Firefox binary: {binary}")

def _find_firefox_binary():
  candidates = [
    os.environ.get("FIREFOX_BIN"),
    "/usr/bin/firefox",
    "/usr/bin/firefox-esr",
    which("firefox"),
    which("firefox-esr"),
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

def _find_geckodriver():
  candidates = [
    os.environ.get("GECKODRIVER_BIN"),
    str(Path(sys.executable).parent / "geckodriver"),
    which("geckodriver"),
  ]

  for candidate in candidates:
    if not candidate:
      continue
    p = Path(candidate)
    if p.is_file() and p.stat().st_mode & 0o111:
      return str(p)

  raise RuntimeError(
    "geckodriver not found. Run 'make setup-tests' to install it."
  )

class Browser(Firefox):
  def __init__(self, headless=True, webgl=False):
    # Remove proxy settings safely
    for key in list(os.environ):
      if 'proxy' in key.lower():
        os.environ.pop(key, None)


    # Make headless explicit for Firefox in CI.
    if headless:
      os.environ["MOZ_HEADLESS"] = "1"
    else:
      os.environ.pop("MOZ_HEADLESS", None)

    # Force Mesa software rendering (llvmpipe/swrast) so a WebGL context can be
    # created even when the runner has no GPU.
    if webgl:
      os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
      os.environ.setdefault("GALLIUM_DRIVER", "llvmpipe")

    options = Options()
    if headless:
      options.add_argument("--headless")

    options.add_argument("--width=1080")
    options.add_argument("--height=1920")
    options.set_preference("webgl.disabled", not webgl)
    options.set_preference("media.hardware-video-decoding.enabled", False)
    options.set_preference("gfx.webrender.software", True)
    options.set_preference("network.proxy.type", 0)

    binary = _find_firefox_binary()
    _validate_firefox(binary)
    options.binary_location = binary

    options.add_argument("--window-size=1080,1920")
    # Resolve Scenescape service hostnames to loopback inside the Firefox process.
    # This applies to geckodriver subprocess, which is unaffected by the Python-level
    # socket.getaddrinfo patch in conftest.py.
    _host_aliases = [
      "broker.scenescape.intel.com",
      "web.scenescape.intel.com",
      "autocalibration.scenescape.intel.com",
      "vdms.scenescape.intel.com",
    ]
    options.set_preference("network.dns.localDomains", ",".join(_host_aliases))
    service = Service(_find_geckodriver())
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

  def find_elements_with_wait(self, by, value, timeout=10):
    return WebDriverWait(self, timeout).until(
      EC.presence_of_all_elements_located((by, value))
    )

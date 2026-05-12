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

MAX_RETRIES = 5
RETRY_DELAY = 30

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

    firefox_path = shutil.which("firefox") or shutil.which("firefox-esr")
    if firefox_path:
      options.binary_location = firefox_path

    geckodriver_path = shutil.which("geckodriver") or geckodriver_autoinstaller.install()
    service = Service(geckodriver_path)

    super().__init__(options=options, service=service)
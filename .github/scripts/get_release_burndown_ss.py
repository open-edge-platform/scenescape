#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.
# See the LICENSE file in the root of this repository for details.

import argparse
import os, time
from jira import JIRA
from selenium import webdriver
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from tests.ui.common_ui_test_utils import wait_for_elements

PROJECT = 'SAIL'
WAIT_TIME = 5

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser = argparse.ArgumentParser(description='Get a Jira release burndown chart.')
parser.add_argument('-v', '--version', type=str, required=True,
                    help='Jira release version for the report. Example: 2024.2')
parser.add_argument('-t', '--token', type=str, required=True,
                    help='Jira authentication token')
parser.add_argument('-b', '--report-path', type=str, default="release_burndown_graph.png",
                    help='Burndown report image path')
parser.add_argument('-p', '--proxy', type=str, default="https://proxy-dmz.intel.com:912",
                    help='Use the following proxy to connect to Jira')
parser.add_argument('-j', '--jira-uri', type=str,
                    default="https://jira.devtools.intel.com", help='Jira instance URI')
parser.add_argument('-c', '--cert', default=False,
                    help='Certificate Path for the Jira connections')
parser.add_argument('-g', '--gecko-path', type=str, default=None,
                    help='Path to geckodriver if none is found by default')
args = parser.parse_args()

session_params = { 'verify': args.cert if args.cert else False }
jira = JIRA(server=args.jira_uri, token_auth=args.token, options=session_params)
version_obj = jira.get_project_version_by_name(PROJECT, args.version)
if not version_obj:
  print(f"The {PROJECT} project doesn't have the {args.version} version!")
  exit(1)

if not os.path.isabs(args.report_path):
  script_directory = os.path.dirname(os.path.abspath(__file__))
  args.report_path = os.path.join(script_directory, args.report_path)
  print(f"The report will be saved in: {args.report_path}")

options = Options()
options.add_argument("--headless")
seleniumwire_options = { "proxy": { "http": args.proxy } }
service = Service(executable_path=args.gecko_path) if args.gecko_path else None
driver = webdriver.Firefox(seleniumwire_options = seleniumwire_options,
                           options = options, service=service)

def interceptor(request):
  request.headers['Authorization'] = "Bearer " + args.token

driver.request_interceptor = interceptor
report_location = args.jira_uri + "/secure/RapidBoard.jspa?rapidView=32465" + \
                  "&projectKey=" + PROJECT + \
                  "&view=reporting&chart=releaseBurndown&version=" + version_obj.id
driver.get(report_location)
print(driver.title)

element_xpath = "//*[@id='ghx-chart-group']"
found_element = wait_for_elements(driver, element_xpath, maxWait=10, refreshPage=False)

time.sleep(WAIT_TIME) # Time until the graph is populated with data

# Take the element screenshot
try:
  if found_element:
    jira_chart = driver.find_element(By.XPATH, element_xpath)
    jira_chart.screenshot(args.report_path)
    print("The screenshot was saved successfully: " + args.report_path)
except Exception as e:
  print("Exception occurred " + str(e))

driver.close()

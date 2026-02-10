# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
from pathlib import Path
from typing import Dict, List
from jinja2 import Template
import argparse
import json
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

class TestResult(dict):
  def __init__(self, test_name: str, test_case: str, result: str):
    dict.__init__(self, test_name=test_name, test_case=test_case, result=result)

test_template = Template("""
<!DOCTYPE html>
<html>
<head>
  <title>Test Report - {{ run_name }}</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 20px;
    }
    td, th {
      border: 1px solid #dddddd;
      text-align: left;
      padding: 10px;
    }
  </style>
</head>
<body>
  <h1>Test Report - {{ run_name }}</h1>
  {{ pie_chart | safe }}
  <table border='1' align='center'>
    <tr>
      <th>Test Case</th>
      <th>Test Name</th>
      <th>Result</th>
    </tr>
    {% for test_result in results %}
    <tr>
      <td>{{ test_result.test_case }}</td>
      <td>{{ test_result.test_name }}</td>
      {% if test_result.result == "PASS" %}
      <td style='background-color:green; color:white; font-weight:bold; text-align: center'>{{ test_result.result }}</td>
      {% elif test_result.result == "FAIL" %}
      <td style='background-color:red; color:white; font-weight:bold; text-align: center'>{{ test_result.result }}</td>
      {% elif test_result.result == "NOT EXECUTED" %}
      <td style='background-color:grey; color:black; font-weight:bold; text-align: center'>{{ test_result.result }}</td>
      {% endif %}
    </tr>
    {% endfor %}
  </table>
</body>
</html>
""")

def read_test_cases(path: str) -> Dict[str, str]:
  """
  Read a file and return a list of lines (stripped). Empty lines are skipped.
  """
  p = Path(path)
  result: Dict[str, str] = {}
  with p.open("r", encoding="utf-8") as f:
    for raw in f:
      line = raw.strip()
      if not line:
        continue
      key, value = line.split()
      if result.get(key.strip()) is not None:
        print(f"Warning: Duplicate key '{key.strip()}' found.")
        result[key.strip()] += f",{value.strip()}"
        continue;
      result[key.strip()] = value.strip()
  return result


def read_test_results(path: str, delimiter: str = ": ") -> Dict[str, str]:
  """
  Read a file where each non-empty line contains "key<delimiter>value".
  Returns a dict mapping key -> value. Lines without the delimiter are ignored.
  """
  p = Path(path)
  result: Dict[str, str] = {}
  with p.open("r", encoding="utf-8") as f:
    for raw in f:
      line = raw.strip()
      if not line:
        continue
      if delimiter in line:
        key, value = line.split(delimiter, 1)
        if result.get(key.strip()) is not None:
          print(f"Warning: Duplicate key '{key.strip()}' found.")
          print(f"Existing value: '{result[key.strip()]}' vs New value: '{value.strip()}'")
          if(result[key.strip()] == "PASS" and value.strip() != "PASS" ):
            printf(f"Updating value with {value.strip()} for key {key.strip()}")
            result[key.strip()] = value.strip()
          else:
            continue
        result[key.strip()] = value.strip()
  return result

def prepare_results(test_cases: Dict[str, str], results: Dict[str, str]):
  """
  For each test case in test_cases, read the result from results dict.
  If a test case is missing in results, print "NOT EXECUTED".
  """
  all_results: List[TestResult] = []
  for test_case in test_cases:
    all_results.append(TestResult(test_name=test_cases[test_case], test_case=test_case, result=results.get(test_case, "NOT EXECUTED")))
  return all_results

def get_pass_rate(results: List[TestResult]) -> float:
  """
  Calculate the pass rate as a percentage of tests that passed out of those executed.
  Tests that are "NOT EXECUTED" are not counted in the denominator.
  """
  total_executed = sum(1 for result in results if result["result"] != "NOT EXECUTED")
  if total_executed == 0:
    return 0.0
  passed = sum(1 for result in results if result["result"] == "PASS")
  return (passed / total_executed) * 100.0

def generate_html_report(results: List[TestResult], run_name: str, output_path: str = "report.html"):
  """
  Generate a simple HTML report from the results list and save it to output_path.
  """
  pass_rate = get_pass_rate(results)
  pass_count = sum(1 for result in results if result["result"] == "PASS")
  fail_count = sum(1 for result in results if result["result"] == "FAIL")
  not_executed_count = sum(1 for result in results if result["result"] == "NOT EXECUTED")
  pie_chart = create_pie_chart(pass_count, fail_count, not_executed_count)
  html_content =  test_template.render(run_name=run_name,results=results, pass_rate=pass_rate, pass_count=pass_count, fail_count=fail_count, not_executed_count=not_executed_count, pie_chart=pie_chart.to_html())

  with open(output_path, "w", encoding="utf-8") as f:
    f.write(html_content)

def create_pie_chart(pass_count: int, fail_count: int, not_executed_count: int, output_path: str = "pie_chart.png"):
  """
  Create a pie chart showing the distribution of PASS, FAIL, and NOT EXECUTED results.
  Saves the chart as an image file.
  """
  # Your data
  results = {
      'PASS': pass_count,
      'FAIL': fail_count,
      'NOT_EXECUTED': not_executed_count
  }

  df = pd.DataFrame(list(results.items()), columns=['Result', 'Count'])
  total = df['Count'].sum()
  df['Percentage'] = (df['Count'] / total * 100).round(1)

  # Create pie chart with numbers
  fig = px.pie(df, values='Count', names='Result',labels='Result',
              color='Result',
              color_discrete_map={
                  'PASS': 'green',      # Green
                  'FAIL': 'red',      # Red
                  'NOT_EXECUTED': 'grey'  # grey
              },
              hole=.15
              )
  fig.update_traces(textposition='inside', textinfo='label+percent',hovertemplate='%{label}: %{value} tests (%{percent})',
              marker=dict(line=dict(color='#000000', width=2)))
  fig.update_layout(uniformtext_minsize=12, uniformtext_mode='hide')
  return fig


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Read two files: one -> list, one -> map by delimiter")
  parser.add_argument("test_cases_file", help="Path to file with all test cases")
  parser.add_argument("results_file", help='Path to file with test results in TEST_CASE: RESULT format')
  parser.add_argument("run_name", help='Name of the test run')
  args = parser.parse_args()

  test_cases = read_test_cases(args.test_cases_file)
  results = read_test_results(args.results_file)
  all_results = prepare_results(test_cases, results)
  generate_html_report(all_results, args.run_name, f"{args.run_name}_test_report.html")

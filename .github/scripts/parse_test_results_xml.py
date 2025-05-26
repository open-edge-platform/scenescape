#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys, getopt, os
import xml.etree.ElementTree as ET

def main(argv):
    inputFile = 'testResults.xml'
    outputFile = 'TestResults.txt'

    try:
        opts, args = getopt.getopt(argv,"hi:o:",["ifile=","ofile="])
    except getopt.GetoptError:
        print ('python3 get_test.py -i <inputFile> -o <outputFile>')
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print ('python3 get_test.py -i <inputFile> -o <outputFile>')
            sys.exit()
        elif opt in ("-i", "--ifile"):
            inputFile = arg
        elif opt in ("-o", "--ofile"):
            outputFile = arg

    root = ET.parse(inputFile).getroot()
    suiteResults = ''
    os.makedirs(os.path.realpath(os.path.dirname(outputFile)), exist_ok=True)
    file = open(outputFile, "w", encoding='utf-8')

    totalPassCount = 0
    totalFailCount = 0
    totalSkipCount = 0
    for suite in root.findall('suite'):
        suite_name = suite.find('name').text
        passCount = 0
        failCount = 0
        skipCount = 0
        for tc in suite.findall('case'):
            tc_name = tc.find('name').text
            tc_result = tc.find('status').text

            file.write(f"{tc_name}: {tc_result[0:4]}\n")

            if tc_result == 'PASSED' or tc_result == "FIXED":
                passCount += 1
                totalPassCount += 1
            elif tc_result == 'SKIPPED':
                skipCount += 1
                totalSkipCount += 1
            else:
                failCount += 1
                totalFailCount += 1
        suiteResults += suite_name + '|' + str(passCount) + '|' + str(failCount) + '|' + str(skipCount) + '\n'
    file.close()
    suiteResults += 'TOTAL' + '|' + str(totalPassCount) + '|' + str(totalFailCount) + '|' + str(totalSkipCount)

    print(suiteResults)

if __name__ == "__main__":
   main(sys.argv[1:])

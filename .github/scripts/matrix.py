#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
    Treaceability Matrix builder
    Program requires dependinecies. use below command to install them
    $ pip3 install pylightxl xlsxwriter getopt --proxy=$https_proxy
"""

import csv
import sys
import getopt
import pylightxl as xl
import xlsxwriter


def usage():
    """Print program usage"""
    print('matrix.py -r <requirements_trace_file> -t <test_exec_trace_file> '
          '-o <traceabilty_matrix_output>')


def new_worksheet(worksheet, header_format):
    """! method used to format worksheet table header
    @param worksheet        Worksheet to be used
    @param header_format    Text formating for header
    """
    # Prepare header and style for output data
    worksheet.write('A1', 'Requirement ID', header_format)
    worksheet.write('B1', 'Requirement Description', header_format)
    worksheet.write('C1', 'Test ID', header_format)
    worksheet.write('D1', 'Test Description', header_format)
    worksheet.write('E1', 'Execution Status', header_format)
    worksheet.write('F1', 'Execution Date', header_format)
    worksheet.write('G1', 'Executed by', header_format)

    # Set worksheet columns width
    worksheet.set_column('A:A', 15)
    worksheet.set_column('B:B', 70)
    worksheet.set_column('C:C', 15)
    worksheet.set_column('D:D', 70)
    worksheet.set_column('E:E', 20)
    worksheet.set_column('F:F', 20)
    worksheet.set_column('G:G', 25)


def add_record(worksheet, entry, data, cell_format):
    """! method used to write entries in each lane
    @param worksheet    worksheet in which we write
    @param entry        lane index
    @param data         data vector
    @param cel_format   cel format
    """
    worksheet.write(entry, 0, data[0])
    worksheet.write(entry, 1, data[1])
    worksheet.write(entry, 2, data[2])
    worksheet.write(entry, 3, data[3])
    worksheet.write(entry, 4, data[4][0], cell_format)
    worksheet.write(entry, 5, data[4][2])
    worksheet.write(entry, 6, data[4][3])


def main(argv):
    """
    @file matrix.py

    @brief  Python file used to concatenate data from
    requirements coverage report and test execution record
    into a single Traceability File
    """
    try:
        opts, args = getopt.getopt(argv,
                                   "hr:t:o:",
                                   ["rfile=", "tfile=", "ofile="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-r", "--rfile"):
            file_req_matrix = arg
        elif opt in ("-t", "--tfile"):
            file_test_record = arg
        elif opt in ("-o", "--ofile"):
            file_matrix_output = arg
        else:
            usage()
            sys.exit()
    print(f'Using following data to generate report:\n\t '
          f'matrix={file_req_matrix} \n\t '
          f'exec={file_test_record} \n\t output={file_matrix_output}')

    xl_db = xl.readxl(fn=file_req_matrix)

    # XLS sheet
    xl_worksheet = xl_db.ws(ws='Sheet1')

    # Create a new Workbook
    workbook = xlsxwriter.Workbook(file_matrix_output)
    # Prepare table format
    header_format = workbook.add_format({'bold': True})

    # Add new worksheet into the new workbook
    worksheet = workbook.add_worksheet()
    new_worksheet(worksheet, header_format)

    # worksheet.set_row(1,10) # Row hight - not neede for now

    # Variables required for parsing PRD export data
    rows, col = xl_worksheet.size
    row_skip = 5
    previous_entry = [None, None]
    entry = 1

    # For each requirement parse the execution record file
    while row_skip <= rows:
        req = xl_worksheet.index(
            row=row_skip, col=1) \
            or previous_entry[0]
        req_desc = xl_worksheet.index(
            row=(row_skip + 3), col=1) \
            or previous_entry[1]
        test_id = xl_worksheet.index(row=row_skip, col=2)
        test_desc = xl_worksheet.index(row=(row_skip+3), col=2)

        with open(file_test_record, encoding="utf8", newline='') as csvfile:
            fieldnames = ["ID",
                          "Status",
                          "Summary",
                          "Defects",
                          "Component",
                          "Folder",
                          "Label",
                          "Executed By",
                          "Executed On",
                          "Comment",
                          "Custom Fields"]
            reader = csv.DictReader(csvfile, fieldnames=fieldnames)
            for row in reader:
                if row['ID'].startswith(test_id):
                    test_execution = [row['Status'], row['Summary'],
                                      row['Executed On'], row['Executed By']]

        cell_format = workbook.add_format()
        if test_execution[0] == "PASS":
            cell_format.set_font_color('green')
        elif test_execution[0] == "FAIL":
            cell_format.set_font_color('red')
            print('found red FONT')
        else:
            cell_format.set_font_color('grey')

        # Add matching data to a new structure in the new worksheet
        data = [req, req_desc, test_id, test_desc, test_execution]
        add_record(worksheet, entry, data, cell_format)

        # worksheet.merge_range('A%s:A%s' % (entry, entry+1),)

        row_skip += 5   # Matrix requirement at every row_skip

        if req is not None:
            previous_entry[0] = req

        if req_desc is not None:
            previous_entry[1] = req_desc

        entry += 1

    worksheet.autofilter('A1:G500')     # Aproximative size for now
    workbook.close()


if __name__ == '__main__':
    if len(sys.argv) == 1:
        usage()
    else:
        main(sys.argv[1:])

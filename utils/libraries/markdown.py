# flake8: noqa: E501

"""
This module parses markdown files to extract structured test case information, 
focusing on identifying test suite requirements, test cases, their summaries, 
requirements mappings, and priorities. It supports validation of JIRA RTM identifiers 
and handles various markdown elements to accurately extract data for test management.

Classes:
- MarkdownParseException: Custom exception class for handling markdown parsing errors.
- ParserState: Enum defining different states in the parsing process.
- ParseState: Class to manage the state during markdown parsing.
- TestCase: Data class to store and manage test case information extracted from markdown.

Functions:
- render_to_markdown: Helper function to convert markdown elements to plain text.
- _get_heading_text: Extracts text from heading elements, handling potential markdown within headings.
- get_all_test_cases: Main function to parse and extract test cases from a markdown document.
- parse_file_for_tests: Parses a file and extracts test cases, setting up logging and file handling.
"""

import logging
import re

import marko
from marko.md_renderer import MarkdownRenderer

from enum import Enum

logger = logging.getLogger(__name__)

"""
Python script to parse all markdown files in given directory.

It finds all the destination of all links checks that all anchor links have target
in the document.
"""

JIRA_RTM_RE = re.compile(r'^(?:PTCV|NEX|ITEP|(?:NEX)[A-Za-z0-9]+)-\d+$')


class MarkdownParseException(Exception):
    """Exception raised for errors in the markdown parsing process."""
    pass


class ParserState(Enum):
    """Enumeration of different states in the markdown parsing process for structured test case extraction."""
    LOOKING_FOR_TITLE_TEST_SUITE_RTM = 1
    LOOKING_FOR_TEST_SUITE_RTM = 2
    LOOKING_FOR_TITLE_ID = 3
    LOOKING_FOR_TITLE_SUMMARY = 4
    LOOKING_FOR_SUMMARY = 5
    LOOKING_FOR_TITLE_TEST_RTM = 6
    LOOKING_FOR_TEST_RTM = 7
    LOOKING_FOR_TITLE_PRIORITY = 8
    LOOKING_FOR_PRIORITY = 9


class ParseState():
    """
    Manages the state during the parsing of markdown documents to track and control the flow based on the content structure.

    Attributes:
        state (ParserState): The current state of the parser.
        test_cases (list): Accumulated test cases during parsing.
        suite_rtm (list): List of RTM identifiers found at the suite level.
    """
    def __init__(self):
        self.state = ParserState.LOOKING_FOR_TITLE_TEST_SUITE_RTM
        self.test_cases = []
        self.suite_rtm = []


class TestCase():
    """
    Represents a test case with attributes extracted from markdown content.

    Attributes:
        title (str): The title of the test case.
        summary (str): The summary description of the test case.
        rtm (list): List of requirement traceability matrix identifiers.
        priority (str): Priority of the test case.
        path (str): File path where the test case is documented.
    """
    def __init__(self, title="", summary="", rtm=None, priority=""):
        self.title = title
        self.summary = summary
        self.versions = []
        self.automated = None  # None = not specified, True/False = yes/no
        if rtm:
            self.rtm = rtm[::]  # make a copy
        else:
            self.rtm = []
        self.priority = priority

        self.path = ""

    def __str__(self):
        return self.title

    def __repr__(self):
        return repr([self.title, self.summary, self.rtm, self.priority, self.automated, self.versions])


def render_to_markdown(e):
    """
    Renders markdown elements to plain text using a markdown renderer.
    This is used to handle markdown within elements like headings.

    Parameters:
        e (element): The markdown element to render.

    Returns:
        str: The rendered plain text.
    """
    m = marko.Markdown(renderer=MarkdownRenderer)
    m.parse('')  # bug in marko that need to parse before render
    return m.render(e)


def _get_heading_text(c):
    """
    Extracts and returns text from a markdown heading element, ensuring it does not contain additional markdown formatting.

    Parameters:
        c (element): The heading element.

    Returns:
        str: The text of the heading.

    Raises:
        MarkdownParseException: If the heading contains additional markdown elements.
    """
    heading = c.children[0].children  # header text is the first child
    if not isinstance(heading, str):
        render = render_to_markdown(c).strip()
        raise MarkdownParseException(f"Heading should not contain additional markdown: '{render}'")
    return heading


def get_all_test_cases(e, state=None, depth=1):  # noqa:C901
    """
    Recursively extracts all test cases from a markdown document using depth-first search of parsed tree.
    Get all headings in given markdown document. 

    Parameters:
        e (element): The root element of the markdown document.
        state (ParseState, optional): The current state of parsing.
        depth (int): Current depth in the recursive parsing process.

    Returns:
        list: A list of TestCase instances extracted from the document.
    """
    if state is None:
        state = ParseState()

    for c in e.children:
        if state.state == ParserState.LOOKING_FOR_TEST_SUITE_RTM:
            if isinstance(c, marko.block.Heading):
                state.state = ParserState.LOOKING_FOR_TITLE_ID
            else:
                if isinstance(c, marko.block.List):
                    for list_item in c.children:
                        # Skip empty list items
                        if not list_item.children:
                            continue
                        paragraph = list_item.children[0]
                        # Skip list items without proper structure
                        if not hasattr(paragraph, 'children') or not paragraph.children:
                            continue
                        link = paragraph.children[0]
                        if not hasattr(link, 'children') or not link.children:
                            continue
                        if not hasattr(link.children[0], 'children'):
                            continue
                        title = link.children[0].children
                        if JIRA_RTM_RE.match(title):
                            state.suite_rtm.append(title)
                    continue
                else:
                    if isinstance(c, marko.block.BlankLine):
                        continue
                    else:
                        raise MarkdownParseException("Unexpected content when looking for suite level RTM")

        if state.state == ParserState.LOOKING_FOR_SUMMARY:
            if isinstance(c, marko.block.Heading):
                state.state = ParserState.LOOKING_FOR_TITLE_TEST_RTM
            else:
                render = render_to_markdown(c)
                state.test_cases[-1].summary += render
                continue  # this is the leaf so we wont descend further

        if state.state == ParserState.LOOKING_FOR_TEST_RTM:
            if isinstance(c, marko.block.Heading):
                state.state = ParserState.LOOKING_FOR_TITLE_PRIORITY
            else:
                if isinstance(c, marko.block.List):
                    state.test_cases[-1].rtm = []
                    for list_item in c.children:
                        # Skip empty list items
                        if not list_item.children:
                            continue
                        paragraph = list_item.children[0]
                        # Skip list items without proper structure
                        if not hasattr(paragraph, 'children') or not paragraph.children:
                            continue
                        link = paragraph.children[0]
                        if not hasattr(link, 'children') or not link.children:
                            continue
                        if not hasattr(link.children[0], 'children'):
                            continue
                        title = link.children[0].children
                        if JIRA_RTM_RE.match(title):
                            state.test_cases[-1].rtm.append(title)
                    continue
                else:
                    if isinstance(c, marko.block.BlankLine):
                        continue
                    else:
                        raise MarkdownParseException("Unexpected content when looking for suite level RTM")

        if state.state == ParserState.LOOKING_FOR_PRIORITY:
            if isinstance(c, marko.block.Heading):
                state.state = ParserState.LOOKING_FOR_TITLE_ID
            else:
                if isinstance(c, marko.block.List):
                    list_items = c.children
                    # Skip if no list items or first item is empty
                    if not list_items or not list_items[0].children:
                        continue
                    paragraph = list_items[0].children[0]
                    if not hasattr(paragraph, 'children') or not paragraph.children:
                        continue
                    if not hasattr(paragraph.children[0], 'children'):
                        continue
                    priority = paragraph.children[0].children
                    state.test_cases[-1].priority = priority
                    continue
                else:
                    if isinstance(c, marko.block.BlankLine):
                        continue
                    else:
                        raise MarkdownParseException("Unexpected content when looking for suite level RTM")

        if state.state == ParserState.LOOKING_FOR_TITLE_TEST_SUITE_RTM:
            if isinstance(c, marko.block.Heading):
                title = _get_heading_text(c)
                if re.match(r'Test suite requirements mapping', title):
                    state.state = ParserState.LOOKING_FOR_TEST_SUITE_RTM
                    continue

        if state.state in (ParserState.LOOKING_FOR_TITLE_ID,
                           # We can be looking for this since optional
                           ParserState.LOOKING_FOR_TITLE_TEST_SUITE_RTM,
                           # We can be looking for these two also since they are optional
                           ParserState.LOOKING_FOR_TITLE_TEST_RTM,
                           ParserState.LOOKING_FOR_TITLE_PRIORITY,
                           ):
            if isinstance(c, marko.block.Heading):
                title = _get_heading_text(c)
                if re.match(r'^Vis[^ ]+\d+: ', title):
                    state.test_cases.append(TestCase(title, rtm=state.suite_rtm))
                    state.state = ParserState.LOOKING_FOR_TITLE_SUMMARY
                    continue

        if state.state == ParserState.LOOKING_FOR_TITLE_SUMMARY:
            if isinstance(c, marko.block.Heading):
                title = _get_heading_text(c)
                if re.match(r'Test summary', title):
                    state.state = ParserState.LOOKING_FOR_SUMMARY
                    continue
            else:
                if isinstance(c, marko.block.BlankLine):
                    pass
                elif isinstance(c, marko.block.Paragraph):
                    paragraph = render_to_markdown(c).strip()
                    # Accept both "Affects Versions:" and "Affected Versions:"
                    if paragraph.startswith("Affects Versions:") or paragraph.startswith("Affected Versions:"):
                        vv = paragraph.split(' ')[2:]
                        state.test_cases[-1].versions = vv
                    # Parse "Automated: yes/no"
                    elif paragraph.startswith("Automated:"):
                        automated_value = paragraph.split(':', 1)[1].strip().lower()
                        if automated_value in ('yes', 'true'):
                            state.test_cases[-1].automated = True
                        elif automated_value in ('no', 'false'):
                            state.test_cases[-1].automated = False
                        # If value is invalid or empty, leave as None
                    continue  # we rendered so don't descend further
                else:
                    raise MarkdownParseException("Found something unexpected when looking for title_summary")


        if state.state == ParserState.LOOKING_FOR_TITLE_TEST_RTM:
            if isinstance(c, marko.block.Heading):
                title = _get_heading_text(c)
                if re.match(r'Test requirements mapping', title):
                    state.state = ParserState.LOOKING_FOR_TEST_RTM
                    continue

        if state.state in (ParserState.LOOKING_FOR_TITLE_PRIORITY,
                           # we can be looking for test rtm since it is optional
                           ParserState.LOOKING_FOR_TITLE_TEST_RTM,
                           ):
            if isinstance(c, marko.block.Heading):
                title = _get_heading_text(c)
                if re.match(r'Test priority', title):
                    state.state = ParserState.LOOKING_FOR_PRIORITY
                    continue

        if hasattr(c, 'children') and isinstance(c.children, list) \
                and (not isinstance(c, marko.block.Heading)):  # only descend if there are children
            get_all_test_cases(c, state, depth+1)

    if depth == 1 and state.state == ParserState.LOOKING_FOR_TITLE_SUMMARY:
        raise MarkdownParseException("Found EOF when looking for 'Test summary' (note case-sensitive)")

    return state.test_cases


def parse_file_for_tests(fn):
    """
    Opens and parses a markdown file to extract test cases.

    Parameters:
        fn (str): Filename of the markdown file to parse.

    Returns:
        list: A list of TestCase instances extracted from the file.
    """
    logger.info(f"Processing: {fn}")

    with open(fn, 'r') as fh:
        data = fh.read()

    doc = marko.parse(data)

    test_cases = get_all_test_cases(doc)

    for test in test_cases:
        test.path = fn

    return test_cases

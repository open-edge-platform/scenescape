# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Configuration file for the Sphinx documentation builder.
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

import os
import sys

# -- Project information -----------------------------------------------------

project = 'Cluster Analytics'
copyright = '2025, Intel Corporation'
author = 'Intel Corporation'

# The full version, including alpha/beta/rc tags
release = '1.0.0'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinxcontrib.mermaid',  # Add mermaid extension for diagram support
    'myst_parser',  # Support for Markdown files
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The suffix(es) of source filenames.
source_suffix = {
    '.rst': None,
    '.md': 'markdown',
}

# The master toctree document.
master_doc = 'toc'

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = 'sphinx_rtd_theme'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# -- Extension configuration -------------------------------------------------

# -- Options for mermaid extension ------------------------------------------

# Configure mermaid to use a specific version (optional)
mermaid_version = "10.6.1"

# Mermaid configuration (optional)
mermaid_init_js = """
mermaid.initialize({
    theme: 'default',
    themeVariables: {
        primaryColor: '#0071c5',
        primaryTextColor: '#000000',
        primaryBorderColor: '#0071c5',
        lineColor: '#666666',
        secondaryColor: '#f4f4f4',
        tertiaryColor: '#ffffff'
    }
});
"""

# -- Options for MyST parser ------------------------------------------------

# Allow parsing of markdown files
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "html_admonition",
    "html_image",
    "linkify",
    "replacements",
    "smartquotes",
    "substitution",
    "tasklist"
]

# -- Options for intersphinx extension --------------------------------------

# Links to other projects' documentation
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}
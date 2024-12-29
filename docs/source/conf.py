#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# grill documentation build configuration file, created by
# sphinx-quickstart on Thu Mar 23 23:30:17 2017.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))
import functools
from datetime import datetime
from sphinxcontrib.doxylink import doxylink as _doxylink_ext

# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.doctest',
    'sphinx.ext.intersphinx',
    'sphinx.ext.inheritance_diagram',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.graphviz',
    "myst_parser",
    'sphinx_copybutton',
    'sphinx_toggleprompt',
    'sphinx_togglebutton',
    'sphinx_inline_tabs',
    'hoverxref.extension',
    'sphinx.ext.autosectionlabel',
    'sphinxcontrib.doxylink',
]

# Offset to play well with copybutton
toggleprompt_offset_right = 35
togglebutton_hint = " "
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'usd': ('https://openusd.org/release/', None),
    'networkx': ('https://networkx.org/documentation/stable/', None),
    'naming': ('https://naming.readthedocs.io/en/latest/', None),
    'grill.names': ('https://grill-names.readthedocs.io/en/latest/', None)
}

hoverxref_auto_ref = True
hoverxref_default_type = 'tooltip'

hoverxref_intersphinx = list(set(intersphinx_mapping) - {'python', 'usd', 'networkx'})  # only works for RTD hosted docs
hoverxref_intersphinx_types = dict.fromkeys(intersphinx_mapping, hoverxref_default_type)
hoverxref_domains = ['py']
always_document_param_types = True
autodoc_member_order = 'groupwise'
maximum_signature_line_length = 150
inheritance_graph_attrs = dict(rankdir="TB", bgcolor='transparent')

inheritance_node_attrs = dict(
    shape='Mrecord',
    color='"#088d91"',
    style='filled',
    fillcolor='"#ecf8f9"',
    size='"6.0, 8.0"'
)

inheritance_edge_attrs = dict(color='"#088d91"')

autodoc_default_flags = ['members', 'show-inheritance']
# graphviz_dot = r'B:\__appdata__\graphviz\bin\dot.exe'
graphviz_output_format = 'svg'
# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
source_suffix = ['.rst', '.md']

# The master toctree document.
master_doc = 'index'

# General information about the project.
# project = 'grill'
project = '👨‍🍳 Cook digital.'
copyright = f'{datetime.now().year}, The Grill'
author = 'The Grill'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
version = '0.18'
# The full version, including alpha/beta/rc tags.
release = '0.18.0'

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = 'en'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This patterns also effect to html_static_path and html_extra_path
exclude_patterns = []

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'
highlight_language = 'python3'

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
# also tried: python_docs_theme, sphinx_rtd_theme
html_theme = 'shibuya'

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
#

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']
html_css_files = [
  'custom.css',
]

# -- Options for HTMLHelp output ------------------------------------------

# Output file base name for HTML help builder.
htmlhelp_basename = 'grilldoc'
html_sidebars = {
    '**': [
    ]
}
html_title = '👨‍🍳 The Grill'
html_theme_options = {
    "accent_color": "sky",
    "github_url": "https://github.com/thegrill/grill",
    "globaltoc_expand_depth": 2,
    "toctree_collapse": True,
    "toctree_titles_only": False,
}
# -- Options for LaTeX output ---------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #
    # 'papersize': 'letterpaper',

    # The font size ('10pt', '11pt' or '12pt').
    #
    # 'pointsize': '10pt',

    # Additional stuff for the LaTeX preamble.
    #
    # 'preamble': '',

    # Latex figure (float) alignment
    #
    # 'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    (master_doc, 'grill.tex', 'grill Documentation',
     'The Grill', 'manual'),
]


# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    (master_doc, 'grill', 'grill Documentation',
     [author], 1)
]


# -- Options for Texinfo output -------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (master_doc, 'grill', 'grill Documentation',
     author, 'grill', 'One line description of project.',
     'Miscellaneous'),
]



# -- Options for Epub output ----------------------------------------------

# Bibliographic Dublin Core info.
epub_title = project
epub_author = author
epub_publisher = author
epub_copyright = copyright

# The unique identifier of the text. This can be a ISBN number
# or the project homepage.
#
# epub_identifier = ''

# A unique identification for the text.
#
# epub_uid = ''

# A list of files that should not be packed into the epub file.
epub_exclude_files = ['search.html']

_USD_DOXYGEN_CACHE_NAME = 'usdcpp'
_USD_DOXYGEN_ROOT_DIR = "https://openusd.org/release/api/"
doxylink = {
    _USD_DOXYGEN_CACHE_NAME: ("https://openusd.org/release/USD.tag", _USD_DOXYGEN_ROOT_DIR)
}


@functools.cache
def _get_doxylink_part(text):
    __, __, part = _doxylink_ext.split_explicit_title(text)
    return _doxylink_ext.utils.unescape(part)


@functools.cache
def _get_usd_ref_tooltip(app):
    # TODO: find a less hacky way of achieving this (aiming for consistency with intersphinx titles on hovered links)
    proj, version, __, __ = app.env.intersphinx_named_inventory['usd']['std:doc']['README']
    return f"(in {proj} v{version})"


@functools.cache
def _get_url_for_target(app, target):
    pxr_obj_namespace = target.removeprefix('pxr.').replace(".", "")
    pxr_obj_namespace = {
        "UsdInitialLoadSet": "UsdStage::InitialLoadSet",   # there's indirection in the python bindings
        "UsdFilter": "UsdPrimCompositionQuery::Filter",    # filter is a member of the query type
        "UsdCompositionArc": "UsdPrimCompositionQueryArc",
        "Usd_Term": "primFlags.h",
        "Usd_PrimFlagsConjunction": "primFlags.h",
    }.get(pxr_obj_namespace, pxr_obj_namespace)
    part = _get_doxylink_part(pxr_obj_namespace)
    url = app.env.doxylink_cache[_USD_DOXYGEN_CACHE_NAME]['mapping'][part]
    full_url = _doxylink_ext.join(_USD_DOXYGEN_ROOT_DIR, url.file)
    reftitle = _get_usd_ref_tooltip(app)
    return part + " " + reftitle, full_url


def _handle_missing_usd_reference(app, env, node, contnode):
    from docutils import nodes

    target = node['reftarget']
    if not target.startswith('pxr.'):
        return None

    reftitle, refuri = _get_url_for_target(app, target)
    node = nodes.reference('', contnode.astext(), internal=False, refuri=refuri, reftitle=reftitle)
    return node


def _grill_process_signature(app, what, name, obj, options, signature, return_annotation):
    if name == "grill.usd.iprims":
        # TODO: Report to pixar
        #   Prim predicates don't have a __repr__, which creates malformed signature formatting (no new lines, no links)
        signature = signature.replace("<pxr.Usd._PrimFlagsConjunction object>", "Usd.PrimDefaultPredicate")
    return signature, return_annotation


_doxylink_create_role = _doxylink_ext.create_role


def _create_doxylink_role_with_title(app, *args, **kwargs):
    # TODO: find a less hacky way of achieving this (aiming for consistency with intersphinx titles on hovered links)
    doxylink_role = _doxylink_create_role(app, *args, **kwargs)
    intersphinx_title = _get_usd_ref_tooltip(app)

    def _find_doxygen_link_with_title(name, rawtext, text, *patched_args, **patched_kwargs):
        inner_result = doxylink_role(name, rawtext, text, *patched_args, **patched_kwargs)
        node = inner_result[0][0]

        part = _get_doxylink_part(text)

        node.attributes['reftitle'] = part + " " + intersphinx_title
        return inner_result

    return _find_doxygen_link_with_title


_doxylink_ext.create_role = _create_doxylink_role_with_title


def setup(app):
    """Setup Sphinx to handle missing USD references. This can be removed when the USD C++ docs ship with an inventory of the USD types for python bindings."""
    app.connect("autodoc-process-signature", _grill_process_signature)
    app.connect("missing-reference", _handle_missing_usd_reference)
    return {"parallel_read_safe": True, "parallel_write_safe": True}

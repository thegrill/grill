.. grill documentation master file, created by
   sphinx-quickstart on Thu Mar 23 23:30:17 2017.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. mdinclude:: ../../README.md

.. toctree::
   :maxdepth: 2

----

.. include:: install.rst

Pipeline
========

Core Concepts
-------------
.. graphviz:: pipeline_concepts.dot

Relationships
-------------
.. graphviz:: pipeline_relationships.dot

Data Flow
---------
.. graphviz:: pipeline_flow.dot

Workflow Charts Legend
----------------------

``The Grill`` flow charts will use the following symbol legend:

.. graphviz:: flowchart_legend.dot

Data Creation
-------------

At the highest level, all asset data, from creation to finish, goes through the same life cycle:

.. graphviz:: data_creation.dot

----

Views (Inspecting / Authoring)
==============================

The ``grill.views`` package provides Qt widgets to author and inspect USD scene graphs.

Convenience launchers and menus for **USDView**, **Houdini** and **Maya** are provided (appearing under the ``👨‍🍳 Grill`` menu), but any DCC or environment with ``USD`` and ``PySide2`` should be able to use the widgets.

.. include:: spreadsheet_editor.rst

.. include:: prim_composition.rst

.. include:: layerstack_composition.rst


End to End Example
==================

.. include:: creating_assets.rst

Indices and tables
==================

* :ref:`genindex`

.. grill documentation master file, created by
   sphinx-quickstart on Thu Mar 23 23:30:17 2017.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. mdinclude:: ../../README.md

.. toctree::
   :maxdepth: 2

----

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

----

Workflow Charts Legend
----------------------

``the grill`` flow charts will use the following symbol legend:

.. graphviz:: flowchart_legend.dot

----

Data Creation
-------------

At the highest level, all asset data, from creation to finish, goes through the same life cycle:

.. graphviz:: data_creation.dot

----

Indices and tables
------------------

* :ref:`genindex`

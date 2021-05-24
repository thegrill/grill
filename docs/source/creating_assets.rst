Creating Assets
---------------

Repository Path
~~~~~~~~~~~~~~~

Creating assets requires a repository path to be set. If not set, a dialog to set it will be prompted upon creation request.

To set the repository path at any point, go to ``Grill -> Preferences -> Repository Path``:

.. image:: https://user-images.githubusercontent.com/8294116/114215808-681a2a00-99a9-11eb-85c2-04d45d5a3aef.gif

Defining Taxonomy
~~~~~~~~~~~~~~~~~

The default is one, but any number of assets can be created at the same time by changing the ``Amount`` value.

For asset organization, ``The Grill`` uses the concept of asset `taxonomy`_. This is a hierarchy for organizing assets into groups (``Taxa``) where members of each individual group (``Taxon``) share characteristics (e.g. ``Characters``, ``Props`` and ``Shots`` are common organizational groups found on ``Film`` and ``Animation`` projects). To define new ``taxa``, the ``Taxonomy Editor`` provides basic functionality. It has the following structure:

.. image:: https://user-images.githubusercontent.com/8294116/119260086-8ca62a80-bc14-11eb-91be-23a191c97503.PNG

Where: 

::

    +----------------------------------------------------------------------------------------------------------------------------------------------------+
    | Amount of Taxa to Create (Defaults to 1)                                                                                                           |
    +=================================================+===========================+======================================+===============================+
    | Existing Taxa (If any)                          | New Taxon Name (Required) |       References (Optional)          |      ID Fields (Optional)     |
    +-------------------------------------------------+                           |                                      |                               |
    | Selected Taxon Graph                            |                           | - New taxon will inherit properties  | - Additional key value asset  |
    |                                                 |                           |   from selected pre-existing taxa.   |   field identifiers.          |
    | - In the form of:                               |                           |                                      |                               |
    |                                                 |                           |                                      |                               |
    |   ancestor(s) -> selected taxon -> successor(s) |                           |                                      |                               |
    +-------------------------------------------------+---------------------------+--------------------------------------+-------------------------------+


Creating Asset Units
~~~~~~~~~~~~~~~~~~~~

An ``Asset Unit`` is considered to be a meaningful, unique member for each taxon. A ``taxon`` can contain any number of individual ``units``.

In the example below, 240 “City” assets are created, copied from a CSV file and pasted directly on the “Create Assets” table.

All created assets are saved to disk on the current repository path.

.. image:: https://user-images.githubusercontent.com/8294116/112751505-263ccb80-901a-11eb-8a64-d46ef43dd087.gif


Modifying Assets
~~~~~~~~~~~~~~~~

Any USD application should now be able to modify the grill assets.

In the example below, an asset defined on USDView (on the right) is opened and modified in Maya (on the left). Then reloaded in USDView. Taxonomy can also be modified in Maya and USDView will receive changes.

.. image:: https://user-images.githubusercontent.com/8294116/119356500-d6147980-bce9-11eb-946e-486986071ef8.gif

.. _taxonomy: https://en.wikipedia.org/wiki/Taxonomy

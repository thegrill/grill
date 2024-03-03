Connections Viewer
------------------

From a given `prim`_, recursively traverse its connections through `UsdShade.ConnectableAPI`_.
Every node represents a `prim`_, with its name at the top, followed by each of its inputs and outputs.
Outputs are marked as red. Inputs are blue (light for non connected inputs, dark for ones with incoming connections).

.. tab:: USDView

    .. image:: images/connections_viewer_usdview.gif

.. tab:: Houdini

    .. image:: images/connections_viewer_hou.jpg

.. tab:: Maya

    .. image:: images/connections_viewer_maya.jpg

.. _UsdShade.ConnectableAPI: https://openusd.org/release/api/class_usd_shade_connectable_a_p_i.html
.. _prim: https://openusd.org/release/glossary.html#usdglossary-prim


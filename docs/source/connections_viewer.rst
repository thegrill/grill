Connections Viewer
------------------

From a given :ref:`glossary:prim`, recursively traverse its :ref:`Connections <glossary:connection>` through :usdcpp:`UsdShadeConnectableAPI`.
Every node represents a :ref:`glossary:prim`, with its name at the top, followed by each of its :usdcpp:`inputs <UsdShadeInput>` (colored dark blue if :usdcpp:`connected <UsdShadeInput::GetConnectedSources>`, else light blue) and :usdcpp:`outputs <UsdShadeOutput>` (in red).

.. tab:: USDView

    .. image:: images/connections_viewer_usdview.gif

.. tab:: Houdini

    .. image:: images/connections_viewer_hou.jpg

.. tab:: Maya

    .. image:: images/connections_viewer_maya.jpg

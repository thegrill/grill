Connections Viewer
------------------

From a given :ref:`glossary:prim`, recursively traverse its upstream :ref:`Connections <glossary:connection>`.

When the prim has :usdcpp:`UsdShadeConnectableAPI` inputs or outputs, connections are followed through the shading API. Otherwise, connections are followed through :usdcpp:`UsdAttribute` connection paths. This includes **OpenExec invertible rigs** (``IrJointScope``, ``IrFkController``, ``IrSwitchController``, and related prims) where animation and controller wiring is authored via attribute ``.connect`` relationships.

Every node represents a :ref:`glossary:prim` with its name at the top (and schema type when available). Ports below represent connected attributes or shade inputs/outputs.

Port colors
~~~~~~~~~~~

**UsdShade prims**

- :usdcpp:`Inputs <UsdShadeInput>` — dark blue if :usdcpp:`connected <UsdShadeInput::GetConnectedSources>`, otherwise light blue
- :usdcpp:`Outputs <UsdShadeOutput>` — red (light coral)

**OpenExec / attribute-connected prims**

When schema metadata is available, port colors reflect ``irRole``:

- **InputAttribute** — dark blue if connected, otherwise light blue (controller inputs, wired avars)
- **OutputAttribute** — red (light coral); computed outputs such as ``out:space`` and ``posed:space``
- **SwitchAttribute** — gold (switch tokens, rotation order)
- **PassthroughAttribute** — light gray (passthrough spaces such as ``in:defaultSpace``)

The viewer shows the **authored connection graph** on the USD stage. It does not display the compiled OpenExec evaluation network (that requires C++ ``ExecUsdSystem`` diagnostics today).

.. tab:: USDView

    .. image:: images/connections_viewer_usdview.gif

.. tab:: Houdini

    .. image:: images/connections_viewer_hou.jpg

.. tab:: Maya

    .. image:: images/connections_viewer_maya.jpg

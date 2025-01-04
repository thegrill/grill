Prim Composition
----------------

Uses existing :ref:`glossary:prim` utilities (:usdcpp:`UsdPrimCompositionQuery`, :usdcpp:`PcpPrimIndex::DumpToDotGraph`, :usdcpp:`PcpPrimIndex::DumpToString`) to help inspect :ref:`glossary:composition arcs` beyond what is possible by default in :ref:`toolset:usdview`.

To visualize the :ref:`glossary:composition` graph, the ``graphviz`` library needs to be available in the environment.

.. tab:: USDView

    .. image:: images/prim_composition_usdview.gif

.. tab:: Houdini

    .. image:: https://user-images.githubusercontent.com/8294116/223416152-d7c456d1-6995-48e4-93e0-a89f89200d4e.gif

.. tab:: Maya

    .. image:: prim_composition_maya.gif


Setting an Edit Target
~~~~~~~~~~~~~~~~~~~~~~

The ``Prim Composition`` tree exposes a context menu with a ``Set as Edit Target`` item.
This redirects edits under the selected :ref:`arc <glossary:composition arcs>` by setting the current :ref:`stage's <glossary:stage>` :ref:`glossary:edittarget`.

In the examples below, prims under ``ChairB_2`` and ``CheerioA_164`` have their :usdcpp:`displayColor <UsdGeomGprim::GetDisplayColorAttr>`, :usdcpp:`doc <UsdObject::GetDocumentation>` and :usdcpp:`active <UsdPrim::SetActive>` properties modified in ``USDView``, ``Houdini`` and ``Maya`` respectively, and changes are inspected via the ``Layer Content Browser`` view.

.. tab:: USDView

    #. The :ref:`glossary:references` arc targeting the ``Chair.geom.usd`` :ref:`glossary:layer` is set as :ref:`glossary:edittarget`.

       When :usdcpp:`displayColor <UsdGeomGprim::GetDisplayColorAttr>` is modified, the changes are visible on **both** ``ChairB_1`` **and** ``ChairB_2``, since they share that arc.

    #. The :ref:`local arc <glossary:livrps strength ordering>` targeting the :ref:`local root <glossary:root layerstack>` ``Kitchen_set.usd`` layer is set as :ref:`glossary:edittarget`.

       Once the :usdcpp:`displayColor <UsdGeomGprim::GetDisplayColorAttr>` is modified, the changes are visible on ``ChairB_2`` **only**, since nothing else shares that arc.

    .. image:: https://user-images.githubusercontent.com/8294116/156912114-a24b81f4-63b1-4b62-9d84-9e2c07aaef5c.gif

.. tab:: Houdini

    #. The :ref:`glossary:payload` arc targeting the ``Cheerio_payload.usd`` layer is set as :ref:`glossary:edittarget`.

       When :usdcpp:`doc <UsdObject::GetDocumentation>` of the ``CheerioA_164`` prim is modified, the changes are visible on **all** ``CheerioA_*`` prims, since they share the composition arc and the layer being modified.

    #. The :ref:`local arc <glossary:livrps strength ordering>` arc targeting the anonymous houdini LOP layer from the :ref:`glossary:root layerstack` is set as :ref:`glossary:edittarget`.

       Once the :usdcpp:`doc <UsdObject::GetDocumentation>` is modified, the changes are visible on ``CheerioA_164`` **only**, since nothing else shares that arc.

    .. image:: https://user-images.githubusercontent.com/8294116/158165374-fe42d80e-8d32-48a4-a628-f6255b5a9e55.gif

.. tab:: Maya

    #. The :ref:`glossary:payload` arc targeting the ``Chair_payload.usd`` layer is set as :ref:`glossary:edittarget`.

       When the :usdcpp:`active <UsdPrim::SetActive>` property is modified, the changes are visible on **both** ``ChairB_1`` **and** ``ChairB_2``, since they share the composition arc and the layer being modified.

    #. The :ref:`local arc <glossary:livrps strength ordering>` targeting the ``Kitchen_set.usd`` layer in the :ref:`glossary:root layerstack` is set as :ref:`glossary:edittarget`.

       Once the :usdcpp:`active <UsdPrim::SetActive>` property is modified, the changes are visible on ``ChairB_2`` **only**, since nothing else shares that arc.

    .. image:: https://user-images.githubusercontent.com/8294116/158165402-c1dd5119-fe78-4332-8ded-1495703345f9.gif

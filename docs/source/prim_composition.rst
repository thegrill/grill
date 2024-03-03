Prim Composition
----------------

Uses existing `USD Prim`_ utilities (`Usd.PrimCompositionQuery`_, `PrimIndex.DumpToDotGraph`_, `PrimIndex.DumpToString`_) to help inspect `composition arc details`_ beyond what is possible by default in USD view.
To visualize the composition graph, the ``graphviz`` library needs to be available on the environment.

.. tab:: USDView

    .. image:: images/prim_composition_usdview.gif

.. tab:: Houdini

    .. image:: https://user-images.githubusercontent.com/8294116/223416152-d7c456d1-6995-48e4-93e0-a89f89200d4e.gif

.. tab:: Maya

    .. image:: https://user-images.githubusercontent.com/8294116/115137817-9fed3580-a06b-11eb-81d6-07d7c0fd854d.gif


Setting an Edit Target
~~~~~~~~~~~~~~~~~~~~~~

The ``Prim Composition`` tree exposes a context menu with a ``Set as Edit Target`` item.
This redirect edits under the selected arc by setting the current stage's `Edit Target`_.

In the examples below, prims under ``ChairB_2`` and ``CheerioA_164`` have their `displayColor`_, ``doc`` and ``active`` properties modified in ``USDView``, ``Houdini`` and ``Maya`` respectively, and changes are inspected via the ``Layer Content Browser`` view.

.. tab:: USDView

    #. The ``reference`` arc targeting the ``Chair.geom.usd`` layer is set as `Edit Target`_.

       When `displayColor`_ is modified, the changes are visible on **both** ``ChairB_1`` **and** ``ChairB_2``, since they share the composition arc and the layer being modified.

    #. The ``root`` arc targeting the ``Kitchen_set.usd`` layer is set as `Edit Target`_.

       Once the `displayColor`_ is modified, the changes are visible on ``ChairB_2`` **only**, since nothing else shares that arc.

    .. image:: https://user-images.githubusercontent.com/8294116/156912114-a24b81f4-63b1-4b62-9d84-9e2c07aaef5c.gif

.. tab:: Houdini

    #. The ``payload`` arc targeting the ``Cheerio_payload.usd`` layer is set as `Edit Target`_.

       When ``doc`` of the ``CheerioA_164`` prim is modified, the changes are visible on **all** ``CheerioA_*`` prims, since they share the composition arc and the layer being modified.

    #. The ``root`` arc targeting the anonymous houdini LOP layer is set as `Edit Target`_.

       Once the ``doc`` is modified, the changes are visible on ``CheerioA_164`` **only**, since nothing else shares that arc.

    .. image:: https://user-images.githubusercontent.com/8294116/158165374-fe42d80e-8d32-48a4-a628-f6255b5a9e55.gif

.. tab:: Maya

    #. The ``payload`` arc targeting the ``Chair_payload.usd`` layer is set as `Edit Target`_.

       When ``active`` property is modified, the changes are visible on **both** ``ChairB_1`` **and** ``ChairB_2``, since they share the composition arc and the layer being modified.

    #. The ``root`` arc targeting the ``Kitchen_set.usd`` layer is set as `Edit Target`_.

       Once the ``active`` property is modified, the changes are visible on ``ChairB_2`` **only**, since nothing else shares that arc.

    .. image:: https://user-images.githubusercontent.com/8294116/158165402-c1dd5119-fe78-4332-8ded-1495703345f9.gif

.. _Usd.PrimCompositionQuery: https://openusd.org/release/api/class_usd_prim_composition_query.html
.. _PrimIndex.DumpToDotGraph: https://openusd.org/release/api/class_pcp_prim_index.html#a354744c0f0132f3be40ba4d0b85c966d
.. _PrimIndex.DumpToString: https://openusd.org/release/api/class_pcp_prim_index.html#a04007d783df319a8101b20e99bbdddd5
.. _USD Prim: https://openusd.org/release/glossary.html#usdglossary-prim
.. _composition arc details: https://openusd.org/release/glossary.html#usdglossary-compositionarcs
.. _Edit Target: https://openusd.org/release/glossary.html#edittarget
.. _displayColor: https://openusd.org/release/api/class_usd_geom_gprim.html#a0f8310a9dbe0bfc4be2bf4aa32e4a3e4
.. _Mesh: https://openusd.org/release/api/class_usd_geom_mesh.html#details

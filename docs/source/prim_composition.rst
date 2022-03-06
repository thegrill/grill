Prim Composition
----------------

Uses existing `USD Prim`_ utilities to present extended `composition arc details`_ than the ones visible by default on USD view.
To visualize the composition graph, the ``graphviz`` library needs to be available on the environment.

.. tab:: USDView

    .. image:: https://user-images.githubusercontent.com/8294116/98809052-1f4d5c00-2471-11eb-965d-43cea0c57322.gif

.. tab:: Houdini

    .. image:: https://user-images.githubusercontent.com/8294116/98945804-1dee6300-2547-11eb-8e9b-3f0211af6f3c.gif

.. tab:: Maya

    .. image:: https://user-images.githubusercontent.com/8294116/115137817-9fed3580-a06b-11eb-81d6-07d7c0fd854d.gif


Setting an Edit Target
~~~~~~~~~~~~~~~~~~~~~~

The ``Prim Composition`` tree exposes a context menu with a ``Set as Edit Target`` item.
This redirect edits under the selected arc by setting the current stage's `Edit Target`_.

In the example below, Mesh prims under ChairB_2 have their displayColor property modified:

#. The reference arc targeting the ``Chair.geom.usd`` layer is set as `Edit Target`_.

   When ``displayColor`` is modified, the changes are visible on **both** ``ChairB_1`` **and** ``ChairB_2``, since they share the composition arc and the layer being modified.

#. The root arc targeting the ``Kitchen_set.usd`` layer is set as `Edit Target`_.

   Once the ``displayColor`` is modified, the changes are visible on ``ChairB_2`` **only**, since nothing else shares that arc.

.. _USD Prim: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Prim
.. _composition arc details: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-CompositionArcs
.. _Edit Target: https://graphics.pixar.com/usd/release/api/class_usd_edit_target.html

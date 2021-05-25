Prim Composition
----------------

Uses existing USD Prim utilities to present extended `composition arc details`_ than the ones visible by default on USD view.
To visualize the composition graph, the ``graphviz`` library needs to be available on the environment.

.. tab:: USDView

    .. image:: https://user-images.githubusercontent.com/8294116/98809052-1f4d5c00-2471-11eb-965d-43cea0c57322.gif

.. tab:: Houdini

    .. code:: python

       from grill.views import houdini
       houdini.prim_composition()

    .. image:: https://user-images.githubusercontent.com/8294116/98945804-1dee6300-2547-11eb-8e9b-3f0211af6f3c.gif

.. tab:: Maya

    .. code:: python

       from grill.views import maya
       maya.prim_composition()

    .. image:: https://user-images.githubusercontent.com/8294116/115137817-9fed3580-a06b-11eb-81d6-07d7c0fd854d.gif

.. _USD stage: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Stage
.. _prims: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Prim
.. _composition arc details: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-CompositionArcs
.. _layer stacks: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-LayerStack
.. _layers: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Layer

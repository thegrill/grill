Layer Stack Composition
-----------------------

Similar to ``Prim Composition``, but available for the whole `stage`_ by
creating a graph of `layer stacks`_. This helps answer questions like:

-  What prims are being affected by `layers`_ X and Y?

On the upper left, all used layers in the current `stage`_ are listed. On
the upper right, all `prims`_ that are affected by the selected `layers`_ are
listed. On the bottom, a `composition arcs`_ graph is displayed for the
selected `layers`_ plus the neighbors (predecessors and successors) for
each of them.


.. tab:: USDView

    .. image:: https://user-images.githubusercontent.com/8294116/131240483-9b428c4a-92fc-4d79-b464-8b1d07f982e0.gif

.. tab:: Houdini

    .. image:: https://user-images.githubusercontent.com/8294116/131242061-a42c2637-b550-4e1f-89e5-2328f8491333.gif

.. tab:: Maya

    .. image:: https://user-images.githubusercontent.com/8294116/131242058-68f20283-0894-463b-9af0-914941356f8c.gif

.. hint::
    It is also possible to compute the graph from currently selected prims:

    .. image:: https://user-images.githubusercontent.com/8294116/131242428-7b06729d-f96e-4b92-b02f-1608e99859bd.gif

.. _layer stacks: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-LayerStack
.. _layers: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Layer
.. _stage: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Stage
.. _prims: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Prim
.. _composition arcs: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-CompositionArcs


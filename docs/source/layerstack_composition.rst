Layer Stack Composition
-----------------------

Similar to ``Prim Composition``, but available for the whole `stage`_ by
creating a graph of `layer stacks`_. This helps answer questions like:

-  What prims are being affected by `layers`_ X and Y?

.. tab:: USDView

    .. image:: https://user-images.githubusercontent.com/8294116/131240483-9b428c4a-92fc-4d79-b464-8b1d07f982e0.gif

.. tab:: Houdini

    .. image:: https://user-images.githubusercontent.com/8294116/131242061-a42c2637-b550-4e1f-89e5-2328f8491333.gif

.. tab:: Maya

    .. image:: https://user-images.githubusercontent.com/8294116/131242058-68f20283-0894-463b-9af0-914941356f8c.gif

In the above example, we're inspecting `Animal Logic's USD ALab`_.

1. On the upper left, all used layers in the current `stage`_ are listed.
2. On the upper right, all `prims`_ that are affected by the selected `layers`_ are listed.
3. On the bottom, a `composition arcs`_ graph is displayed for the selected `layers`_ plus the neighbors (predecessors and successors) for each of them.

   - Nodes in the network represent `layer stacks`_.
   - Edges are the `composition arcs`_ between them (it follows the same color scheme as the ones provided by Pcp.PrimIndex.DumpToDotGraph).
   - Options to filter `composition arcs`_ are provided on the up left corner of the network view.

     .. image:: https://user-images.githubusercontent.com/8294116/131248473-8855cca9-f011-4c2e-af3c-1f1eb50d4acb.png

   - The additional option ``Precise Source Layer`` (**off** by default) exists to draw the edge source from the layer from the stack that introduces it.
     This allows to go from this:

     .. image:: https://user-images.githubusercontent.com/8294116/131248571-3d4a7e31-eb1c-434c-953d-eef51bc5808c.png

     To (note the outputs of ``books_magazines01_surfacing`` and ``books_magazines01_modelling``):

     .. image:: https://user-images.githubusercontent.com/8294116/131248575-e50a6d64-c298-48fa-a9d2-290696c6d5eb.png


.. hint::
    It is also possible to compute the graph from currently selected prims:

    .. image:: https://user-images.githubusercontent.com/8294116/131242428-7b06729d-f96e-4b92-b02f-1608e99859bd.gif

.. _Animal Logic's USD ALab: https://animallogic.com/usd-alab
.. _layer stacks: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-LayerStack
.. _layers: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Layer
.. _stage: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Stage
.. _prims: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Prim
.. _composition arcs: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-CompositionArcs


Layer Stack Composition
-----------------------

Similar to ``Prim Composition``, but available for the whole `stage`_ or multiple `prims`_ at once.
This helps answer questions like:

-  What prims are being affected by `layers`_ X and Y?

.. tab:: USDView

    .. image:: images/layerstack_composition_usdview.gif

.. tab:: Houdini

    .. image:: https://user-images.githubusercontent.com/8294116/131242061-a42c2637-b550-4e1f-89e5-2328f8491333.gif

.. tab:: Maya

    .. image:: https://user-images.githubusercontent.com/8294116/131242058-68f20283-0894-463b-9af0-914941356f8c.gif

In the above example, we're inspecting `Animal Logic's USD ALab`_.

1. On the upper left, all used layers in the composition of the inspected `stage`_ or `prims`_ are listed.
2. On the upper right, all `prims`_ that are affected by the current selected `layers`_ are listed.
3. On the bottom, a `composition arcs`_ graph is displayed for the selected `layers`_ plus the neighbors (predecessors and successors) for each of their `layerStacks`_.

   - Nodes in the network represent `layerStacks`_.
   - Edges are the `composition arcs`_ between them (it follows the same color scheme as the ones provided by Pcp.PrimIndex.DumpToDotGraph).
   - Options to filter `composition arcs`_ are provided above the network view.

     .. image:: images/layerstack_composition_arc_filter_options.jpg

   - The additional option ``Precise Source Layer`` (**off** by default) exists to draw the edge source from the layer from the stack that introduces it.
     This allows to go from this:

     .. image:: images/layerstack_composition_options_default.jpg
     To (note the outputs of ``books_magazines01_surfacing`` and ``books_magazines01_modelling``):

     .. image:: images/layerstack_composition_options_precise_source_layer.jpg


.. warning::
    Time for computing this graph increases with stage complexity. So for larger stages, it is recommended to start the widget with the `prims`_ of interest rather than the complete `stage`_:

    .. image:: https://user-images.githubusercontent.com/8294116/131242428-7b06729d-f96e-4b92-b02f-1608e99859bd.gif

.. _Animal Logic's USD ALab: https://animallogic.com/usd-alab
.. _layerStacks: https://openusd.org/release/glossary.html#usdglossary-layerstack
.. _layers: https://openusd.org/release/glossary.html#usdglossary-layer
.. _stage: https://openusd.org/release/glossary.html#usdglossary-stage
.. _prims: https://openusd.org/release/glossary.html#usdglossary-prim
.. _composition arcs: https://openusd.org/release/glossary.html#usdglossary-compositionarcs


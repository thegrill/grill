Layer Stack Composition
-----------------------

Similar to ``Prim Composition``, but available for the whole stage by
creating a graph of `layer stacks`_. This helps answer questions like:

-  What prims are being affected by `layers`_ X and Y?

On the upper left, all used layers in the current stage are listed. On
the upper right, all prims that are affected by the selected layers are
listed. On the bottom, a composition arcs graph is displayed for the
selected layers plus the neighbors (predecessors and successors) for
each of them.


.. tab:: USDView

    .. image:: https://user-images.githubusercontent.com/8294116/100603669-8a47cf80-3359-11eb-85fd-ce0e2aa96d60.gif

.. tab:: Houdini

    .. code:: python

       from grill.views import houdini
       houdini.layerstack_composition()

    .. image:: https://user-images.githubusercontent.com/8294116/100744825-7cb24880-3432-11eb-8906-9c2c4019678e.gif

.. tab:: Maya

    .. code:: python

       from grill.views import houdini
       houdini.layerstack_composition()

    .. image:: https://user-images.githubusercontent.com/8294116/115137947-6668fa00-a06c-11eb-8ec6-3fce8d92627f.gif

.. _layer stacks: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-LayerStack
.. _layers: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Layer
.. _USD stage: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Stage
.. _prims: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-Prim
.. _composition arc details: https://graphics.pixar.com/usd/docs/USD-Glossary.html#USDGlossary-CompositionArcs


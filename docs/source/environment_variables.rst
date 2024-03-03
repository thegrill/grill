Environment Variables
---------------------

``The Grill`` defaults to an interactive graph explorer for views like the ``ConnectionViewer``, ``LayerStack Composition`` and ``Taxonomy Editor``.
Previously, these views used to load static SVG images, leveraging ``QtWebEngine`` for performance.
However, some environments do not bring ``QtWebEngine`` with them, and others lead to crashes (see `thegrill#36 <https://github.com/thegrill/grill/issues/36>`_ as an example).

In order to help with these issues and to bring interactivity to graph views, `thegrill#35 <https://github.com/thegrill/grill/issues/35>`_ introduced GraphViewer.

The following environment variables will help bring old SVG behavior and still prevent ``QtWebEngine`` crashes:

GRILL_GRAPH_VIEW_VIA_SVG
~~~~~~~~~~~~~~~~~~~~~~~~

Enable this with a boolean value to inspect graphs as SVG images. A value of ``0`` will restore the default interactive GraphViewer:

.. tab:: GRILL_GRAPH_VIEW_VIA_SVG=0

    .. tab:: Connections Viewer

        .. image:: images/connections_viewer_interactive.jpg

    .. tab:: LayerStack Composition

        .. image:: images/layerstack_composition_interactive.jpg

.. tab:: GRILL_GRAPH_VIEW_VIA_SVG=1

    .. tab:: Connections Viewer

        .. image:: images/connections_viewer_svg.jpg

    .. tab:: LayerStack Composition

        .. image:: images/layerstack_composition_svg.jpg

If you come across any reason to inspect images as SVG, please reach out on GitHub as this will help assess if this should be removed or better integrated beyond an env variable.

GRILL_SVG_VIEW_AS_PIXMAP
~~~~~~~~~~~~~~~~~~~~~~~~

Enable this with a boolean value to load SVG images as pixmaps (thus avoiding use of ``QtWebEngine``):

.. tab:: GRILL_SVG_VIEW_AS_PIXMAP=0

    .. image:: images/prim_composition_svg.jpg

.. tab:: GRILL_SVG_VIEW_AS_PIXMAP=1

    .. image:: images/prim_composition_pixmap.jpg


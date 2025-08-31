Installation
============

Pip Install
-----------

By default, ``grill`` won't install ``USD``, ``PySide(2|6)`` & ``PyOpenGL``. This is because
DCC apps and other environments bundle them outside of ``pip``. To include them, use the ``[full]`` option.

Similarly, ``grill`` won't install asset creation capabilities, as those are opinionated. To enable these, use the ``[create]`` option.

Other dependencies like ``numpy``, ``networkx`` or ``pydot`` can be skipped by using the ``--no-deps`` flag.

.. tab:: Default

    .. code-block:: bash

        python -m pip install grill

.. tab:: Full

    .. code-block:: bash

        python -m pip install grill[full]

.. tab:: Create

    .. code-block:: bash

        python -m pip install grill[create]

.. tab:: No Dependencies

    .. code-block:: bash

        python -m pip install --no-deps grill

.. note::

    For some DCC applications (e.g. **Houdini**, **Maya**) ``pip`` needs to run
    from their corresponding python interpreters:

    .. tab:: Houdini

        If ``pip`` is missing, `follow this guide <https://wordpress.discretization.de/houdini/home/advanced-2/installing-and-using-scipy-in-houdini/>`_.

        .. code-block:: bash

            hython -m pip install grill

    .. tab:: Maya

        Visit the `official docs <https://help.autodesk.com/view/MAYAUL/2025/ENU/?guid=GUID-72A245EC-CDB4-46AB-BEE0-4BBBF9791627>`_ for more details.

        .. code-block:: bash

            mayapy -m pip install grill


Extra Dependencies
------------------

The following optional dependencies should be installed separately.

- `graphviz`_ for graph widgets. See conda example below for instructions.
- :ref:`toolset:usdview`
  (hopefully will be available soon via `pypi <https://pypi.org/>`_). In the meantime, it can be built from USD source
  (`conda recipe <https://github.com/PixarAnimationStudios/USD/issues/1260#issuecomment-656985888>`_).

Conda Environment Example
-------------------------

For environment management, ``The Grill`` uses `conda`_. This is a
walk-through on how to start using ``The Grill`` tools with a fresh
`conda`_ environment.

1. If the ``conda`` command is not on the system yet, install `miniconda`_.

   .. hint::
      `conda`_ installation comes in two flavors:

      - `Anaconda`_, which is `conda`_ + a lot of `extra utilities <https://docs.conda.io/projects/conda/en/latest/glossary.html#anaconda-glossary>`_.
      - `miniconda`_, which is the minimal bootstrap for ``conda``. When in doubt, install this one.

2. Launch `Anaconda Prompt <https://docs.anaconda.com/anaconda/user-guide/getting-started/#open-anaconda-prompt>`_
   (it came as part of the `miniconda`_ installation).

3. Create a new ``conda`` environment with ``python=3.10``, for example:

   .. code:: PowerShell

      (base) C:\>conda create -n grilldemo01 python=3.10

4. Activate that environment:

   .. code:: PowerShell

      (base) C:\>conda activate grilldemo01

5. Install ``grill`` via ``pip``; use the ``[full,create]`` options to use standalone.
   Refer to the `pip install instructions <#pip-install>`_ for more details.

   .. code:: PowerShell

      (grilldemo01) C:\>python -m pip install grill[full,create]

6. If missing, (optionally) install `graphviz`_ via ``conda``:

   .. code:: PowerShell

      (grilldemo01) C:\>conda install conda-forge::graphviz

   .. hint::
      For graph visualization, a python library for ``graphviz`` is required. ``grill`` supports ``pydot`` and ``pygraphviz``:

      - `pydot`_, is the default (installed with the ``grill`` package) but can be slower for large graphs (4k+ nodes)
      - `pygraphviz`_, is faster but challenging to insall (visit `pygraphviz#468 <https://github.com/pygraphviz/pygraphviz/pull/468>`_ for more details)

7. You should be able to see the ``👨‍🍳 Grill`` menu in **USDView**, **Maya** and **Houdini***.

   .. tab:: USDView

        .. image:: images/menu_usdview.gif

   .. tab:: Houdini

        .. image:: images/menu_hou.gif

   .. tab:: Maya

        .. image:: images/menu_maya.gif

   .. important::

        To see the menu in **Houdini**, run this additional step (which installs the grill `houdini package <https://www.sidefx.com/docs/houdini/ref/plugins.html>`_ on the **Houdini's** user preferences):

        .. code:: bash

            hython -c "from grill.__startup__ import houdini;houdini.install_package()"

        The manual execution of this step might be removed in the future.

.. _graphviz: http://graphviz.org
.. _pydot: https://github.com/pydot/pydot
.. _pygraphviz: https://pygraphviz.github.io/documentation/stable/index.html
.. _miniconda: https://docs.conda.io/en/latest/miniconda.html
.. _Anaconda: https://docs.anaconda.com/anaconda/user-guide/getting-started/
.. _conda: https://docs.conda.io/projects/conda/en/latest/index.html

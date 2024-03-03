Installation
============

Pip Install
-----------

By default, ``grill`` won't install ``USD``, ``PySide(2|6)`` & ``PyOpenGL``. This is because
DCC apps and other environments bundle them outside of ``pip``. To include them, use the ``[full]`` option.

.. tab:: Default

    .. code-block:: bash

        python -m pip install grill

.. tab:: Full

    .. code-block:: bash

        python -m pip install grill[full]

.. note::

    For some DCC applications (e.g. **Houdini**, **Maya**) ``pip`` needs to run
    from their corresponding python interpreters:

    .. tab:: Houdini

        If ``pip`` is missing, `follow this guide <https://wordpress.discretization.de/houdini/home/advanced-2/installing-and-using-scipy-in-houdini/>`_.

        .. code-block:: bash

            hython -m pip install grill

    .. tab:: Maya

        Visit the `official docs <https://help.autodesk.com/view/MAYAUL/2022/ENU/?guid=GUID-72A245EC-CDB4-46AB-BEE0-4BBBF9791627>`_ for more details.

        .. code-block:: bash

            mayapy -m pip install grill


Extra Dependencies
------------------

The following optional dependencies should be installed separately.

- `graphviz <http://graphviz.org/>`_ and `pygraphviz`_ for graph widgets. See conda example below for instructions.
- `usdview <https://openusd.org/release/toolset.html#usdview>`_
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

3. Create a new ``conda`` environment with ``python=3.9``, for example:

   .. code:: PowerShell

      (base) C:\>conda create -n grilldemo01 python=3.9

4. Activate that environment:

   .. code:: PowerShell

      (base) C:\>conda activate grilldemo01

5. Install ``grill`` via ``pip``; use the ``full`` option to use standalone.
   Refer to the `pip install instructions <#pip-install>`_ for more details.

   .. code:: PowerShell

      (grilldemo01) C:\>python -m pip install grill[full]

6. If missing, (optionally) install `pygraphviz`_ via ``conda``:

   .. warning::

      At the moment, installing `pygraphviz`_ can be tricky. Hopefully a simpler pip+wheel based solution comes with `pygraphviz#167 <https://github.com/pygraphviz/pygraphviz/issues/167>`_.

      Versions older than ``pip-23.3.2`` may have trouble installing `pygraphviz`_ in Windows for DCCs like ``Maya`` and ``Houdini``.
      If you come through this trouble, visit `pygraphviz#468 <https://github.com/pygraphviz/pygraphviz/pull/468>`_ and try to install with this exact particular version of ``pip``.
      The below tests ran successfully with ``Maya-2024`` and ``Houdini-20.0`` on ``Windows-10`` and ``pip-23.3.2``.

      The current ``pip`` version can be extracted like so:

      .. tab:: Standalone Python

         .. code:: PowerShell

            python -m pip -V

      .. tab:: Houdini

         .. code:: PowerShell

            hython -m pip -V

      .. tab:: Maya

         .. code:: PowerShell

            mayapy -m pip -V

      To update to ``23.3.2``, update the interpreter command to run:

      .. tab:: Standalone Python

         .. code:: PowerShell

            python -m pip install -U pip==23.3.2

      .. tab:: Houdini

         .. code:: PowerShell

            hython -m pip install -U pip==23.3.2

      .. tab:: Maya

         .. code:: PowerShell

            mayapy -m pip install -U pip==23.3.2

   .. tab:: Standalone Python

     Replace ``--global-option`` to the correct ``Include`` and ``Lib`` paths on the system (where ``graphviz\cgraph.h`` and ``cgraph.lib`` paths exist, respectively):

     .. code:: PowerShell

        (grilldemo01) C:\>conda install --channel conda-forge pygraphviz
        (grilldemo01) C:\>python -m pip install --global-option=build_ext --global-option="-IC:\Users\Christian\.conda\envs\glowdeps\Library\include" --global-option="-LC:\Users\Christian\.conda\envs\glowdeps\Library\lib" pygraphviz

   .. tab:: Houdini

     Replace ``--global-option`` to the correct ``Include`` and ``Lib`` paths on the system (where ``graphviz\cgraph.h`` and ``cgraph.lib`` paths exist, respectively):

     .. code:: PowerShell

        (grilldemo01) C:\>conda install --channel conda-forge pygraphviz
        (grilldemo01) C:\Program Files\Side Effects Software\Houdini 19.5.534\bin>hython -m pip install -vvv --use-pep517 --config-settings="--global-option=build_ext" --config-settings="--global-option=-IC:\Users\Christian\.conda\envs\pygraphviz310\Library\include" --config-settings="--global-option=-LC:\Users\Christian\.conda\envs\pygraphviz310\Library\lib" pygraphviz

   .. tab:: Maya

     Replace ``--global-option`` to the correct ``Include`` and ``Lib`` paths on the system (where ``graphviz\cgraph.h`` and ``cgraph.lib`` paths exist, respectively) **and** the Maya Python ``include`` and ``lib`` paths:

     .. code:: PowerShell

        (grilldemo01) C:\>conda install --channel conda-forge pygraphviz
        (grilldemo01) C:\Program Files\Autodesk\Maya2023\bin>mayapy -m pip install -U pip==23.3.2
        (grilldemo01) C:\Program Files\Autodesk\Maya2023\bin>mayapy -m pip install -vvv --use-pep517 --config-settings="--global-option=build_ext" --config-settings="--global-option=-IC:\Users\Christian\.conda\envs\pygraphviz310\Library\include;C:\Program Files\Autodesk\Maya2024\include\Python39\Python" --config-settings="--global-option=-LC:\Users\Christian\.conda\envs\pygraphviz310\Library\lib;C:\Program Files\Autodesk\Maya2024\lib" pygraphviz


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

.. _pygraphviz: https://pygraphviz.github.io/documentation/stable/install.html
.. _miniconda: https://docs.conda.io/en/latest/miniconda.html
.. _Anaconda: https://docs.anaconda.com/anaconda/user-guide/getting-started/
.. _conda: https://docs.conda.io/projects/conda/en/latest/index.html

Installation
------------

Pip Install
~~~~~~~~~~~

The ``grill`` package includes install options for situations where core libraries
have been installed outside of ``pip`` (e.g. ``USD`` & ``PySide2`` are bundled
with DCC apps). This is the default. The ``[full]`` option will install ``USD``, ``PySide2``
and ``PyOpenGL``, so use it if those are missing from the current environment.

.. tab:: Default

    .. code-block:: bash

        python -m pip install grill

.. tab:: Full

    .. code-block:: bash

        python -m pip install grill[full]

.. note::

    For some DCC applications (e.g. **Maya**, **Houdini**) ``pip`` needs to run
    from their corresponding python interpreters:

    .. tab:: Maya

        Visit `official docs <https://help.autodesk.com/view/MAYAUL/2022/ENU/?guid=GUID-72A245EC-CDB4-46AB-BEE0-4BBBF9791627>`_ for more details.

        .. code-block:: bash

            mayapy -m pip install grill

    .. tab:: Houdini

        If ``pip`` is missing, it can be downloaded `from this guide <https://wordpress.discretization.de/houdini/home/advanced-2/installing-and-using-scipy-in-houdini/>`_, then:

        .. code-block:: bash

            hython3.7 -m pip install grill

Extra Dependencies
~~~~~~~~~~~~~~~~~~

The following optional dependencies should be installed separately.

- `graphviz <http://graphviz.org/>`_ (for graph widgets).
- `usdview <https://graphics.pixar.com/usd/docs/USD-Toolset.html#USDToolset-usdview>`_
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

3. Create a new ``conda`` environment with ``python=3.7``, for example:

   .. code:: bash

      (base) C:\>conda create -n grilldemo01 python=3.7

4. Activate that environment:

   .. code:: bash

      (base) C:\>conda activate grilldemo01

5. Install ``grill`` via pip; use the ``full`` option to use standalone.
   For more details, refer to the `pip install instructions above <#pip-install>`_.

   .. code:: bash

      (grilldemo01) C:\>python -m pip install grill[full]

6. If missing, (optionally) install ``graphviz`` via ``conda``:

   .. code:: bash

      (grilldemo01) C:\>conda install -c anaconda graphviz

7. You should be able to see the ``👨‍🍳 Grill`` menu in **USDView** as well as **Maya**.

   .. image:: https://user-images.githubusercontent.com/8294116/114263497-2d57d680-9a29-11eb-8992-6b443f942263.gif

   .. image:: https://user-images.githubusercontent.com/8294116/115981668-bdc11a00-a5d8-11eb-9897-6061639d1c39.gif

   .. important::
      To see the menu in **Houdini**, run this additional step (which installs the grill `houdini package <https://www.sidefx.com/docs/houdini/ref/plugins.html>`_ on the **Houdini's** user preferences):

      .. code:: bash

         hython3.7.exe -c "from grill.__startup__ import houdini;houdini.install_package()"

      The manual execution of this step might be removed in the future.

   .. image:: https://user-images.githubusercontent.com/8294116/115981745-68d1d380-a5d9-11eb-8033-979d72ca0e6b.gif

.. _miniconda: https://docs.conda.io/en/latest/miniconda.html
.. _Anaconda: https://docs.anaconda.com/anaconda/user-guide/getting-started/
.. _conda: https://docs.conda.io/projects/conda/en/latest/index.html

API Reference
-------------

grill.usd
~~~~~~~~~

.. automodule:: grill.usd
   :members:


grill.cook
~~~~~~~~~~

.. important::
   In order to use this module, ensure the extra feature ``grill[create]`` was installed. Alternatively, the module will be enabled by installing ``grill-names`` in the environment.
   Refer to the `install instructions <install.html#pip-install>`_ for more details.

.. automodule:: grill.cook
   :members:

.. autoclass:: grill.cook.UsdAsset

    .. note::

        This class is defined on the ``grill.names`` `module <https://grill-names.readthedocs.io/en/latest/names.html>`_ but is exposed here for convenience.

    .. hint::

        For quick prototyping, :py:meth:`grill.names.UsdAsset.get_anonymous` can be used to get temporary but valid ``grill`` identifiers.

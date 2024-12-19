Layer Content Browser
---------------------

Uses :ref:`toolset:sdffilter` and :ref:`toolset:usdtree` to display content from USD layers (regardless of format or if they have been saved on disk).

Array attributes and time samples have their contents reduced to a maximum of 6 entries.

.. image:: https://user-images.githubusercontent.com/8294116/231415967-c960d036-05e6-42d3-905f-d673f8cf2579.gif

The browser can be opened from USDView's ``Composition`` tab (as shown above), as well as from the :ref:`Layer Stack Composition`'s layer tree:

.. image:: https://user-images.githubusercontent.com/8294116/156912110-a573d9a6-6aed-4b8a-b492-dbaad2613283.gif

Images from formats supported by Qt through ``QtGui.QImageReader.supportedImageFormats`` will also be displayed:

.. image:: images/layer_content_browser_image_tab_update.gif

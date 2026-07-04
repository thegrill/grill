Playground
==========

Try ``grill.cook`` and ``grill.names`` in your browser. Packages are loaded via Pyodide; USD comes from the experimental ``grill-usd-core`` WASM build.

.. attention::

   This REPL is experimental. Asset creation writes to a temporary in-browser filesystem that is lost on refresh.

.. py-repl::
   :packages: grill-usd-core==26.8, grill-names>=2.6.0, grill==0.19.1
   :repl-title: Grill Cook Playground
   :theme: catppuccin-latte
   :no-banner:

   >>> from grill import cook, names
   >>> import tempfile
   >>> from pathlib import Path
   >>> cook.Repository.set(Path(tempfile.mkdtemp()))
   >>> stage = cook.fetch_stage(cook.UsdAsset.get_anonymous())
   >>> character = cook.define_taxon(stage, "Character")
   >>> character
   >>> cook.create_unit(character, "Hero01", label="Hero 01")

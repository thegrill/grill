# The Grill
[![Build Status](https://travis-ci.org/thegrill/grill.svg?branch=master)](https://travis-ci.org/thegrill/grill)
[![codecov](https://codecov.io/gh/thegrill/grill/branch/master/graph/badge.svg)](https://codecov.io/gh/thegrill/grill)
[![Documentation Status](https://readthedocs.org/projects/grill/badge/?version=latest)](https://grill.readthedocs.io/en/latest/?badge=latest)
[![PyPI version](https://badge.fury.io/py/grill.svg)](https://badge.fury.io/py/grill)
[![PyPI](https://img.shields.io/pypi/pyversions/grill.svg)](https://pypi.python.org/pypi/grill)
---
Cook digital.

`grill` namespace, meta-package with core tools and philosophy guidelines.

With future users and readers in mind, `the grill` aims to stick to the following principles:

- [DRY (don't repeat yourself)](https://en.wikipedia.org/wiki/Don%27t_repeat_yourself)
- [SSOT (single source of truth)](https://en.wikipedia.org/wiki/Single_source_of_truth)
- [Convention over configuration (sensible defaults)](https://en.wikipedia.org/wiki/Convention_over_configuration)
- [SOLID (understandable, flexible and maintainable)](https://en.wikipedia.org/wiki/SOLID)
- [KISS (keep it simple)](https://en.wikipedia.org/wiki/KISS_principle)

Foundational tools:
- [Python](https://docs.python.org/3/)
- [USD](https://graphics.pixar.com/usd/docs/index.html)
- [EdgeDB](https://edgedb.com)

## Install

```bash
python -m pip install grill
```

## Extra Dependencies

The following optional dependencies should be installed separately.

- [graphviz](http://graphviz.org/) (for graph widgets)
- [usdview](https://graphics.pixar.com/usd/docs/USD-Toolset.html#USDToolset-usdview) (hopefully will be available soon via pypi). In the meantime, it can be downloaded from [NVidia](https://developer.nvidia.com/usd) or built from USD source ([conda recipe](https://github.com/PixarAnimationStudios/USD/issues/1260#issuecomment-656985888))

## Conda Environment Example

For environment management, `the grill` uses `conda`.
This is a walk-through on how to start using `the grill` tools with a fresh `conda` environment. 

1. If `conda` is not on the system yet, install [miniconda](https://docs.conda.io/en/latest/miniconda.html).

   Note: `conda` environment manager comes in two flavours: 
   - [Anaconda](https://docs.anaconda.com/anaconda/user-guide/getting-started/), which is [conda](https://docs.conda.io/projects/conda/en/latest/index.html) + a lot of extra utilities.
   - [miniconda](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html) is the main bootstrap for `conda` and is the preferred one. When in doubt, install this one.
2. Launch [Anaconda Prompt](https://docs.anaconda.com/anaconda/user-guide/getting-started/#open-anaconda-prompt) (it came as part of the `miniconda` installation)
3. Create a new `conda` environment with `python=3.7`, e.g:
   ```
   (base) C:\>conda create -n grilldemo01 python=3.7
   ```
4. Activate that environment
   ```
   (base) C:\>conda activate grilldemo01
   ```
5. Install `grill` via pip
   ```
   (grilldemo01) C:\>python -m pip install grill
   ```
6. If missing, optionally install `graphviz` via conda
   ```
   (grilldemo01) C:\>conda install -c anaconda graphviz
   ```
7. If missing, optionally install `usdview` via [NVidia builds](https://developer.nvidia.com/usd) or via building USD from source using this [conda recipe](https://github.com/PixarAnimationStudios/USD/issues/1260#issuecomment-656985888).
   
   Note that if you're installing via the NVidia builds, you'll need `PyOpenGL` as well:
   ```
   (grilldemo01) C:\>python -m pip install PyOpenGL
   ```
8. Extend the `PXR_PLUGINPATH_NAME` environment variable to include the `plugInfo.json` file from the `grill.resources` path location.
   
   To know where the installed file is, run the following python command:
   ```
   (grilldemo01) C:\Users\Christian>python -c "from pathlib import Path;from grill import resources;path=(Path(resources.__path__._path[0]) / 'plugInfo.json');assert path.is_file();print(path)
   ``` 
   It will print something like:
   ```
   C:\Users\Christian\.conda\envs\grilldemo01\lib\site-packages\grill\resources\plugInfo.json
   ```
   Which you can use to extend the pixar environment variable, e.g:
   ```
   (grilldemo01) C:\Users\Christian>set PXR_PLUGINPATH_NAME=%PXR_PLUGINPATH_NAME%;C:\Users\Christian\.conda\envs\grilldemo01\lib\site-packages\grill\resources\plugInfo.json
   ```
9. You should be able to launch `usdview` and see the `Grill` menu on the menu bar.
    ```
    (grilldemo01) C:\Users\Christian>usdview B:\read\cg\downloads\Kitchen_set\Kitchen_set\Kitchen_set.usd
    ```
   ![usdview_grill_menu](https://user-images.githubusercontent.com/8294116/102703258-b2738000-42c0-11eb-8db4-29003fe928b3.gif)

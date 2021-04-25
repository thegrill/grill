The `grill.views` package provides Qt widgets to author and inspect USD scene graphs.

Convenience launchers for USDView, Houdini and Maya are provided, but any DCC with USD and Qt support should be able to make use of the widgets, as well as launching them standalone.

## Spreadsheet Editor

Tabular representation of a stage. Ability to quickly inspect and edit prims in bulk is the main motivation for this view to exist.
Copy pasting functionality like in other spreadsheet applications should be possible (via csv clipboards). 

#### USD View

Located under the `Grill` menu, the `Spreadsheet Editor` takes the current active stage.

![spreadsheet_editor_5](https://user-images.githubusercontent.com/8294116/99148142-3e9af200-26da-11eb-9a9d-3c63a3c32ccb.gif)

#### Houdini

Available from the `Grill` menu or the following python code:

```python
from grill.views import houdini
houdini.spreadsheet()
``` 

Same as with USDView, the current active stage is loaded:

![spreadsheet_editor_houdini_5](https://user-images.githubusercontent.com/8294116/99145748-57e57380-26c5-11eb-847f-ea01f023caf0.gif)

#### Maya

Available from the `Grill` menu or the following python code:

```python
from grill.views import maya
maya.spreadsheet()
``` 

At the moment, the first found stage is picked: 

![grill_maya_sheet04](https://user-images.githubusercontent.com/8294116/115137690-e0987f00-a06a-11eb-9ba3-1e7df3c0163c.gif)

## Prim Composition

Uses existing USD Prim utilities to present extended composition arc details than the ones visible by default on USD view.  
To visualize the composition graph, the `graphviz` library needs to be available on the environment. 

#### USD View

![prim_description_7](https://user-images.githubusercontent.com/8294116/98809052-1f4d5c00-2471-11eb-965d-43cea0c57322.gif)

#### Houdini

Available from the `Grill` menu or the following python code:
```python
from grill.views import houdini
houdini.prim_composition()
``` 

![prim_description_hou_4](https://user-images.githubusercontent.com/8294116/98945804-1dee6300-2547-11eb-8e9b-3f0211af6f3c.gif)

#### Maya

Available from the `Grill` menu or the following python code:
```python
from grill.views import maya
maya.prim_composition()
``` 

![grill_maya_primcomp01](https://user-images.githubusercontent.com/8294116/115137817-9fed3580-a06b-11eb-81d6-07d7c0fd854d.gif)


## Layer Stack Composition

Similar to `Prim Composition`, but available for the whole stage.
This helps answer questions like:

- What prims are being affected by layers X and Y?

On the upper left, all used layers in the current stage are listed.
On the upper right, all prims that are affected by the selected layers are listed.
On the bottom, a composition arcs graph is displayed for the selected layers plus the neighbors (predecessors and successors) for each of them.     
 
#### USD View

![stack_composition_4](https://user-images.githubusercontent.com/8294116/100603669-8a47cf80-3359-11eb-85fd-ce0e2aa96d60.gif)

#### Houdini
Available from the `Grill` menu or the following python code:
```python
from grill.views import houdini
houdini.layerstack_composition()
```

![stack_composition_houdin_2](https://user-images.githubusercontent.com/8294116/100744825-7cb24880-3432-11eb-8906-9c2c4019678e.gif)

#### Maya

Available from the `Grill` menu or the following python code:

```python
from grill.views import houdini
houdini.layerstack_composition()
```

![grill_maya_layerstack01](https://user-images.githubusercontent.com/8294116/115137947-6668fa00-a06c-11eb-8ec6-3fce8d92627f.gif)

## Creating Assets

#### USD View

Creating assets requires a repository path to be set. If not set, a dialog to set it will be prompted upon creation request.

To set the repository path at any point, go to `Grill -> Preferences -> Repository Path`:

![grill_select_repopath_4](https://user-images.githubusercontent.com/8294116/114215808-681a2a00-99a9-11eb-85c2-04d45d5a3aef.gif)


With a repository path set, assets can be created via the `Create Assets` menu. The default is one, but any number of assets can be created at the same time by changing the `Amount` value.

In the example below, 240 "City" assets are created, copied from a CSV file and pasted directly on the "Create Assets" table.

All created assets are saved to disk on the current repository path.

![grill_create_cities](https://user-images.githubusercontent.com/8294116/112751505-263ccb80-901a-11eb-8a64-d46ef43dd087.gif)

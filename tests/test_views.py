import unittest

from pxr import Usd, UsdGeom, Sdf
from PySide2 import QtWidgets, QtCore

from grill.views import description, spreadsheet


class TestViews(unittest.TestCase):
    def test_layer_composition(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

        sphere = Usd.Stage.CreateInMemory()
        UsdGeom.Sphere.Define(sphere, "/sph")
        root_path = "/root"
        sphere_root = sphere.DefinePrim(root_path)
        sphere_root.CreateAttribute("greet", Sdf.ValueTypeNames.String).Set("hello")
        sphere.SetDefaultPrim(sphere_root)
        print(sphere.GetRootLayer().ExportToString())

        capsule = Usd.Stage.CreateInMemory()
        UsdGeom.Capsule.Define(capsule, "/cap")
        root_path = "/root"
        capsule_root = capsule.DefinePrim(root_path)
        capsule_root.CreateAttribute("who", Sdf.ValueTypeNames.String).Set("world")
        capsule.SetDefaultPrim(capsule_root)
        print(capsule.GetRootLayer().ExportToString())

        merge = Usd.Stage.CreateInMemory()
        for i in (capsule, sphere):
            merge.GetRootLayer().subLayerPaths.append(i.GetRootLayer().identifier)
        merge.SetDefaultPrim(merge.GetPrimAtPath(root_path))
        print(merge.GetRootLayer().ExportToString())

        world = Usd.Stage.CreateInMemory()
        nested = world.DefinePrim("/nested/child")
        nested.GetReferences().AddReference(merge.GetRootLayer().identifier)
        print(world.GetRootLayer().ExportToString())

        widget = description.LayersComposition()
        widget.setStage(world)

        # cheap. All these layers affect a single prim
        affectedPaths = dict.fromkeys((i.GetRootLayer() for i in (capsule, sphere, merge)), 1)

        # the world affects both root and the nested prims
        affectedPaths[world.GetRootLayer()] = 2

        for row in range(widget._layers.model.rowCount()):
            layer = widget._layers.model.item(row, 0).data(QtCore.Qt.UserRole)
            widget._layers.table.selectRow(row)
            expectedAffectedPrims = affectedPaths[layer]
            actualListedPrims = widget._prims.model.rowCount()
            self.assertEqual(expectedAffectedPrims, actualListedPrims)
        widget.deleteLater()

    def test_prim_composition(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

        sphere = Usd.Stage.CreateInMemory()
        UsdGeom.Sphere.Define(sphere, "/sph")
        root_path = "/root"
        sphere_root = sphere.DefinePrim(root_path)
        sphere_root.CreateAttribute("greet", Sdf.ValueTypeNames.String).Set("hello")
        sphere.SetDefaultPrim(sphere_root)
        print(sphere.GetRootLayer().ExportToString())

        capsule = Usd.Stage.CreateInMemory()
        UsdGeom.Capsule.Define(capsule, "/cap")
        root_path = "/root"
        capsule_root = capsule.DefinePrim(root_path)
        capsule_root.CreateAttribute("who", Sdf.ValueTypeNames.String).Set("world")
        capsule.SetDefaultPrim(capsule_root)
        print(capsule.GetRootLayer().ExportToString())

        merge = Usd.Stage.CreateInMemory()
        for i in (capsule, sphere):
            merge.GetRootLayer().subLayerPaths.append(i.GetRootLayer().identifier)
        merge.SetDefaultPrim(merge.GetPrimAtPath(root_path))
        print(merge.GetRootLayer().ExportToString())

        world = Usd.Stage.CreateInMemory()
        nested = world.DefinePrim("/nested/child")
        nested.GetReferences().AddReference(merge.GetRootLayer().identifier)
        print(world.GetRootLayer().ExportToString())

        widget = description.PrimComposition()
        widget.setPrim(nested)

        # cheap. prim is affected by 2 layers
        topLevel = widget.composition_tree.topLevelItem(0)
        # single child for this prim.
        self.assertEqual(topLevel.childCount(), 1)

    def test_spreadsheet_editor(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

        sphere = Usd.Stage.CreateInMemory()
        UsdGeom.Sphere.Define(sphere, "/sph")
        root_path = "/root"
        sphere_root = sphere.DefinePrim(root_path)
        sphere_root.CreateAttribute("greet", Sdf.ValueTypeNames.String).Set("hello")
        sphere.SetDefaultPrim(sphere_root)
        print(sphere.GetRootLayer().ExportToString())

        capsule = Usd.Stage.CreateInMemory()
        UsdGeom.Capsule.Define(capsule, "/cap")
        root_path = "/root"
        capsule_root = capsule.DefinePrim(root_path)
        capsule_root.CreateAttribute("who", Sdf.ValueTypeNames.String).Set("world")
        capsule.SetDefaultPrim(capsule_root)
        print(capsule.GetRootLayer().ExportToString())

        merge = Usd.Stage.CreateInMemory()
        for i in (capsule, sphere):
            merge.GetRootLayer().subLayerPaths.append(i.GetRootLayer().identifier)
        merge.SetDefaultPrim(merge.GetPrimAtPath(root_path))
        print(merge.GetRootLayer().ExportToString())

        world = Usd.Stage.CreateInMemory()
        nested = world.DefinePrim("/nested/child")
        nested.GetReferences().AddReference(merge.GetRootLayer().identifier)
        print(world.GetRootLayer().ExportToString())

        widget = spreadsheet.SpreadsheetEditor()
        widget.setStage(world)

        # cheap. prim is affected by 2 layers
        self.assertEqual(widget.model.rowCount(), 2)

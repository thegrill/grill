import unittest

from pxr import Usd, UsdGeom, Sdf

import grill.usd as gusd

# 2024-11-09 - Python-3.13 & USD-24.11
# python -m unittest --durations 0 test_usd
# .....
# Slowest test durations
# ----------------------------------------------------------------------
# 0.026s     test_edit_context (test_usd.TestUSD.test_edit_context)
# 0.001s     test_format_tree (test_usd.TestUSD.test_format_tree)
# 0.001s     test_make_plane (test_usd.TestUSD.test_make_plane)
#
# (durations < 0.001s were hidden; use -v to show these durations)
# ----------------------------------------------------------------------
# Ran 5 tests in 0.030s


class TestUSD(unittest.TestCase):
    def test_edit_context(self):
        main = Usd.Stage.CreateInMemory()
        # Jump between 3 different layer stacks adding variants to the same set
        # main [variant blue] -> reference [variant green] -> payload [variant red]
        referenced = Usd.Stage.CreateInMemory()
        referenced.SetDefaultPrim(referenced.DefinePrim("/Referenced"))
        reference = Sdf.Reference(referenced.GetRootLayer().identifier)

        payloaded = Usd.Stage.CreateInMemory()
        payloaded.SetDefaultPrim(payloaded.DefinePrim("/Payloaded"))
        payload = Sdf.Payload(payloaded.GetRootLayer().identifier)

        top = main.DefinePrim("/Top")
        main.SetDefaultPrim(top)
        top.GetReferences().AddReference(reference)

        with gusd.edit_context(reference, top):
            top.GetPayloads().AddPayload(payload)
            with gusd.edit_context(payload, top):
                geom = UsdGeom.Sphere.Define(main, top.GetPath().AppendPath("inner/child"))
                color = geom.GetDisplayColorAttr()
                color_set = geom.GetPrim().GetVariantSets().AddVariantSet("color")
                color_set.AddVariant("from_payload")
                color_set.SetVariantSelection("from_payload")
                with gusd.edit_context(color_set, payloaded.GetRootLayer()):  # color_set.GetVariantEditContext() would fail here
                    color.Set([(1,0,0)])
                color_set.ClearVariantSelection()
            color_set.AddVariant("from_reference")
            color_set.SetVariantSelection("from_reference")
            with gusd.edit_context(color_set, referenced.GetRootLayer()):
                color.Set([(0,1,0)])
            color_set.ClearVariantSelection()

        color_set.AddVariant("from_top")
        color_set.SetVariantSelection("from_top")
        with color_set.GetVariantEditContext():
            color.Set([(0,0,1)])

        color_set.ClearVariantSelection()

        self.assertIn(payload, referenced.GetRootLayer().GetPrimAtPath(referenced.GetDefaultPrim().GetPath()).payloadList.GetAddedOrExplicitItems())
        self.assertIn(reference, main.GetRootLayer().GetPrimAtPath(top.GetPath()).referenceList.GetAddedOrExplicitItems())

        for stage, variant_name in (
            (main, "from_top"),
            (referenced, "from_reference"),
            (payloaded, "from_payload")
        ):
            layer = stage.GetRootLayer()
            self.assertIsNotNone(layer.GetPrimAtPath(f"{layer.defaultPrim}/inner/child{{color={variant_name}}}"))

    def test_missing_arc(self):
        stage = Usd.Stage.CreateInMemory()
        prim = stage.DefinePrim("/Referenced")
        anon = Usd.Stage.CreateInMemory()
        reference = Sdf.Reference(anon.GetRootLayer().identifier)
        with self.assertRaisesRegex(ValueError, "without a prim path"):
            gusd.edit_context(reference, prim)

    def test_missing_layer(self):
        stage = Usd.Stage.CreateInMemory()
        prim = stage.DefinePrim("/Referenced")
        reference = Sdf.Reference("non_existing")
        with self.assertRaisesRegex(ValueError, "ability to find layer"):
            gusd.edit_context(reference, prim)

    def test_format_tree(self):
        stage = Usd.Stage.CreateInMemory()
        child1 = stage.DefinePrim("/path/to/child1")
        stage.DefinePrim("/path/to/child02")
        self.assertEqual('┐to\n├── child1\n└── child02', gusd._format_prim_hierarchy([child1.GetParent()]))
        self.assertEqual('┐to', gusd._format_prim_hierarchy([child1.GetParent()], include_descendants=False))
        self.assertEqual('┐/\n└── path\n    └── to\n        ├── child1\n        └── child02', gusd._format_prim_hierarchy([stage.GetPseudoRoot()]))
        self.assertEqual('┐/', gusd._format_prim_hierarchy([stage.GetPseudoRoot()], include_descendants=False))

    def test_make_plane(self):
        """Not a public API yet"""
        stage = Usd.Stage.CreateInMemory()
        width, depth = 10, 8
        mesh = UsdGeom.Mesh.Define(stage, "/m")
        gusd._make_plane(mesh, width, depth)
        self.assertEqual(80, len(mesh.GetPointsAttr().Get()))
        self.assertEqual(252, len(mesh.GetFaceVertexIndicesAttr().Get()))
        self.assertEqual(63, len(mesh.GetFaceVertexCountsAttr().Get()))

import unittest

from pxr import Usd, UsdGeom, Sdf

import grill.usd as gusd


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


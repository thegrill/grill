import uuid
import logging
import unittest
import tempfile

from pathlib import Path

from pxr import Usd, UsdGeom, Sdf, Ar, Tf

try:
    from grill import cook, names, tokens, usd
    _COOK_AVAILABLE = True
except ImportError as exc:
    _COOK_AVAILABLE = False
    print(f"'grill.cook' module failed to import. Unable to test: {exc.msg}")

logger = logging.getLogger(__name__)

# 2024-11-09 - Python-3.13 & USD-24.11
# python -m unittest --durations 0 test_cook
# Slowest test durations
# ----------------------------------------------------------------------
# 0.044s     test_inherited_and_specialized_contexts (test_cook.TestCook.test_inherited_and_specialized_contexts)
# 0.036s     test_asset_unit (test_cook.TestCook.test_asset_unit)
# 0.024s     test_spawn_many (test_cook.TestCook.test_spawn_many)
# 0.024s     test_create_many_in_memory (test_cook.TestCook.test_create_many_in_memory)
# 0.014s     test_taxonomy (test_cook.TestCook.test_taxonomy)
# 0.010s     test_fetch_stage (test_cook.TestCook.test_fetch_stage)
#
# ----------------------------------------------------------------------
# Ran 6 tests in 0.152s

@unittest.skipUnless(_COOK_AVAILABLE, "Unable to test without 'grill.cook' module")
class TestCook(unittest.TestCase):
    def setUp(self) -> None:
        tempdir = tempfile.mkdtemp()
        logger.debug(f"Repository root directory: {tempdir}")
        self.root_asset = names.UsdAsset.get_anonymous()
        self.token = cook.Repository.set(Path(tempdir) / "repo")

    def tearDown(self) -> None:
        cook.Repository.reset(self.token)

    def test_fetch_stage(self):
        root_asset = self.root_asset
        root_stage = cook.fetch_stage(root_asset)

        # fetching stage outside of AR _context should resolve to same stage
        self.assertEqual(cook.asset_identifier(root_stage.GetRootLayer().identifier), root_asset.name)

        repo_path = cook.Repository.get()
        resolver_ctx = Ar.DefaultResolverContext([str(repo_path)])

        # confirm that a stage from a layer created separately is fetched with the correct resolver context
        usd_opened = str(names.UsdAsset.get_anonymous(item='usd_opened'))
        Sdf.Layer.CreateNew(str(repo_path / usd_opened))

        with self.assertRaisesRegex(Tf.ErrorException, "Failed to open layer"):
            # no resolver context, so unable to open stage
            Usd.Stage.Open(usd_opened)

        with Ar.ResolverContextBinder(resolver_ctx):
            opened_stage = Usd.Stage.Open(usd_opened)

        # when fetching the same asset identifier, the root layer should be the same
        fetched_stage = cook.fetch_stage(usd_opened)
        self.assertIs(opened_stage.GetRootLayer(), fetched_stage.GetRootLayer())
        # but the stages should be different
        self.assertIsNot(opened_stage, fetched_stage)

        in_memory = Usd.Stage.CreateInMemory()
        from_memory = str(names.UsdAsset.get_anonymous(item='from_memory'))
        with self.assertRaises(ValueError):
            # a stage with an empty resolver that fetches a valid identifier should fail.
            cook.fetch_stage(from_memory, context=in_memory.GetPathResolverContext())

    def test_taxonomy(self):
        stage = Usd.Stage.CreateInMemory()

        # An anonymous stage (non grill anonymous) should fail to define taxon.
        with self.assertRaisesRegex(ValueError, "Could not find a valid pipeline layer"):
            cook.define_taxon(stage, "ShouldFail")

        # Same stage containing a grill anon layer on its stack should succeed.
        anon_pipeline = Sdf.Layer.CreateNew(str(cook.Repository.get() / names.UsdAsset.get_anonymous().name))
        stage.GetRootLayer().subLayerPaths.append(anon_pipeline.realPath)

        # Now, test stages fetched from the start via "common" pipeline calls.
        with self.assertRaisesRegex(ValueError, "reserved name"):
            cook.define_taxon(stage, cook._TAXONOMY_NAME)

        with self.assertRaisesRegex(ValueError, "must be a valid identifier for a prim"):
            cook.define_taxon(stage, "/InvalidName")

        with self.assertRaisesRegex(ValueError, "reserved id fields"):
            cook.define_taxon(stage, "taxonomy_not_allowed", id_fields={cook._TAXONOMY_UNIQUE_ID: "by_id_value"})

        with self.assertRaisesRegex(ValueError, "reserved id fields"):
            cook.define_taxon(stage, "taxonomy_not_allowed", id_fields={cook._TAXONOMY_UNIQUE_ID.name: "by_id_name"})

        with self.assertRaisesRegex(ValueError, "invalid id_field keys"):
            cook.define_taxon(stage, "nonexistingfield", id_fields={str(uuid.uuid4()): "by_id_name"})

        missing_or_empty_fields_msg = f"Missing or empty '{cook._FIELDS_KEY}'"
        not_taxon = stage.DefinePrim("/not/a/taxon")
        with self.assertRaisesRegex(ValueError, missing_or_empty_fields_msg):
            cook.create_unit(not_taxon, "NoTaxon")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {})
        with self.assertRaisesRegex(ValueError, missing_or_empty_fields_msg):
            cook.create_unit(not_taxon, "EmptyAssetInfo")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {'invalid': 42})
        with self.assertRaisesRegex(ValueError, missing_or_empty_fields_msg):
            cook.create_unit(not_taxon, "InvalidAssetInfo")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {cook._FIELDS_KEY: 42})
        with self.assertRaisesRegex(TypeError, f"Expected mapping on key '{cook._FIELDS_KEY}'"):
            cook.create_unit(not_taxon, "InvalidAssetInfo")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {cook._FIELDS_KEY: {}})
        with self.assertRaisesRegex(ValueError, missing_or_empty_fields_msg):
            cook.create_unit(not_taxon, "EmptyFields")

        first = cook.define_taxon(stage, "first")
        # idempotent call should keep previously created prim
        self.assertEqual(first, cook.define_taxon(stage, "first"))

        second = cook.define_taxon(stage, "second", references=(first,))
        self.assertTrue(second.IsValid())

        third = cook.define_taxon(stage, "third", references=(first,))

        found_taxa = set(cook.itaxa(stage))
        self.assertSetEqual(set(found_taxa), {first, second, third})

        with self.assertRaisesRegex(ValueError, "is not a taxon."):
            cook.taxonomy_graph([first.GetParent()], "")

        graph_from_stage = cook.taxonomy_graph(found_taxa, "")
        first_successors = set(graph_from_stage.successors(first.GetName()))
        self.assertEqual(first_successors, {second.GetName(), third.GetName()})
        self.assertEqual(set(cook.taxonomy_graph(stage, "").nodes), set(graph_from_stage.nodes))

    def test_asset_unit(self):
        stage = cook.fetch_stage(self.root_asset)
        taxon_name = "taxon"
        unit_name = "unit"
        unit = cook.create_unit(cook.define_taxon(stage, "taxon"), "unit")
        unit_asset = cook.unit_asset(unit)
        unit_id = names.UsdAsset(cook.asset_identifier(unit_asset.identifier))
        self.assertEqual(unit_name, getattr(unit_id, cook._UNIT_UNIQUE_ID.name))
        self.assertEqual(taxon_name, getattr(unit_id, cook._TAXONOMY_UNIQUE_ID.name))

        # When asset identifier is empty or non existing, the fallback inspection of the prim itself should get the same result
        Usd.ModelAPI(unit).SetAssetIdentifier("")
        self.assertEqual(cook.unit_asset(unit).identifier, unit_asset.identifier)

    def test_create_many_in_memory(self):
        stage = Usd.Stage.CreateInMemory()
        # Root_asset is an empty anonymous asset with a pipeline compliant identifier. Create and sublayer it
        anon_pipeline = Sdf.Layer.CreateNew(str(cook.Repository.get() / self.root_asset.name))
        stage.GetRootLayer().subLayerPaths.append(anon_pipeline.identifier)
        cook.create_many(cook.define_taxon(stage, "Anon"), ("first", "second"))

    def test_spawn_many(self):
        stage = cook.fetch_stage(self.root_asset)

        parent = stage.DefinePrim("/a")
        with self.assertRaisesRegex(ValueError, "Can not spawn .* to itself."):
            cook.spawn_many(parent, parent, ["impossible"])
        child = stage.DefinePrim("/b")  # child needs to be a grill unit
        with self.assertRaisesRegex(ValueError, "Could not extract identifier from"):
            cook.spawn_many(parent, child, ["b"])
        invalid_path = "/invalid/path"
        with self.assertRaisesRegex(ValueError, "needs to be a child path of parent path"):
            cook.spawn_unit(parent, child, invalid_path)

        id_fields = {tokens.ids.CGAsset.kingdom.name: "K"}
        taxon = cook.define_taxon(stage, "Another", id_fields=id_fields)
        parent, child = cook.create_many(taxon, ['A', 'B'])
        cook.spawn_many(parent, child, ["b", "nested/c"], labels=["1", "2", "3"])
        self.assertEqual(len(parent.GetChildren()), 2)

        geom = cook.fetch_stage(cook.UsdAsset.get_anonymous(part="Geom"))
        geom.SetDefaultPrim(geom.DefinePrim(cook._UNIT_ORIGIN_PATH))
        payload = Sdf.Payload(cook.asset_identifier(geom.GetRootLayer().identifier))

        with cook.unit_context(child):
            geom_root = stage.DefinePrim(child.GetPath().AppendChild("Geom"))
            geom_root.GetPayloads().AddPayload(payload)
            with usd.edit_context(payload, geom_root):
                with self.assertRaisesRegex(RuntimeError, 'No spec path.*Could not set kind to "assembly"'):
                    cook.spawn_many(child, parent, paths=[geom_root.GetPath().AppendChild('this_will_fail')])

    def test_inherited_and_specialized_contexts(self):
        stage = cook.fetch_stage(self.root_asset)
        id_fields = {tokens.ids.CGAsset.kingdom.name: "K"}
        taxon = cook.define_taxon(stage, "Another", id_fields=id_fields)
        parent_unit, to_be_specialized, to_be_inherited, not_under_context = cook.create_many(
            taxon, ['parent_unit', 'to_be_specialized', 'to_be_inherited', 'not_under_context']
        )

        not_a_unit = stage.DefinePrim("/vanilla_prim")

        with self.assertRaisesRegex(ValueError, "is not a valid unit"):
            cook.specialized_context(not_a_unit)
        with self.assertRaisesRegex(ValueError, "needs to be a valid unit"):
            # current parent prim is not a valid unit in the catalogue (it's just a group)
            cook.specialized_context(to_be_specialized, to_be_specialized.GetParent())

        with self.assertRaisesRegex(ValueError, "is not a descendant"):
            cook.specialized_context(parent_unit, to_be_specialized)
        # return
        spawned_invalid = cook.spawn_unit(parent_unit, not_under_context)

        with self.assertRaisesRegex(ValueError, "Is there a composition arc bringing"):
            # TODO: find a more meaningful message (higher level) than the edit target context one.
            cook.specialized_context(spawned_invalid, parent_unit)

        with cook.unit_context(parent_unit):
            specialized_spawned = cook.spawn_unit(parent_unit, to_be_specialized)
            inherited_spawned = cook.spawn_unit(parent_unit, to_be_inherited)

        with cook.inherited_context(parent_unit):
            UsdGeom.Gprim(parent_unit).MakeInvisible()
        with cook.specialized_context(specialized_spawned, parent_unit):
            UsdGeom.Gprim(specialized_spawned).MakeInvisible()
        with cook.inherited_context(inherited_spawned):
            UsdGeom.Gprim(inherited_spawned).MakeInvisible()

        def _check_broadcasted_invisibility(asset, prim, method):
            target_stage = Usd.Stage.Open(asset)
            target_prefix = cook._broadcast_root_path(prim, method)
            authored = UsdGeom.Gprim(target_stage.GetPrimAtPath(target_prefix.AppendChild(Usd.ModelAPI(prim).GetAssetName()))).GetVisibilityAttr().Get()
            self.assertEqual(authored, 'invisible')

        for target_asset, target_prim, broadcast_type in (
                (parent_unit, parent_unit, Usd.Inherits),  # non-referenced, no context, asset unit is the target
                (inherited_spawned, inherited_spawned, Usd.Inherits),  # referenced asset unit, no context, asset unit is the target
                (parent_unit, specialized_spawned, Usd.Specializes),  # referenced, context unit is the target
        ):
            with self.subTest(target_asset=str(target_asset), target_prim=str(target_prim), broadcast_type=str(broadcast_type)):
                _check_broadcasted_invisibility(cook.unit_asset(target_asset), target_prim, broadcast_type)

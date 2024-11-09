import uuid
import logging
import unittest
import tempfile

from pathlib import Path

from pxr import Usd, UsdGeom, Sdf, Ar, UsdUtils, Tf

from grill import cook, names, usd as gusd, tokens

logger = logging.getLogger(__name__)

# 2024-11-09 - Python-3.13 & USD-24.11
# python -m unittest --durations 0 test_cook
# Slowest test durations
# ----------------------------------------------------------------------
# 0.050s     test_define_taxon (test_cook.TestCook.test_define_taxon)
# 0.049s     test_inherited_and_specialized_contexts (test_cook.TestCook.test_inherited_and_specialized_contexts)
# 0.039s     test_asset_unit (test_cook.TestCook.test_asset_unit)
# 0.036s     test_create_on_previous_stage (test_cook.TestCook.test_create_on_previous_stage)
# 0.031s     test_spawn_unit (test_cook.TestCook.test_spawn_unit)
# 0.028s     test_create_many_in_memory (test_cook.TestCook.test_create_many_in_memory)
# 0.028s     test_spawn_unit_with_absolute_paths (test_cook.TestCook.test_spawn_unit_with_absolute_paths)
# 0.027s     test_spawn_many (test_cook.TestCook.test_spawn_many)
# 0.026s     test_create_many (test_cook.TestCook.test_create_many)
# 0.020s     test_fetch_stage (test_cook.TestCook.test_fetch_stage)
# 0.006s     test_match (test_cook.TestCook.test_match)
# 0.005s     test_edit_context (test_cook.TestCook.test_edit_context)
# 0.001s     test_spawn_many_invalid (test_cook.TestCook.test_spawn_many_invalid)
#
# ----------------------------------------------------------------------
# Ran 13 tests in 0.347s

# empty test:
# Ran 13 tests in 0.012s

# fetchin layers as recently created:
# Ran 13 tests in 0.056s

# fetching stage:
# Ran 13 tests in 0.065s

# fetchin layers as recently created:
# Ran 14 tests in 0.059s


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

        # TODO: cleanup this test. fetch_stage used to keep stages in a cache but not anymore.
        root_stage = cook.fetch_stage(root_asset)
        # fetching stage outside of AR _context should resolve to same stage
        self.assertEqual(cook.asset_identifier(root_stage.GetRootLayer().identifier), root_asset.name)

        repo_path = cook.Repository.get()
        resolver_ctx = Ar.DefaultResolverContext([str(repo_path)])

        # confirm that a stage from a layer created separately is fetched with the correct resolver context
        usd_opened = str(names.UsdAsset.get_anonymous(item='usd_opened'))
        Sdf.Layer.CreateNew(str(repo_path / usd_opened))

        with self.assertRaises(Tf.ErrorException):
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

    # def test_match(self):
    #     root_stage = cook.fetch_stage(self.root_asset)
    #     return
    #     with self.assertRaises(ValueError):
    #         cook._find_layer_matching(dict(missing='tokens'), root_stage.GetLayerStack())

    # def test_edit_context(self):
    #     cook.fetch_stage(self.root_asset)
    #     # return
    #     with self.assertRaises(TypeError):
    #         gusd.edit_context(object(), cook.fetch_stage(self.root_asset))

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

        # with cook.taxonomy_context(stage):
        #     first.CreateAttribute("label", Sdf.ValueTypeNames.String)
        second = cook.define_taxon(stage, "second", references=(first,))
        self.assertTrue(second.IsValid())

        third = cook.define_taxon(stage, "third", references=(first,))

        found_taxa = set(cook.itaxa(stage))
        self.assertSetEqual(set(found_taxa), {first, second, third})

        graph_from_stage = cook.taxonomy_graph(found_taxa, "")
        first_successors = set(graph_from_stage.successors(first.GetName()))
        self.assertEqual(first_successors, {second.GetName(), third.GetName()})
        self.assertEqual(set(cook.taxonomy_graph(stage, "").nodes), set(graph_from_stage.nodes))
        # breakpoint()
        # found_taxa = len(graph_from_stage.nodes)
        # self.assertEqual(found_taxa, 3)
        # self.assertEqual(len(cook.taxonomy_graph(stage, "").nodes), found_taxa)
        return
        # emil = cook.create_unit(person, "EmilSinclair", label="Emil Sinclair")
        # self.assertEqual(emil, cook.create_unit(person, "EmilSinclair"))
        #
        # with cook.unit_context(emil):
        #     emil.GetVariantSet("Transport").SetVariantSelection("HorseDrawnCarriage")
        # return
        # hero = cook.define_taxon(stage, "Hero", references=(person,))
        # batman = cook.create_unit(hero, "Batman")
        # expected_people = [emil, batman]  # batman is also a person
        # expected_heroes = [batman]
        # stage_prims = root_stage.Traverse()
        # self.assertEqual(expected_people, list(cook.itaxa(stage_prims, person)))
        # self.assertEqual(expected_heroes, list(cook.itaxa(stage_prims, hero)))

    def test_create_on_previous_stage(self):
        """Confirm that creating assets on a previously saved stage works.

        The default behavior from layer identifiers that are relative to the resolver search path is to be absolute
        when a stage using them is re-opened, so:
            original_identifier.usda
                becomes
            /absolute/path/original_identifier.usda
        """
        root_asset = names.UsdAsset.get_anonymous()
        root_stage = cook.fetch_stage(root_asset)
        return
        # creates taxonomy.usda and adds it to the stage layer stack
        cook.define_taxon(root_stage, "FirstTaxon")
        root_stage.Save()
        del root_stage

        reopened_stage = cook.fetch_stage(root_asset)
        # the taxonomy.usda now has as identifier /absolute/path/taxonomy.usda, so confirm we can use it still
        cook.create_many(cook.define_taxon(reopened_stage, "SecondTaxon"), ["A", "B"])

    def test_asset_unit(self):
        stage = cook.fetch_stage(self.root_asset)
        return
        taxon_name = "Person"
        person = cook.define_taxon(stage, taxon_name)
        unit_name = "EmilSinclair"
        emil = cook.create_unit(person, unit_name, label="Emil Sinclair")
        unit_asset = cook.unit_asset(emil)
        unit_id = names.UsdAsset(unit_asset.identifier)
        self.assertEqual(unit_name, getattr(unit_id, cook._UNIT_UNIQUE_ID.name))
        self.assertEqual(taxon_name, getattr(unit_id, cook._TAXONOMY_UNIQUE_ID.name))

        not_a_unit = stage.DefinePrim(emil.GetPath().AppendChild("not_a_unit"))
        with self.assertRaisesRegex(ValueError, "Missing or empty"):
            cook.unit_asset(not_a_unit)

        layer = Sdf.Layer.CreateAnonymous()
        with self.assertRaisesRegex(ValueError, "Could not find appropriate node for edit target"):
            gusd.edit_context(not_a_unit, Usd.PrimCompositionQuery.Filter(), lambda arc: arc.GetTargetNode().layerStack.identifier.rootLayer == layer)

        # break the unit model API
        Usd.ModelAPI(emil).SetAssetIdentifier("")
        without_modelapi = cook.unit_asset(emil)
        self.assertEqual(unit_asset, without_modelapi)  # we should get the same result

        Usd.ModelAPI(emil).SetAssetName("not_emil")
        with self.assertRaisesRegex(ValueError, "Could not find layer matching"):
            cook.unit_asset(emil)

    # def test_create_many(self):
    #     stage = cook.fetch_stage(self.root_asset)
    #     return
    #     taxon = cook.define_taxon(stage, "Anon")
    #     cook.create_many(taxon, ("first", "second"))

    def test_create_many_in_memory(self):
        stage = Usd.Stage.CreateInMemory()
        # Root_asset is an empty anonymous asset with a pipeline compliant identifier. Create and sublayer it
        anon_pipeline = Sdf.Layer.CreateNew(str(cook.Repository.get() / self.root_asset.name))
        stage.GetRootLayer().subLayerPaths.append(anon_pipeline.identifier)
        cook.create_many(cook.define_taxon(stage, "Anon"), ("first", "second"))

    def test_spawn_unit(self):
        stage = cook.fetch_stage(self.root_asset)
        return
        id_fields = {tokens.ids.CGAsset.kingdom.name: "K"}
        taxon = cook.define_taxon(stage, "Another", id_fields=id_fields)
        parent, child = cook.create_many(taxon, ['A', 'B'])
        with cook.unit_context(parent):
            for path, value in (
                    ("", (2, 15, 6)),
                    ("Deeper/Nested/Golden1", (-4, 5, 1)),
                    ("Deeper/Nested/Golden2", (-4, -10, 1)),
                    ("Deeper/Nested/Golden3", (0, 10, -2)),
            ):
                cook.spawn_unit(parent, child, path)

    # def test_spawn_unit_with_absolute_paths(self):
    #     stage = cook.fetch_stage(self.root_asset)
    #     # return
    #     id_fields = {tokens.ids.CGAsset.kingdom.name: "K"}
    #     taxon = cook.define_taxon(stage, "Another", id_fields=id_fields)
    #     parent, child = cook.create_many(taxon, ['A', 'B'])


    def test_spawn_many(self):
        stage = cook.fetch_stage(self.root_asset)
        # return
        id_fields = {tokens.ids.CGAsset.kingdom.name: "K"}
        taxon = cook.define_taxon(stage, "Another", id_fields=id_fields)
        parent, child = cook.create_many(taxon, ['A', 'B'])
        cook.spawn_many(parent, child, ["b"], labels=["1", "2"])
        self.assertEqual(len(parent.GetChildren()), 1)
        # valid_path = parent.GetPath().AppendPath("Deeper/Nested/Golden1")
        # self.assertTrue(cook.spawn_unit(parent, child, valid_path))

    def test_spawn_many_invalid(self):
        stage = Usd.Stage.CreateInMemory()
        # return
        parent = stage.DefinePrim("/a")
        with self.assertRaisesRegex(ValueError, "Can not spawn .* to itself."):
            cook.spawn_many(parent, parent, ["impossible"])
        child = stage.DefinePrim("/b")  # child needs to be a grill unit
        with self.assertRaisesRegex(ValueError, "Could not extract identifier from"):
            cook.spawn_many(parent, child, ["b"])

        invalid_path = "/invalid/path"
        with self.assertRaisesRegex(ValueError, "needs to be a child path of parent path"):
            cook.spawn_unit(parent, child, invalid_path)

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

    # def test_taxonomy_graph(self):
    #     return
    #     stage = cook.fetch_stage(self.root_asset)
    #     a = cook.define_taxon(stage, "a")
    #     b = cook.define_taxon(stage, "b")
    #     cook.define_taxon(stage, "c", references=(a, b))
    #     graph = cook.taxonomy_graph(cook.i_taxa(stage), "")
    #     found_taxa = len(graph.nodes)
    #     self.assertEqual(found_taxa, 3)
    #     self.assertEqual(len(cook.taxonomy_graph(stage, "").nodes), found_taxa)

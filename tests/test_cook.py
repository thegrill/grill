import uuid
import logging
import unittest
import tempfile

from pathlib import Path

from pxr import Usd, UsdGeom, Sdf, Ar, UsdUtils

from grill import cook, names, usd as gusd, tokens

logger = logging.getLogger(__name__)


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
        self.assertEqual(root_stage.GetRootLayer().identifier, root_asset.name)

        repo_path = cook.Repository.get()
        resolver_ctx = Ar.DefaultResolverContext([str(repo_path)])
        with Ar.ResolverContextBinder(resolver_ctx):
            # inside an AR resolver _context, a new layer and custom stage should end up
            # in that stage not resolving to the same as the one from write.fetch_stage
            usd_opened = str(names.UsdAsset.get_anonymous(item='usd_opened'))
            Sdf.Layer.CreateNew(str(repo_path / usd_opened))
            non_cache_stage = Usd.Stage.Open(usd_opened)
            cached_stage = cook.fetch_stage(usd_opened)
            self.assertIsNot(non_cache_stage, cached_stage)
            # Even after fetching once, subsequent fetches should be different
            self.assertIsNot(cached_stage, cook.fetch_stage(usd_opened))

            # creating a new layer + stage + adding it to the cache manually
            # should still have fetch_stage to retrieve a different stage.
            sdf_opened = str(names.UsdAsset.get_default(item='sdf_opened'))
            Sdf.Layer.CreateNew(str(repo_path / sdf_opened))
            cached_layer = Sdf.Layer.FindOrOpen(sdf_opened)
            opened_stage = Usd.Stage.Open(cached_layer)
            cache = UsdUtils.StageCache.Get()
            cache.Insert(opened_stage)
            self.assertIsNot(opened_stage, cook.fetch_stage(sdf_opened))

        in_memory = Usd.Stage.CreateInMemory()
        from_memory = str(names.UsdAsset.get_anonymous(item='from_memory'))
        with self.assertRaises(ValueError):
            # a stage with an empty resolver that fetches a valid identifier should fail.
            cook.fetch_stage(from_memory, context=in_memory.GetPathResolverContext())

        unbound_resolver = str(names.UsdAsset.get_anonymous(item='unbound_resolver'))
        with self.assertRaises(RuntimeError):
            # directly fetching a new layer without a context with statement should fail
            cook._fetch_layer(unbound_resolver, root_stage.GetPathResolverContext())

    def test_match(self):
        root_stage = cook.fetch_stage(self.root_asset)
        with self.assertRaises(ValueError):
            cook._find_layer_matching(dict(missing='tokens'), root_stage.GetLayerStack())

    def test_edit_context(self):
        with self.assertRaises(TypeError):
            gusd.edit_context(object(), cook.fetch_stage(self.root_asset))

    def test_define_taxon(self):
        # An anonymous stage (non grill anonymous) should fail to define taxon.
        anon_stage = Usd.Stage.CreateInMemory()
        with self.assertRaises(ValueError):
            cook.define_taxon(anon_stage, "ShouldFail")
        # Same stage containing a grill anon layer on its stack should succeed.
        anon_pipeline = cook.fetch_stage(names.UsdAsset.get_anonymous())
        anon_stage.GetRootLayer().subLayerPaths.append(anon_pipeline.GetRootLayer().realPath)
        self.assertTrue(cook.define_taxon(anon_stage, "ShouldSucceed").IsValid())

        # Now, test stages fetched from the start via "common" pipeline calls.
        root_stage = cook.fetch_stage(self.root_asset)

        with self.assertRaisesRegex(ValueError, "reserved name"):
            cook.define_taxon(root_stage, cook._TAXONOMY_NAME)

        with self.assertRaisesRegex(ValueError, "reserved id fields"):
            cook.define_taxon(root_stage, "taxonomy_not_allowed", id_fields={cook._TAXONOMY_UNIQUE_ID: "by_id_value"})

        with self.assertRaisesRegex(ValueError, "reserved id fields"):
            cook.define_taxon(root_stage, "taxonomy_not_allowed", id_fields={cook._TAXONOMY_UNIQUE_ID.name: "by_id_name"})

        with self.assertRaisesRegex(ValueError, "invalid id_field keys"):
            cook.define_taxon(root_stage, "nonexistingfield", id_fields={str(uuid.uuid4()): "by_id_name"})

        displayable = cook.define_taxon(root_stage, "DisplayableName")
        # idempotent call should keep previously created prim
        self.assertEqual(displayable, cook.define_taxon(root_stage, "DisplayableName"))

        person = cook.define_taxon(root_stage, "Person", references=(displayable,))

        with cook.taxonomy_context(root_stage):
            displayable.CreateAttribute("label", Sdf.ValueTypeNames.String)

        missing_or_empty_fields_msg = f"Missing or empty '{cook._FIELDS_KEY}'"
        not_taxon = root_stage.DefinePrim("/not/a/taxon")
        with self.assertRaisesRegex(ValueError, missing_or_empty_fields_msg):
            cook.create_unit(not_taxon, "WillFail")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {})
        with self.assertRaisesRegex(ValueError, missing_or_empty_fields_msg):
            cook.create_unit(not_taxon, "WillFail")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {'invalid': 42})
        with self.assertRaisesRegex(ValueError, missing_or_empty_fields_msg):
            cook.create_unit(not_taxon, "WillFail")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {cook._FIELDS_KEY: 42})
        with self.assertRaisesRegex(TypeError, f"Expected mapping on key '{cook._FIELDS_KEY}'"):
            cook.create_unit(not_taxon, "WillFail")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {cook._FIELDS_KEY: {}})
        with self.assertRaisesRegex(ValueError, missing_or_empty_fields_msg):
            cook.create_unit(not_taxon, "WillFail")

        emil = cook.create_unit(person, "EmilSinclair", label="Emil Sinclair")
        self.assertEqual(emil, cook.create_unit(person, "EmilSinclair"))

        with cook.unit_context(emil):
            emil.GetVariantSet("Transport").SetVariantSelection("HorseDrawnCarriage")

        hero = cook.define_taxon(root_stage, "Hero", references=(person,))
        batman = cook.create_unit(hero, "Batman")
        expected_people = [emil, batman]  # batman is also a person
        expected_heroes = [batman]
        stage_prims = root_stage.Traverse()
        self.assertEqual(expected_people, list(cook.itaxa(stage_prims, person)))
        self.assertEqual(expected_heroes, list(cook.itaxa(stage_prims, hero)))

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
        # creates taxonomy.usda and adds it to the stage layer stack
        cook.define_taxon(root_stage, "FirstTaxon")
        root_stage.Save()
        del root_stage

        reopened_stage = cook.fetch_stage(root_asset)
        # the taxonomy.usda now has as identifier /absolute/path/taxonomy.usda, so confirm we can use it still
        cook.create_many(cook.define_taxon(reopened_stage, "SecondTaxon"), ["A", "B"])

    def test_asset_unit(self):
        stage = cook.fetch_stage(self.root_asset)
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

    def test_create_many(self):
        stage = cook.fetch_stage(self.root_asset)
        taxon = cook.define_taxon(stage, "Another")
        cook.create_many(taxon, (f"new_{x}" for x in range(10)))

        anon_stage = Usd.Stage.CreateInMemory()
        # An anon stage containing a grill layer on its stack should succeed.
        anon_pipeline = cook.fetch_stage(names.UsdAsset.get_anonymous())
        anon_stage.GetRootLayer().subLayerPaths.append(anon_pipeline.GetRootLayer().realPath)
        anon_taxon = cook.define_taxon(anon_stage, "Anon")
        cook.create_many(anon_taxon, ("first", "second"))

    def test_spawn_unit(self):
        stage = cook.fetch_stage(self.root_asset)
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

    def test_spawn_unit_with_absolute_paths(self):
        stage = cook.fetch_stage(self.root_asset)
        id_fields = {tokens.ids.CGAsset.kingdom.name: "K"}
        taxon = cook.define_taxon(stage, "Another", id_fields=id_fields)
        parent, child = cook.create_many(taxon, ['A', 'B'])
        valid_path = parent.GetPath().AppendPath("Deeper/Nested/Golden1")
        invalid_path = "/invalid/path"
        self.assertTrue(cook.spawn_unit(parent, child, valid_path))
        with self.assertRaisesRegex(ValueError, "needs to be a child path of parent path"):
            cook.spawn_unit(parent, child, invalid_path)

    def test_spawn_many(self):
        stage = cook.fetch_stage(self.root_asset)
        id_fields = {tokens.ids.CGAsset.kingdom.name: "K"}
        taxon = cook.define_taxon(stage, "Another", id_fields=id_fields)
        parent, child = cook.create_many(taxon, ['A', 'B'])
        cook.spawn_many(parent, child, ["b"], labels=["1", "2"])
        self.assertEqual(len(parent.GetChildren()), 1)

    def test_spawn_many_invalid(self):
        stage = Usd.Stage.CreateInMemory()
        parent = stage.DefinePrim("/a")
        with self.assertRaisesRegex(ValueError, "Can not spawn .* to itself."):
            cook.spawn_many(parent, parent, ["impossible"])
        child = stage.DefinePrim("/b")  # child needs to be a grill unit
        with self.assertRaisesRegex(ValueError, "Could not extract identifier from"):
            cook.spawn_many(parent, child, ["b"])

    def test_inherited_and_specialized_contexts(self):
        stage = cook.fetch_stage(self.root_asset)
        id_fields = {tokens.ids.CGAsset.kingdom.name: "K"}
        taxon = cook.define_taxon(stage, "Another", id_fields=id_fields)
        parent, via_s, via_i, not_under_context = cook.create_many(taxon, ['parent', 'via_s', 'via_i', 'not_under_context'])

        not_a_unit = stage.DefinePrim("/vanilla_prim")
        with self.assertRaisesRegex(ValueError, "is not a valid unit"):
            cook.specialized_context(not_a_unit)

        with self.assertRaisesRegex(ValueError, "needs to be a valid unit"):
            cook.specialized_context(via_s, via_s.GetParent())

        with self.assertRaisesRegex(ValueError, "is not a descendant"):
            cook.specialized_context(parent, via_s)

        spawned_invalid = cook.spawn_unit(parent, not_under_context)
        with self.assertRaisesRegex(ValueError, "Is there a composition arc bringing"):
            # TODO: find a more meaningful message (higher level) than the edit target context one.
            cook.specialized_context(spawned_invalid, parent)

        with cook.unit_context(parent):
            via_s_spawned = cook.spawn_unit(parent, via_s)
            via_i_spawned = cook.spawn_unit(parent, via_i)

        with cook.inherited_context(not_under_context):
            UsdGeom.Gprim(not_under_context).MakeInvisible()

        with cook.specialized_context(via_s_spawned, parent):
            UsdGeom.Gprim(via_s_spawned).MakeInvisible()

        with cook.inherited_context(via_i_spawned):
            UsdGeom.Gprim(via_i_spawned).MakeInvisible()

        def _check_broadcasted_invisibility(asset, prim, method):
            target_stage = Usd.Stage.Open(asset)
            target_prefix = cook._broadcast_root_path(prim, method)
            authored = UsdGeom.Gprim(target_stage.GetPrimAtPath(target_prefix.AppendChild(Usd.ModelAPI(prim).GetAssetName()))).GetVisibilityAttr().Get()
            self.assertEqual(authored, 'invisible')

        for target_asset, target_prim, broadcast_type in (
                (not_under_context, not_under_context, Usd.Inherits),  # non-referenced, no context, asset unit is the target
                (via_i_spawned, via_i_spawned, Usd.Inherits),  # referenced asset unit, no context, asset unit is the target
                (parent, via_s_spawned, Usd.Specializes),  # referenced, context unit is the target
        ):
            with self.subTest(target_asset=str(target_asset), target_prim=str(target_prim), broadcast_type=str(broadcast_type)):
                _check_broadcasted_invisibility(cook.unit_asset(target_asset), target_prim, broadcast_type)

import uuid
import logging
import unittest
import tempfile

from pathlib import Path

from pxr import Usd, Sdf, Ar, UsdUtils

from grill import cook, names, usd as gusd

logger = logging.getLogger(__name__)


class TestWrite(unittest.TestCase):
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
        self.assertIs(root_stage, cook.fetch_stage(root_asset))

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
            # but after fetching once, subsequent fetches should persist
            self.assertIs(cached_stage, cook.fetch_stage(usd_opened))

            # creating a new layer + stage + adding it to the cache manually
            # should allow fetch_stage to retrieve it as well.
            sdf_opened = str(names.UsdAsset.get_default(item='sdf_opened'))
            layer = Sdf.Layer.CreateNew(str(repo_path / sdf_opened))
            del layer
            cached_layer = Sdf.Layer.FindOrOpen(sdf_opened)
            opened_stage = Usd.Stage.Open(cached_layer)
            cache = UsdUtils.StageCache.Get()
            cache.Insert(opened_stage)
            self.assertIs(opened_stage, cook.fetch_stage(sdf_opened))

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

        with self.assertRaises(ValueError):
            cook.define_taxon(root_stage, cook._TAXONOMY_NAME)

        with self.assertRaises(ValueError):
            cook.define_taxon(root_stage, "taxonomy_not_allowed", id_fields={cook._TAXONOMY_UNIQUE_ID: "by_id_value"})

        with self.assertRaises(ValueError):
            cook.define_taxon(root_stage, "taxonomy_not_allowed", id_fields={cook._TAXONOMY_UNIQUE_ID.name: "by_id_name"})

        with self.assertRaises(ValueError):
            cook.define_taxon(root_stage, "nonexistingfield", id_fields={str(uuid.uuid4()): "by_id_name"})

        displayable = cook.define_taxon(root_stage, "DisplayableName")
        # idempotent call should keep previously created prim
        self.assertEqual(displayable, cook.define_taxon(root_stage, "DisplayableName"))

        person = cook.define_taxon(root_stage, "Person", references=(displayable,))

        with cook.taxonomy_context(root_stage):
            displayable.CreateAttribute("label", Sdf.ValueTypeNames.String)

        not_taxon = root_stage.DefinePrim("/not/a/taxon")
        with self.assertRaises(ValueError):
            cook.create(not_taxon, "WillFail")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {})
        with self.assertRaises(ValueError):
            cook.create(not_taxon, "WillFail")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {'invalid': 42})
        with self.assertRaises(ValueError):
            cook.create(not_taxon, "WillFail")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {cook._FIELDS_KEY: 42})
        with self.assertRaises(TypeError):
            cook.create(not_taxon, "WillFail")

        not_taxon.SetAssetInfoByKey(cook._ASSETINFO_KEY, {cook._FIELDS_KEY: {}})
        with self.assertRaises(ValueError):
            cook.create(not_taxon, "WillFail")

        emil = cook.create(person, "EmilSinclair", label="Emil Sinclair")
        self.assertEqual(emil, cook.create(person, "EmilSinclair"))

        with cook.unit_context(emil):
            emil.GetVariantSet("Transport").SetVariantSelection("HorseDrawnCarriage")

        hero = cook.define_taxon(root_stage, "Hero", references=(person,))
        batman = cook.create(hero, "Batman")
        expected_people = [emil, batman]  # batman is also a person
        expected_heroes = [batman]
        stage_prims = root_stage.Traverse()
        self.assertEqual(expected_people, list(cook.itaxa(stage_prims, person)))
        self.assertEqual(expected_heroes, list(cook.itaxa(stage_prims, hero)))

    def test_asset_unit(self):
        stage = cook.fetch_stage(self.root_asset)
        taxon_name = "Person"
        person = cook.define_taxon(stage, taxon_name)
        unit_name = "EmilSinclair"
        emil = cook.create(person, unit_name, label="Emil Sinclair")
        unit_asset = cook.unit_asset(emil)
        unit_id = names.UsdAsset(unit_asset.identifier)
        self.assertEqual(unit_name, getattr(unit_id, cook._UNIT_UNIQUE_ID.name))
        self.assertEqual(taxon_name, getattr(unit_id, cook._TAXONOMY_UNIQUE_ID.name))

        not_a_unit = stage.DefinePrim(emil.GetPath().AppendChild("not_a_unit"))
        with self.assertRaisesRegex(ValueError, "Missing or empty"):
            cook.unit_asset(not_a_unit)

        layer = Sdf.Layer.CreateAnonymous()
        with self.assertRaisesRegex(ValueError, "Could not find appropriate node for edit target"):
            gusd.edit_context(not_a_unit, Usd.PrimCompositionQuery.Filter(), lambda node: node.layerStack.identifier.rootLayer == layer)

    def test_create_many(self):
        stage = cook.fetch_stage(self.root_asset)
        taxon = cook.define_taxon(stage, "Another")
        cook.create_many(taxon, (f"new_{x}" for x in range(10)))

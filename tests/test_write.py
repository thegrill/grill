import uuid
import logging
import unittest
import tempfile

from pathlib import Path

from pxr import Usd, Sdf, Ar, UsdUtils

from grill import write

logger = logging.getLogger(__name__)


class TestUsdAsset(unittest.TestCase):
    def test_usd_asset(self):
        assetname = write.UsdAsset.get_anonymous(stream='test', suffix='usdz')
        self.assertEqual(assetname.stream, 'test')
        self.assertEqual(assetname.suffix, 'usdz')
        with self.assertRaises(ValueError):
            write.UsdAsset.get_anonymous(suffix='xyz')


class TestWrite(unittest.TestCase):
    def setUp(self) -> None:
        tempdir = tempfile.mkdtemp()
        logger.debug(f"Repository root directory: {tempdir}")
        self.root_asset = write.UsdAsset.get_anonymous()
        self.token = write.repo.set(Path(tempdir) / "repo")

    def tearDown(self) -> None:
        write.repo.reset(self.token)

    def test_fetch_stage(self):
        root_asset = self.root_asset

        root_stage = write.fetch_stage(root_asset)
        # fetching stage outside of AR _context should resolve to same stage
        self.assertIs(root_stage, write.fetch_stage(root_asset))

        repo_path = write.repo.get()
        resolver_ctx = Ar.DefaultResolverContext([str(repo_path)])
        with Ar.ResolverContextBinder(resolver_ctx):
            # inside an AR resolver _context, a new layer and custom stage should end up
            # in that stage not resolving to the same as the one from write.fetch_stage
            usd_opened = str(write.UsdAsset.get_anonymous(item='usd_opened'))
            Sdf.Layer.CreateNew(str(repo_path / usd_opened))
            non_cache_stage = Usd.Stage.Open(usd_opened)
            cached_stage = write.fetch_stage(usd_opened)
            self.assertIsNot(non_cache_stage, cached_stage)
            # but after fetching once, subsequent fetches should persist
            self.assertIs(cached_stage, write.fetch_stage(usd_opened))

            # creating a new layer + stage + adding it to the cache manually
            # should allow fetch_stage to retrieve it as well.
            sdf_opened = str(write.UsdAsset.get_default(item='sdf_opened'))
            layer = Sdf.Layer.CreateNew(str(repo_path / sdf_opened))
            del layer
            cached_layer = Sdf.Layer.FindOrOpen(sdf_opened)
            opened_stage = Usd.Stage.Open(cached_layer)
            cache = UsdUtils.StageCache.Get()
            cache.Insert(opened_stage)
            self.assertIs(opened_stage, write.fetch_stage(sdf_opened))

    def test_match(self):
        root_stage = write.fetch_stage(self.root_asset)
        with self.assertRaises(ValueError):
            write._find_layer_matching(dict(missing='tokens'), root_stage.GetLayerStack())

    def test_invalid_stack(self):
        with self.assertRaises(TypeError):
            write._layer_stack(object())

    def test_edit_context(self):
        with self.assertRaises(TypeError):
            write._edit_context(object(), write.fetch_stage(self.root_asset))

    def test_define_taxon(self):
        # An anonymous stage (non grill anonymous) should fail to define taxon.
        anon_stage = Usd.Stage.CreateInMemory()
        with self.assertRaises(ValueError):
            write.define_taxon(anon_stage, "ShouldFail")
        # Same stage containing a grill anon layer on its stack should succeed.
        anon_pipeline = write.fetch_stage(write.UsdAsset.get_anonymous())
        anon_stage.GetRootLayer().subLayerPaths.append(anon_pipeline.GetRootLayer().realPath)
        self.assertTrue(write.define_taxon(anon_stage, "ShouldSucceed").IsValid())

        # Now, test stages fetched from the start via "common" pipeline calls.
        root_stage = write.fetch_stage(self.root_asset)

        with self.assertRaises(ValueError):
            write.define_taxon(root_stage, write._TAXONOMY_NAME)

        with self.assertRaises(ValueError):
            write.define_taxon(root_stage, "taxonomy_not_allowed", id_fields={write._TAXONOMY_UNIQUE_ID: "by_id_value"})

        with self.assertRaises(ValueError):
            write.define_taxon(root_stage, "taxonomy_not_allowed", id_fields={write._TAXONOMY_UNIQUE_ID.name: "by_id_name"})

        with self.assertRaises(ValueError):
            write.define_taxon(root_stage, "nonexistingfield", id_fields={str(uuid.uuid4()): "by_id_name"})

        displayable = write.define_taxon(root_stage, "DisplayableName")
        # idempotent call should keep previously created prim
        self.assertEqual(displayable, write.define_taxon(root_stage, "DisplayableName"))

        person = write.define_taxon(root_stage, "Person", references=(displayable,))

        with write.taxonomy_context(root_stage):
            displayable.CreateAttribute("label", Sdf.ValueTypeNames.String)

        not_taxon = root_stage.DefinePrim("/not/a/taxon")
        with self.assertRaises(ValueError):
            write.create(not_taxon, "WillFail")

        not_taxon.SetCustomDataByKey(write._PRIM_GRILL_KEY, {})
        with self.assertRaises(ValueError):
            write.create(not_taxon, "WillFail")

        not_taxon.SetCustomDataByKey(write._PRIM_GRILL_KEY, {'invalid': 42})
        with self.assertRaises(ValueError):
            write.create(not_taxon, "WillFail")

        not_taxon.SetCustomDataByKey(write._PRIM_GRILL_KEY, {write._PRIM_FIELDS_KEY: 42})
        with self.assertRaises(TypeError):
            write.create(not_taxon, "WillFail")

        not_taxon.SetCustomDataByKey(write._PRIM_GRILL_KEY, {write._PRIM_FIELDS_KEY: {}})
        with self.assertRaises(ValueError):
            write.create(not_taxon, "WillFail")

        emil = write.create(person, "EmilSinclair", label="Emil Sinclair")
        self.assertEqual(emil, write.create(person, "EmilSinclair"))

        with write.unit_context(emil):
            emil.GetVariantSet("Transport").SetVariantSelection("HorseDrawnCarriage")

    def test_create_many(self):
        stage = write.fetch_stage(self.root_asset)
        taxon = write.define_taxon(stage, "Another")
        write.create_many(taxon, (f"new_{x}" for x in range(10)))

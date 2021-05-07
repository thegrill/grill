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
        # fetching stage outside of AR context should resolve to same stage
        self.assertIs(root_stage, write.fetch_stage(root_asset))

        repo_path = write.repo.get()
        resolver_ctx = Ar.DefaultResolverContext([str(repo_path)])
        with Ar.ResolverContextBinder(resolver_ctx):
            # inside an AR resolver context, a new layer and custom stage should end up
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

    def test_edit_context(self):
        with self.assertRaises(TypeError):
            write._edit_context(object(), write.fetch_stage(self.root_asset))

    def test_define_taxon(self):
        root_stage = write.fetch_stage(self.root_asset)
        displayable = write.define_taxon(root_stage, "DisplayableName")
        # idempotent call should keep previously created prim
        self.assertEqual(displayable, write.define_taxon(root_stage, "DisplayableName"))

        person = write.define_taxon(root_stage, "Person", references=(displayable,))

        with write.taxonomy_context(root_stage):
            displayable.CreateAttribute("label", Sdf.ValueTypeNames.String)

        emil = write.create(person, "EmilSinclair", label="Emil Sinclair")
        self.assertEqual(emil, write.create(person, "EmilSinclair"))

        with write.asset_context(emil):
            emil.GetVariantSet("Transport").SetVariantSelection("HorseDrawnCarriage")

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
            write.find_layer_matching(dict(missing='tokens'), root_stage.GetLayerStack())

    def test_define_asset_type(self):
        root_stage = write.fetch_stage(self.root_asset)
        displayable_type = write.define_db_type(root_stage, "DisplayableName")
        # idempotent call should keep previously created prim
        self.assertEqual(displayable_type, write.define_db_type(root_stage, "DisplayableName"))

        asset_types_layer = write.find_layer_matching(write._DB_TOKENS, root_stage.GetLayerStack())

        # transport_enum = write.define_db_type(root_stage, "Transport")
        # person_type = write.define_db_type(stage, "Person", (displayable_type,))
        pc_type = write.define_db_type(root_stage, "PC", (displayable_type,))
        # npc_type = write.define_db_type(stage, "NPC", (person_type,))
        # vampire_type = write.define_db_type(stage, "Vampire", (person_type,))
        # place_type = write.define_db_type(stage, "Place", (displayable_type,))
        # country_type = write.define_db_type(stage, "Country", (place_type,))
        # city_type = write.define_db_type(root_stage, "City", (displayable_type,))
        #
        # # TODO: the following db relationships as well. This time we do this with an edit target
        # db_layer = write.find_layer_matching(write._DB_TOKENS, stage.GetLayerStack())
        #
        # ### DB edits  ###
        with self.assertRaises(TypeError):
            write.edit_context(object(), root_stage)

        with write.edit_context(asset_types_layer, root_stage):
            displayable_type.CreateAttribute("display_name", Sdf.ValueTypeNames.String)
            # variant_set = transport_enum.GetVariantSets().AddVariantSet("Transport")
            # for set_name in ("Feet", "Train", "HorseDrawnCarriage"):
            #     variant_set.AddVariant(set_name)

        # assets_type_stage = Usd.Stage.Open(asset_types_layer)
        # self.assertTrue(assets_type_stage.GetPrimAtPath("/DBTypes/DisplayableName").GetAttribute("display_name").IsValid())
        # self.assertTrue(assets_type_stage.GetPrimAtPath("/DBTypes/Transport").GetVariantSets().GetVariantSet("Transport").IsValid)
        # print(asset_types_layer.ExportToString())
        # self.assertTrue(False)
        #
        #     # TODO: how to add constraints? Useful to catch errors before they hit the database
        #     #   https://github.com/edgedb/easy-edgedb/blob/master/chapter3/index.md#adding-constraints
        #     person_type.CreateAttribute('age', Sdf.ValueTypeNames.Int2)
        #     person_type.CreateRelationship('places_visited')
        #     person_type.CreateRelationship('lover')
        #
        #     place_type.CreateAttribute("modern_name", Sdf.ValueTypeNames.String)
        #     for each in (city_type, country_type):
        #         # all places that end up in the database are "important places"
        #         Usd.ModelAPI(each).SetKind(Kind.Tokens.assembly)
        #
        # ### DB END ###
        # cityRoot = stage.DefinePrim(f"/{city_type.GetName()}")
        #
        # munich = write.create(root_stage, city_type, 'Munich', display_name="Mónaco")
        # self.assertEqual(munich, write.create(root_stage, city_type, 'Munich'))
        # return
        # write.create(stage, city_type, 'Munich')
        #
        #
        # write.create(stage, city_type, 'Budapest', display_name='Buda-Pesth')
        # bistritz = write.create(stage, city_type, 'Bistritz', display_name='Bistritz')
        # london = write.create(stage, city_type, 'London')
        #
        # bistritz_layer = write.find_layer_matching(
        #     dict(item='Bistritz', kingdom='assets'),
        #     (stack.layer for stack in bistritz.GetPrimStack())
        # )
        #
        # with write.edit_context(bistritz, bistritz_layer, stage):
        #     bistritz.GetAttribute("modern_name").Set('Bistrița')
        #
        # write.create(stage, country_type, 'Hungary')
        # romania = write.create(stage, country_type, 'Romania')
        #
        # jonathan = write.create(stage, pc_type, 'JonathanHarker',
        #                         display_name='Jonathan Harker')
        emil = write.create(root_stage, pc_type, "EmilSinclair",
                            display_name="Emil Sinclair")
        # dracula = write.create(stage, vampire_type, 'CountDracula',
        #                        display_name='Count Dracula')
        # mina = write.create(stage, npc_type, 'MinaMurray', display_name='Mina Murray')
        # mina.GetRelationship("lover").AddTarget(jonathan.GetPath())
        #
        # for prim, places in {
        #     jonathan: cityRoot.GetChildren(),
        #     emil: cityRoot.GetChildren(),
        #     dracula: [romania],
        #     mina: [london],
        # }.items():
        #     visitRel = prim.GetRelationship('places_visited')
        #     for place in places:
        #         visitRel.AddTarget(place.GetPath())
        #
        # # we could set "important_places" as a custom new property
        # # but "important" prims are already provided by the USD model hierarchy.
        # # let's try it and see if we can get away with it.
        # goldenKrone = write.create(stage, place_type, 'GoldenKroneHotel',
        #                            'Golden Krone Hotel')
        # # also, let's make it a child of bistritz
        # childPrim = stage.OverridePrim(
        #     bistritz.GetPath().AppendChild(goldenKrone.GetName()))
        # childPrim.GetReferences().AddInternalReference(goldenKrone.GetPath())
        # Usd.ModelAPI(childPrim).SetKind(
        #     Kind.Tokens.component)  # should be component or reference?
        #
        emil_layer = write.find_layer_matching(
            dict(item='EmilSinclair', kingdom='assets'),
            (stack.layer for stack in emil.GetPrimStack())
        )
        #
        with write.edit_context(emil, emil_layer, root_stage):
            emil.GetVariantSet("Transport").SetVariantSelection("HorseDrawnCarriage")

        return
        ##############################################################################
        # transport_enum = write.define_db_type(root_stage, "Transport")
        # person_type = write.define_db_type(stage, "Person", (displayable_type,))
        # pc_type = write.define_db_type(stage, "PC", (person_type, transport_enum))
        # npc_type = write.define_db_type(stage, "NPC", (person_type,))
        # vampire_type = write.define_db_type(stage, "Vampire", (person_type,))
        # place_type = write.define_db_type(stage, "Place", (displayable_type,))
        # country_type = write.define_db_type(stage, "Country", (place_type,))
        # city_type = write.define_db_type(stage, "City", (place_type,))
        #
        # # TODO: the following db relationships as well. This time we do this with an edit target
        # db_layer = write.find_layer_matching(write._DB_TOKENS, stage.GetLayerStack())
        #
        # ### DB edits  ###
        with write.edit_context(asset_types_layer, root_stage):
            displayable_type.CreateAttribute("display_name", Sdf.ValueTypeNames.String)
            # variant_set = transport_enum.GetVariantSets().AddVariantSet("Transport")
            # for set_name in ("Feet", "Train", "HorseDrawnCarriage"):
            #     variant_set.AddVariant(set_name)

        # assets_type_stage = Usd.Stage.Open(asset_types_layer)
        # self.assertTrue(assets_type_stage.GetPrimAtPath("/DBTypes/DisplayableName").GetAttribute("display_name").IsValid())
        # self.assertTrue(assets_type_stage.GetPrimAtPath("/DBTypes/Transport").GetVariantSets().GetVariantSet("Transport").IsValid)
        # print(asset_types_layer.ExportToString())
        # self.assertTrue(False)
        #
        #     # TODO: how to add constraints? Useful to catch errors before they hit the database
        #     #   https://github.com/edgedb/easy-edgedb/blob/master/chapter3/index.md#adding-constraints
        #     person_type.CreateAttribute('age', Sdf.ValueTypeNames.Int2)
        #     person_type.CreateRelationship('places_visited')
        #     person_type.CreateRelationship('lover')
        #
        #     place_type.CreateAttribute("modern_name", Sdf.ValueTypeNames.String)
        #     for each in (city_type, country_type):
        #         # all places that end up in the database are "important places"
        #         Usd.ModelAPI(each).SetKind(Kind.Tokens.assembly)
        #
        # ### DB END ###
        # cityRoot = stage.DefinePrim(f"/{city_type.GetName()}")
        #
        write.create(stage, city_type, 'Munich')
        # write.create(stage, city_type, 'Munich')
        #
        # with self.assertRaises(TypeError):
        #     write.edit_context(object(), stage)
        #
        # write.create(stage, city_type, 'Budapest', display_name='Buda-Pesth')
        # bistritz = write.create(stage, city_type, 'Bistritz', display_name='Bistritz')
        # london = write.create(stage, city_type, 'London')
        #
        # bistritz_layer = write.find_layer_matching(
        #     dict(item='Bistritz', kingdom='assets'),
        #     (stack.layer for stack in bistritz.GetPrimStack())
        # )
        #
        # with write.edit_context(bistritz, bistritz_layer, stage):
        #     bistritz.GetAttribute("modern_name").Set('Bistrița')
        #
        # write.create(stage, country_type, 'Hungary')
        # romania = write.create(stage, country_type, 'Romania')
        #
        # jonathan = write.create(stage, pc_type, 'JonathanHarker',
        #                         display_name='Jonathan Harker')
        # emil = write.create(stage, pc_type, "EmilSinclair",
        #                     display_name="Emil Sinclair")
        # dracula = write.create(stage, vampire_type, 'CountDracula',
        #                        display_name='Count Dracula')
        # mina = write.create(stage, npc_type, 'MinaMurray', display_name='Mina Murray')
        # mina.GetRelationship("lover").AddTarget(jonathan.GetPath())
        #
        # for prim, places in {
        #     jonathan: cityRoot.GetChildren(),
        #     emil: cityRoot.GetChildren(),
        #     dracula: [romania],
        #     mina: [london],
        # }.items():
        #     visitRel = prim.GetRelationship('places_visited')
        #     for place in places:
        #         visitRel.AddTarget(place.GetPath())
        #
        # # we could set "important_places" as a custom new property
        # # but "important" prims are already provided by the USD model hierarchy.
        # # let's try it and see if we can get away with it.
        # goldenKrone = write.create(stage, place_type, 'GoldenKroneHotel',
        #                            'Golden Krone Hotel')
        # # also, let's make it a child of bistritz
        # childPrim = stage.OverridePrim(
        #     bistritz.GetPath().AppendChild(goldenKrone.GetName()))
        # childPrim.GetReferences().AddInternalReference(goldenKrone.GetPath())
        # Usd.ModelAPI(childPrim).SetKind(
        #     Kind.Tokens.component)  # should be component or reference?
        #
        # emil_layer = write.find_layer_matching(
        #     dict(item='EmilSinclair', kingdom='assets'),
        #     (stack.layer for stack in emil.GetPrimStack())
        # )
        #
        # with write.edit_context(emil, emil_layer, stage):
        #     emil.GetVariantSet("Transport").SetVariantSelection("HorseDrawnCarriage")

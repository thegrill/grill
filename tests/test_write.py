import logging
import unittest
import tempfile

from pathlib import Path

from pxr import Kind, Usd, Sdf, Ar, UsdUtils

from grill import write

logger = logging.getLogger(__name__)


class TestWrite(unittest.TestCase):
    def setUp(self) -> None:
        tempdir = tempfile.mkdtemp()
        logger.debug(f"Repository root directory: {tempdir}")
        self.token = write.repo.set(Path(tempdir) / "repo")

    def tearDown(self) -> None:
        write.repo.reset(self.token)

    def test_write(self):
        rootf = write.UsdFile.get_anonymous()

        stage = write.fetch_stage(rootf)
        # fetching stage outside of AR context should resolve to same stage
        self.assertIs(stage, write.fetch_stage(rootf))

        repo_path = write.repo.get()
        resolver_ctx = Ar.DefaultResolverContext([str(repo_path)])
        with Ar.ResolverContextBinder(resolver_ctx):
            # inside an AR resolver context, a new layer and custom stage should end up
            # in that stage not resolving to the same as the one from write.fetch_stage
            layer_id = str(write.UsdFile.get_anonymous(item='non_cached'))
            Sdf.Layer.CreateNew(str(repo_path / layer_id))
            non_cache_stage = Usd.Stage.Open(layer_id)
            cached_stage = write.fetch_stage(layer_id)
            self.assertIsNot(non_cache_stage, cached_stage)
            # but after fetching once, subsequent fetches should persist
            self.assertIs(cached_stage, write.fetch_stage(layer_id))

            # creating a new layer + stage + adding it to the cache maually
            # should allow fetch_stage to retrieve it as well.
            custom_cached = str(write.UsdFile.get_default(item='cached'))
            layer = Sdf.Layer.CreateNew(str(repo_path / custom_cached))
            del layer
            custom_cached_layer = Sdf.Layer.FindOrOpen(custom_cached)
            custom_cached_stage = Usd.Stage.Open(custom_cached_layer)
            cache = UsdUtils.StageCache.Get()
            cache.Insert(custom_cached_stage)
            self.assertIs(custom_cached_stage, write.fetch_stage(custom_cached))

        with self.assertRaises(ValueError):
            write._first_matching(dict(missing='tokens'), stage.GetLayerStack())

        displayable_type = write.define_db_type(stage, "DisplayableName")
        # idempotent call should keep previously created prim
        self.assertEqual(displayable_type, write.define_db_type(stage, "DisplayableName"))

        transport_enum = write.define_db_type(stage, "Transport")
        person_type = write.define_db_type(stage, "Person", (displayable_type,))
        pc_type = write.define_db_type(stage, "PC", (person_type, transport_enum))
        npc_type = write.define_db_type(stage, "NPC", (person_type,))
        vampire_type = write.define_db_type(stage, "Vampire", (person_type,))
        place_type = write.define_db_type(stage, "Place", (displayable_type,))
        country_type = write.define_db_type(stage, "Country", (place_type,))
        city_type = write.define_db_type(stage, "City", (place_type,))

        # TODO: the following db relationships as well. This time we do this with an edit target
        db_layer = write._first_matching(write._DB_TOKENS, stage.GetLayerStack())

        ### DB edits  ###
        with write.edit_context(db_layer, stage):
            displayable_type.CreateAttribute("display_name", Sdf.ValueTypeNames.String)
            variant_set = transport_enum.GetVariantSets().AddVariantSet("Transport")
            for set_name in ("Feet", "Train", "HorseDrawnCarriage"):
                variant_set.AddVariant(set_name)

            # TODO: how to add constraints? Useful to catch errors before they hit the database
            #   https://github.com/edgedb/easy-edgedb/blob/master/chapter3/index.md#adding-constraints
            person_type.CreateAttribute('age', Sdf.ValueTypeNames.Int2)
            person_type.CreateRelationship('places_visited')
            person_type.CreateRelationship('lover')

            place_type.CreateAttribute("modern_name", Sdf.ValueTypeNames.String)
            for each in (city_type, country_type):
                # all places that end up in the database are "important places"
                Usd.ModelAPI(each).SetKind(Kind.Tokens.assembly)

        ### DB END ###
        cityRoot = stage.DefinePrim(f"/{city_type.GetName()}")

        write.create(stage, city_type, 'Munich')
        write.create(stage, city_type, 'Munich')

        with self.assertRaises(TypeError):
            write.edit_context(object(), stage)

        write.create(stage, city_type, 'Budapest', display_name='Buda-Pesth')
        bistritz = write.create(stage, city_type, 'Bistritz', display_name='Bistritz')
        london = write.create(stage, city_type, 'London')

        bistritz_layer = write._first_matching(
            dict(item='Bistritz', kingdom='assets'),
            (stack.layer for stack in bistritz.GetPrimStack())
        )

        with write.edit_context(bistritz, bistritz_layer, stage):
            bistritz.GetAttribute("modern_name").Set('Bistrița')

        write.create(stage, country_type, 'Hungary')
        romania = write.create(stage, country_type, 'Romania')

        jonathan = write.create(stage, pc_type, 'JonathanHarker',
                                display_name='Jonathan Harker')
        emil = write.create(stage, pc_type, "EmilSinclair",
                            display_name="Emil Sinclair")
        dracula = write.create(stage, vampire_type, 'CountDracula',
                               display_name='Count Dracula')
        mina = write.create(stage, npc_type, 'MinaMurray', display_name='Mina Murray')
        mina.GetRelationship("lover").AddTarget(jonathan.GetPath())

        for prim, places in {
            jonathan: cityRoot.GetChildren(),
            emil: cityRoot.GetChildren(),
            dracula: [romania],
            mina: [london],
        }.items():
            visitRel = prim.GetRelationship('places_visited')
            for place in places:
                visitRel.AddTarget(place.GetPath())

        # we could set "important_places" as a custom new property
        # but "important" prims are already provided by the USD model hierarchy.
        # let's try it and see if we can get away with it.
        goldenKrone = write.create(stage, place_type, 'GoldenKroneHotel',
                                   'Golden Krone Hotel')
        # also, let's make it a child of bistritz
        childPrim = stage.OverridePrim(
            bistritz.GetPath().AppendChild(goldenKrone.GetName()))
        childPrim.GetReferences().AddInternalReference(goldenKrone.GetPath())
        Usd.ModelAPI(childPrim).SetKind(
            Kind.Tokens.component)  # should be component or reference?

        emil_layer = write._first_matching(
            dict(item='EmilSinclair', kingdom='assets'),
            (stack.layer for stack in emil.GetPrimStack())
        )

        with write.edit_context(emil, emil_layer, stage):
            emil.GetVariantSet("Transport").SetVariantSelection("HorseDrawnCarriage")

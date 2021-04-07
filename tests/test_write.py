import logging
from pathlib import Path

from pxr import Usd, Sdf, Kind
import sys
# sys.path.append(r"B:\write\code\git\grill")
from grill import write

import datetime

import io
import csv
import unittest

from pxr import Usd, UsdGeom, Sdf
from PySide2 import QtWidgets, QtCore

from grill.views import description, sheets, create

from grill import write

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestViews(unittest.TestCase):
    def setUp(self):
        sphere = Usd.Stage.CreateInMemory()
        UsdGeom.Sphere.Define(sphere, "/sph")
        root_path = "/root"
        sphere_root = sphere.DefinePrim(root_path)
        sphere_root.CreateAttribute("greet", Sdf.ValueTypeNames.String).Set("hello")
        sphere.SetDefaultPrim(sphere_root)
        # print(sphere.GetRootLayer().ExportToString())

        capsule = Usd.Stage.CreateInMemory()
        UsdGeom.Capsule.Define(capsule, "/cap")
        root_path = "/root"
        capsule_root = capsule.DefinePrim(root_path)
        capsule_root.CreateAttribute("who", Sdf.ValueTypeNames.String).Set("world")
        capsule.SetDefaultPrim(capsule_root)
        # print(capsule.GetRootLayer().ExportToString())

        merge = Usd.Stage.CreateInMemory()
        for i in (capsule, sphere):
            merge.GetRootLayer().subLayerPaths.append(i.GetRootLayer().identifier)
        merge.SetDefaultPrim(merge.GetPrimAtPath(root_path))
        # print(merge.GetRootLayer().ExportToString())

        world = Usd.Stage.CreateInMemory()
        self.nested = world.DefinePrim("/nested/child")
        self.nested.GetReferences().AddReference(merge.GetRootLayer().identifier)
        # print(world.GetRootLayer().ExportToString())

        self.capsule = capsule
        self.sphere = sphere
        self.merge = merge
        self.world = world

    def test_layer_composition(self):
        dracula_root_id = write.UsdFile.get_default(code='dracula')

        import tempfile
        tmpf = tempfile.mkdtemp()
        token = write.repo.set(Path(tmpf) / "repo")

        logger.info(f"Repository path: {write.repo.get()}")
        logger.info(f"Stage identifier: {dracula_root_id}")

        stage = write.fetch_stage(dracula_root_id)
        tos = lambda: logger.info(stage.GetRootLayer().ExportToString())

        assert stage is write.fetch_stage(dracula_root_id)

        # types, types.
        # this types should ideally come directly from EdgeDB? without reaching the database first?

        # TODO: what should person and place be? Assemblies vs components.
        #   For now, only cities are considered assemblies.

        # all DB definitions go to the db types asset.
        displayable_type = write.define_db_type(stage, "DisplayableName")
        displayable_type = write.define_db_type(stage, "DisplayableName")

        with self.assertRaises(ValueError):
            write._first_matching(dict(missing='tokens'), stage.GetLayerStack())

        from pxr import Ar
        repo_path = write.repo.get()
        resolver_ctx = Ar.DefaultResolverContext([str(repo_path)])
        with Ar.ResolverContextBinder(resolver_ctx):
            layer_id = str(write.UsdFile.get_default(stream='temp_test'))
            Sdf.Layer.CreateNew(str(repo_path / layer_id))
            non_cache_stage = Usd.Stage.Open(layer_id)
            cached_stage = write.fetch_stage(layer_id)
            self.assertIsNot(non_cache_stage, cached_stage)
            self.assertIs(cached_stage, write.fetch_stage(layer_id))

            custom_cached = str(write.UsdFile.get_default(stream='temp_test', item='custom_cached'))
            layer = Sdf.Layer.CreateNew(str(repo_path / custom_cached))
            del layer

            custom_cached_layer = Sdf.Layer.FindOrOpen(custom_cached)
            custom_cached_stage = Usd.Stage.Open(custom_cached_layer)
            from pxr import UsdUtils
            cache = UsdUtils.StageCache.Get()
            cache.Insert(custom_cached_stage)
            self.assertIs(custom_cached_stage, write.fetch_stage(custom_cached))

        transport_enum = write.define_db_type(stage, "Transport")
        person_type = write.define_db_type(stage, "Person", (displayable_type,))
        pc_type = write.define_db_type(stage, "PC", (person_type, transport_enum))
        npc_type = write.define_db_type(stage, "NPC", (person_type,))
        vampire_type = write.define_db_type(stage, "Vampire", (person_type,))
        place_type = write.define_db_type(stage, "Place", (displayable_type,))
        country_type = write.define_db_type(stage, "Country", (place_type,))
        city_type = write.define_db_type(stage, "City", (place_type,))

        # TODO: the following db relationships as well. This time we do this with an edit target
        db_layer = write._first_matching(write.DB_TOKENS, stage.GetLayerStack())

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
        # TODO: LIMIT, how to? (Unsure if USD supports constraints on relationships.
        mina.GetRelationship("lover").AddTarget(jonathan.GetPath())
        """
        If you just want to return a single part of a type without the object structure, you can use . after the type name. For example, SELECT City.modern_name will give this output:

        {'Budapest', 'Bistrița'}
        """

        logger.info([p for p in Usd.PrimRange(cityRoot) if
                     p.GetAttribute("modern_name").IsValid() and p.GetAttribute(
                         "modern_name").Get()])

        """
        But we want to have Jonathan be connected to the cities he has traveled to. We'll change places_visited when we INSERT to places_visited := City:
        """

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

        # DELETING
        # try deleting the countries, this works as long as definitions are on the current edit target
        # note how relationships still exist (since they're authored paths)
        # country_root = stage.GetPrimAtPath(f"/{city_type.GetName()}")
        # stage.RemovePrim(country_root.GetPath())

        # 4 Questions / Unresolved
        # Time type, needed? Has "awake" property  driven by hour ( awake < 7am asleep < 19h awake

        for x in range(5):
            # for x in range(1_000):
            # atm creating 1_000 new cities (including each USD file) takes around 7 seconds.
            # could be faster.
            write.create(stage, city_type, f'NewCity{x}',
                         display_name=f"New City Hello {x}")

        stage.Save()

        # code that uses 'var'; var.get() returns 'new value'. Call at the end.
        write.repo.reset(token)

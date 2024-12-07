import os
import io
import csv
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pxr import Usd, UsdGeom, Sdf, UsdShade

from grill import cook, usd, names
from grill.views import description, sheets, create, _attributes, stats, _core, _graph, _qt
from grill.views._qt import QtWidgets, QtCore, QtGui

# 2024-02-03 - Python-3.12 & USD-23.11
# leaving the PySide6 import below freezes windows in Python-3.12. Importing it first when running tests "fixes" the freeze.
# from PySide6 import QtWebEngineWidgets
# alternatively, the following can be called to ensure shared contexts are set, which also prevent the freeze of the application:
QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
# but don't want to use that since that needs to be set prior to an application initialization (which grill can't control as in USDView, Maya, Houdini...)
# https://stackoverflow.com/questions/56159475/qt-webengine-seems-to-be-initialized

# There's about ~0.4s overhead from creating a QApplication for the tests.

# 2024-11-09 - Python-3.13 & USD-24.11
# python -m unittest --durations 0 test_views
# Slowest test durations
# ----------------------------------------------------------------------
# 0.354s     test_spreadsheet_editor (tests.test_views.TestViews.test_spreadsheet_editor)
# 0.288s     test_connection_view (tests.test_views.TestViews.test_connection_view)
# 0.237s     test_taxonomy_editor (tests.test_views.TestViews.test_taxonomy_editor)
# 0.236s     test_content_browser (tests.test_views.TestViews.test_content_browser)
# 0.217s     test_scenegraph_composition (tests.test_views.TestViews.test_scenegraph_composition)
# 0.180s     test_dot_call (tests.test_views.TestViews.test_dot_call)
# 0.051s     test_prim_filter_data (tests.test_views.TestViews.test_prim_filter_data)
# 0.050s     test_create_assets (tests.test_views.TestViews.test_create_assets)
# 0.038s     test_stats (tests.test_views.TestViews.test_stats)
# 0.037s     test_graph_views (tests.test_views.TestViews.test_graph_views)
# 0.032s     test_prim_composition (tests.test_views.TestViews.test_prim_composition)
# 0.029s     test_display_color_editor (tests.test_views.TestViews.test_display_color_editor)
# 0.004s     test_pan (tests.test_views.TestViews.test_pan)
# 0.001s     test_horizontal_scroll (tests.test_views.TestViews.test_horizontal_scroll)
#
# (durations < 0.001s were hidden; use -v to show these durations)
# ----------------------------------------------------------------------
# Ran 18 tests in 2.141s


class TestPrivate(unittest.TestCase):
    def test_common_paths(self):
        input_paths = [
            Sdf.Path("/world/hi"),
            Sdf.Path.absoluteRootPath,
            Sdf.Path("/hola/hello/new1"),
            Sdf.Path("/world/child/nested"),
            Sdf.Path("/invalid/1"),
            Sdf.Path("/hola/hello/new2"),
            Sdf.Path("/hola/hello/new2/twochild"),
            Sdf.Path("/hola/hello/new2/twochild/more"),
            Sdf.Path("/hola/hello/new2/a"),
            Sdf.Path("/hola/hello/new2/zzzzzzzzzzzzzzzzzzz"),
            Sdf.Path("/hola/hello/new3"),
            Sdf.Path("/hola/hello/n9/nested/one"),
            Sdf.Path("/hola/hello/new01/nested/deep"),
            Sdf.Path("/hola/hello/n9/nested/two"),
            Sdf.Path("/hola/bye/child"),
            Sdf.Path("/deep/nested/unique/path"),
            Sdf.Path("/alone"),
        ]
        actual = usd.common_paths(input_paths)
        expected = [
            Sdf.Path('/alone'),
            Sdf.Path('/deep/nested/unique/path'),
            Sdf.Path('/hola/bye/child'),
            Sdf.Path('/hola/hello/n9/nested/one'),
            Sdf.Path('/hola/hello/n9/nested/two'),
            Sdf.Path('/hola/hello/new01/nested/deep'),
            Sdf.Path('/hola/hello/new1'),
            Sdf.Path('/hola/hello/new2'),
            Sdf.Path('/hola/hello/new3'),
            Sdf.Path('/world/child/nested'),
            Sdf.Path('/world/hi'),
        ]
        self.assertEqual(actual, expected)

    def test_core(self):
        _core._ensure_dot()


_test_bed = Path(__file__).parent / "mini_test_bed" / "main-world-test.1.usda"


class TestViews(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        ...
        # return

        # self.grill_world = Usd.Stage.Open(str(_test_bed))

        # root_path = "/root"
        #
        # sphere_stage = Usd.Stage.CreateInMemory()
        # UsdGeom.Sphere.Define(sphere_stage, "/sph")
        # sphere_root = sphere_stage.DefinePrim(root_path)
        # sphere_root.CreateAttribute("greet", Sdf.ValueTypeNames.String).Set("hello")
        # sphere_stage.SetDefaultPrim(sphere_root)
        #
        # capsule_stage = Usd.Stage.CreateInMemory()
        # UsdGeom.Capsule.Define(capsule_stage, "/cap")
        # capsule_root = capsule_stage.DefinePrim(root_path)
        # capsule_root.CreateAttribute("who", Sdf.ValueTypeNames.String).Set("world")
        # capsule_stage.SetDefaultPrim(capsule_root)
        #
        # merged_stage = Usd.Stage.CreateInMemory()
        # with Sdf.ChangeBlock():
        #     for i in (capsule_stage, sphere_stage):
        #         merged_stage.GetRootLayer().subLayerPaths.append(i.GetRootLayer().identifier)
        # merged_stage.SetDefaultPrim(merged_stage.GetPrimAtPath(root_path))
        #
        # world = Usd.Stage.CreateInMemory()
        # self.nested = world.DefinePrim("/nested/child")
        # self.sibling = world.DefinePrim("/nested/sibling")
        # self.nested.GetReferences().AddReference(merged_stage.GetRootLayer().identifier)
        #
        # self.capsule = capsule_stage
        # self.sphere = sphere_stage
        # self.merge = merged_stage
        # self.world = world
        #
        self._tmpf = tempfile.mkdtemp()
        self._token = cook.Repository.set(cook.Path(self._tmpf) / "repo")
        # self.grill_root_asset = names.UsdAsset.get_anonymous()
        # self.grill_world = gworld = cook.fetch_stage(self.grill_root_asset.name)
        # self.taxon_a = cook.define_taxon(gworld, "a")
        # self.taxon_b = cook.define_taxon(gworld, "b", references=(self.taxon_a,))
        # self.unit_b = cook.create_unit(self.taxon_b, "GenericAgent")

    def tearDown(self) -> None:
        cook.Repository.reset(self._token)
        # Reset all members to USD objects to ensure the used layers are cleared
        # (otherwise in Windows this can cause failure to remove the temporary files)
        # self.grill_world = None
        shutil.rmtree(self._tmpf)

    @classmethod
    def tearDownClass(cls):
        cls._app.quit()

    def test_connection_view(self):
        # https://openusd.org/release/tut_simple_shading.html
        stage = Usd.Stage.CreateInMemory()
        material = UsdShade.Material.Define(stage, '/TexModel/boardMat')
        pbrShader = UsdShade.Shader.Define(stage, '/TexModel/boardMat/PBRShader')
        pbrShader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.4)
        material.CreateSurfaceOutput().ConnectToSource(pbrShader.ConnectableAPI(), "surface")
        # Ensure cycles don't cause recursion
        cycle_input = pbrShader.CreateInput("cycle_in", Sdf.ValueTypeNames.Float)
        cycle_output = pbrShader.CreateOutput("cycle_out", Sdf.ValueTypeNames.Float)
        cycle_input.ConnectToSource(cycle_output)
        description._graph_from_connections(material)
        viewer = description._ConnectableAPIViewer()
        # GraphView capabilities are tested elsewhere, so mock 'view' here.
        viewer._graph_view.view = lambda indices: None
        viewer.setPrim(material)
        viewer.setPrim(None)

    def test_scenegraph_composition(self):
        """Confirm that bidirectionality between layer stacks completes.

        Bidirectionality in the composition graph is achieved by:
            - parent_stage -> child_stage via a reference, payload arcs
            - child_stage -> parent_stage via a inherits, specializes arcs
        """
        stage = Usd.Stage.Open(str(_test_bed))

        widget = description.LayerStackComposition()
        # GraphView capabilities are tested elsewhere, so mock 'view' here.
        widget._graph_view.view = lambda indices: None
        widget.setStage(stage)

        widget._layers.table.selectAll()
        expectedAffectedPrims = 306
        actualListedPrims = widget._prims.model.rowCount()
        self.assertEqual(expectedAffectedPrims, actualListedPrims)

        widget._graph_precise_source_ports.setChecked(True)
        widget._update_graph_from_graph_info(widget._computed_graph_info)

        widget._has_specs.setChecked(True)
        widget._graph_edge_include[description.Pcp.ArcTypeReference].setChecked(False)
        widget.setPrimPaths({"/Catalogue/Model/Elements/Apartment"})
        widget.setStage(stage)

        widget._layers.table.selectAll()
        self.assertEqual(5, widget._layers.model.rowCount())
        self.assertEqual(1, widget._prims.model.rowCount())
        # add_dll_directory only on Windows
        os.add_dll_directory = lambda path: print(f"Added {path}") if not hasattr(os, "add_dll_directory") else os.add_dll_directory

        _core._which.cache_clear()
        with mock.patch("grill.views.description._which") as patch:  # simulate dot is not in the environment
            patch.return_value = None
            widget._graph_view.view([0,1])

        _core._which.cache_clear()
        with mock.patch("grill.views.description.nx.nx_agraph.write_dot") as patch:  # simulate pygraphviz is not installed
            patch.side_effect = ImportError
            widget._graph_view.view([0])

        widget.deleteLater()

    def test_prim_composition(self):
        temp = Usd.Stage.CreateInMemory()
        ancestor = temp.DefinePrim("/a")
        prim = temp.DefinePrim("/b")
        prim.GetReferences().AddReference(Sdf.Reference(primPath=ancestor.GetPath()))
        widget = description.PrimComposition()
        # DotView capabilities are tested elsewhere, so mock 'setDotPath' here.
        widget._dot_view.setDotPath = lambda fp: None
        widget.setPrim(prim)

        # cheap. prim is affected by 2 layers
        # single child for this prim.
        self.assertTrue(widget.composition_tree._model.invisibleRootItem().hasChildren())

        widget._complete_target_layerstack.setChecked(True)
        widget.setPrim(prim)
        self.assertTrue(widget.composition_tree._model.invisibleRootItem().hasChildren())

        with mock.patch("grill.views.description.QtWidgets.QApplication.keyboardModifiers") as patch:
            patch.return_value = QtCore.Qt.ShiftModifier
            root_idx = widget.composition_tree._model.index(0, 0)
            widget.composition_tree.expanded.emit(root_idx)
            widget.composition_tree.collapsed.emit(root_idx)

        widget.setPrim(None)
        self.assertFalse(widget.composition_tree._model.invisibleRootItem().hasChildren())

        widget.clear()

    def test_create_assets(self):
        stage = cook.fetch_stage(cook.UsdAsset.get_anonymous())
        for each in range(1, 6):
            cook.define_taxon(stage, f"Option{each}")

        widget = create.CreateAssets()
        widget.setStage(stage)

        widget._amount.setValue(3)  # TODO: create 10 assets, clear tmp directory

        data = (
            ['Option1', 'asset01', 'Asset 01', 'Description 01'],
            ['Option2', 'asset02', 'Asset 02', 'Description 02'],
            ['Option2', '',        'Asset 03', 'Description 03'],
        )

        QtWidgets.QApplication.instance().clipboard().setText('')
        widget.sheet._pasteClipboard()

        stream = io.StringIO()
        csv.writer(stream, delimiter=csv.excel_tab.delimiter).writerows(data)
        QtWidgets.QApplication.instance().clipboard().setText(stream.getvalue())

        widget.sheet.table.selectAll()
        widget.sheet._pasteClipboard()
        widget._create()
        taxon_editor = widget.sheet._columns[0].editor(widget, None, None)
        self.assertIsInstance(taxon_editor, QtWidgets.QComboBox)
        widget._apply()

    def test_taxonomy_editor(self):
        class MiniAsset(names.UsdAsset):
            drop = ('code', 'media', 'area', 'stream', 'step', 'variant', 'part')
            DEFAULT_SUFFIX = "usda"

        cook.UsdAsset = MiniAsset
        stage = Usd.Stage.Open(str(_test_bed))
        # stage = cook.fetch_stage(cook.UsdAsset.get_anonymous())
        existing = list(cook.itaxa(stage))
        # existing = [cook.define_taxon(stage, f"Option{each}") for each in range(1, 6)]
        widget = create.TaxonomyEditor()
        # GraphView capabilities are tested elsewhere, so mock 'view' here.
        widget._graph_view.view = lambda indices: None
        # if isinstance(widget._graph_view, _graph.GraphView):
        #     with self.assertRaisesRegex(LookupError, "Could not find sender"):
        #         invalid_uril = QtCore.QUrl(f"{widget._graph_view.url_id_prefix}not_a_digit")
        #         widget._graph_view._graph_url_changed(invalid_uril)
        # else:
        #     with self.assertRaisesRegex(RuntimeError, "'graph' attribute not set yet"):
        #         invalid_uril = QtCore.QUrl(f"{widget._graph_view.url_id_prefix}not_a_digit")
        #         widget._graph_view._graph_url_changed(invalid_uril)
        widget.setStage(stage)

        widget._amount.setValue(3)  # TODO: create 10 assets, clear tmp directory

        valid_data = (
            ['NewType1', existing[0].GetName(), 'Id1', ],
            ['NewType2', '', 'Id2', ],
        )
        data = valid_data + (
            ['',         existing[0].GetName(), 'Id3', ],
        )

        QtWidgets.QApplication.instance().clipboard().setText('')
        widget.sheet._pasteClipboard()

        stream = io.StringIO()
        csv.writer(stream, delimiter=csv.excel_tab.delimiter).writerows(data)
        QtWidgets.QApplication.instance().clipboard().setText(stream.getvalue())

        widget.sheet.table.selectAll()
        widget.sheet._pasteClipboard()
        widget._create()

        for name, __, __ in valid_data:
            created = stage.GetPrimAtPath(cook._TAXONOMY_ROOT_PATH).GetPrimAtPath(name)
            self.assertTrue(created.IsValid())

        sheet_model = widget.sheet.model
        index = sheet_model.index(0, 1)
        editor = widget.sheet._columns[1].editor(None, None, index)
        self.assertIsInstance(editor, QtWidgets.QDialog)
        widget.sheet._columns[1].setter(editor, sheet_model, index)
        editor._options.selectAll()
        menu = editor._create_context_menu()
        menu.actions()[0].trigger()

        # after creation, set stage again to test existing column
        widget._apply()
        widget._existing.table.selectAll()
        selected_items = widget._existing.table.selectedIndexes()
        self.assertEqual(len(selected_items), len(valid_data) + len(existing))

        # if isinstance(widget._graph_view, _graph.GraphView):
        #     sender = next(iter(widget._graph_view._nodes_map.values()), None)
        #     self.assertIsNotNone(sender, msg=f"Expected sender to be an actual object of type {_graph._Node}. Got None, check pygraphviz / pydot requirements")
        #     sender.linkActivated.emit("")
        # else:
        #     valid_url = QtCore.QUrl(f"{widget._graph_view.url_id_prefix}{existing[-1].GetName()}")
        #     widget._graph_view._graph_url_changed(valid_url)
        #     # Nitpick, wait for dot 2 svg conversions to finish
        #     # This does not crash the program but an exception is logged when race
        #     # conditions apply (e.g. the object is deleted before the runnable completes).
        #     # This logged exception comes in the form of:
        #     # RuntimeError: Internal C++ object (_Dot2SvgSignals) already deleted.
        #     # Solution seems to be to block and wait for all runnables to complete.
        #     widget._graph_view._threadpool.waitForDone(10_000)

    def test_spreadsheet_editor(self):
        # return
        widget = sheets.SpreadsheetEditor()
        widget._model_hierarchy.setChecked(False)  # default is True
        stage = Usd.Stage.Open(str(_test_bed))
        stage.OverridePrim("/child_orphaned")
        # self.nested.SetInstanceable(True)
        widget._orphaned.setChecked(True)
        # assert self.nested.IsInstance()
        widget.setStage(stage)
        self.assertEqual(stage, widget.stage)
        widget.table.scrollContentsBy(10, 10)

        widget.table.selectAll()
        # expected_rows = {0, 1, 2, 3}  # 3 prims from path: /nested, /nested/child, /nested/sibling, /child_orphaned
        # expected_rows = set(range(len(list(Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate))))))
        # visible_rows = ({i.row() for i in widget.table.selectedIndexes()})
        # self.assertEqual(expected_rows, visible_rows)

        widget.table.clearSelection()
        widget._column_options[0]._line_filter.setText("hade")
        widget._column_options[0]._updateMask()
        widget.table.resizeColumnToContents(0)

        widget.table.selectAll()
        expected_rows = {0, 1, 2}  # 1 prim from filtered name: /Catalogue/Shade /Catalogue/Shade/Color /Catalogue/Shade/Color/ModelDefault
        # for each in widget.table.selectedIndexes():
        #     print(each.data())
        visible_rows = ({i.row() for i in widget.table.selectedIndexes()})
        self.assertEqual(expected_rows, visible_rows)

        widget._copySelection()
        clip = QtWidgets.QApplication.instance().clipboard().text()
        data = tuple(csv.reader(io.StringIO(clip), delimiter=csv.excel_tab.delimiter))
        expected_data = (
            ['/Catalogue/Shade', 'Shade', '', '', '', 'False', '', 'False'],
            ['/Catalogue/Shade/Color', 'Color', '', '', '', 'False', '', 'False'],
            ['/Catalogue/Shade/Color/ModelDefault', 'ModelDefault', 'ModelDefault', '', '', 'False', '', 'False'],
        )
        self.assertEqual(data, expected_data)

        widget.table.clearSelection()

        widget._model_hierarchy.click()  # enables model hierarchy, which we don't have any
        widget.table.selectAll()
        expected_rows = {0, 1}
        visible_rows = ({i.row() for i in widget.table.selectedIndexes()})
        self.assertEqual(expected_rows, visible_rows)

        widget.table.clearSelection()

        widget._lock_all.click()
        widget._conformLockSwitch()
        widget._vis_all.click()
        widget._conformVisibilitySwitch()

        widget._column_options[0]._line_filter.setText("")
        widget._model_hierarchy.click()  # disables model hierarchy, which we don't have any
        widget.table.selectAll()
        _log = lambda *args: print(args)
        with mock.patch(f"{QtWidgets.__name__}.QMessageBox.warning", new=_log):
            widget._pasteClipboard()

        widget.model._prune_children = {Sdf.Path("/pruned")}
        # gworld = self.grill_world

        # with cook.unit_context(self.unit_b):
        #     child_agent = gworld.DefinePrim(self.unit_b.GetPath().AppendChild("child"))
        #     child_attr = child_agent.CreateAttribute("agent_greet", Sdf.ValueTypeNames.String, custom=False)
        #     child_attr.Set("aloha")
        # agent_id = cook.unit_asset(self.unit_b)
        # for i in range(3):
        #     agent = gworld.DefinePrim(f"/Instanced/Agent{i}")
        #     agent.GetReferences().AddReference(agent_id.identifier)
        #     agent.SetInstanceable(True)
        # agent.SetActive(False)
        # gworld.OverridePrim("/non/existing/prim")
        # gworld.DefinePrim("/pruned/prim")
        # inactive = gworld.DefinePrim("/another_inactive")
        # inactive.SetActive(False)
        # gworld.GetRootLayer().subLayerPaths.append(self.world.GetRootLayer().identifier)
        widget._column_options[0]._line_filter.setText("")
        widget.table.clearSelection()
        widget._active.setChecked(False)
        widget._classes.setChecked(True)
        widget._filters_logical_op.setCurrentIndex(1)
        widget.stage = stage
        widget.table.selectAll()
        expected_colors = {str(each.value): each for each in sheets._PrimTextColor}  # colors are not hashable
        expected_fonts = {each.weight() for each in (  # font not hashable in PySide2
            sheets._prim_font(),
            sheets._prim_font(abstract=True),
            sheets._prim_font(abstract=True, orphaned=True),
            sheets._prim_font(orphaned=True),
        )}
        self.assertEqual(len(expected_fonts), 3)  # three weights: Light, ExtraLight, Normal
        collected_fonts = set()
        for each in widget.table.selectionModel().selectedIndexes():
            color_key = str(each.data(role=QtCore.Qt.ForegroundRole))
            font = each.data(role=QtCore.Qt.FontRole)
            font_key = font.weight()
            expected_colors.pop(color_key, None)
            collected_fonts.add(font_key)

        # self.assertEqual(expected_colors, dict())
        self.assertEqual(expected_fonts, collected_fonts)

    def test_prim_filter_data(self):
        # return
        stage = cook.fetch_stage(cook.UsdAsset.get_anonymous())
        person = cook.define_taxon(stage, "Person")
        agent = cook.define_taxon(stage, "Agent", references=(person,))
        generic = cook.create_unit(agent, "GenericAgent")
        with cook.unit_context(generic):
            stage.DefinePrim(generic.GetPath().AppendChild("ChildPrim"))
        generic_asset = cook.unit_asset(generic)
        for each in range(10):
            path = Sdf.Path.absoluteRootPath.AppendChild(f"Instance{each}")
            instance = stage.DefinePrim(path)
            instance.SetInstanceable(True)
            instance.GetPayloads().AddPayload(generic_asset.identifier)
        instance.SetActive(False)
        instance.Unload()
        over = stage.OverridePrim("/Orphaned")
        widget = sheets.SpreadsheetEditor()
        for stage_value in (stage, None):
            widget.setStage(stage_value)
            for each in range(2):
                widget._filters_logical_op.setCurrentIndex(each)
                widget._model_hierarchy.click()  # default is True
                widget._orphaned.click()
                widget._classes.click()
                widget._defined.click()
                widget._active.click()
                widget._inactive.click()
        widget.model._root_paths = {over.GetPath(), over.GetPath()}
        widget.model._prune_children = {over.GetPath()}
        widget.setStage(stage)

    def test_dot_call(self):
        # return
        """Test execution of function by mocking dot with python call"""
        with mock.patch("grill.views.description._which") as patch:
            patch.return_value = 'python'
            error, targetpath = _graph._dot_2_svg('nonexisting_path')
            # an error would be reported back
            self.assertIsNotNone(error)

    def test_content_browser(self):
        # return
        # class MiniAsset(names.UsdAsset):
        #     drop = ('code', 'media', 'area', 'stream', 'step', 'variant', 'part')
        #     DEFAULT_SUFFIX = "usda"
        #
        # cook.UsdAsset = MiniAsset
        stage = stage = Usd.Stage.Open(str(_test_bed))
        # stage = self.grill_world
        # taxon = self.taxon_a
        # parent, child = cook.create_many(taxon, ['A', 'B'])
        # for path, value in (
        #         ("", (2, 15, 6)),
        #         ("Deeper/Nested/Golden1", (-4, 5, 1)),
        #         # ("Deeper/Nested/Golden2", (-4, -10, 1)),
        #         # ("Deeper/Nested/Golden3", (0, 10, -2)),
        # ):
        #     spawned = UsdGeom.Xform(cook.spawn_unit(parent, child, path))
        #     spawned.AddTranslateOp().Set(value=value)
        # variant_set_name = "testset"
        # variant_name = "testvar"
        # vset = child.GetVariantSet(variant_set_name)
        # vset.AddVariant(variant_name)
        # vset.SetVariantSelection(variant_name)
        # with vset.GetVariantEditContext():
        #     stage.DefinePrim(child.GetPath().AppendChild("in_variant"))
        # path_with_variant = child.GetPath().AppendVariantSelection(variant_set_name, variant_name)

        path_with_variant = Sdf.Path("/Catalogue/Model/Elements/Apartment")
        spawned_path = Sdf.Path("/Catalogue/Model/Buildings/Multi_Story_Building/Windows/Apartment")
        layers = stage.GetLayerStack()
        args = stage.GetLayerStack(), None, stage.GetPathResolverContext(), (Sdf.Path("/"), spawned_path, path_with_variant)
        anchor = layers[0]

        def _log(*args):
            print(args)

        _core_run = _core._run

        def _fake_run(run_args: list):
            return "", Sdf.Layer.FindOrOpen(run_args[-1]).ExportToString()
        # return
        # sdffilter still not coming via pypi, so patch for now
        with mock.patch("grill.views.description._core._run", new=_fake_run):
            dialog = description._start_content_browser(*args)
            browser: description._PseudoUSDBrowser = dialog.findChild(description._PseudoUSDBrowser)
            assert browser._browsers_by_layer.values()
            first_browser_widget, = browser._browsers_by_layer.values()
            first_browser_widget._format_options.setCurrentIndex(0)  # pseudoLayer (through sdffilter)
            first_browser_widget._format_options.setCurrentIndex(1)  # outline (through sdffilter)
            first_browser_widget._format_options.setCurrentIndex(2)  # usdtree (through usdtree)
            first_browser_widget._format_options.setCurrentIndex(0)

            browser_tab: description._PseudoUSDTabBrowser = first_browser_widget.findChild(description._PseudoUSDTabBrowser)
            browser._on_identifier_requested(anchor, layers[1].identifier)
            with mock.patch(f"{QtWidgets.__name__}.QMessageBox.warning", new=_log):
                browser._on_identifier_requested(anchor, "/missing/file.usd")
                _, empty_png = tempfile.mkstemp(suffix=".png")
                browser._on_identifier_requested(anchor, empty_png)
                _, empty_usd = tempfile.mkstemp(suffix=".usda")
                browser._on_identifier_requested(anchor, empty_usd)

            menu = browser._menu_for_tab(0)
            self.assertTrue(bool(menu.actions()))

            position = QtCore.QPoint(10, 10)
            pixelDelta = QtCore.QPoint(0, 0)
            angleDelta_zoomIn = QtCore.QPoint(0, 120)
            buttons = QtCore.Qt.NoButton
            modifiers = QtCore.Qt.ControlModifier
            phase = QtCore.Qt.NoScrollPhase
            inverted = False
            # return
            # ZOOM IN
            event = QtGui.QWheelEvent(position, position, pixelDelta, angleDelta_zoomIn, buttons, modifiers, phase, inverted)
            browser_tab.wheelEvent(event)

            # Assert that the scale has changed according to the zoom logic
            angleDelta_zoomOut = QtCore.QPoint(-120, 0)

            # ZOOM OUT
            event = QtGui.QWheelEvent(position, position, pixelDelta, angleDelta_zoomOut, buttons, modifiers, phase, inverted)
            browser_tab.wheelEvent(event)
            # return
            browser._close_many(range(len(browser._tab_layer_by_idx)))
            for child in dialog.findChildren(description._PseudoUSDBrowser):
                child._resolved_layers.clear()

            # create a temporary file loadable by our image tab
            image = QtGui.QImage(QtCore.QSize(1, 1), QtGui.QImage.Format_RGB888)
            image.fill(QtGui.QColor(255, 0, 0))
            targetpath = str(_test_bed.with_suffix(".jpg"))
            image.save(targetpath, "JPG")
            browser._on_identifier_requested(anchor, targetpath)
            # return
            invalid_crate_layer = Sdf.Layer.CreateAnonymous()
            invalid_crate_layer.ImportFromString(
                # Not valid in USD-24.05: https://github.com/PixarAnimationStudios/OpenUSD/blob/59992d2178afcebd89273759f2bddfe730e59aa8/pxr/usd/sdf/testenv/testSdfParsing.testenv/baseline/127_varyingRelationship.sdf#L9
                """#sdf 1.4.32
                def GprimSphere "Sphere"
                {
                    delete varying rel constraintTarget = </Pivot3>
                    add varying rel constraintTarget = [
                        </Pivot3>,
                        </Pivot2>,
                    ]
                    reorder varying rel constraintTarget = [
                        </Pivot2>,
                        </Pivot>,
                    ]
                    varying rel constraintTarget.default = </Pivot>    
                }
                """
            )
            description._start_content_browser([invalid_crate_layer], None, stage.GetPathResolverContext(), ())

        with mock.patch("grill.views.description._which") as patch:
            patch.return_value = None
            with self.assertRaisesRegex(ValueError, "Expected arguments to contain an executable value on the first index"):
                description._start_content_browser(*args)

        error, result = _core._run(["python", 42])
        self.assertTrue(error.startswith('expected str'))
        self.assertEqual(result, "")

    def test_display_color_editor(self):
        # return
        stage = cook.fetch_stage(cook.UsdAsset.get_anonymous())
        sphere = UsdGeom.Sphere.Define(stage, "/volume")
        color_var = sphere.GetDisplayColorPrimvar()
        editor = _attributes._DisplayColorEditor(color_var)

        with mock.patch("grill.views._attributes.QtWidgets.QColorDialog.getColor", new=lambda *_, **__: QtGui.QColor(255, 255, 0)):
            editor._color_launchers["Color"][0].click()

        color_var.SetInterpolation(UsdGeom.Tokens.vertex)
        editor = _attributes._DisplayColorEditor(color_var)
        editor._update_value()
        editor._random.click()

        xform = stage.DefinePrim("/x")
        primvar = UsdGeom.Gprim(xform.GetPrim()).CreateDisplayColorPrimvar()
        editor = _attributes._DisplayColorEditor(primvar)
        with self.assertRaises(TypeError):  # atm some gprim types are not supported
            editor._update_value()

        editor = _attributes._DisplayColorEditor(UsdGeom.Primvar())
        self.assertEqual(len(editor._value), 1)

    def test_stats(self):
        # return
        empty = stats.StageStats()
        self.assertEqual(empty._usd_tree.topLevelItemCount(), 0)

        stage = Usd.Stage.Open(str(_test_bed))
        widget = stats.StageStats(stage=stage)
        self.assertGreater(widget._usd_tree.topLevelItemCount(), 1)
        current = _qt.QtCharts
        del _qt.QtCharts
        stats.StageStats(stage=stage)
        _qt.QtCharts = current

    def test_graph_views(self):
        nodes_info = {
            1: dict(
                label="{<0>x:y:z|<1>z}",
                style="rounded,filled",
                shape="record",
            ),
            2: dict(
                label="{<0>a|<1>b}",
                style='rounded,filled',
                shape="record",
            ),
        }
        edges_info = (
            (1, 1, dict(color='sienna:crimson:orange')),
            (1, 2, dict(color='crimson')),
            (2, 1, dict(color='green')),
        )

        graph = _graph.nx.MultiDiGraph()
        graph.add_nodes_from(nodes_info.items())
        graph.add_edges_from(edges_info)
        graph.graph['graph'] = {'rankdir': 'LR'}
        graph.graph['edge'] = {"color": 'crimson'}
        outline_color = "#4682B4"  # 'steelblue'
        background_color = "#F0FFFF"  # 'azure'
        table_row = '<tr><td port="{port}" border="0" bgcolor="{color}" style="ROUNDED">{text}</td></tr>'

        connection_nodes = dict(
            ancestor=dict(
                plugs={
                    '': 0,
                    'cycle_in': 1,
                    'roughness': 2,
                    'cycle_out': 3,
                    'surface': 4
                },
                active_plugs={'cycle_in', 'cycle_out', 'roughness', 'surface'},
                shape='none',
                connections=dict(
                    surface=[('successor', 'surface')],
                    cycle_out=[('ancestor', 'cycle_in')],
                )
            ),
            successor=dict(
                plugs={'': 0, 'surface': 1},
                active_plugs={'surface'},
                shape='none',
                connections=dict(),
            )
        )
        connection_edges = []

        def _add_edges(src_node, src_name, tgt_node, tgt_name):
            tooltip = f"{src_node}.{src_name} -> {tgt_node}.{tgt_name}"
            connection_edges.append((src_node, tgt_node, {"tailport": src_name, "headport": tgt_name, "tooltip": tooltip}))

        for node, data in connection_nodes.items():
            label = f'<<table border="1" cellspacing="2" style="ROUNDED" bgcolor="{background_color}" color="{outline_color}">'
            label += table_row.format(port="", color="white",
                                      text=f'<font color="{outline_color}"><b>{node}</b></font>')
            # for index, plug in enumerate(data['plugs'], start=1):  # we start at 1 because index 0 is the node itself
            for plug, index in data['plugs'].items():  # we start at 1 because index 0 is the node itself
                if not plug:
                    continue
                plug_name = plug
                sources = data['connections'].get(plug, [])  # (valid, invalid): we care only about valid sources (index 0)
                color = r"#F08080" if sources else background_color
                # color = plug_colors[type(plug)] if isinstance(plug, UsdShade.Output) or sources else background_color
                label += table_row.format(port=plug_name, color=color, text=f'<font color="#242828">{plug_name}</font>')
                for source_node, source_plug in sources:
                    _add_edges(source_node, source_plug, node, plug_name)

            label += '</table>>'
            data['label'] = label

        graph.add_nodes_from(connection_nodes.items())
        graph.add_edges_from(connection_edges)

        widget = QtWidgets.QFrame()
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        def _use_test_dot(subgraph, fp):
            shutil.copy(Path(__file__).parent / "test_data/_mini_graph.dot", fp)

        def _use_test_svg(self, filepath):
            return self._on_dot_result(str(Path(__file__).parent / "test_data/_mini_graph.svg"))

        def _test_positions(graph, prog):
            return {
                1: (40.0, 18.5),
                2: (156.38, 18.5),
                'ancestor': (156.38, 134.5),
                'successor': (40.0, 101.5)
            }

        with (
            mock.patch(f"grill.views._graph.nx.nx_pydot.write_dot", new=_use_test_dot),
            mock.patch(f"grill.views._graph._DotViewer.setDotPath", new=_use_test_svg),
            mock.patch(f"grill.views._graph.drawing.nx_pydot.graphviz_layout", new=_test_positions),
        ):
            for cls in _graph.GraphView, _graph._GraphSVGViewer:
                for pixmap_enabled in ((True, False) if cls == _graph._GraphSVGViewer else (False,)):
                    _graph._USE_SVG_VIEWPORT = pixmap_enabled
                    child = cls(parent=widget)
                    if cls == _graph._GraphSVGViewer:
                        child._graph_view.load = lambda fp: None
                    child._graph = graph
                    child.view(graph.nodes)
                    child.setMinimumWidth(150)
                    splitter.addWidget(child)

                    if isinstance(child, _graph.GraphView):
                        for item in child.scene().items():
                            item.boundingRect()  # trigger bounding rect logic
                            if isinstance(item, _graph._Edge):
                                cycle_collected = True
                            if isinstance(item, _graph._Node):
                                nodes_hovered_checked = True

                                # Test hover with no modifiers
                                event = QtWidgets.QGraphicsSceneHoverEvent(QtCore.QEvent.GraphicsSceneHoverMove)
                                center = item.sceneBoundingRect().center()
                                event.setScenePos(center)
                                item.hoverEnterEvent(event)
                                self.assertEqual(item.cursor().shape(), QtGui.Qt.ArrowCursor)
                                self.assertEqual(item.textInteractionFlags(), item._default_text_interaction)
                                item.hoverLeaveEvent(event)

                                # Test hover with Ctrl modifier
                                event = QtWidgets.QGraphicsSceneHoverEvent(QtCore.QEvent.GraphicsSceneHoverMove)
                                event.setScenePos(center)
                                event.setModifiers(QtCore.Qt.ControlModifier)
                                item.hoverEnterEvent(event)
                                self.assertEqual(item.cursor().shape(), QtGui.Qt.PointingHandCursor)
                                item.hoverLeaveEvent(event)

                                # Test hover with Alt modifier
                                event = QtWidgets.QGraphicsSceneHoverEvent(QtCore.QEvent.GraphicsSceneHoverMove)
                                event.setScenePos(item.sceneBoundingRect().center())
                                event.setModifiers(QtCore.Qt.AltModifier)
                                item.hoverEnterEvent(event)
                                self.assertEqual(item.cursor().shape(), QtGui.Qt.ClosedHandCursor)
                                self.assertEqual(item.textInteractionFlags(), QtCore.Qt.NoTextInteraction)
                                item.hoverLeaveEvent(event)

                        self.assertTrue(cycle_collected)
                        self.assertTrue(nodes_hovered_checked)

    def test_zoom(self):
        return

        """Zoom is triggered by ctrl + mouse wheel"""
        view = _graph._GraphicsViewport()

        initial_scale = view.transform().m11()

        position = QtCore.QPoint(10, 10)
        pixelDelta = QtCore.QPoint(0, 0)
        angleDelta_zoomIn = QtCore.QPoint(0, 120)
        buttons = QtCore.Qt.NoButton
        modifiers = QtCore.Qt.ControlModifier
        phase = QtCore.Qt.NoScrollPhase
        inverted = False

        # ZOOM IN
        event = QtGui.QWheelEvent(position, position, pixelDelta, angleDelta_zoomIn, buttons, modifiers, phase, inverted)
        view.wheelEvent(event)

        zoomed_in_scale = view.transform().m11()

        # Assert that the scale has changed according to the zoom logic
        self.assertGreater(zoomed_in_scale, initial_scale)
        angleDelta_zoomOut = QtCore.QPoint(-120, 0)

        # ZOOM OUT
        event = QtGui.QWheelEvent(position, position, pixelDelta, angleDelta_zoomOut, buttons, modifiers, phase, inverted)
        view.wheelEvent(event)
        self.assertGreater(zoomed_in_scale, view.transform().m11())

    def test_horizontal_scroll(self):
        """Horizontal scrolling with alt + mouse wheel"""
        view = _graph._GraphicsViewport()
        scroll_bar = view.horizontalScrollBar()
        initial_value = scroll_bar.value()
        scroll_bar.setMaximum(200)
        position = QtCore.QPoint(10, 10)
        pixelDelta = QtCore.QPoint(0, 0)
        angleDelta= QtCore.QPoint(-120, 0)
        buttons = QtCore.Qt.NoButton
        modifiers = QtCore.Qt.AltModifier
        phase = QtCore.Qt.NoScrollPhase
        inverted = False
        event = QtGui.QWheelEvent(position, position, pixelDelta, angleDelta, buttons, modifiers, phase, inverted)
        view.wheelEvent(event)
        final_value = scroll_bar.value()
        # Assert that the horizontal scroll has changed according to your pan logic
        self.assertGreater(final_value, initial_value)

    def test_vertical_scroll(self):
        """Vertical scroll with only mouse wheel"""
        view = _graph._GraphicsViewport()
        scroll_bar = view.verticalScrollBar()
        initial_value = scroll_bar.value()
        scroll_bar.setMaximum(200)
        position = QtCore.QPoint(10, 10)
        pixelDelta = QtCore.QPoint(0, 0)
        angleDelta = QtCore.QPoint(0, -120)
        buttons = QtCore.Qt.NoButton
        modifiers = QtCore.Qt.NoModifier
        phase = QtCore.Qt.NoScrollPhase
        inverted = False
        event = QtGui.QWheelEvent(position, position, pixelDelta, angleDelta, buttons, modifiers, phase, inverted)
        view.wheelEvent(event)
        final_value = scroll_bar.value()
        # Assert that the horizontal scroll has changed according to your pan logic
        self.assertGreater(final_value, initial_value)

    def test_pan(self):
        """Horizontal and vertical pan with mouse middle button"""
        view = _graph._GraphicsViewport()
        vertical_scroll_bar = view.verticalScrollBar()
        vertical_scroll_bar.setMaximum(200)
        horizontal_scroll_bar = view.horizontalScrollBar()
        horizontal_scroll_bar.setMaximum(200)
        start_position = QtCore.QPoint(50, 50)
        end_position = QtCore.QPoint(-5, -5)

        # 1. Mouse press
        middle_button_event = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, start_position, QtCore.Qt.MiddleButton, QtCore.Qt.MiddleButton, QtCore.Qt.NoModifier)
        vertical_value = vertical_scroll_bar.value()
        horizontal_value = horizontal_scroll_bar.value()
        view.mousePressEvent(middle_button_event)
        self.assertEqual(self._app.overrideCursor().shape(), QtGui.Qt.ClosedHandCursor)
        self.assertTrue(view._dragging)

        # 2. Mouse move
        view._last_pan_pos = _graph._EVENT_POSITION_FUNC(middle_button_event) + QtCore.QPoint(10,10)
        move_event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, end_position, QtCore.Qt.MiddleButton, QtCore.Qt.MiddleButton, QtCore.Qt.NoModifier)
        view.mouseMoveEvent(move_event)
        last_vertical_scroll_bar = vertical_scroll_bar.value()
        last_horizontal_scroll_bar = horizontal_scroll_bar.value()
        self.assertGreater(last_vertical_scroll_bar, vertical_value)
        self.assertGreater(last_horizontal_scroll_bar, horizontal_value)

        # 3. Release
        view.mouseReleaseEvent(middle_button_event)
        view._last_pan_pos = _graph._EVENT_POSITION_FUNC(middle_button_event) + QtCore.QPoint(20, 20)
        view.mouseMoveEvent(move_event)
        # Confirm no further move is performed
        self.assertEqual(last_vertical_scroll_bar, vertical_scroll_bar.value())
        self.assertEqual(last_horizontal_scroll_bar, horizontal_scroll_bar.value())


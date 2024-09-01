import os
import io
import csv
import shutil
import tempfile
import unittest
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

# 2024-02-03
# python -m unittest --durations 0 test_views
# Slowest test durations
# ----------------------------------------------------------------------
# 1.963s     test_scenegraph_composition (test_views.TestViews.test_scenegraph_composition)
# 1.882s     test_taxonomy_editor (test_views.TestViews.test_taxonomy_editor)
# 1.579s     test_content_browser (test_views.TestViews.test_content_browser)
# 0.789s     test_spreadsheet_editor (test_views.TestViews.test_spreadsheet_editor)
# 0.383s     test_horizontal_scroll (test_views.TestGraphicsViewport.test_horizontal_scroll)
# 0.329s     test_connection_view (test_views.TestViews.test_connection_view)
# 0.322s     test_layer_stack_hovers (test_views.TestViews.test_layer_stack_hovers)
# 0.204s     test_dot_call (test_views.TestViews.test_dot_call)
# 0.169s     test_display_color_editor (test_views.TestViews.test_display_color_editor)
# 0.167s     test_stats (test_views.TestViews.test_stats)
# 0.121s     test_prim_filter_data (test_views.TestViews.test_prim_filter_data)
# 0.116s     test_prim_composition (test_views.TestViews.test_prim_composition)
# 0.106s     test_create_assets (test_views.TestViews.test_create_assets)
# 0.014s     test_pan (test_views.TestGraphicsViewport.test_pan)
#
# (durations < 0.001s were hidden; use -v to show these durations)
# ----------------------------------------------------------------------
# Ran 18 tests in 8.216s


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


class TestViews(unittest.TestCase):
    def setUp(self):
        self._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

        sphere = Usd.Stage.CreateInMemory()
        UsdGeom.Sphere.Define(sphere, "/sph")
        root_path = "/root"
        sphere_root = sphere.DefinePrim(root_path)
        sphere_root.CreateAttribute("greet", Sdf.ValueTypeNames.String).Set("hello")
        sphere.SetDefaultPrim(sphere_root)

        capsule = Usd.Stage.CreateInMemory()
        UsdGeom.Capsule.Define(capsule, "/cap")
        root_path = "/root"
        capsule_root = capsule.DefinePrim(root_path)
        capsule_root.CreateAttribute("who", Sdf.ValueTypeNames.String).Set("world")
        capsule.SetDefaultPrim(capsule_root)

        merge = Usd.Stage.CreateInMemory()
        for i in (capsule, sphere):
            merge.GetRootLayer().subLayerPaths.append(i.GetRootLayer().identifier)
        merge.SetDefaultPrim(merge.GetPrimAtPath(root_path))

        world = Usd.Stage.CreateInMemory()
        self.nested = world.DefinePrim("/nested/child")
        self.sibling = world.DefinePrim("/nested/sibling")
        self.nested.GetReferences().AddReference(merge.GetRootLayer().identifier)

        self.capsule = capsule
        self.sphere = sphere
        self.merge = merge
        self.world = world

        self._tmpf = tempfile.mkdtemp()
        self._token = cook.Repository.set(cook.Path(self._tmpf) / "repo")
        self.rootf = names.UsdAsset.get_anonymous()
        self.grill_world = gworld = cook.fetch_stage(self.rootf.name)
        self.person = cook.define_taxon(gworld, "Person")
        self.agent = cook.define_taxon(gworld, "Agent", references=(self.person,))
        self.generic_agent = cook.create_unit(self.agent, "GenericAgent")

    def tearDown(self) -> None:
        cook.Repository.reset(self._token)
        # Reset all members to USD objects to ensure the used layers are cleared
        # (otherwise in Windows this can cause failure to remove the temporary files)
        self.generic_agent = None
        self.agent = None
        self.person = None
        self.grill_world = None
        self.capsule = None
        self.sphere = None
        self.merge = None
        self.world = None
        self.nested = None
        self.sibling = None
        shutil.rmtree(self._tmpf)
        self._app.quit()

    def test_connection_view(self):
        for graph_viewer in _graph.GraphView, _graph._GraphSVGViewer:
            with self.subTest(graph_viewer=graph_viewer):
                _graph._GraphViewer = graph_viewer
                if graph_viewer == _graph._GraphSVGViewer:
                    for pixmap_enabled in True, False:
                        with self.subTest(pixmap_enabled=pixmap_enabled):
                            _graph._USE_SVG_VIEWPORT = pixmap_enabled
                            self._sub_test_connection_view()
                else:
                    self._sub_test_connection_view()

    def _sub_test_connection_view(self):
        # https://openusd.org/release/tut_simple_shading.html
        stage = Usd.Stage.CreateInMemory()
        material = UsdShade.Material.Define(stage, '/TexModel/boardMat')
        pbrShader = UsdShade.Shader.Define(stage, '/TexModel/boardMat/PBRShader')
        pbrShader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.4)
        material.CreateSurfaceOutput().ConnectToSource(pbrShader.ConnectableAPI(), "surface")
        # Ensure cycles don't cause recursion
        cycle_input = pbrShader.CreateInput("cycle_in", Sdf.ValueTypeNames.Float)
        cycle_output = pbrShader.CreateOutput("cycle_out", Sdf.ValueTypeNames.Float)
        cycle_output.ConnectToSource(cycle_input)
        description._graph_from_connections(material)
        viewer = description._ConnectableAPIViewer()
        viewer.setPrim(material)
        viewer.setPrim(None)

    def test_scenegraph_composition(self):
        for graph_viewer in _graph.GraphView, _graph._GraphSVGViewer:
            with self.subTest(graph_viewer=graph_viewer):
                _graph._GraphViewer = graph_viewer
                if graph_viewer == _graph._GraphSVGViewer:
                    for pixmap_enabled in True, False:
                        with self.subTest(pixmap_enabled=pixmap_enabled):
                            _graph._USE_SVG_VIEWPORT = pixmap_enabled
                            self._sub_test_scenegraph_composition()
                            self._sub_test_layer_stack_bidirectionality()
                else:
                    self._sub_test_scenegraph_composition()
                    self._sub_test_layer_stack_bidirectionality()

    def _sub_test_scenegraph_composition(self):
        widget = description.LayerStackComposition()
        widget.setStage(self.world)

        # cheap. All these layers affect a single prim
        affectedPaths = dict.fromkeys((i.GetRootLayer() for i in (self.capsule, self.sphere, self.merge)), 1)

        # the world affects both root and the nested prims, stage layer stack is included
        affectedPaths.update(dict.fromkeys(self.world.GetLayerStack(), 3))

        for row in range(widget._layers.model.rowCount()):
            layer = widget._layers.model._objects[row]
            widget._layers.table.selectRow(row)
            expectedAffectedPrims = affectedPaths[layer]
            actualListedPrims = widget._prims.model.rowCount()
            self.assertEqual(expectedAffectedPrims, actualListedPrims)

        widget._layers.table.selectAll()
        self.assertEqual(len(affectedPaths), widget._layers.model.rowCount())
        self.assertEqual(3, widget._prims.model.rowCount())

        widget.setPrimPaths({"/nested/sibling"})
        widget.setStage(self.world)

        widget._layers.table.selectAll()
        self.assertEqual(2, widget._layers.model.rowCount())
        self.assertEqual(1, widget._prims.model.rowCount())

        widget._has_specs.setChecked(True)
        widget._graph_edge_include[description.Pcp.ArcTypeReference].setChecked(False)
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

    def _sub_test_layer_stack_bidirectionality(self):
        """Confirm that bidirectionality between layer stacks completes.

        Bidirectionality in the composition graph is achieved by:
            - parent_stage -> child_stage via a reference, payload arcs
            - child_stage -> parent_stage via a inherits, specializes arcs
        """
        parent_stage = Usd.Stage.CreateInMemory()
        child_stage = Usd.Stage.CreateInMemory()
        prim = parent_stage.DefinePrim("/a/b")
        child_prim = child_stage.DefinePrim("/child")
        child_prim.GetInherits().AddInherit("/foo")
        child_prim.GetSpecializes().AddSpecialize("/foo")
        child_stage.SetDefaultPrim(child_prim)
        child_identifier = child_stage.GetRootLayer().identifier
        prim.GetReferences().AddReference(child_identifier)
        prim.GetPayloads().AddPayload(child_identifier)

        widget = description.LayerStackComposition()
        widget.setStage(parent_stage)
        widget._layers.table.selectAll()

        graph_view = widget._graph_view

    def test_layer_stack_hovers(self):
        _graph._GraphViewer = _graph.GraphView
        _graph._USE_SVG_VIEWPORT = False

        parent_stage = Usd.Stage.CreateInMemory()
        child_stage = Usd.Stage.CreateInMemory()
        prim = parent_stage.DefinePrim("/a/b")
        child_prim = child_stage.DefinePrim("/child")
        child_prim.GetInherits().AddInherit("/foo")
        child_prim.GetSpecializes().AddSpecialize("/foo")
        child_stage.SetDefaultPrim(child_prim)
        child_identifier = child_stage.GetRootLayer().identifier
        prim.GetReferences().AddReference(child_identifier)
        prim.GetPayloads().AddPayload(child_identifier)

        widget = description.LayerStackComposition()
        widget.setStage(parent_stage)
        widget._graph_precise_source_ports.setChecked(True)
        widget._has_specs.setCheckState(QtCore.Qt.CheckState.PartiallyChecked)

        widget._layers.table.selectAll()
        graph_view = widget._graph_view
        cycle_collected = False
        nodes_hovered_checked = False
        for item in graph_view.scene().items():
            item.boundingRect()  # trigger bounding rect logic
            if isinstance(item, _graph._Edge):
                cycle_collected = True
            if isinstance(item, _graph._Node) and item.isVisible():
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

    def test_prim_composition(self):
        for pixmap_enabled in True, False:
            with self.subTest(pixmap_enabled=pixmap_enabled):
                description._SVG_AS_PIXMAP = pixmap_enabled
                self._sub_test_prim_composition()

    def _sub_test_prim_composition(self):
        temp = Usd.Stage.CreateInMemory()
        temp.GetRootLayer().subLayerPaths = [self.nested.GetStage().GetRootLayer().identifier]
        prim = temp.GetPrimAtPath(self.nested.GetPath())
        widget = description.PrimComposition()
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
        stage = cook.fetch_stage(str(self.rootf))

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
        for graph_viewer in _graph.GraphView, _graph._GraphSVGViewer:
            with self.subTest(graph_viewer=graph_viewer):
                _graph._GraphViewer = graph_viewer
                if graph_viewer == _graph._GraphSVGViewer:
                    for pixmap_enabled in True, False:
                        with self.subTest(pixmap_enabled=pixmap_enabled):
                            _graph._USE_SVG_VIEWPORT = pixmap_enabled
                            self._sub_test_taxonomy_editor()
                else:
                    self._sub_test_taxonomy_editor()

    def _sub_test_taxonomy_editor(self):
        stage = cook.fetch_stage(str(self.rootf.get_anonymous()))

        existing = [cook.define_taxon(stage, f"Option{each}") for each in range(1, 6)]
        widget = create.TaxonomyEditor()
        if isinstance(widget._graph_view, _graph.GraphView):
            with self.assertRaisesRegex(LookupError, "Could not find sender"):
                invalid_uril = QtCore.QUrl(f"{widget._graph_view.url_id_prefix}not_a_digit")
                widget._graph_view._graph_url_changed(invalid_uril)
        else:
            with self.assertRaisesRegex(RuntimeError, "'graph' attribute not set yet"):
                invalid_uril = QtCore.QUrl(f"{widget._graph_view.url_id_prefix}not_a_digit")
                widget._graph_view._graph_url_changed(invalid_uril)
        widget.setStage(stage)

        widget._amount.setValue(3)  # TODO: create 10 assets, clear tmp directory

        valid_data = (
            ['NewType1', 'Option1', 'Id1', ],
            ['NewType2', '', 'Id2', ],
        )
        data = valid_data + (
            ['',         'Option1', 'Id3', ],
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

        if isinstance(widget._graph_view, _graph.GraphView):
            sender = next(iter(widget._graph_view._nodes_map.values()))
            sender.linkActivated.emit("")
        else:
            valid_url = QtCore.QUrl(f"{widget._graph_view.url_id_prefix}{existing[-1].GetName()}")
            widget._graph_view._graph_url_changed(valid_url)
            # Nitpick, wait for dot 2 svg conversions to finish
            # This does not crash the program but an exception is logged when race
            # conditions apply (e.g. the object is deleted before the runnable completes).
            # This logged exception comes in the form of:
            # RuntimeError: Internal C++ object (_Dot2SvgSignals) already deleted.
            # Solution seems to be to block and wait for all runnables to complete.
            widget._graph_view._threadpool.waitForDone(10_000)

    def test_spreadsheet_editor(self):
        widget = sheets.SpreadsheetEditor()
        widget._model_hierarchy.setChecked(False)  # default is True
        self.world.OverridePrim("/child_orphaned")
        self.nested.SetInstanceable(True)
        widget._orphaned.setChecked(True)
        assert self.nested.IsInstance()
        widget.setStage(self.world)
        self.assertEqual(self.world, widget.stage)
        widget.table.scrollContentsBy(10, 10)

        widget.table.selectAll()
        expected_rows = {0, 1, 2, 3}  # 3 prims from path: /nested, /nested/child, /nested/sibling, /child_orphaned
        visible_rows = ({i.row() for i in widget.table.selectedIndexes()})
        self.assertEqual(expected_rows, visible_rows)

        widget.table.clearSelection()
        widget._column_options[0]._line_filter.setText("chi")
        widget._column_options[0]._updateMask()
        widget.table.resizeColumnToContents(0)

        widget.table.selectAll()
        expected_rows = {0, 1}  # 1 prim from filtered name: /nested/child
        visible_rows = ({i.row() for i in widget.table.selectedIndexes()})
        self.assertEqual(expected_rows, visible_rows)

        widget._copySelection()
        clip = QtWidgets.QApplication.instance().clipboard().text()
        data = tuple(csv.reader(io.StringIO(clip), delimiter=csv.excel_tab.delimiter))
        expected_data = (
            ['/nested/child', 'child', '', '', '', 'True', '', 'False'],
            ['/child_orphaned', 'child_orphaned', '', '', '', 'False', '', 'False'],
        )
        self.assertEqual(data, expected_data)

        widget.table.clearSelection()

        widget._model_hierarchy.click()  # enables model hierarchy, which we don't have any
        widget.table.selectAll()
        expected_rows = set()
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
        gworld = self.grill_world
        with cook.unit_context(self.generic_agent):
            child_agent = gworld.DefinePrim(self.generic_agent.GetPath().AppendChild("child"))
            child_attr = child_agent.CreateAttribute("agent_greet", Sdf.ValueTypeNames.String, custom=False)
            child_attr.Set("aloha")
        agent_id = cook.unit_asset(self.generic_agent)
        for i in range(3):
            agent = gworld.DefinePrim(f"/Instanced/Agent{i}")
            agent.GetReferences().AddReference(agent_id.identifier)
            agent.SetInstanceable(True)
        agent.SetActive(False)
        gworld.OverridePrim("/non/existing/prim")
        gworld.DefinePrim("/pruned/prim")
        inactive = gworld.DefinePrim("/another_inactive")
        inactive.SetActive(False)
        gworld.GetRootLayer().subLayerPaths.append(self.world.GetRootLayer().identifier)
        widget._column_options[0]._line_filter.setText("")
        widget.table.clearSelection()
        widget._active.setChecked(False)
        widget._classes.setChecked(True)
        widget._filters_logical_op.setCurrentIndex(1)
        widget.stage = gworld
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

        self.assertEqual(expected_colors, dict())
        self.assertEqual(expected_fonts, collected_fonts)

    def test_prim_filter_data(self):
        stage = cook.fetch_stage(self.rootf)
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
        """Test execution of function by mocking dot with python call"""
        with mock.patch("grill.views.description._which") as patch:
            patch.return_value = 'python'
            error, targetpath = _graph._dot_2_svg('nonexisting_path')
            # an error would be reported back
            self.assertIsNotNone(error)

    def test_content_browser(self):
        stage = cook.fetch_stage(self.rootf)
        taxon = cook.define_taxon(stage, "Another")
        parent, child = cook.create_many(taxon, ['A', 'B'])
        for path, value in (
                ("", (2, 15, 6)),
                ("Deeper/Nested/Golden1", (-4, 5, 1)),
                ("Deeper/Nested/Golden2", (-4, -10, 1)),
                ("Deeper/Nested/Golden3", (0, 10, -2)),
        ):
            spawned = UsdGeom.Xform(cook.spawn_unit(parent, child, path))
            spawned.AddTranslateOp().Set(value=value)
        variant_set_name = "testset"
        variant_name = "testvar"
        vset = child.GetVariantSet(variant_set_name)
        vset.AddVariant(variant_name)
        vset.SetVariantSelection(variant_name)
        with vset.GetVariantEditContext():
            stage.DefinePrim(child.GetPath().AppendChild("in_variant"))
        path_with_variant = child.GetPath().AppendVariantSelection(variant_set_name, variant_name)

        _core_run = _core._run
        # sdffilter still not coming via pypi, so patch for now
        if not description._which("sdffilter"):
            def _fake_run(run_args: list):
                print(f"{run_args=}")
                *_, path = run_args
                return "", Sdf.Layer.FindOrOpen(path).ExportToString()
        else:
            _fake_run = _core_run

        layers = stage.GetLayerStack()
        args = stage.GetLayerStack(), None, stage.GetPathResolverContext(), (Sdf.Path("/"), spawned.GetPrim().GetPath(), path_with_variant)
        anchor = layers[0]

        def _log(*args):
            print(args)

        with mock.patch("grill.views.description._core._run", new=_fake_run):
            dialog = description._start_content_browser(*args)
            browser = dialog.findChild(description._PseudoUSDBrowser)
            assert browser._browsers_by_layer.values()
            first_browser_widget, = browser._browsers_by_layer.values()
            first_browser_widget._format_options.setCurrentIndex(0)  # pseudoLayer (through sdffilter)
            first_browser_widget._format_options.setCurrentIndex(1)  # outline (through sdffilter)
            first_browser_widget._format_options.setCurrentIndex(2)  # usdtree (through usdtree)
            first_browser_widget._format_options.setCurrentIndex(0)
            browser._on_identifier_requested(anchor, layers[1].identifier)
            with mock.patch(f"{QtWidgets.__name__}.QMessageBox.warning", new=_log):
                browser._on_identifier_requested(anchor, "/missing/file.usd")
            browser.tabCloseRequested.emit(0)  # request closing our first tab
            for child in dialog.findChildren(description._PseudoUSDBrowser):
                child._resolved_layers.clear()

            prim_index = parent.GetPrimIndex()
            _, sourcepath = tempfile.mkstemp()
            prim_index.DumpToDotGraph(sourcepath)
            targetpath = f"{sourcepath}.png"
            error, __ = _core_run([_core._which("dot"), sourcepath, "-Tpng", "-o", targetpath])
            if error:
                raise RuntimeError(error)
            browser._addImageTab(targetpath, identifier=targetpath)

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
        stage = cook.fetch_stage(self.rootf)
        sphere = UsdGeom.Sphere.Define(stage, "/volume")
        color_var = sphere.GetDisplayColorPrimvar()
        editor = _attributes._DisplayColorEditor(color_var)
        editor._update_value()

        color_var.SetInterpolation(UsdGeom.Tokens.vertex)
        editor = _attributes._DisplayColorEditor(color_var)
        editor._update_value()
        editor._random.click()

        xform = stage.DefinePrim("/x")
        primvar = UsdGeom.Gprim(xform.GetPrim()).CreateDisplayColorPrimvar()
        editor = _attributes._DisplayColorEditor(primvar)
        with self.assertRaises(TypeError):  # atm some gprim types are not supported
            editor._update_value()

    def test_stats(self):
        empty = stats.StageStats()
        self.assertEqual(empty._usd_tree.topLevelItemCount(), 0)

        widget = stats.StageStats(stage=self.world)
        self.assertGreater(widget._usd_tree.topLevelItemCount(), 1)
        current = _qt.QtCharts
        del _qt.QtCharts
        stats.StageStats(stage=self.world)
        _qt.QtCharts = current


class TestGraphicsViewport(unittest.TestCase):
    def setUp(self):
        self._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def tearDown(self):
        self._app.quit()

    def test_zoom(self):
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

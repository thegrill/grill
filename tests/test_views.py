import io
import csv
import shutil
import tempfile
import unittest
from unittest import mock

from pxr import Usd, UsdGeom, Sdf

from grill import cook, usd, names
from grill.views import description, sheets, create, _attributes, stats
from grill.views._qt import QtWidgets, QtCore


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
        shutil.rmtree(self._tmpf)

    def test_layer_composition(self):
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

        widget.deleteLater()

    def test_prim_composition(self):
        widget = description.PrimComposition()
        widget.setPrim(self.nested)

        # cheap. prim is affected by 2 layers
        # single child for this prim.
        self.assertTrue(widget.composition_tree._model.invisibleRootItem().hasChildren())

        widget._complete_target_layerstack.setChecked(True)

        self.assertTrue(widget.composition_tree._model.invisibleRootItem().hasChildren())

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
        stage = cook.fetch_stage(str(self.rootf.get_anonymous()))

        existing = [cook.define_taxon(stage, f"Option{each}") for each in range(1, 6)]

        widget = create.TaxonomyEditor()
        with self.assertRaises(ValueError):
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
        valid_url = QtCore.QUrl(f"{widget._graph_view.url_id_prefix}{len(existing)}")
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
        widget.setStage(self.world)
        widget.table.scrollContentsBy(10, 10)

        widget.table.selectAll()
        expected_rows = {0, 1, 2}  # 3 prims from path: /nested, /nested/child, /nested/sibling
        visible_rows = ({i.row() for i in widget.table.selectedIndexes()})
        self.assertEqual(expected_rows, visible_rows)

        widget.table.clearSelection()
        widget._column_options[0]._line_filter.setText("chi")
        widget._column_options[0]._updateMask()
        widget.table.resizeColumnToContents(0)

        widget.table.selectAll()
        expected_rows = {0}  # 1 prim from filtered name: /nested/child
        visible_rows = ({i.row() for i in widget.table.selectedIndexes()})
        self.assertEqual(expected_rows, visible_rows)

        widget._copySelection()
        clip = QtWidgets.QApplication.instance().clipboard().text()
        data = tuple(csv.reader(io.StringIO(clip), delimiter=csv.excel_tab.delimiter))
        expected_data = (['/nested/child', 'child', '', '', '', 'False', '', 'False'],)
        self.assertEqual(data, expected_data)

        widget.table.clearSelection()

        widget._model_hierarchy.click()  # enables model hierarchy, which we don't have any
        widget.table.selectAll()
        expected_rows = set()  # 0 prim from filtered name + no model
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
        widget._pasteClipboard()

        widget.model._prune_children = {Sdf.Path("/inactive")}
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
        gworld.OverridePrim("/non/existing/prim")
        inactive = gworld.DefinePrim("/inactive/prim")
        inactive.SetActive(False)
        widget.setStage(self.grill_world)

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
            error, targetpath = description._dot_2_svg('nonexisting_path')
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

        # sdffilter still not coming via pypi, so patch for now
        if not description._which("sdffilter"):
            def _to_ascii(layer):
                return "", layer.ExportToString()
        else:
            _to_ascii = description._pseudo_layer

        layers = stage.GetLayerStack()
        args = stage.GetLayerStack(), None, stage.GetPathResolverContext()
        anchor = layers[0]

        def _log(*args):
            print(args)

        with mock.patch("grill.views.description._pseudo_layer", new=_to_ascii):
            dialog = description._start_content_browser(*args)
            browser = dialog.findChild(description._PseudoUSDBrowser)
            browser._on_identifier_requested(anchor, layers[1].identifier)
            with mock.patch("PySide2.QtWidgets.QMessageBox.warning", new=_log):
                browser._on_identifier_requested(anchor, "/missing/file.usd")
            browser.tabCloseRequested.emit(0)  # request closing our first tab

        with mock.patch("grill.views.description._which") as patch:
            patch.return_value = None
            with self.assertRaisesRegex(ValueError, "Expected arguments to contain an executable value on the first index"):
                description._start_content_browser(*args)

        error, result = description._run(["python", 42])
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

        xform = UsdGeom.Xform.Define(stage, "/x")
        primvar = UsdGeom.Gprim(xform.GetPrim()).CreateDisplayColorPrimvar()
        editor = _attributes._DisplayColorEditor(primvar)
        with self.assertRaises(TypeError):  # atm some gprim types are not supported
            editor._update_value()

    def test_stats(self):
        empty = stats.StageStats()
        self.assertEqual(empty._usd_tree.topLevelItemCount(), 0)

        widget = stats.StageStats(stage=self.world)
        self.assertGreater(widget._usd_tree.topLevelItemCount(), 1)

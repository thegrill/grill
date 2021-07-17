import io
import csv
import shutil
import tempfile
import unittest
from unittest import mock

from pxr import Usd, UsdGeom, Sdf
from PySide2 import QtWidgets, QtCore

from grill import write
from grill.views import description, sheets, create


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
        self.nested.GetReferences().AddReference(merge.GetRootLayer().identifier)

        self.capsule = capsule
        self.sphere = sphere
        self.merge = merge
        self.world = world

        self._tmpf = tempfile.mkdtemp()
        self._token = write.Repository.set(write.Path(self._tmpf) / "repo")
        self.rootf = write.UsdAsset.get_anonymous()

    def tearDown(self) -> None:
        write.Repository.reset(self._token)
        shutil.rmtree(self._tmpf)

    def test_layer_composition(self):
        widget = description.LayerStackComposition()
        widget.setStage(self.world)

        # cheap. All these layers affect a single prim
        affectedPaths = dict.fromkeys((i.GetRootLayer() for i in (self.capsule, self.sphere, self.merge)), 1)

        # the world affects both root and the nested prims
        affectedPaths[self.world.GetRootLayer()] = 2

        for row in range(widget._layers.model.rowCount()):
            layer = widget._layers.model.item(row, 0).data(QtCore.Qt.UserRole)
            widget._layers.table.selectRow(row)
            expectedAffectedPrims = affectedPaths[layer]
            actualListedPrims = widget._prims.model.rowCount()
            self.assertEqual(expectedAffectedPrims, actualListedPrims)
        widget.deleteLater()

    def test_prim_composition(self):
        widget = description.PrimComposition()
        widget.setPrim(self.nested)

        # cheap. prim is affected by 2 layers
        topLevel = widget.composition_tree.topLevelItem(0)
        # single child for this prim.
        self.assertEqual(topLevel.childCount(), 1)

        widget.clear()

    def test_create_assets(self):
        stage = write.fetch_stage(str(self.rootf))

        for each in range(1, 6):
            write.define_taxon(stage, f"Option{each}")

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
        taxon_editor = widget.sheet._columns_spec[0].editor(widget, None, None)
        self.assertIsInstance(taxon_editor, QtWidgets.QComboBox)
        widget._apply()

    def test_taxonomy_editor(self):
        stage = write.fetch_stage(str(self.rootf))

        existing = [write.define_taxon(stage, f"Option{each}") for each in range(1, 6)]

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
            created = stage.GetPrimAtPath(write._TAXONOMY_ROOT_PATH).GetPrimAtPath(name)
            self.assertTrue(created.IsValid())

        sheet_model = widget.sheet.model
        index = sheet_model.index(0, 1)
        editor = widget.sheet._columns_spec[1].editor(None, None, index)
        self.assertIsInstance(editor, QtWidgets.QDialog)
        self.assertEqual(editor.property('value'), [valid_data[0][1]])
        widget.sheet._columns_spec[1].model_setter(editor, sheet_model, index)
        editor._options.selectAll()
        menu = editor._create_context_menu()
        menu.actions()[0].trigger()
        self.assertIsNone(editor.property('text'))

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
        widget.setStage(self.world)
        widget.table.scrollContentsBy(10, 10)

        widget.table.selectAll()
        expected_rows = {0, 1}  # 2 prims from path: /nested & /nested/child
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
        expected_data = (['child', '/nested/child', '', '', 'False', '', 'False'],)
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

    def test_dot_call(self):
        """Test execution of function by mocking dot with python call"""
        with mock.patch("grill.views.description._dot_exe") as patch:
            patch.return_value = 'python'
            error, targetpath = description._dot_2_svg('nonexisting_path')
            # an error would be reported back
            self.assertIsNotNone(error)

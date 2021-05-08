import io
import csv
import tempfile
import unittest

from pxr import Usd, UsdGeom, Sdf
from PySide2 import QtWidgets, QtCore

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

    def test_layer_composition(self):
        widget = description.LayersComposition()
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
        tmpf = tempfile.mkdtemp()
        token = create.write.repo.set(create.write.Path(tmpf) / "repo")
        rootf = create.write.UsdAsset.get_default(stream='testestest')
        stage = create.write.fetch_stage(str(rootf))

        for each in range(1, 6):
            create.write.define_taxon(stage, f"Option{each}")

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

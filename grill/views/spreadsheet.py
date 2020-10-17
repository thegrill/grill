import io
import csv
import inspect
import itertools

from pxr import Usd, UsdGeom
from typing import NamedTuple
from PySide2 import QtCore, QtWidgets, QtGui
from functools import partial

# {Mesh: UsdGeom.Mesh, Xform: UsdGeom.Xform}
options = dict(x for x in inspect.getmembers(UsdGeom, inspect.isclass) if Usd.Typed in x[-1].mro())

headers = ["Name", "Type", "Documentation", "Rating"]


class Column(NamedTuple):
    name: str
    getter: callable
    setter: callable
    readonly: bool = False


_COLUMNS = (
    Column("Name", lambda x: x.GetName(), lambda x, y: x, True),
    Column("Path", lambda x: str(x.GetPath()), lambda x, y: x, True),
    Column("Type", lambda x: x.GetTypeName(), lambda x, y: x.SetTypeName(y)),
    Column("Documentation", lambda x: x.GetDocumentation(), lambda x, y: x.SetDocumentation(y)),
    Column("Hidden", lambda x: x.IsHidden(), lambda x, y: x.SetHidden(y)),
)
columns_ids = {column.name: i for i, column in enumerate(_COLUMNS)}


class ColumnOptions(QtWidgets.QWidget):
    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()
        options_layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        # Search filter
        line_filter = QtWidgets.QLineEdit()
        line_filter.setPlaceholderText("Filter")
        line_filter.setToolTip(r"Negative lookahead: ^((?!{expression}).)*$")
        self.line_filter = line_filter
        # Visibility
        vis_button = QtWidgets.QPushButton("👀")
        vis_button.setCheckable(True)
        vis_button.setChecked(True)
        vis_button.setFlat(True)
        self.vis_button = vis_button

        # Lock
        lock_button = QtWidgets.QPushButton()
        lock_button.setCheckable(True)
        lock_button.setFlat(True)
        self.lock_button = lock_button

        # allow for a bit of extra space with option buttons
        label = QtWidgets.QLabel(f"{name} ")
        self.label = label
        label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        options_layout.addWidget(label)
        options_layout.addWidget(vis_button)
        options_layout.addWidget(lock_button)
        options_layout.addStretch()
        layout.addLayout(options_layout)
        self.filter_layout = filter_layout = QtWidgets.QFormLayout()
        filter_layout.addRow("🔎", line_filter)
        layout.addLayout(filter_layout)

        self._decorateLockButton(lock_button, lock_button.isChecked())
        lock_button.toggled.connect(partial(self._decorateLockButton, lock_button))

    def resizeEvent(self, event:QtGui.QResizeEvent):
        value = super().resizeEvent(event)
        self._updateMask()
        return value

    def _updateMask(self):
        self.setMask(
            QtGui.QRegion(self.filter_layout.geometry()) +
            # when button are flat, geometry has a small render offset on x
            QtGui.QRegion(self.lock_button.geometry().adjusted(-2, 0, 2, 0)) +
            QtGui.QRegion(self.vis_button.geometry().adjusted(-2, 0, 2, 0))
        )

    def _decorateLockButton(self, button, locked):
        if locked:
            text = "🔐"
            tip = "Non-editable (locked).\nClick to allow edits."
        else:
            text = "🔓"
            tip = "Edits are allowed (unlocked).\nClick to block edits."
        button.setText(text)
        button.setToolTip(tip)


class CustomFilter(QtCore.QSortFilterProxyModel):
    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = ..., ):
        # https://www.walletfox.com/course/qsortfilterproxymodelexample.php
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Vertical:
            if orientation == QtCore.Qt.Vertical:
                return section + 1
        return super().headerData(section, orientation, role)


# https://www.qt.io/blog/2014/04/11/qt-weekly-5-widgets-on-a-qheaderview
# https://www.qt.io/blog/2012/09/28/qt-support-weekly-27-widgets-on-a-header
# https://www.learnpyqt.com/courses/model-views/qtableview-modelviews-numpy-pandas/
class CustomHeader(QtWidgets.QHeaderView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sectionResized.connect(self._handleSectionResized)
        self.sectionMoved.connect(self._handleSectionMoved)
        self.setSectionsMovable(True)
        self._options_frames = dict()
        self._proxy_labels = dict()  # I've found no other way around this

        for index, columndata in enumerate(_COLUMNS):
            column_options = ColumnOptions(columndata.name, parent=self)
            column_options.layout().setContentsMargins(0, 0, 0, 0)
            self._options_frames[index] = column_options
            proxy_label = QtWidgets.QLabel(parent=self)
            proxy_label.setText(column_options.label.text())
            proxy_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            self._proxy_labels[column_options.label] = proxy_label
            size_hint = column_options.sizeHint()
            self.setMinimumHeight(size_hint.height() + 20)

    def showEvent(self, event:QtGui.QShowEvent):
        for index, widget in self._options_frames.items():
            widget.setGeometry(*self._geometryForWidget(index))
            widget.show()
            self.resizeSection(index, widget.sizeHint().width() + 20)
            label_geo = widget.label.geometry()
            label_geo.moveTo(widget.pos())
            self._proxy_labels[widget.label].setGeometry(label_geo)
        super().showEvent(event)

    def _handleSectionResized(self, index):
        for visual_index in range(self.visualIndex(index), self.count()):
            logical_index = self.logicalIndex(visual_index)
            widget = self._options_frames[logical_index]
            geometry = self._geometryForWidget(logical_index)
            widget.setGeometry(*geometry)
            label_geo = widget.label.geometry()
            label_geo.moveTo(widget.pos())
            self._proxy_labels[widget.label].setGeometry(label_geo)

        for index, widget in self._options_frames.items():
            vis = (widget.minimumSizeHint().width() / 2.0) < self.sectionSize(index)
            widget.setVisible(vis)
            self._proxy_labels[widget.label].setVisible(vis)

    def _handleSectionMoved(self, logical_index, old_visual_index, new_visual_index):
        for visual_index in range(min(old_visual_index, new_visual_index), self.count()):
            logical_index = self.logicalIndex(visual_index)
            widget = self._options_frames[logical_index]
            geometry = self._geometryForWidget(logical_index)
            widget.setGeometry(*geometry)
            label_geo = widget.label.geometry()
            label_geo.moveTo(widget.pos())
            self._proxy_labels[widget.label].setGeometry(label_geo)

    def _geometryForWidget(self, index):
        """Main geometry for the widget to show at the given index"""
        return self.sectionViewportPosition(index) + 10, 10, self.sectionSize(index) - 20, self.height() - 20


class Table(QtWidgets.QTableView):
    def scrollContentsBy(self, dx:int, dy:int):
        super().scrollContentsBy(dx, dy)
        if dx:
            self._fixPositions()

    def _fixPositions(self):
        header = self.horizontalHeader()
        for index, widget in header._options_frames.items():
            widget.setGeometry(*header._geometryForWidget(index))


class Spreadsheet(QtWidgets.QDialog):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent=parent, **kwargs)
        model = QtGui.QStandardItemModel(0, len(headers))
        self.model = model
        self._stage = Usd.Stage.CreateInMemory()
        self.model.setHorizontalHeaderLabels(['']* len(columns_ids))
        # for every column, create a proxy model and chain it to the next one
        proxy_model = source_model = model
        filters_layout = QtWidgets.QHBoxLayout()
        table = Table()
        def _toggleColumnVis(index, value):
            table.setColumnHidden(index, not value)

        header = CustomHeader(QtCore.Qt.Horizontal)
        for column_index, columndata in enumerate(_COLUMNS):
            proxy_model = CustomFilter()
            proxy_model.setSourceModel(source_model)
            proxy_model.setFilterKeyColumn(column_index)
            source_model = proxy_model
            column_options = header._options_frames[column_index]
            column_options.line_filter.textChanged.connect(proxy_model.setFilterRegExp)
            column_options.vis_button.toggled.connect(partial(_toggleColumnVis, column_index))
            column_options.lock_button.toggled.connect(partial(self._setColumnLocked, column_index))

        table.setModel(proxy_model)

        header.setModel(proxy_model)
        header.setSectionsClickable(True)
        table.setHorizontalHeader(header)
        table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.SelectedClicked)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)

        sorting_enabled = QtWidgets.QCheckBox("Sorting Enabled")
        sorting_enabled.setChecked(True)
        sorting_enabled.toggled.connect(table.setSortingEnabled)

        self.sorting_enabled = sorting_enabled

        self.table = table
        all_layout = QtWidgets.QHBoxLayout()
        all_layout.addWidget(sorting_enabled)
        lock_all = QtWidgets.QPushButton("🔐 Lock All")
        hide_all = QtWidgets.QPushButton("👀 Hide All")
        all_layout.addWidget(lock_all)
        all_layout.addWidget(hide_all)
        all_layout.addStretch()
        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(all_layout)
        layout.addLayout(filters_layout)
        layout.addWidget(self.table)
        btn = QtWidgets.QPushButton("Add Row")
        btn.clicked.connect(lambda: self.table.insertRow(self.table.rowCount()))
        layout.addWidget(btn)
        self.setLayout(layout)
        self.installEventFilter(self)

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.KeyPress and event.matches(QtGui.QKeySequence.Copy):
            self.copySelection()
        elif event.type() == QtCore.QEvent.KeyPress and event.matches(QtGui.QKeySequence.Paste):
            self._pasteClipboard()
        return super().eventFilter(source, event)

    def _pasteClipboard(self):
        text = QtWidgets.QApplication.instance().clipboard().text()
        print(f"Creating rows with:\n{text}")
        if not text:
            print("Nothing to do!")
            return
        selection = self.table.selectedIndexes()
        selected_rows = [i.row() for i in selection]
        selected_columns = [i.column() for i in selection]
        # if selection is not continuous, alert the user and abort instead of
        # trying to figure out what to paste where.
        if len(selection) != len(set(selected_rows)) * len(set(selected_columns)):
            msg = ("Cells need to be selected continuously "
                   "(no gaps between rows / columns)\n"
                   "to paste with multiple selection.")
            QtWidgets.QMessageBox.warning(self, "Invalid Paste Selection", msg)
            return
        model = self.model
        current_count = model.rowCount()
        selected_row = min(selected_rows, default=current_count)
        selected_column = min(selected_columns, default=0)
        # print(f"{selected_row=}")
        # print(f"{selected_column=}")
        data = tuple(csv.reader(io.StringIO(text), delimiter=csv.excel_tab.delimiter))
        # print(f"{data=}")
        self.table.setSortingEnabled(False)  # prevent auto sort while adding rows

        maxrow = max(selected_row + len(data) - 1,  # either the amount of rows to paste
                     max(selected_rows, default=current_count))  # or the current row count
        # print(f"{maxrow=}")
        stage = self._stage
        # cycle the data in case that selection to paste on is bigger than source
        for row_index, rowdata in enumerate(itertools.cycle(data), start=selected_row):
            if row_index == model.rowCount():
                # print(f"inserting a row at {row_index=}")
                model.insertRow(row_index)
                from datetime import datetime
                time_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                prim = stage.DefinePrim(f"/root/test_{row_index}_{time_str}")
                print(prim)
                self._addPrimToRow(row_index, prim)
            else:
                prim = model.index(row_index, 0).data(QtCore.Qt.UserRole)
                print(prim)

            for column_index, column_data in enumerate(rowdata, start=selected_column):
                item = model.item(row_index, column_index)
                _COLUMNS[column_index].setter(prim, column_data)
                item.setData(column_data, QtCore.Qt.DisplayRole)

            if row_index == maxrow:
                print("Bye!")
                break

        self.table.setSortingEnabled(self.sorting_enabled.isChecked())  # prevent auto sort while adding rows

    def copySelection(self):
        selection = self.table.selectedIndexes()
        print(selection)
        if selection:
            rows = sorted(index.row() for index in selection)
            columns = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = columns[-1] - columns[0] + 1
            table = [[''] * colcount for _ in range(rowcount)]
            for index in selection:
                row = index.row() - rows[0]
                column = index.column() - columns[0]
                table[row][column] = index.data()
            stream = io.StringIO()

            csv.writer(stream, delimiter=csv.excel_tab.delimiter).writerows(table)
            print(f"Copied!\n{stream.getvalue()}")
            QtWidgets.QApplication.instance().clipboard().setText(stream.getvalue())

    def setStage(self, stage):
        self._stage = stage
        table = self.table
        model = self.model
        model.clear()
        model.setHorizontalHeaderLabels([''] * len(columns_ids))
        table.setSortingEnabled(False)
        combobox_delegate = ComboBoxItemDelegate()
        self.combobox_delegate = combobox_delegate
        table.setItemDelegateForColumn(columns_ids["Type"], combobox_delegate)
        index = -1
        for index, prim in enumerate(stage.TraverseAll()):
            model.insertRow(index)
            self._addPrimToRow(index, prim)

        model.setRowCount(index+1)
        table.setSortingEnabled(self.sorting_enabled.isChecked())

    def _addPrimToRow(self, row_index, prim):
        model = self.model
        for column_index, column_data in enumerate(_COLUMNS):
            attribute = column_data.getter(prim)
            item = QtGui.QStandardItem()
            item.setData(attribute, QtCore.Qt.DisplayRole)
            item.setData(prim, QtCore.Qt.UserRole)
            model.setItem(row_index, column_index, item)

    def _setColumnLocked(self, column_index, value):
        model = self.model
        editable = QtCore.Qt.ItemIsEditable
        for row_index in range(model.rowCount()):
            item = model.item(row_index, column_index)
            current = item.flags()
            # https://www.programcreek.com/python/example/101641/PyQt5.QtCore.Qt.ItemIsEditable
            item.setFlags(current ^ editable if value else current | editable)


class ComboBoxItemDelegate(QtWidgets.QStyledItemDelegate):
    """ A subclass of QStyledItemDelegate that allows us to render our
        pretty star ratings.

    https://doc.qt.io/qtforpython/overviews/sql-presenting.html
    https://doc.qt.io/qtforpython/overviews/qtwidgets-itemviews-spinboxdelegate-example.html
    """
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        combobox = QtWidgets.QComboBox(parent=parent)
        combobox.addItems(options)
        return combobox

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex):
        #     QComboBox *cb = qobject_cast<QComboBox *>(editor);
        #     Q_ASSERT(cb);
        #     // get the index of the text in the combobox that matches the current value of the item
        #     const QString currentText = index.data(Qt::EditRole).toString();
        #     const int cbIndex = cb->findText(currentText);
        #     // if it is valid, adjust the combobox
        #     if (cbIndex >= 0)
        #        cb->setCurrentIndex(cbIndex);
        currentText = index.data(QtCore.Qt.EditRole)
        # print(f"{currentText=}")
        cbox_index = editor.findText(currentText)
        # print(f"{cbox_index=}")
        if cbox_index:
            editor.setCurrentIndex(cbox_index)

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex):
        prim = index.data(QtCore.Qt.UserRole)
        prim.SetTypeName(editor.currentText())
        model.setData(index, editor.currentText(), QtCore.Qt.EditRole)

    # def commitAndCloseEditor(self):
    #     """ Erm... commits the data and closes the editor. :) """
    #     editor = self.sender()
    #
    #     # The commitData signal must be emitted when we've finished editing
    #     # and need to write our changed back to the model.
    #     self.commitData.emit(editor)
    #     self.closeEditor.emit(editor, QStyledItemDelegate.NoHint)


if __name__ == "__main__":
    """ Run the application. """
    import sys
    app = QtWidgets.QApplication(sys.argv)

    # column = ColumnOptions("test uno dos tres ----------------------------")
    stage = Usd.Stage.Open(r"B:\read\cg\downloads\Kitchen_set\Kitchen_set\Kitchen_set.usd")
    # # stage = Usd.Stage.Open(r"B:\read\cg\downloads\UsdSkelExamples\UsdSkelExamples\HumanFemale\HumanFemale.walk.usd")
    # # stage = Usd.Stage.Open(r"B:\read\cg\downloads\PointInstancedMedCity\PointInstancedMedCity.usd")
    spreadsheet = Spreadsheet()
    spreadsheet.setStage(stage)
    spreadsheet.show()
    # column.show()
    sys.exit(app.exec_())


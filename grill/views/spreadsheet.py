import io
import csv
import inspect
import itertools

from typing import NamedTuple
from datetime import datetime
from functools import partial

from pxr import Usd, UsdGeom
from PySide2 import QtCore, QtWidgets, QtGui

# {Mesh: UsdGeom.Mesh, Xform: UsdGeom.Xform}
options = dict(x for x in inspect.getmembers(UsdGeom, inspect.isclass) if Usd.Typed in x[-1].mro())


from contextlib import contextmanager
@contextmanager
def wait():
    try:
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        yield
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()


class Column(NamedTuple):
    name: str
    getter: callable
    setter: callable


_COLUMNS = (
    Column("Name", Usd.Prim.GetName, lambda x, y: x),
    Column("Path", lambda prim: str(prim.GetPath()), lambda x, y: x),
    Column("Type", Usd.Prim.GetTypeName, Usd.Prim.SetTypeName),
    Column("Documentation", Usd.Prim.GetDocumentation, Usd.Prim.SetDocumentation),
    Column("Hidden", Usd.Prim.IsHidden, Usd.Prim.SetHidden),
)
columns_ids = {column.name: i for i, column in enumerate(_COLUMNS)}


class _ColumnOptions(QtWidgets.QWidget):
    """A widget to be used within a header for columns on a USD spreadsheet."""
    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()
        options_layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        # Search filter
        line_filter = QtWidgets.QLineEdit()
        line_filter.setPlaceholderText("Filter")
        line_filter.setToolTip(r"Negative lookahead: ^((?!{expression}).)*$")

        # Visibility
        self._vis_button = vis_button = QtWidgets.QPushButton("👀")
        vis_button.setCheckable(True)
        vis_button.setChecked(True)
        vis_button.setFlat(True)

        # Lock
        self._lock_button = lock_button = QtWidgets.QPushButton()
        lock_button.setCheckable(True)
        lock_button.setFlat(True)

        # allow for a bit of extra space with option buttons
        label = QtWidgets.QLabel(f"{name} ")
        options_layout.addWidget(label)
        options_layout.addWidget(vis_button)
        options_layout.addWidget(lock_button)
        options_layout.addStretch()
        layout.addLayout(options_layout)
        self._filter_layout = filter_layout = QtWidgets.QFormLayout()
        filter_layout.addRow("🔎", line_filter)
        layout.addLayout(filter_layout)

        self._decorateLockButton(lock_button, lock_button.isChecked())
        lock_button.toggled.connect(partial(self._decorateLockButton, lock_button))

        # public members exposure
        self.label = label
        self.locked = self._lock_button.toggled
        self.toggled = self._vis_button.toggled
        self.filterChanged = line_filter.textChanged

    def resizeEvent(self, event:QtGui.QResizeEvent):
        """Update the widget mask after resize to bypass clicks to the parent widget."""
        value = super().resizeEvent(event)
        self._updateMask()
        return value

    def _updateMask(self):
        """We want nothing but the filter and buttons to be clickable on this widget."""
        self.setMask(
            QtGui.QRegion(self._filter_layout.geometry()) +
            # when button are flat, geometry has a small render offset on x
            QtGui.QRegion(self._lock_button.geometry().adjusted(-2, 0, 2, 0)) +
            QtGui.QRegion(self._vis_button.geometry().adjusted(-2, 0, 2, 0))
        )

    def _decorateLockButton(self, button, locked):
        if locked:
            text = "🔐"
            tip = "Column is non-editable (locked).\nClick to allow edits."
        else:
            text = "🔓"
            tip = "Edits are allowed on this column (unlocked).\nClick to block edits."
        button.setText(text)
        button.setToolTip(tip)


def _sourceIndex(index):
    """Recursively get the source index of a proxy model index"""
    source_model = index.model()
    if isinstance(source_model, _ProxyModel):
        return _sourceIndex(source_model.mapToSource(index))
    else:
        return index


class _ProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._useModelHierarchy = False

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        """For a vertical header, display a sequential visual index instead of the logical from the model."""
        # https://www.walletfox.com/course/qsortfilterproxymodelexample.php
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Vertical:
            return section + 1
        return super().headerData(section, orientation, role)

    def _extraFilters(self, source_row, source_parent):
        source_column = self.filterKeyColumn()
        source_model = self.sourceModel()
        index = source_model.index(source_row, source_column, source_parent)
        if not index.isValid():
            raise ValueError(f"Invalid index from source_row={source_row}, source_column={source_column}, source_parent={source_parent}")

        prim = index.data(QtCore.Qt.UserRole)
        if not prim:
            # row may have been just inserted as a result of a model.insertRow or
            # model.appendRow call, so no prim yet. Mmmm see how to prevent this?
            # blocking signals before adding row on setStage does not work around this.
            return True
        if self._useModelHierarchy:
            return prim.IsModel()
        return True

    def filterAcceptsRow(self, source_row:int, source_parent:QtCore.QModelIndex) -> bool:
        result = super().filterAcceptsRow(source_row, source_parent)
        if result:
            result = self._extraFilters(source_row, source_parent)
        return result

    def _setModelHierarchyEnabled(self, value):
        self._useModelHierarchy = value


class _Header(QtWidgets.QHeaderView):
    """A header that allows to display the column options for a USD spreadsheet.

    See also:
        https://www.qt.io/blog/2014/04/11/qt-weekly-5-widgets-on-a-qheaderview
        https://www.qt.io/blog/2012/09/28/qt-support-weekly-27-widgets-on-a-header
        https://www.learnpyqt.com/courses/model-views/qtableview-modelviews-numpy-pandas/
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.section_options = dict()
        self._proxy_labels = dict()  # I've found no other way around this

        for index, columndata in enumerate(_COLUMNS):
            column_options = _ColumnOptions(columndata.name, parent=self)
            column_options.layout().setContentsMargins(0, 0, 0, 0)
            self.section_options[index] = column_options
            self.setMinimumHeight(column_options.sizeHint().height() + 20)

            # we keep track of the column options label but our proxy will bypass clicks
            # allowing for UX when clicking on column headers
            proxy_label = QtWidgets.QLabel(parent=self)
            proxy_label.setText(column_options.label.text())
            proxy_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            self._proxy_labels[column_options.label] = proxy_label

        self.setSectionsMovable(True)
        self.sectionResized.connect(self._handleSectionResized)
        self.sectionMoved.connect(self._handleSectionMoved)

    def _updateOptionsGeometry(self, logical_index: int):
        """Updates the options geometry for the column at the logical index"""
        widget = self.section_options[logical_index]
        geometry = self._geometryForWidget(logical_index)
        widget.setGeometry(*geometry)
        label_geo = widget.label.geometry()
        label_geo.moveTo(widget.pos())
        self._proxy_labels[widget.label].setGeometry(label_geo)

    def _updateVisualSections(self, start_index):
        """Updates all of the sections starting at the given index."""
        for index in range(start_index, self.count()):
            self._updateOptionsGeometry(self.logicalIndex(index))

    def showEvent(self, event:QtGui.QShowEvent):
        for index, widget in self.section_options.items():
            self._updateOptionsGeometry(index)
            # ensure we have readable columns upon show
            self.resizeSection(index, widget.sizeHint().width() + 20)
        super().showEvent(event)

    def _handleSectionResized(self, index):
        self._updateVisualSections(self.visualIndex(index))

        for index, widget in self.section_options.items():
            # if new size is smaller than the width hint half, make options invisible
            vis = widget.minimumSizeHint().width() / 2.0 < self.sectionSize(index)
            widget.setVisible(vis)
            self._proxy_labels[widget.label].setVisible(vis)

    def _handleSectionMoved(self, __, old_visual_index, new_visual_index):
        self._updateVisualSections(min(old_visual_index, new_visual_index))

    def _geometryForWidget(self, index):
        """Main geometry for the widget to show at the given index"""
        return self.sectionViewportPosition(index) + 10, 10, self.sectionSize(index) - 20, self.height() - 20


class _Table(QtWidgets.QTableView):
    def scrollContentsBy(self, dx:int, dy:int):
        super().scrollContentsBy(dx, dy)
        if dx:
            self._fixPositions()

    def _fixPositions(self):
        header = self.horizontalHeader()
        header._updateVisualSections(min(header.section_options))


class Spreadsheet(QtWidgets.QDialog):
    def _toggleColumnVisibility(self, index: int, visible: bool):
        self.table.setColumnHidden(index, not visible)

    def __init__(self, stage=None, parent=None, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.model = model = QtGui.QStandardItemModel(0, len(_COLUMNS))
        header = _Header(QtCore.Qt.Horizontal)
        self.table = table = _Table()

        # for every column, create a proxy model and chain it to the next one
        proxy_model = source_model = model
        model_hierarchy = QtWidgets.QCheckBox("🏡 Model Hierarchy")
        for column_index, columndata in enumerate(_COLUMNS):
            proxy_model = _ProxyModel()
            proxy_model.setSourceModel(source_model)
            proxy_model.setFilterKeyColumn(column_index)
            source_model = proxy_model  # chain so next proxy model takes this one

            column_options = header.section_options[column_index]
            column_options.filterChanged.connect(proxy_model.setFilterRegExp)
            column_options.toggled.connect(partial(self._toggleColumnVisibility, column_index))
            column_options.locked.connect(partial(self._setColumnLocked, column_index))

            if columndata.name == "Type":
                table.setItemDelegateForColumn(column_index, ComboBoxItemDelegate())

            model_hierarchy.toggled.connect(proxy_model._setModelHierarchyEnabled)
            model_hierarchy.clicked.connect(proxy_model.invalidateFilter)

        header.setModel(proxy_model)
        header.setSectionsClickable(True)

        table.setModel(proxy_model)
        table.setHorizontalHeader(header)
        table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.SelectedClicked)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)

        # table options
        sorting_enabled = QtWidgets.QCheckBox("Sorting Enabled")
        sorting_enabled.setChecked(True)
        lock_all = QtWidgets.QPushButton("🔐 Lock All")
        hide_all = QtWidgets.QPushButton("👀 Hide All")

        options_layout = QtWidgets.QHBoxLayout()
        options_layout.addWidget(sorting_enabled)
        options_layout.addWidget(model_hierarchy)
        options_layout.addWidget(lock_all)
        options_layout.addWidget(hide_all)
        options_layout.addStretch()
        sorting_enabled.toggled.connect(table.setSortingEnabled)
        self.sorting_enabled = sorting_enabled

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(options_layout)
        layout.addWidget(table)
        insert_row = QtWidgets.QPushButton("Add Row")
        layout.addWidget(insert_row)
        self.setLayout(layout)
        self.installEventFilter(self)
        self.setStage(stage or Usd.Stage.CreateInMemory())

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
        selection_model = self.table.selectionModel()
        selection = selection_model.selectedIndexes()
        print(f"Selection model indexes: {selection}")

        selected_rows = [i.row() for i in selection]
        selected_columns = [i.column() for i in selection]
        # if selection is not continuous, alert the user and abort instead of
        # trying to figure out what to paste where.
        if len(selection) != len(set(selected_rows)) * len(set(selected_columns)):
            msg = ("To paste with multiple selection,"
                   "cells need to be selected continuously\n"
                   "(no gaps between rows / columns).")
            QtWidgets.QMessageBox.warning(self, "Invalid Paste Selection", msg)
            return

        model = self.table.model()
        print(f"Selected Rows: {selected_rows}")
        print(f"Selected Columns: {selected_columns}")
        current_count = model.rowCount()
        print(f"Current count: {current_count}")
        # selection_model.
        selected_row = min(selected_rows, default=current_count)
        selected_column = min(selected_columns, default=0)
        print(f"selected_row, {selected_row}")
        print(f"selected_column, {selected_column}")
        data = tuple(csv.reader(io.StringIO(text), delimiter=csv.excel_tab.delimiter))
        print(f"data, {data}")
        self.table.setSortingEnabled(False)  # prevent auto sort while adding rows

        maxrow = max(selected_row + len(data) - 1,  # either the amount of rows to paste
                     max(selected_rows, default=current_count))  # or the current row count
        print(f"maxrow, {maxrow}")
        stage = self._stage
        # cycle the data in case that selection to paste on is bigger than source
        table_model = self.table.model()

        # this is a bit broken. When pasting a single row on N non-sequential selected items,
        # we are pasting the same value on all the inbetween non selected rows. please fix
        for visual_row, rowdata in enumerate(itertools.cycle(data), start=selected_row):
            # model.ind
            # table.sele
            # model.data()


            # row_index = visual_row
            if visual_row == current_count:
                # If we are in a filtered place, alert the user if they want to paste rest
                print(f"inserting a row at row_index {visual_row}???")
                # model.insertRow(row_index)
                # time_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                # prim = stage.DefinePrim(f"/root/test_{row_index}_{time_str}")
                # print(prim)
                # self._addPrimToRow(row_index, prim)
            else:

                source_index = _sourceIndex(model.index(visual_row, 0))
                source_item = self.model.itemFromIndex(source_index)
                # model.index
                # prim = self.model.index(row_index, 0).data(QtCore.Qt.UserRole)
                prim = source_item.data(QtCore.Qt.UserRole)
                print("Source model:")
                print(prim)
                # print("Table proxy model:")
                # print(self.table.model().index(row_index, 0).data(QtCore.Qt.UserRole))

                for column_index, column_data in enumerate(rowdata, start=selected_column):
                    # item = model.map
                    # mapped = table_model.mapToSource(table_model.index(row_index, column_index))
                    # _sourceIndex(model.index(visual_row, column_index))
                    # item = model.item(row_index, column_index)
                    s_index = _sourceIndex(model.index(visual_row, column_index))
                    s_item = self.model.itemFromIndex(s_index)
                    assert s_item.data(QtCore.Qt.UserRole) is prim
                    _COLUMNS[column_index].setter(prim, column_data)
                    s_item.setData(column_data, QtCore.Qt.DisplayRole)

            if visual_row == maxrow:
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

    @wait()
    def setStage(self, stage):
        """Sets the USD stage the spreadsheet is looking at."""
        self._stage = stage
        table = self.table
        model = self.model
        model.clear()
        # labels are on the header widgets
        model.setHorizontalHeaderLabels([''] * len(_COLUMNS))
        table.setSortingEnabled(False)
        items = list(enumerate(stage.TraverseAll()))
        model.setRowCount(len(items))
        model.blockSignals(True)  # prevent unneeded events from computing
        for index, prim in enumerate(stage.TraverseAll()):
            self._addPrimToRow(index, prim)
        model.blockSignals(False)
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
        combobox.addItems(list(options.keys()))
        return combobox

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex):
        # get the index of the text in the combobox that matches the current value of the item
        cbox_index = editor.findText(index.data(QtCore.Qt.EditRole))
        if cbox_index:  # if we know about this value, set it already
            editor.setCurrentIndex(cbox_index)

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel, index: QtCore.QModelIndex):
        prim = index.data(QtCore.Qt.UserRole)
        prim.SetTypeName(editor.currentText())
        model.setData(index, editor.currentText(), QtCore.Qt.EditRole)

    # if this was to be an "interactive editing" e.g. a line edit, we'd connect the
    # editingFinished signal to the commitAndCloseEditor method. Mmmm is this needed?
    # def commitAndCloseEditor(self):
    #     editor = self.sender()
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

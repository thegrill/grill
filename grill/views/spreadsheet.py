import io
import csv
import enum
import inspect
import itertools
import contextlib

from typing import NamedTuple
from functools import partial
from collections import Counter

from pxr import Usd, UsdGeom
from PySide2 import QtCore, QtWidgets, QtGui

# {Mesh: UsdGeom.Mesh, Xform: UsdGeom.Xform}
options = dict(x for x in inspect.getmembers(UsdGeom, inspect.isclass) if Usd.Typed in x[-1].mro())


@contextlib.contextmanager
def wait():
    try:
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        yield
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()


class _Column(NamedTuple):
    name: str
    getter: callable
    setter: callable


_COLUMNS = (
    _Column("Name", Usd.Prim.GetName, lambda x, y: x),
    _Column("Path", lambda prim: str(prim.GetPath()), lambda x, y: x),
    _Column("Type", Usd.Prim.GetTypeName, Usd.Prim.SetTypeName),
    _Column("Documentation", Usd.Prim.GetDocumentation, Usd.Prim.SetDocumentation),
    _Column("Hidden", Usd.Prim.IsHidden, Usd.Prim.SetHidden),
)


class _ColumnOptions(enum.Flag):
    """Options that will be available on the header of a table."""
    SEARCH = enum.auto()
    VISIBILITY = enum.auto()
    LOCK = enum.auto()
    ALL = SEARCH | VISIBILITY | LOCK


class _ColumnHeaderOptions(QtWidgets.QWidget):
    """A widget to be used within a header for columns on a USD spreadsheet."""
    def __init__(self, name, options: _ColumnOptions, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()
        options_layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        # Search filter
        line_filter = QtWidgets.QLineEdit()
        line_filter.setPlaceholderText("Filter")
        line_filter.setToolTip(r"Negative lookahead: ^((?!{expression}).)*$")

        # Visibility
        self._vis_button = vis_button = QtWidgets.QPushButton("👀", parent=self)
        vis_button.setCheckable(True)
        vis_button.setChecked(True)
        vis_button.setFlat(True)
        vis_button.setVisible(_ColumnOptions.VISIBILITY in options)

        # Lock
        self._lock_button = lock_button = QtWidgets.QPushButton(parent=self)
        lock_button.setCheckable(True)
        lock_button.setFlat(True)
        lock_button.setVisible(_ColumnOptions.LOCK in options)

        # allow for a bit of extra space with option buttons
        label = QtWidgets.QLabel(f"{name} ", parent=self)
        options_layout.addWidget(label)
        options_layout.addWidget(vis_button)
        options_layout.addWidget(lock_button)
        options_layout.addStretch()
        layout.addLayout(options_layout)
        self._filter_layout = filter_layout = QtWidgets.QFormLayout()
        filter_layout.addRow("🔎", line_filter)
        if _ColumnOptions.SEARCH in options:
            layout.addLayout(filter_layout)
        self._options = options
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
        region = QtGui.QRegion(self._filter_layout.geometry())
        # when buttons are flat, geometry has a small render offset on x
        if _ColumnOptions.LOCK in self._options:
            region += self._lock_button.geometry().adjusted(-2, 0, 2, 0)
        if _ColumnOptions.VISIBILITY in self._options:
            region += self._vis_button.geometry().adjusted(-2, 0, 2, 0)
        self.setMask(region)

    def _decorateLockButton(self, button, locked):
        if locked:
            text = "🔐"
            tip = "Column is non-editable (locked).\nClick to allow edits."
        else:
            text = "🔓"
            tip = "Edits are allowed on this column (unlocked).\nClick to block edits."
        button.setText(text)
        button.setToolTip(tip)

    def _setHidden(self, value):
        self._vis_button.setChecked(not value)


class _ProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # TODO: move model hierarchy filter logic to a different class
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
    def __init__(self, columns, options: _ColumnOptions, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.section_options = dict()
        self._proxy_labels = dict()  # I've found no other way around this

        for index, name in enumerate(columns):
            column_options = _ColumnHeaderOptions(name, options=options, parent=self)
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
            widget.show()
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


class _ComboBoxItemDelegate(QtWidgets.QStyledItemDelegate):
    """
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


class _Spreadsheet(QtWidgets.QDialog):
    def __init__(self, columns, options: _ColumnOptions = _ColumnOptions.ALL, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model = QtGui.QStandardItemModel(0, len(columns))
        header = _Header(columns, options, QtCore.Qt.Horizontal)
        self.table = table = _Table()

        # for every column, create a proxy model and chain it to the next one
        proxy_model = source_model = model

        self._column_options = dict()
        for column_index, column_name in enumerate(columns):
            proxy_model = _ProxyModel()
            proxy_model.setSourceModel(source_model)
            proxy_model.setFilterKeyColumn(column_index)
            source_model = proxy_model  # chain so next proxy model takes this one

            column_options = header.section_options[column_index]
            if _ColumnOptions.SEARCH in options:
                column_options.filterChanged.connect(proxy_model.setFilterRegExp)
            if _ColumnOptions.VISIBILITY in options:
                column_options.toggled.connect(partial(self._setColumnVisibility, column_index))
                column_options._vis_button.clicked.connect(self._conformVisibilitySwitch)
            if _ColumnOptions.LOCK in options:
                column_options.locked.connect(partial(self._setColumnLocked, column_index))
                column_options._lock_button.clicked.connect(self._conformLockSwitch)

            if column_name == "Type":
                table.setItemDelegateForColumn(column_index, _ComboBoxItemDelegate())

            self._column_options[column_index] = column_options
            self._connectProxyModel(proxy_model)  # TODO: only reason of this is model hierarchy. explore to remove soon.

        header.setModel(proxy_model)
        header.setSectionsClickable(True)

        table.setModel(proxy_model)
        table.setHorizontalHeader(header)
        table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.SelectedClicked)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(table)
        self.setLayout(layout)

    def _connectProxyModel(self, proxy_model):
        # TODO: only reason of this is model hierarchy. explore to remove soon.
        pass

    def _setColumnVisibility(self, index: int, visible: bool):
        self.table.setColumnHidden(index, not visible)

    def _setColumnLocked(self, column_index, value):
        model = self.model
        for row_index in range(model.rowCount()):
            item = model.item(row_index, column_index)
            item.setEditable(not value)


class SpreadsheetEditor(_Spreadsheet):
    """TODO:
        - Make paste work with filtered items (paste has been disabled)
        - Per column control on context menu on all vis button
        - Add row creates an anonymous prim
    """
    def __init__(self, stage=None, parent=None, **kwargs):
        columns = [c.name for c in _COLUMNS]
        self._model_hierarchy = model_hierarchy = QtWidgets.QCheckBox("🏡 Model Hierarchy")

        super().__init__(columns, parent=parent, **kwargs)

        hide_key = "👀 Hide All"
        self._vis_states = {"👀 Show All": True, hide_key: False}
        self._vis_key_by_value = {v: k for k, v in self._vis_states.items()}  # True: Show All
        self._vis_all = vis_all = QtWidgets.QPushButton(hide_key)
        vis_all.clicked.connect(self._conformVisibility)
        lock_key = "🔐 Lock All"
        self._lock_states = {lock_key: True, "🔓 Unlock All": False}
        self._lock_key_by_value = {v: k for k, v in self._lock_states.items()}  # True: Lock All
        self._lock_all = lock_all = QtWidgets.QPushButton(lock_key)
        lock_all.clicked.connect(self._conformLocked)

        # table options
        sorting_enabled = QtWidgets.QCheckBox("Sorting Enabled")
        sorting_enabled.setChecked(True)

        options_layout = QtWidgets.QHBoxLayout()
        options_layout.addWidget(sorting_enabled)
        options_layout.addWidget(model_hierarchy)
        options_layout.addWidget(vis_all)
        options_layout.addWidget(lock_all)
        options_layout.addStretch()
        sorting_enabled.toggled.connect(self.table.setSortingEnabled)
        self.sorting_enabled = sorting_enabled

        layout = self.layout()
        layout.addLayout(options_layout)
        layout.addWidget(self.table)
        insert_row = QtWidgets.QPushButton("Add Row")
        layout.addWidget(insert_row)
        self.installEventFilter(self)
        self.setStage(stage or Usd.Stage.CreateInMemory())
        self.setWindowTitle("Spreadsheet Editor")

    def _connectProxyModel(self, proxy_model):
        super()._connectProxyModel(proxy_model)
        self._model_hierarchy.toggled.connect(proxy_model._setModelHierarchyEnabled)
        self._model_hierarchy.clicked.connect(proxy_model.invalidateFilter)

    def _conformVisibilitySwitch(self):
        """Make vis option offer inverse depending on how much is currently hidden"""
        counter = Counter(self.table.isColumnHidden(i) for i in self._column_options)
        current, count = next(iter(counter.most_common(1)))
        self._vis_all.setText(self._vis_key_by_value[current])

    def _conformVisibility(self):
        value = self._vis_states[self._vis_all.text()]
        for index, options in self._column_options.items():
            self._setColumnVisibility(index, value)
            options._setHidden(not value)

        self._vis_all.setText(self._vis_key_by_value[not value])
        self.table.horizontalHeader()._handleSectionResized(0)

    def _conformLockSwitch(self):
        """Make lock option offer inverse depending on how much is currently locked"""
        counter = Counter(widget._lock_button.isChecked() for widget in self._column_options.values())
        current, count = next(iter(counter.most_common(1)))
        self._lock_all.setText(self._lock_key_by_value[not current])

    @wait()
    def _conformLocked(self):
        value = self._lock_states[self._lock_all.text()]
        for index, options in self._column_options.items():
            options._lock_button.setChecked(value)
            self._setColumnLocked(index, value)
        self._lock_all.setText(self._lock_key_by_value[not value])

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.KeyPress and event.matches(QtGui.QKeySequence.Copy):
            self._copySelection()
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
        print("Coming soon!")
        return
        stage = self._stage
        # cycle the data in case that selection to paste on is bigger than source
        table_model = self.table.model()

        # this is a bit broken. When pasting a single row on N non-sequential selected items,
        # we are pasting the same value on all the inbetween non selected rows. please fix
        def _sourceIndex(index):
            """Recursively get the source index of a proxy model index"""
            source_model = index.model()
            if isinstance(source_model, _ProxyModel):
                return _sourceIndex(source_model.mapToSource(index))
            else:
                return index

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

    def _copySelection(self):
        selection = self.table.selectedIndexes()
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


if __name__ == "__main__":
    """ Run the application. """
    import sys
    app = QtWidgets.QApplication(sys.argv)

    stage = Usd.Stage.Open(r"B:\read\cg\downloads\Kitchen_set\Kitchen_set\Kitchen_set.usd")
    # # stage = Usd.Stage.Open(r"B:\read\cg\downloads\UsdSkelExamples\UsdSkelExamples\HumanFemale\HumanFemale.walk.usd")
    # # stage = Usd.Stage.Open(r"B:\read\cg\downloads\PointInstancedMedCity\PointInstancedMedCity.usd")
    spreadsheet = SpreadsheetEditor()
    spreadsheet.setStage(stage)
    spreadsheet.show()
    sys.exit(app.exec_())

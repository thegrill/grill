import io
import csv
import enum
import typing
import inspect
import logging
import operator
import textwrap
import itertools
from collections import Counter
from functools import partial, lru_cache

from pxr import Usd, UsdGeom, Sdf
from PySide2 import QtCore, QtWidgets, QtGui

from . import _core

logger = logging.getLogger(__name__)

# {Mesh: UsdGeom.Mesh, Xform: UsdGeom.Xform}
# TODO: add more types here
_PRIM_TYPE_OPTIONS = dict(x for x in inspect.getmembers(UsdGeom, inspect.isclass) if Usd.Typed in x[-1].mro())


def _prim_type_combobox(parent, option, index):
    # TODO: see if we can lru_cache as well
    combobox = QtWidgets.QComboBox(parent=parent)
    combobox.addItems(sorted(_PRIM_TYPE_OPTIONS))
    return combobox


@lru_cache(maxsize=None)
def _traverse_predicate(*, model_hierarchy: bool = False, instance_proxies: bool = False):
    predicate = Usd.PrimIsModel if model_hierarchy else Usd.PrimAllPrimsPredicate
    return Usd.TraverseInstanceProxies(predicate) if instance_proxies else predicate


@lru_cache(maxsize=None)
def _filter_predicate(*, orphaned, classes, defined, active, inactive, logical_op):
    def specifier(prim):
        is_class = prim.IsAbstract()
        is_defined = prim.IsDefined()
        return ((classes and is_class) or
                (orphaned and not is_defined) or
                (defined and is_defined and not is_class))

    def status(prim):
        is_active = prim.IsActive()
        return (active and is_active) or (inactive and not is_active)

    return lambda prim: logical_op(specifier(prim), status(prim))


def _common_paths(paths):
    """For the given paths, get those which are the common parents."""
    unique = list()
    for path in sorted(filter(lambda p: p and not p.IsAbsoluteRootPath(), paths)):
        if unique and path.HasPrefix(unique[-1]):  # we're a child, so safe to continue.
            continue
        unique.append(path)
    return unique


def _pruned_prims(prim_range, predicate):
    """Convenience generator that prunes a prim range based on the given predicate"""
    for prim in prim_range:
        if predicate(prim):
            prim_range.PruneChildren()
        yield prim


def _iprims(stage, root_paths=None, prune_predicate=None, traverse_predicate=Usd.PrimDefaultPredicate):
    if root_paths:  # Traverse only specific parts of the stage.
        root_paths = _common_paths(root_paths)
        # Usd.PrimRange already discards invalid prims, so no need to check.
        root_prims = map(stage.GetPrimAtPath, root_paths)
        ranges = (Usd.PrimRange(prim, traverse_predicate) for prim in root_prims)
    else:
        ranges = [Usd.PrimRange.Stage(stage, traverse_predicate)]

    if prune_predicate:
        ranges = (_pruned_prims(iter(r), prune_predicate) for r in ranges)

    return itertools.chain.from_iterable(ranges)


@lru_cache(maxsize=None)
def _prim_font(*, abstract=False, orphaned=False):
    # Passing arguments via the constructor does not work even though docs say they should
    font = QtGui.QFont()
    # Abstract prims are also considered defined; since we want to distinguish abstract
    # defined prims from non-abstract defined prims, we check for abstract first.
    if abstract:
        font.setWeight(QtGui.QFont.ExtraLight)
        font.setLetterSpacing(QtGui.QFont.PercentageSpacing, 120)
    elif orphaned:
        font.setWeight(QtGui.QFont.Light)
        font.setItalic(True)
    else:
        font.setWeight(QtGui.QFont.Normal)
    return font


class _Column(typing.NamedTuple):
    name: str
    getter: callable = None
    setter: callable = None
    editor: callable = None


class _ColumnOptions(enum.Flag):
    """Options that will be available on the header of a table."""
    NONE = enum.auto()
    SEARCH = enum.auto()
    VISIBILITY = enum.auto()
    LOCK = enum.auto()
    ALL = SEARCH | VISIBILITY | LOCK


class _PrimTextColor(enum.Enum):
    NONE = None
    INSTANCE = QtGui.QColor('lightskyblue')
    PROTOTYPE = QtGui.QColor('cornflowerblue')
    INACTIVE = QtGui.QColor('darkgray')
    INACTIVE_ARCS = QtGui.QColor('orange').darker(150)
    ARCS = QtGui.QColor('orange')


class _ColumnItemDelegate(QtWidgets.QStyledItemDelegate):
    """
    https://doc.qt.io/qtforpython/overviews/sql-presenting.html
    https://doc.qt.io/qtforpython/overviews/qtwidgets-itemviews-spinboxdelegate-example.html
    """

    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        creator = self.parent()._columns_spec[index.column()].editor or super().createEditor
        return creator(parent, option, index)


class _EmptyItemDelegate(_ColumnItemDelegate):
    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel, index: QtCore.QModelIndex):
        setter = self.parent()._columns_spec[index.column()].setter or super().setModelData
        return setter(editor, model, index)


class _ColumnHeaderOptions(QtWidgets.QWidget):
    """A widget to be used within a header for columns on a USD spreadsheet.

    """
    def __init__(self, name, options: _ColumnOptions, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()
        options_layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        # Search filter
        self._line_filter = line_filter = QtWidgets.QLineEdit()
        line_filter.setPlaceholderText("Filter")
        # TODO: add functionality for "inverse regex"
        line_filter.setToolTip(r"Negative lookahead: ^((?!{expression}).)*$")

        # Visibility
        self._vis_button = vis_button = QtWidgets.QPushButton(_core._EMOJI.VISIBILITY.value)
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
        filter_layout.addRow(_core._EMOJI.SEARCH.value, line_filter)
        if _ColumnOptions.SEARCH in options:
            layout.addLayout(filter_layout)
        self._options = options
        self._decorateLockButton(lock_button, lock_button.isChecked())
        lock_button.toggled.connect(partial(self._decorateLockButton, lock_button))

        # set visibility after widgets are added to our layout
        vis_button.setVisible(_ColumnOptions.VISIBILITY in options)
        lock_button.setVisible(_ColumnOptions.LOCK in options)

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
        region = QtGui.QRegion(self.frameGeometry())
        if _ColumnOptions.SEARCH in self._options:
            region += QtGui.QRegion(self._filter_layout.geometry())
        # when buttons are flat, geometry has a small render offset on x
        if _ColumnOptions.LOCK in self._options:
            region += self._lock_button.geometry().adjusted(-2, 0, 2, 0)
        if _ColumnOptions.VISIBILITY in self._options:
            region += self._vis_button.geometry().adjusted(-2, 0, 2, 0)
        self.setMask(region)

    def _decorateLockButton(self, button, locked):
        if locked:
            text = _core._EMOJI.LOCK.value
            tip = "Column is non-editable (locked).\nClick to allow edits."
        else:
            text = _core._EMOJI.UNLOCK.value
            tip = "Edits are allowed on this column (unlocked).\nClick to block edits."
        button.setText(text)
        button.setToolTip(tip)

    def _setHidden(self, value):
        self._vis_button.setChecked(not value)


class EmptyTableModel(QtGui.QStandardItemModel):
    """Minimal empty table for new data (unlike existing USD stages or layers).

    This is a "transient" model which will eventually have data translated into USD.
    """
    def __init__(self, columns, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._columns_spec = columns
        self._locked_columns = set()  # TODO: make sure this plays well with this and USD table
        self.setHorizontalHeaderLabels([''] * len(columns))


class _ObjectTableModel(QtCore.QAbstractTableModel):
    """Table model objects whose getters / setters are provided via columns.

    Mainly used for USD objects like layers or prims.
    """

    def __init__(self, columns, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._columns_spec = columns
        self._locked_columns = set()
        self._objects = []

    def rowCount(self, parent:QtCore.QModelIndex=...) -> int:
        return len(self._objects)

    def columnCount(self, parent:QtCore.QModelIndex=...) -> int:
        return len(self._columns_spec)

    def data(self, index:QtCore.QModelIndex, role:int=...) -> typing.Any:
        if role == _core._QT_OBJECT_DATA_ROLE:  # raw data
            return self._objects[index.row()]
        elif role == QtCore.Qt.DisplayRole:
            obj = self.data(index, role=_core._QT_OBJECT_DATA_ROLE)
            return self._columns_spec[index.column()].getter(obj)
        elif role == QtCore.Qt.EditRole:
            obj = self.data(index, role=_core._QT_OBJECT_DATA_ROLE)
            return self._columns_spec[index.column()].getter(obj)

    def sort(self, column:int, order:QtCore.Qt.SortOrder=...) -> None:
        self.layoutAboutToBeChanged.emit()
        key = self._columns_spec[column].getter
        reverse = order == QtCore.Qt.SortOrder.AscendingOrder
        try:
            self._objects = sorted(self._objects, key=key, reverse=reverse)
        finally:
            self.layoutChanged.emit()

    def setData(self, index:QtCore.QModelIndex, value:typing.Any, role:int=...) -> bool:
        obj = self.data(index, role=_core._QT_OBJECT_DATA_ROLE)
        result = self._columns_spec[index.column()].setter(obj, value)
        print(f"Result: {result}")
        # self.dataChanged.emit(topLeft, bottomRight)  # needed?
        return True


class _ProxyModel(QtCore.QSortFilterProxyModel):
    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        """For a vertical header, display a sequential visual index instead of the logical from the model."""
        # https://www.walletfox.com/course/qsortfilterproxymodelexample.php
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Vertical:
                return section + 1
            elif orientation == QtCore.Qt.Horizontal:
                return ""  # our horizontal header labels are drawn by custom header
        return super().headerData(section, orientation, role)

    def sort(self, column: int, order: QtCore.Qt.SortOrder = QtCore.Qt.AscendingOrder) -> None:
        self.sourceModel().sort(column, order)


class StageTableModel(_ObjectTableModel):
    """This model provides flexibility for:

    - Specifying traversal method
    - Specifying root prims to traverse
    - Specifying prim paths to prune from traversal
    - Filtering prims based on a provided predicate
    """
    # https://doc.qt.io/qtforpython/PySide6/QtCore/QAbstractItemModel.html
    # https://doc.qt.io/qtforpython/overviews/qtwidgets-itemviews-pixelator-example.html#pixelator-example
    # I tried to implement fetchMore for 250k+ prims (for filtering operations) but
    # it's not as pleasant experience and filtering first on path is a better tactic.
    # https://doc.qt.io/qt-5/qtwidgets-itemviews-fetchmore-example.html
    def __init__(self, columns, *args, **kwargs):
        super().__init__(columns, *args, **kwargs)
        self._stage = None
        self._root_paths = set()
        self._prune_children = set()
        self._filter_predicate = None
        self._traverse_predicate = Usd.PrimAllPrimsPredicate

    @property
    def _prune_predicate(self):
        def prune(prim):
            path = prim.GetPath()
            return any(path.HasPrefix(p) for p in self._prune_children)
        return prune

    @property
    def stage(self):
        return self._stage

    @stage.setter
    def stage(self, value):
        self.beginResetModel()
        self._stage = value
        if value:
            prims = _iprims(
                value,
                root_paths=self._root_paths,
                prune_predicate=self._prune_predicate if self._prune_children else None,
                traverse_predicate=self._traverse_predicate
            )
            self._objects = list(filter(self._filter_predicate, prims))
        else:
            self._objects = []
        self.endResetModel()

    def data(self, index:QtCore.QModelIndex, role:int=...) -> typing.Any:
        # Keep consistency with USDView visual style
        if role == QtCore.Qt.ForegroundRole:
            prim = self.data(index, role=_core._QT_OBJECT_DATA_ROLE)
            active = prim.IsActive()
            if prim.IsInstance():
                color = _PrimTextColor.INSTANCE
            elif prim.IsInPrototype() or prim.IsInstanceProxy():
                color = _PrimTextColor.PROTOTYPE
            elif (
                prim.HasAuthoredReferences() or
                prim.HasAuthoredPayloads() or
                prim.HasAuthoredInherits() or
                prim.HasAuthoredSpecializes() or
                prim.HasVariantSets()
            ):
                color = _PrimTextColor.ARCS if active else _PrimTextColor.INACTIVE_ARCS
            elif not active:
                color = _PrimTextColor.INACTIVE
            else:
                color = _PrimTextColor.NONE
            return color.value
        elif role == QtCore.Qt.FontRole:
            # Keep similar USDView visual style, just  don't "bold" defined prims.
            prim = self.data(index, role=_core._QT_OBJECT_DATA_ROLE)
            return _prim_font(abstract=prim.IsAbstract(), orphaned=not prim.IsDefined())
        return super().data(index, role)

    def flags(self, index:QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        flags = super().flags(index)
        col_index = index.column()
        # only allow edits when:
        if (col_index not in self._locked_columns  # column is unlocked
            and self._columns_spec[col_index].setter  # a setter has been provided
            and not self._objects[index.row()].IsInstanceProxy()  # Not an instance proxy
        ):
            return flags | QtCore.Qt.ItemIsEditable
        return flags


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
        self.sectionClicked.connect(self._handleSectionClicked)

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

    def _handleSectionClicked(self, index):
        """Without this, when a section is clicked (e.g. when sorting),
        we'd have a mismatch on the proxy geometry label.
        """
        self._handleSectionResized(0)
        self._updateVisualSections(0)

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


class _Spreadsheet(QtWidgets.QDialog):
    """TODO:
        - Make paste work with filtered items (paste has been disabled)
        - Setting a prim as instanceable invalidates child prims.
            - Quickest workaround is to invalidate model?
    """
    def __init__(self, model, columns, options: _ColumnOptions = _ColumnOptions.ALL, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model
        self._columns_spec = columns
        header = _Header([col.name for col in columns], options, QtCore.Qt.Horizontal)
        self.table = table = _Table()

        # TODO: item delegate per model type? For now it works ):<
        column_delegate_cls = _ColumnItemDelegate if isinstance(model, _ObjectTableModel) else _EmptyItemDelegate
        self._column_options = header.section_options

        # for every column, create a proxy model and chain it to the next one
        for column_index, column_data in enumerate(columns):
            proxy_model = _ProxyModel()
            proxy_model.setSourceModel(model)
            proxy_model.setFilterKeyColumn(column_index)

            column_options = header.section_options[column_index]
            if _ColumnOptions.SEARCH in options:
                column_options.filterChanged.connect(proxy_model.setFilterRegularExpression)
            if _ColumnOptions.VISIBILITY in options:
                column_options.toggled.connect(partial(self._setColumnVisibility, column_index))

            if _ColumnOptions.LOCK in options:
                column_options.locked.connect(partial(self._setColumnLocked, column_index))

            delegate = column_delegate_cls(parent=self)
            table.setItemDelegateForColumn(column_index, delegate)

            model = proxy_model

        header.setModel(model)
        header.setSectionsClickable(True)

        table.setModel(model)
        table.setHorizontalHeader(header)
        table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.SelectedClicked)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        table.setSortingEnabled(True)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(table)
        self.installEventFilter(self)
        self.setLayout(layout)

    def _setColumnVisibility(self, index: int, visible: bool):
        self.table.setColumnHidden(index, not visible)

    def _setColumnLocked(self, column_index, value):
        method = set.add if value else set.discard
        method(self.model._locked_columns, column_index)

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.KeyPress and event.matches(QtGui.QKeySequence.Copy):
            self._copySelection()
        elif event.type() == QtCore.QEvent.KeyPress and event.matches(QtGui.QKeySequence.Paste):
            with Sdf.ChangeBlock():
                self._pasteClipboard()

        return super().eventFilter(source, event)

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

    def _pasteClipboard(self):
        text = QtWidgets.QApplication.instance().clipboard().text()
        logger.info(f"Creating rows with:\n{text}")
        if not text:
            logger.info("Nothing to do!")
            return
        selection_model = self.table.selectionModel()
        selection = selection_model.selectedIndexes()
        logger.info(f"Selection model indexes: {selection}")

        selected_rows = {i.row() for i in selection}
        selected_columns = {i.column() for i in selection}
        # if selection is not continuous, alert the user and abort instead of
        # trying to figure out what to paste where.
        if len(selection) != len(selected_rows) * len(selected_columns):
            msg = ("To paste with multiple selection,"
                   "cells need to be selected continuously\n"
                   "(no gaps between rows / columns).")
            QtWidgets.QMessageBox.warning(self, "Invalid Paste Selection", msg)
            return

        model = self.table.model()
        current_count = model.rowCount()

        logger.info(f"Selected Rows: {selected_rows}")
        logger.info(f"Selected Columns: {selected_columns}")
        logger.info(f"Current count: {current_count}")
        # selection_model.
        selected_row = min(selected_rows, default=current_count)
        selected_column = min(selected_columns, default=0)
        logger.info(f"selected_row, {selected_row}")
        logger.info(f"selected_column, {selected_column}")
        data = tuple(csv.reader(io.StringIO(text), delimiter=csv.excel_tab.delimiter))
        logger.info(f"data, {data}")

        len_data = len(data)
        single_row_source = len_data == 1
        # if data rows are more than 1, we do not allow for gaps on the selected rows to paste.
        if not single_row_source and len_data != len(range(selected_row, max(selected_rows, default=current_count)+1)):
            msg = ("Clipboard data contains multiple rows,"
                   "in order to paste this content, row cells need to be selected continuously\n"
                   "(no gaps between them).")
            QtWidgets.QMessageBox.warning(self, "Invalid Paste Selection", msg)
            return

        orig_sort_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)  # prevent auto sort while adding rows

        maxrow = max(selected_row + len(data),  # either the amount of rows to paste
                     max(selected_rows, default=current_count) + 1)  # or the current row count
        print(f"maxrow, {maxrow}")

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
            if visual_row > maxrow:
                print(f"Visual row {visual_row} maxed maxrow {maxrow}. Stopping. Bye!")
                break
            if single_row_source and visual_row not in selected_rows:
                print(f"Visual row {visual_row} not in selected rows {selected_rows}. Continue")
                continue

            print(f"visual_row={visual_row}")
            print(f"pasting data={rowdata}")

            if visual_row == current_count:
                # we're at the end of the rows.
                # If we are in a filtered place, alert the user if they want to paste rest
                print(f"inserting a row at row_index {visual_row}???")
                # model.insertRow(row_index)
                # time_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                # prim = stage.DefinePrim(f"/root/test_{row_index}_{time_str}")
                # print(prim)
                # self._addPrimToRow(row_index, prim)
            else:
                # model.data(index, )
                prim = model.data(model.index(visual_row, 0), _core._QT_OBJECT_DATA_ROLE)
                # source_index = _sourceIndex(model.index(visual_row, 0))
                # if isinstance(source_index.model(), _ObjectTableModel):
                #     prim =
                # source_item = self.model.itemFromIndex(source_index)
                # # prim = self.model.index(row_index, 0).data(QtCore.Qt.UserRole)
                #
                # prim = source_item.data(_core._QT_OBJECT_DATA_ROLE)
                # print("Source model:")
                print(prim)
                # print("Table proxy model:")
                # print(self.table.model().index(row_index, 0).data(QtCore.Qt.UserRole))

                for column_index, column_data in enumerate(rowdata, start=selected_column):
                    # item = model.map
                    # mapped = table_model.mapToSource(table_model.index(row_index, column_index))
                    # _sourceIndex(model.index(visual_row, column_index))
                    # item = model.item(row_index, column_index)
                    # s_index = _sourceIndex(model.index(visual_row, column_index))
                    # s_item = self.model.itemFromIndex(s_index)
                    # assert s_item.data(_core._QT_OBJECT_DATA_ROLE) is prim

                    setter = self._columns_spec[column_index].setter
                    if prim:
                        if not setter:
                            print(f"Skipping since missing setter: {column_data}")
                            continue
                        print(f"Setting {column_data} with type {type(column_data)} on {prim}")
                        try:
                            setter(prim, column_data)
                        except Exception as exc:
                            print(exc)
                            import json  # big hack. how to?
                            # due to boolean types
                            column_data = json.loads(column_data.lower())
                            print(f"Attempting to parse an {column_data} with type {type(column_data)} on {prim}")
                            setter(prim, column_data)
                    else:
                        s_index = _sourceIndex(model.index(visual_row, column_index))
                        s_item = self.model.itemFromIndex(s_index)
                        s_item.setData(column_data, QtCore.Qt.DisplayRole)

        self.table.setSortingEnabled(orig_sort_enabled)


class _StageSpreadsheet(_Spreadsheet):
    """TODO:
            - Allow to filter via type inheritance
            - Allow setting root paths from selected paths
    """
    def __init__(self, columns, options: _ColumnOptions = _ColumnOptions.ALL, *args, **kwargs):
        model = StageTableModel(columns=columns)
        super().__init__(model=model, columns=columns, options=options, *args, **kwargs)
        self._model_hierarchy = model_hierarchy = QtWidgets.QPushButton(_core._EMOJI.MODEL_HIERARCHY.value)
        self._filter_predicate = None
        model_hierarchy.setToolTip(
            textwrap.dedent(f"""
                {_core._EMOJI.MODEL_HIERARCHY.value} Valid Model Hierarchy:
    
                The model hierarchy defines a contiguous set of prims descending from a root prim on a stage, all of which are models.
                This means that each prim in the hierarchy is considered "important to consumers".
                """
                    )
        )
        self._instances = instances = QtWidgets.QPushButton(
            _core._EMOJI.INSTANCE_PROXIES.value)
        instances.setToolTip(
            textwrap.dedent(f"""
                {_core._EMOJI.INSTANCE_PROXIES.value} Traverse Instance Proxies:
                
                An instance proxy is a UsdPrim that represents a descendant prim beneath an instance.
                An instance proxy can not be edited. If edits are required, the parent prim makred as "instanceable=True" must
                be updated with "instanceable=False".
                """
                    )
        )
        self._orphaned = orphaned = QtWidgets.QPushButton(_core._EMOJI.ORPHANED.value)
        orphaned.setToolTip(f"{_core._EMOJI.ORPHANED.value} Orphaned Prims")
        self._classes = classes = QtWidgets.QPushButton(_core._EMOJI.CLASSES.value)
        classes.setToolTip(f"{_core._EMOJI.CLASSES.value} Classes (Abstract Prims)")
        self._defined = defined = QtWidgets.QPushButton(_core._EMOJI.DEFINED.value)
        defined.setToolTip(f"{_core._EMOJI.DEFINED.value} Defined Prims")
        self._active = active = QtWidgets.QPushButton(_core._EMOJI.ACTIVE.value)
        active.setToolTip(f"{_core._EMOJI.ACTIVE.value}")
        self._inactive = inactive = QtWidgets.QPushButton(_core._EMOJI.INACTIVE.value)
        inactive.setToolTip(f"{_core._EMOJI.INACTIVE.value}")

        for each in (
        model_hierarchy, instances, orphaned, classes, defined, active, inactive):
            each.setCheckable(True)
            each.clicked.connect(self._update_stage)

        for each in (model_hierarchy, instances, defined, active):
            each.setChecked(True)

        def _buttons_on_frame(*buttons):
            frame = QtWidgets.QFrame()
            layout = QtWidgets.QHBoxLayout()
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setMargin(0)
            for button in buttons:
                layout.addWidget(button)
            frame.setLayout(layout)
            return frame

        prim_traversal_frame = _buttons_on_frame(model_hierarchy, instances)
        prim_specifier_frame = _buttons_on_frame(orphaned, classes, defined)
        prim_status_frame = _buttons_on_frame(active, inactive)

        hide_key = f"{_core._EMOJI.VISIBILITY.value} Hide All"
        self._vis_states = {f"{_core._EMOJI.VISIBILITY.value} Show All": True, hide_key: False}
        self._vis_key_by_value = {v: k for k, v in self._vis_states.items()}  # True: Show All
        self._vis_all = vis_all = QtWidgets.QPushButton(hide_key)

        lock_key = f"{_core._EMOJI.LOCK.value} Lock All"
        self._lock_states = {lock_key: True, f"{_core._EMOJI.UNLOCK.value} Unlock All": False}
        self._lock_key_by_value = {v: k for k, v in self._lock_states.items()}  # True: Lock All
        self._lock_all = lock_all = QtWidgets.QPushButton(lock_key)

        # table options
        sorting_enabled = QtWidgets.QCheckBox("Sorting")
        sorting_enabled.setChecked(True)

        options_layout = QtWidgets.QHBoxLayout()
        options_layout.addWidget(prim_traversal_frame)
        options_layout.addWidget(prim_specifier_frame)

        self._filters_logical_op = filters_logical_op = QtWidgets.QComboBox()
        for op in (operator.and_, operator.or_):
            op_text = op.__name__.strip("_")
            filters_logical_op.addItem(op_text, userData=op)
        self._filters_logical_op.currentIndexChanged.connect(self._update_stage)

        options_layout.addWidget(filters_logical_op)
        options_layout.addWidget(prim_status_frame)

        options_layout.addWidget(sorting_enabled)
        if _ColumnOptions.VISIBILITY in options:
            vis_all.clicked.connect(self._conformVisibility)
            options_layout.addWidget(vis_all)
        if _ColumnOptions.LOCK in options:
            lock_all.clicked.connect(self._conformLocked)
            options_layout.addWidget(lock_all)
        options_layout.addStretch()
        sorting_enabled.toggled.connect(self.table.setSortingEnabled)
        self.sorting_enabled = sorting_enabled

        layout = self.layout()
        layout.addLayout(options_layout)
        layout.addWidget(self.table)
        self.setWindowTitle("Spreadsheet Editor")

        # these are here because of the "higher level methods"
        for column_index, column_options in self._column_options.items():
            # TODO: move this to be "public" signals
            column_options._vis_button.clicked.connect(self._conformVisibilitySwitch)
            column_options._lock_button.clicked.connect(self._conformLockSwitch)

    def _conformVisibilitySwitch(self):
        """Make vis option offer inverse depending on how much is currently hidden"""
        counter = Counter(self.table.isColumnHidden(i) for i in self._column_options)
        current, count = next(iter(counter.most_common(1)))
        self._vis_all.setText(self._vis_key_by_value[current])
        return current

    def _conformLockSwitch(self):
        """Make lock option offer inverse depending on how much is currently locked"""
        counter = Counter(widget._lock_button.isChecked() for widget in self._column_options.values())
        current, count = next(iter(counter.most_common(1)))
        self._lock_all.setText(self._lock_key_by_value[not current])
        return current

    def _conformVisibility(self):
        value = self._vis_states[self._vis_all.text()]
        for index, options in self._column_options.items():
            self._setColumnVisibility(index, value)
            options._setHidden(not value)

        self._vis_all.setText(self._vis_key_by_value[not value])
        self.table.horizontalHeader()._handleSectionResized(0)

    @_core.wait()
    def _conformLocked(self):
        value = self._lock_states[self._lock_all.text()]
        for index, options in self._column_options.items():
            options._lock_button.setChecked(value)
            self._setColumnLocked(index, value)
        self._lock_all.setText(self._lock_key_by_value[not value])

    @property
    def stage(self):
        return self.model.stage

    @stage.setter
    def stage(self, value):
        self._update_stage(stage=value)

    def setStage(self, stage):  # TODO: remove in favor of property
        """Sets the USD stage the spreadsheet is looking at."""
        self._update_stage(stage=stage)

    @_core.wait()
    def _update_stage(self, *args, stage=None):
        filter_predicate = _filter_predicate(
            orphaned=self._orphaned.isChecked(),
            classes=self._classes.isChecked(),
            defined=self._defined.isChecked(),
            active=self._active.isChecked(),
            inactive=self._inactive.isChecked(),
            logical_op=self._filters_logical_op.currentData(QtCore.Qt.UserRole)
        )
        if self._filter_predicate:
            self.model._filter_predicate = lambda prim: self._filter_predicate(prim) and filter_predicate(prim)
        else:
            self.model._filter_predicate = filter_predicate

        self.model._traverse_predicate = _traverse_predicate(
            model_hierarchy=self._model_hierarchy.isChecked(),
            instance_proxies=self._instances.isChecked(),
        )
        self.model.stage = stage if stage else self.model.stage


class SpreadsheetEditor(_StageSpreadsheet):
    def __init__(self, *args, **kwargs):
        def _vis_value(prim):
            # keep homogeneus array by returning a value of the same type for prims
            # that are not imageable (e.g. untyped prims)
            imageable = UsdGeom.Imageable(prim)
            return imageable.GetVisibilityAttr().Get() if imageable else ""
        columns = (
            _Column("Path", lambda prim: str(prim.GetPath())),
            _Column("Name", Usd.Prim.GetName),
            _Column("Type", Usd.Prim.GetTypeName, Usd.Prim.SetTypeName, editor=_prim_type_combobox),
            _Column("Documentation", Usd.Prim.GetDocumentation,
                    Usd.Prim.SetDocumentation),
            _Column("Instanceable", Usd.Prim.IsInstance, Usd.Prim.SetInstanceable),
            _Column("Visibility", _vis_value),
            _Column("Hidden", Usd.Prim.IsHidden, Usd.Prim.SetHidden),
        )
        super().__init__(columns=columns, *args, **kwargs)

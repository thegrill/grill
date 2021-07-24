import io
import csv
import enum
import typing
import inspect
import logging
import itertools
import contextlib

from typing import NamedTuple
from collections import Counter
from functools import partial, lru_cache

from pxr import Usd, UsdGeom, Sdf
from PySide2 import QtCore, QtWidgets, QtGui

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _emoji_suffix():
    # Maya widgets strip the last character of widgets with emoji on them.
    # Remove this workaround when QtWidgets.QLabel("🔎 Hello") does not show as "🔎 Hell".
    text_test = "🔎 Hello"
    return "" if QtWidgets.QLabel(text_test).text() == text_test else " "


class _ColumnOptions(enum.Flag):
    """Options that will be available on the header of a table."""
    NONE = enum.auto()
    SEARCH = enum.auto()
    VISIBILITY = enum.auto()
    LOCK = enum.auto()
    ALL = SEARCH | VISIBILITY | LOCK


class _Column(NamedTuple):
    name: str
    getter: callable
    setter: callable = lambda x, y: x  # "Read-only" by default


class _ColumnHeaderOptions(QtWidgets.QWidget):
    """A widget to be used within a header for columns on a USD spreadsheet."""
    def __init__(self, name, options: _ColumnOptions, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()
        options_layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        # Search filter
        self._line_filter = line_filter = QtWidgets.QLineEdit()
        line_filter.setPlaceholderText("Filter")
        line_filter.setToolTip(r"Negative lookahead: ^((?!{expression}).)*$")

        # Visibility
        self._vis_button = vis_button = QtWidgets.QPushButton(f"👀{_emoji_suffix()}")
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
        filter_layout.addRow(f"🔎{_emoji_suffix()}", line_filter)
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
            text = "🔐"
            tip = "Column is non-editable (locked).\nClick to allow edits."
        else:
            text = "🔓"
            tip = "Edits are allowed on this column (unlocked).\nClick to block edits."
        button.setText(f"{text}{_emoji_suffix()}")
        button.setToolTip(tip)

    def _setHidden(self, value):
        self._vis_button.setChecked(not value)


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
            proxy_label.setText(f"{column_options.label.text()}{_emoji_suffix()}")
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


# Agreement: raw data accessible here
_USD_DATA_ROLE = QtCore.Qt.UserRole + 1


class StageTableModel(QtCore.QAbstractTableModel):
    # https://doc.qt.io/qtforpython/PySide6/QtCore/QAbstractItemModel.html
    # https://doc.qt.io/qtforpython/overviews/qtwidgets-itemviews-pixelator-example.html#pixelator-example
    # I tried to implement fetchMore for 250k+ prims (for filtering operations) but
    # it's not as pleasant experience and filtering first on path is a better tactic.
    # https://doc.qt.io/qt-5/qtwidgets-itemviews-fetchmore-example.html

    def __init__(self, columns, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._columns_spec = columns
        self._stage = None
        self._prims = []
        self._locked_columns = set()

    @property
    def stage(self):
        return self._stage

    @stage.setter
    def stage(self, value):
        self.beginResetModel()
        self._stage = value
        flags = Usd.PrimIsLoaded & ~Usd.PrimIsAbstract
        self._prims = list(Usd.PrimRange.Stage(self.stage, flags))
        self.endResetModel()

    def rowCount(self, parent:QtCore.QModelIndex=...) -> int:
        return len(self._prims)

    def columnCount(self, parent:QtCore.QModelIndex=...) -> int:
        return len(self._columns_spec)

    def data(self, index:QtCore.QModelIndex, role:int=...) -> typing.Any:
        if not index.isValid():
            return None
        elif role == _USD_DATA_ROLE:  # raw data
            return self._prims[index.row()]
        elif role != QtCore.Qt.DisplayRole:
            return None
        prim = self._prims[index.row()]
        return self._columns_spec[index.column()].getter(prim)

    def sort(self, column:int, order:QtCore.Qt.SortOrder=...) -> None:
        self.layoutAboutToBeChanged.emit()
        key = self._columns_spec[column].getter
        reverse = order == QtCore.Qt.SortOrder.AscendingOrder
        try:
            self._prims = sorted(self._prims, key=key, reverse=reverse)
        finally:
            self.layoutChanged.emit()

    def flags(self, index:QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        flags = super().flags(index)
        if index.column() not in self._locked_columns:
            return flags | QtCore.Qt.ItemIsEditable
        return flags


class _Table(QtWidgets.QTableView):
    def scrollContentsBy(self, dx:int, dy:int):
        super().scrollContentsBy(dx, dy)
        if dx:
            self._fixPositions()

    def _fixPositions(self):
        header = self.horizontalHeader()
        header._updateVisualSections(min(header.section_options))


class StageTable(QtWidgets.QDialog):
    def __init__(self, options: _ColumnOptions = _ColumnOptions.ALL, *args, **kwargs):
        super().__init__(*args, **kwargs)
        columns = (
            _Column("Path", lambda prim: str(prim.GetPath())),
            _Column("Name", Usd.Prim.GetName),
            _Column("Type", Usd.Prim.GetTypeName, Usd.Prim.SetTypeName),
            _Column("Documentation", Usd.Prim.GetDocumentation,
                    Usd.Prim.SetDocumentation),
            _Column("Instanceable", Usd.Prim.IsInstance, Usd.Prim.SetInstanceable),
            _Column("Visibility",
                    lambda prim: UsdGeom.Imageable(prim).GetVisibilityAttr().Get()),
            _Column("Hidden", Usd.Prim.IsHidden, Usd.Prim.SetHidden),
        )
        self.model = source_model = StageTableModel(columns=columns)
        self._columns_spec = columns
        header = _Header([col.name for col in columns], options, QtCore.Qt.Horizontal)
        self.table = table = _Table()

        self._column_options = header.section_options

        # for every column, create a proxy model and chain it to the next one
        for column_index, column_data in enumerate(columns):
            proxy_model = _ProxyModel()
            proxy_model.setSourceModel(source_model)
            proxy_model.setFilterKeyColumn(column_index)
            # proxy_model.setFilterRole(_USD_DATA_ROLE)

            column_options = header.section_options[column_index]
            if _ColumnOptions.SEARCH in options:
                column_options.filterChanged.connect(proxy_model.setFilterRegularExpression)
            if _ColumnOptions.VISIBILITY in options:
                column_options.toggled.connect(partial(self._setColumnVisibility, column_index))
            if _ColumnOptions.LOCK in options:
                column_options.locked.connect(partial(self._setColumnLocked, column_index))

            source_model = proxy_model


        header.setModel(source_model)
        header.setSectionsClickable(True)

        table.setModel(source_model)
        table.setHorizontalHeader(header)
        table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.SelectedClicked)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        table.setSortingEnabled(True)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(table)
        self.setLayout(layout)

    @property
    def stage(self):
        return self.model.stage

    @stage.setter
    def stage(self, value):
        self.model.stage = value

    def _setColumnVisibility(self, index: int, visible: bool):
        self.table.setColumnHidden(index, not visible)

    def _setColumnLocked(self, column_index, value):
        method = set.add if value else set.discard
        method(self.model._locked_columns, column_index)


if __name__ == "__main__":
    import sys
    # from PySide2 import QtWebEngine
    # QtWebEngine.QtWebEngine.initialize()
    app = QtWidgets.QApplication(sys.argv)
    stage = Usd.Stage.Open(r"B:\read\cg\downloads\Kitchen_set\Kitchen_set\Kitchen_set.usd")
    # stage = Usd.Stage.Open(r"B:\read\cg\downloads\Kitchen_set\Kitchen_set\kitchen_multi.usda")
    # _COLUMNS = (
    #     _Column("Name", Usd.Prim.GetName),
    #     _Column("Path", lambda prim: str(prim.GetPath())),
    #     # _Column("Type", Usd.Prim.GetTypeName, Usd.Prim.SetTypeName, _prim_type_combobox),
    #     _Column("Type", Usd.Prim.GetTypeName, Usd.Prim.SetTypeName),
    #     _Column("Documentation", Usd.Prim.GetDocumentation, Usd.Prim.SetDocumentation),
    #     _Column("Instanceable", Usd.Prim.IsInstance, Usd.Prim.SetInstanceable),
    #     _Column("Visibility", lambda prim: UsdGeom.Imageable(prim).GetVisibilityAttr().Get()),
    #     _Column("Hidden", Usd.Prim.IsHidden, Usd.Prim.SetHidden),
    # )
    w = StageTable()
    w.stage = stage
    w.show()
    sys.exit(app.exec_())

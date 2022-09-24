"""Shared members for views modules, not considered public API."""
import enum
import typing
import contextlib
from functools import partial

from ._qt import QtWidgets, QtGui, QtCore

# Agreement: raw data accessible here
_QT_OBJECT_DATA_ROLE = QtCore.Qt.UserRole + 1

# Very slightly modified USDView stylesheet for the push buttons.
_USDVIEW_PUSH_BUTTON_STYLE = """
QPushButton{
    /* gradient background */
    background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(100, 100, 100), stop: 1 rgb(90, 90, 90));

    /* thin dark round border */
    border-width: 1px;
    border-color: rgb(42, 42, 42);
    border-style: solid;
    border-radius: 3;

    /* give the text enough space */
    padding: 3px;
    padding-right: 10px;
    padding-left: 10px;
}

/* Darker gradient when the button is pressed down */
QPushButton:pressed {
    background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(50, 50, 50), stop: 1 rgb(60, 60, 60));
}

QPushButton:checked {
    background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(60, 65, 70), stop: 1 rgb(70, 75, 80));
}

/* Greyed-out colors when the button is disabled */
QPushButton:disabled {
    background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(66, 66, 66), stop: 1 rgb(56, 56, 56));
}

"""

# Taken from QTreeWidget style and adapted for _Tree:
# https://github.com/PixarAnimationStudios/USD/blob/3abc46452b1271df7650e9948fef9f0ce602e3b2/pxr/usdImaging/usdviewq/usdviewstyle.qss#L258
_USDVIEW_QTREEVIEW_STYLE = """
_Tree {
    alternate-background-color: rgb(59, 59, 59);
}

._Tree::item, QTableView::item {
    /* this border serves to separate the columns
     * since the grid is often invised */
    border-right: 1px solid rgb(41, 41, 41);
    padding-top: 1px;
    padding-bottom: 1px;
}

/* Selected items highlighted in orange */
._Tree::item:selected,
_Tree::branch:selected,
QTableView::item:selected {
    background: rgb(189, 155, 84);
}

/* hover items a bit lighter */
._Tree::item:hover:!pressed:!selected,
_Tree::branch:hover:!pressed:!selected,
QTableView::item:hover:!pressed:!selected {
    background: rgb(70, 70, 70);
}

._Tree::item:hover:!pressed:selected,
_Tree::branch:hover:!pressed:selected,
QTableView::item:hover:!pressed:selected {
/*    background: rgb(132, 109, 59); */
    background: rgb(227, 186, 101);
}

/* Set the branch triangle icons */
_Tree::branch:has-children:!has-siblings:closed,
_Tree::branch:closed:has-children:has-siblings {
    border-image: none;
    image: url(%(RESOURCE_DIR)s/icons/branch-closed.png);
}

_Tree::branch:open:has-children:!has-siblings,
_Tree::branch:open:has-children:has-siblings  {
    border-image: none;
    image: url(%(RESOURCE_DIR)s/icons/branch-open.png);
}

_Tree::branch:selected:has-children:!has-siblings:closed,
_Tree::branch:selected:closed:has-children:has-siblings {
    border-image: none;
    image: url(%(RESOURCE_DIR)s/icons/branch-closed-selected.png);
}

_Tree::branch:selected:open:has-children:!has-siblings,
_Tree::branch:selected:open:has-children:has-siblings  {
    border-image: none;
    image: url(%(RESOURCE_DIR)s/icons/branch-open-selected.png);
}
"""


@contextlib.contextmanager
def wait():
    try:
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        yield
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()


class _EMOJI(enum.Enum):  # Replace with StrEnum in 3.11
    # GENERAL
    ID = "🕵"
    VISIBILITY = "👀"
    SEARCH = "🔎"
    LOCK = "🔐"
    UNLOCK = "🔓"

    # STAGE TRAVERSAL
    MODEL_HIERARCHY = "🏡"
    INSTANCE_PROXIES = "💠"

    # PRIM SPECIFIER
    ORPHANED = "👻"
    CLASSES = "🧪"
    DEFINED = "🧱"

    # PRIM STATUS
    ACTIVE = "💡"
    INACTIVE = "🌒"

    # IDENTIFICATION
    NAME = "🔖"


class _Column(typing.NamedTuple):
    """Foundational structure for a column and how to retrieve / set model data."""
    name: str
    getter: callable = None
    setter: callable = None
    editor: callable = None


class _ColumnOptions(enum.Flag):
    """Options that will be available on the header columns of a view."""
    NONE = enum.auto()
    SEARCH = enum.auto()
    VISIBILITY = enum.auto()
    LOCK = enum.auto()
    ALL = SEARCH | VISIBILITY | LOCK


class _ColumnItemDelegate(QtWidgets.QStyledItemDelegate):
    """
    https://doc.qt.io/qtforpython/overviews/sql-presenting.html
    https://doc.qt.io/qtforpython/overviews/qtwidgets-itemviews-spinboxdelegate-example.html
    """

    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        creator = self.parent()._model._columns[index.column()].editor or super().createEditor
        return creator(parent, option, index)


class _EmptyItemDelegate(_ColumnItemDelegate):
    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel, index: QtCore.QModelIndex):
        setter = self.parent()._model._columns[index.column()].setter or super().setModelData
        return setter(editor, model, index)


class _ColumnHeaderOptions(QtWidgets.QWidget):
    """A widget to be used within a header for columns on a table / tree view."""
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
        self._vis_button = vis_button = QtWidgets.QPushButton(_EMOJI.VISIBILITY.value)
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
        filter_layout.addRow(_EMOJI.SEARCH.value, line_filter)
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
            text = _EMOJI.LOCK.value
            tip = "Column is non-editable (locked).\nClick to allow edits."
        else:
            text = _EMOJI.UNLOCK.value
            tip = "Edits are allowed on this column (unlocked).\nClick to block edits."
        button.setText(text)
        button.setToolTip(tip)

    def _setHidden(self, value):
        self._vis_button.setChecked(not value)


class _Header(QtWidgets.QHeaderView):
    """A header that allows to display the column options for a table / tree.

    See also:
        https://www.qt.io/blog/2014/04/11/qt-weekly-5-widgets-on-a-qheaderview
        https://www.qt.io/blog/2012/09/28/qt-support-weekly-27-widgets-on-a-header
        https://www.learnpyqt.com/courses/model-views/qtableview-modelviews-numpy-pandas/
    """
    def __init__(self, columns: typing.Iterable[str], options: _ColumnOptions, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options_by_index = dict()  # {int: _ColumnHeaderOptions}
        self._proxy_labels = dict()  # I've found no other way around this
        for index, name in enumerate(columns):
            column_options = _ColumnHeaderOptions(name, options=options, parent=self)
            column_options.layout().setContentsMargins(0, 0, 0, 0)
            self.options_by_index[index] = column_options
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
        widget = self.options_by_index[logical_index]
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
        for index, widget in self.options_by_index.items():
            self._updateOptionsGeometry(index)
            # ensure we have readable columns upon show
            widget.show()
            self.resizeSection(index, widget.sizeHint().width() + 20)
        super().showEvent(event)

    def _handleSectionResized(self, index):
        self._updateVisualSections(self.visualIndex(index))
        for index, widget in self.options_by_index.items():
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


class EmptyTableModel(QtGui.QStandardItemModel):
    """Minimal empty table for new data (unlike existing USD stages or layers).

    This is a "transient" model which will eventually have data translated into USD.
    """
    def __init__(self, columns, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._columns = columns
        self._locked_columns = set()  # TODO: make sure this plays well with this and USD table
        self.setHorizontalHeaderLabels([''] * len(columns))


class _ObjectTableModel(QtCore.QAbstractTableModel):
    """Table model objects whose getters / setters are provided via columns.

    Mainly used for USD objects like layers or prims.
    """

    def __init__(self, columns, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._columns = columns
        self._locked_columns = set()
        self._objects = []

    def rowCount(self, parent:QtCore.QModelIndex=...) -> int:
        return len(self._objects)

    def columnCount(self, parent:QtCore.QModelIndex=...) -> int:
        return len(self._columns)

    def data(self, index:QtCore.QModelIndex, role:int=...) -> typing.Any:
        if role == _QT_OBJECT_DATA_ROLE:  # raw data
            return self._objects[index.row()]
        elif role == QtCore.Qt.DisplayRole:
            obj = self.data(index, role=_QT_OBJECT_DATA_ROLE)
            return self._columns[index.column()].getter(obj)
        elif role == QtCore.Qt.EditRole:
            obj = self.data(index, role=_QT_OBJECT_DATA_ROLE)
            return self._columns[index.column()].getter(obj)

    def sort(self, column:int, order:QtCore.Qt.SortOrder=...) -> None:
        self.layoutAboutToBeChanged.emit()
        key = self._columns[column].getter
        reverse = order == QtCore.Qt.SortOrder.AscendingOrder
        try:
            self._objects = sorted(self._objects, key=key, reverse=reverse)
        finally:
            self.layoutChanged.emit()

    def setData(self, index:QtCore.QModelIndex, value:typing.Any, role:int=...) -> bool:
        obj = self.data(index, role=_QT_OBJECT_DATA_ROLE)
        result = self._columns[index.column()].setter(obj, value)
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


class _ColumnHeaderMixin:
    # TODO: see if this makes sense.
    def __init__(self, model, columns: typing.Iterable[_Column], options: _ColumnOptions, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # TODO: I tried splitting this into a setModel method but keeping a self reference
        #   for columns or options causes python to segfault on Travis (not locally)
        # self._columns = columns
        # self._options = options
        self._model = model
        header = _Header([col.name for col in columns], options, QtCore.Qt.Horizontal)

        # TODO: item delegate per model type? For now it works ):<
        column_delegate_cls = _ColumnItemDelegate if isinstance(model, _ObjectTableModel) else _EmptyItemDelegate
        self._column_options = header.options_by_index

        # for every column, create a proxy model and chain it to the next one
        for column_index, column_data in enumerate(columns):
            proxy_model = _ProxyModel()
            proxy_model.setSourceModel(model)
            proxy_model.setFilterKeyColumn(column_index)

            column_options = header.options_by_index[column_index]
            if _ColumnOptions.SEARCH in options:
                self._connect_search(column_options, column_index, proxy_model)
            if _ColumnOptions.VISIBILITY in options:
                self._connect_visibility(column_options, column_index, proxy_model)
            if _ColumnOptions.LOCK in options:
                self._connect_locked(column_options, column_index, proxy_model)

            delegate = column_delegate_cls(parent=self)
            self.setItemDelegateForColumn(column_index, delegate)

            model = proxy_model

        header.setModel(model)
        header.setSectionsClickable(True)

        self.setModel(model)
        try:
            self.setHorizontalHeader(header)
        except AttributeError:
            self.setHeader(header)

    def _connect_search(self, options, index, model):
        options.filterChanged.connect(model.setFilterRegularExpression)

    def _connect_visibility(self, options, index, model):
        options.toggled.connect(partial(self._setColumnVisibility, index))

    def _connect_locked(self, options, index, model):
        options.locked.connect(partial(self._setColumnLocked, index))

    def _setColumnVisibility(self, index: int, visible: bool):
        self.setColumnHidden(index, not visible)

    def _setColumnLocked(self, column_index, value):
        method = set.add if value else set.discard
        method(self._model._locked_columns, column_index)

    def scrollContentsBy(self, dx:int, dy:int):
        super().scrollContentsBy(dx, dy)
        if dx:
            self._fixPositions()

    def _fixPositions(self):
        try:
            header = self.horizontalHeader()  # Tables
        except AttributeError:
            header = self.header()  # Trees
        header._updateVisualSections(min(header.options_by_index))

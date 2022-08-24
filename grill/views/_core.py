"""Shared members for views modules, not considered public API."""
import enum
import contextlib

from ._qt import QtWidgets, QtGui, QtCore

# Agreement: raw data accessible here
_QT_OBJECT_DATA_ROLE = QtCore.Qt.UserRole + 1


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
import typing
import logging
import operator

from pxr import Usd
from PySide2 import QtCore, QtWidgets

logger = logging.getLogger(__name__)


class StageTableModel(QtCore.QAbstractTableModel):
    # See:
    # https://doc.qt.io/qtforpython/PySide6/QtCore/QAbstractItemModel.html
    # https://doc.qt.io/qtforpython/overviews/qtwidgets-itemviews-pixelator-example.html#pixelator-example
    _stage = None
    _prims = []

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
        return len(COLUMNS)

    def data(self, index:QtCore.QModelIndex, role:int=...) -> typing.Any:
        # if (!index.isValid() || role != Qt::DisplayRole)
        #         return QVariant();
        #     return qGray(modelImage.pixel(index.column(), index.row()));
        if not index.isValid() or role != QtCore.Qt.DisplayRole:
            return None
        prim = self._prims[index.row()]
        if index.column() == 0:
            return str(prim.GetPath())
        elif index.column() == 1:
            return prim.GetTypeName()

    def sort(self, column:int, order:QtCore.Qt.SortOrder=...) -> None:
        self.layoutAboutToBeChanged.emit()
        if column == 0:
            key = operator.methodcaller('GetPath')
        elif column == 1:
            key = operator.methodcaller('GetTypeName')
        reverse = order == QtCore.Qt.SortOrder.AscendingOrder
        try:
            self._prims = sorted(self._prims, key=key, reverse=reverse)
        finally:
            self.layoutChanged.emit()

    def headerData(self, section:int, orientation:QtCore.Qt.Orientation, role:int=...) -> typing.Any:
        #     if (role == Qt::SizeHintRole)
        #         return QSize(1, 1);
        #     return QVariant();
        if role == QtCore.Qt.SizeHintRole:
            return QtCore.QSize(50, 50)
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Vertical:
            return section + 1
        return super().headerData(section, orientation, role)


class _ProxyModel(QtCore.QSortFilterProxyModel):
    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        """For a vertical header, display a sequential visual index instead of the logical from the model."""
        # https://www.walletfox.com/course/qsortfilterproxymodelexample.php
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Vertical:
            return section + 1
        return super().headerData(section, orientation, role)

    def sort(self, column: int, order: QtCore.Qt.SortOrder = QtCore.Qt.AscendingOrder) -> None:
        self.sourceModel().sort(column, order)


COLUMNS = (1,2)


class StageTable(QtWidgets.QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()
        self.model = source_model = StageTableModel()
        for column_index, column_data in enumerate(COLUMNS):
            proxy_model = _ProxyModel()
            proxy_model.setSourceModel(source_model)
            proxy_model.setFilterKeyColumn(column_index)
            source_model = proxy_model
        self.table = table = QtWidgets.QTableView(parent=self)
        table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.SelectedClicked)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        table.setSortingEnabled(True)
        table.setModel(source_model)
        layout.addWidget(table)
        self.setLayout(layout)

    def setStage(self, value):
        self.model.stage = value


if __name__ == "__main__":
    import sys
    # from PySide2 import QtWebEngine
    # QtWebEngine.QtWebEngine.initialize()
    app = QtWidgets.QApplication(sys.argv)
    # stage = Usd.Stage.Open(r"B:\read\cg\downloads\Kitchen_set\Kitchen_set\Kitchen_set.usd")
    stage = Usd.Stage.Open(r"B:\read\cg\downloads\Kitchen_set\Kitchen_set\kitchen_multi.usda")
    w = StageTable()
    w.setStage(stage)
    w.show()
    sys.exit(app.exec_())

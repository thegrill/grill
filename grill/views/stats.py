from functools import partial
from pxr import UsdUtils

from ._qt import QtWidgets, QtCore, QtCharts, QtGui


class _ContainerTree(QtWidgets.QTreeWidget):
    def __init__(self, *args, value=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setColumnCount(2)  # 0: key, 1: value
        self.setHeaderHidden(True)
        self.setSelectionMode(self.SelectionMode.ExtendedSelection)
        self.setData(value)

    def setData(self, value):
        self.clear()
        containers = (dict, list, tuple)
        def populate(parent, data):
            if isinstance(data, containers):
                for _key, _value in data.items() if isinstance(data, dict) else enumerate(data):
                    display = None if isinstance(_value, containers) else str(_value)
                    populate(QtWidgets.QTreeWidgetItem(parent, [str(_key), display]), _value)

        populate(self.invisibleRootItem(), value)
        self.expandAll()
        self.resizeColumnToContents(0)
        self.resizeColumnToContents(1)


class _StatsPie(QtWidgets.QWidget):
    def __init__(self, *args, stats=None, **kwargs):
        super().__init__(*args, **kwargs)
        if stats:
            self.setStats(stats)

    def setStats(self, value, *, title=None):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        def populate(parent, data: dict, chart_title: str = ""):
            def show_label(pie, state):
                pie.setExploded(state)

            substats = []
            stats = []
            for data_key, data_value  in data.items():
                target = substats if isinstance(data_value, dict) else stats
                target.append((data_key, data_value))

            if stats:
                series = QtCharts.QPieSeries()
                for stat_key, stat_value in stats:
                    series.append(f"{stat_key}: {stat_value}", stat_value)
                series.setLabelsVisible(True)
                for slice in series.slices():
                    slice.hovered.connect(partial(show_label, slice))
                chart = QtCharts.QChart()
                chart.addSeries(series)
                chart.legend().hide()

                if chart_title:
                    chart.setTitle(chart_title)
                view = QtCharts.QChartView(chart)
                view.setRenderHint(QtGui.QPainter.Antialiasing)
                parent.addWidget(view)

            if substats:
                subparent = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
                parent.addWidget(subparent)
                for substat_key, substat_value in substats:
                    subtitle = f"{'' if stats else chart_title + ': '}{substat_key}"
                    populate(subparent, substat_value, chart_title=subtitle)  # lazy

        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        layout.addWidget(main_splitter)
        # Note: this is relying on current structure from return value of
        # UsdUtils.ComputeUsdStageStats dict[str: (str|int|dict)]
        # if that changes we might have to change, but for now don't think much about it
        populate(main_splitter, value, chart_title=title)
        self.setLayout(layout)


class StageStats(QtWidgets.QDialog):
    def __init__(self, *args, stage=None, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QHBoxLayout()
        self._usd_tree = _ContainerTree(parent=self)
        self._pie = _StatsPie(parent=self)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self._pie)
        splitter.addWidget(self._usd_tree)
        layout.addWidget(splitter)
        self.setLayout(layout)
        if stage:
            self.setStage(stage)

    def setStage(self, stage):
        stats = UsdUtils.ComputeUsdStageStats(stage)
        self._usd_tree.setData(stats)
        self._pie.setStats(stats, title=f'Stats for {stage.GetRootLayer().identifier}')

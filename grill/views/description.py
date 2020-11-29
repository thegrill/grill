"""Views related to USD scene description"""

import shutil
import tempfile
import subprocess
from pathlib import Path
from itertools import chain
from functools import lru_cache
from collections import defaultdict

import networkx
from pxr import Usd, Pcp
from networkx.drawing import nx_pydot
from PySide2 import QtWidgets, QtGui, QtCore, QtWebEngineWidgets

from grill.views import spreadsheet as _tables


_COLUMNS = {
    "Target Layer": lambda arc: arc.GetTargetNode().layerStack.identifier.rootLayer.identifier,
    "Target Path": lambda arc: arc.GetTargetNode().path,
    "Arc": lambda arc: arc.GetArcType().displayName,
    "Has Specs": Usd.CompositionArc.HasSpecs,
    "Is Ancestral": Usd.CompositionArc.IsAncestral,
    "Is Implicit": Usd.CompositionArc.IsImplicit,
    "From Root Layer Prim Spec": Usd.CompositionArc.IsIntroducedInRootLayerPrimSpec,
    "From Root Layer Stack": Usd.CompositionArc.IsIntroducedInRootLayerStack,
}


@lru_cache(maxsize=None)
def _dot_exe():
    return shutil.which("dot")


@lru_cache(maxsize=None)
def _dot_2_svg(sourcepath):
    print(f"Creating svg for: {sourcepath}")
    targetpath = f"{sourcepath}.svg"
    dotargs = [_dot_exe(), sourcepath, "-Tsvg", "-o", targetpath]
    result = subprocess.run(dotargs, capture_output=True)
    error = result.stderr.decode() if result.returncode else None
    return error, targetpath


class _Dot2SvgSignals(QtCore.QObject):
    error = QtCore.Signal(str)
    result = QtCore.Signal(str)


class _Dot2Svg(QtCore.QRunnable):
    def __init__(self, source_fp):
        super().__init__()
        self.signals = _Dot2SvgSignals()
        self.source_fp = source_fp

    @QtCore.Slot()
    def run(self):
        if not _dot_exe():
            self.signals.error.emit(
                "In order to display composition arcs in a graph,\n"
                "the 'dot' command must be available on the current environment.\n\n"
                "Please make sure graphviz is installed and 'dot' available \n"
                "on the system's PATH environment variable."
            )
            return
        error, svg_fp = _dot_2_svg(self.source_fp)
        self.signals.error.emit(error) if error else self.signals.result.emit(svg_fp)


class _DotViewer(QtWidgets.QFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()
        self._graph_view = QtWebEngineWidgets.QWebEngineView(parent=self)
        self._error_view = QtWidgets.QTextBrowser()
        layout.addWidget(self._graph_view)
        layout.addWidget(self._error_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self._error_view.setVisible(False)
        self.setLayout(layout)
        self.urlChanged = self._graph_view.urlChanged
        self._dot2svg = None
        self._threadpool = QtCore.QThreadPool()

    def setDotPath(self, path):
        if self._dot2svg:  # forget about previous, unfinished runners
            self._dot2svg.signals.error.disconnect()
            self._dot2svg.signals.result.disconnect()

        self._dot2svg = dot2svg = _Dot2Svg(path)
        dot2svg.signals.error.connect(self._on_dot_error)
        dot2svg.signals.result.connect(self._on_dot_result)
        self._threadpool.start(dot2svg)

    def _on_dot_error(self, message):
        self._error_view.setVisible(True)
        self._graph_view.setVisible(False)
        self._error_view.setText(message)

    def _on_dot_result(self, filepath):
        self._error_view.setVisible(False)
        self._graph_view.setVisible(True)
        self._graph_view.load(QtCore.QUrl.fromLocalFile(filepath))


class PrimComposition(QtWidgets.QDialog):
    def __init__(self, *args, **kwargs):
        """For inspection and debug purposes, this widget makes primary use of:

            - Usd.PrimCompositionQuery  (similar to USDView's composition tab)
            - Pcp.PrimIndex.DumpToString
            - Pcp.PrimIndex.DumpToDotGraph  (when dot is available)
        """
        super().__init__(*args, **kwargs)
        self.index_box = QtWidgets.QTextBrowser()
        self.index_box.setLineWrapMode(self.index_box.NoWrap)
        self.composition_tree = tree = QtWidgets.QTreeWidget()
        tree.setColumnCount(len(_COLUMNS))
        tree.setHeaderLabels([k for k in _COLUMNS])
        tree.setAlternatingRowColors(True)
        self._dot_view = _DotViewer()
        vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        vertical.addWidget(tree)
        vertical.addWidget(self._dot_view)
        horizontal = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        horizontal.addWidget(vertical)
        horizontal.addWidget(self.index_box)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(horizontal)
        self.setLayout(layout)
        self.setWindowTitle("Prim Composition")

    def clear(self):
        self.composition_tree.clear()
        self.index_box.clear()

    def setPrim(self, prim):
        prim_index = prim.GetPrimIndex()
        self.index_box.setText(prim_index.DumpToString())
        tree = self.composition_tree
        tree.clear()
        query = Usd.PrimCompositionQuery(prim)
        tree_items = dict()  # Sdf.Layer: QTreeWidgetItem
        for arc in query.GetCompositionArcs():
            strings = [str(getter(arc)) for getter in _COLUMNS.values()]
            intro_layer = arc.GetIntroducingLayer()
            if intro_layer and intro_layer in tree_items:
                parent = tree_items[intro_layer]
            else:
                parent = tree
            target_layer = arc.GetTargetNode().layerStack.identifier.rootLayer
            tree_items[target_layer] = QtWidgets.QTreeWidgetItem(parent, strings)

        tree.expandAll()
        fd, fp = tempfile.mkstemp()
        prim_index.DumpToDotGraph(fp)
        self._dot_view.setDotPath(fp)


_LAYERS_COMPOSITION_LAYER_IDS = {
    "Layer Identifier": lambda layer: layer.identifier,
}
_LAYERS_COMPOSITION_PRIM_PATHS = {
    "Spec on Prim Path": lambda prim: str(prim.GetPath()),
}


class LayersComposition(QtWidgets.QDialog):

    def __init__(self, stage=None, parent=None, **kwargs):
        super().__init__(parent=parent, **kwargs)
        options = _tables.ColumnOptions.SEARCH
        self._layers = _tables._Spreadsheet(list(_LAYERS_COMPOSITION_LAYER_IDS), options)
        self._prims = _tables._Spreadsheet(list(_LAYERS_COMPOSITION_PRIM_PATHS), options)

        for each in self._layers, self._prims:
            each.layout().setContentsMargins(0,0,0,0)
            each.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self._dot_view = _DotViewer()
        self._dot_view.urlChanged.connect(self._graph_url_changed)

        horizontal = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        horizontal.addWidget(self._layers)
        horizontal.addWidget(self._prims)

        vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        vertical.addWidget(horizontal)
        vertical.addWidget(self._dot_view)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(vertical)

        self.setLayout(layout)
        self.setStage(stage or Usd.Stage.CreateInMemory())
        self.setWindowTitle("Layer Stack Composition")

        selectionModel = self._layers.table.selectionModel()
        selectionModel.selectionChanged.connect(self._selectionChanged)
        self._paths = dict()

    def _selectionChanged(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection):
        node_ids = [index.data() for index in self._layers.table.selectedIndexes()]
        node_indices = [self._node_index_by_id[i] for i in node_ids]
        paths = set(chain.from_iterable(self._paths[i] for i in node_ids))

        prims_model = self._prims.model
        prims_model.clear()
        prims_model.setHorizontalHeaderLabels([''] * len(_LAYERS_COMPOSITION_PRIM_PATHS))
        prims_model.setRowCount(len(paths))
        prims_model.blockSignals(True)
        for row_index, path in enumerate(paths):
            for column_index, getter in enumerate(_LAYERS_COMPOSITION_PRIM_PATHS):
                item = QtGui.QStandardItem()
                item.setData(path, QtCore.Qt.DisplayRole)
                item.setData(path, QtCore.Qt.UserRole)
                prims_model.setItem(row_index, column_index, item)
        prims_model.blockSignals(False)
        self._prims.table.resizeColumnsToContents()
        self._prims.table.horizontalHeader()._updateVisualSections(0)
        self._update_node_graph_view(node_indices)

    def _graph_url_changed(self, url: QtCore.QUrl):
        node_uri = url.toString()
        node_uri_stem = node_uri.split("/")[-1]
        node_index = node_uri_stem.split("node_id_")[-1]
        if node_index.isdigit():
            node_index = int(node_index)
            self._update_node_graph_view([node_index])

    @lru_cache(maxsize=None)
    def _subgraph_dot_path(self, node_indices: tuple):
        print(f"Getting subgraph for: {node_indices}")
        successors = chain.from_iterable(
            self._graph.successors(index) for index in node_indices)
        predecessors = chain.from_iterable(
            self._graph.predecessors(index) for index in node_indices)
        nodes_of_interest = list(range(6))  # needs to be label nodes
        nodes_of_interest.extend(chain(node_indices, successors, predecessors))
        subgraph = self._graph.subgraph(nodes_of_interest)

        fd, fp = tempfile.mkstemp()
        nx_pydot.write_dot(subgraph, fp)

        return fp

    def _update_node_graph_view(self, node_indices: list):
        dot_path = self._subgraph_dot_path(tuple(node_indices))
        self._dot_view.setDotPath(dot_path)

    @_tables.wait()
    def setStage(self, stage):
        """Sets the USD stage the spreadsheet is looking at."""
        self._stage = stage
        for table in self._layers, self._prims:
            table.model.clear()
            table.table.setSortingEnabled(False)

        # labels are on the header widgets
        self._layers.model.setHorizontalHeaderLabels([''] * len(_LAYERS_COMPOSITION_LAYER_IDS))
        self._prims.model.setHorizontalHeaderLabels([''] * len(_LAYERS_COMPOSITION_PRIM_PATHS))

        self._graph = graph = networkx.DiGraph(tooltip="My label")
        # legend
        arcs_to_display = {  # should include all?
            Pcp.ArcTypePayload: dict(color=10, colorscheme="paired12", fontcolor=10),  # purple
            Pcp.ArcTypeReference: dict(color=6, colorscheme="paired12", fontcolor=6),  # red
            Pcp.ArcTypeVariant: dict(color=8, colorscheme="paired12", fontcolor=8), # yellow
        }
        legend_node_ids = set()
        for arc_type, edge_attrs in arcs_to_display.items():
            label = f" {arc_type.displayName}"
            arc_node_indices = {len(legend_node_ids), len(legend_node_ids)+1}
            graph.add_nodes_from(arc_node_indices, style='invis')
            graph.add_edge(*arc_node_indices, label=label, **edge_attrs)
            legend_node_ids.update(arc_node_indices)

        self._node_id_by_index = node_id_by_index = dict.fromkeys(legend_node_ids)  # {42: layer.identifier}
        self._node_index_by_id = node_index_by_id = dict.fromkeys(legend_node_ids)  # {layer.identifier: 42}

        def _add_layer_node(layer):
            layer_id = layer.identifier
            if layer_id in node_index_by_id:
                return
            index = len(node_id_by_index)
            node_id_by_index[index] = layer_id
            node_index_by_id[layer_id] = index
            label = Path(layer.realPath).stem

            graph.add_node(index, style='rounded', shape='rect', label=label, tooltip=layer_id, title='world', href=f"node_id_{index}")

        self._paths = paths = defaultdict(set)  # {layer.identifier: {path1, ..., pathN}}
        for prim in stage.TraverseAll():
            query = Usd.PrimCompositionQuery(prim)
            for arc in query.GetCompositionArcs():
                if not arc.HasSpecs():
                    continue
                target = arc.GetTargetNode().layerStack.identifier.rootLayer
                target_id = target.identifier
                _add_layer_node(target)

                paths[target_id].add(str(prim.GetPath()))
                intro = arc.GetIntroducingLayer()
                if intro:
                    _add_layer_node(intro)
                    # graph.add_edge(node_index_by_id[intro.identifier], node_index_by_id[target_id], label=f" {arc.GetArcType().displayName}")
                    edge_attrs = arcs_to_display[arc.GetArcType()]
                    graph.add_edge(node_index_by_id[intro.identifier], node_index_by_id[target_id], **edge_attrs)

        layers_model = self._layers.model
        layers_model.setRowCount(len(graph))
        layers_model.blockSignals(True)  # prevent unneeded events from computing

        for node_id, node in enumerate(sorted(set(graph.nodes) - legend_node_ids)):
            item = QtGui.QStandardItem()
            print(f"Setting {node_id_by_index[node]}")
            item.setData(node_id_by_index[node], QtCore.Qt.DisplayRole)
            layers_model.setItem(node_id, 0, item)

        layers_model.blockSignals(False)
        for table in self._layers, self._prims:
            table.table.setSortingEnabled(True)


if __name__ == "__main__":
    import sys
    stage = Usd.Stage.Open(r"B:\read\cg\downloads\Kitchen_set\Kitchen_set\Kitchen_set.usd")
    app = QtWidgets.QApplication(sys.argv)
    description = PrimComposition()
    prim = stage.GetPrimAtPath(r"/Kitchen_set/Props_grp/DiningTable_grp/TableTop_grp/CerealBowl_grp/BowlD_1")
    description.setPrim(prim.GetChildren()[0])
    description.show()
    lc = LayersComposition()
    lc.setStage(stage)
    lc.show()
    sys.exit(app.exec_())

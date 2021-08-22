"""Views related to USD scene description"""
import shutil
import operator
import tempfile
import subprocess
from pathlib import Path
from itertools import chain
from functools import lru_cache
from collections import defaultdict
from types import MappingProxyType

import networkx as nx
from pxr import Usd, Pcp, UsdUtils
from networkx.drawing import nx_pydot
from PySide2 import QtWidgets, QtCore, QtWebEngineWidgets

from . import sheets as _sheets, _core


_ARCS_COLOR_SCHEME = "paired12"
_ARCS_LEGEND = MappingProxyType({
    Pcp.ArcTypeInherit: dict(color=4, colorscheme=_ARCS_COLOR_SCHEME, fontcolor=4),       # green
    Pcp.ArcTypeVariant: dict(color=8, colorscheme=_ARCS_COLOR_SCHEME, fontcolor=8),       # yellow
    Pcp.ArcTypeReference: dict(color=6, colorscheme=_ARCS_COLOR_SCHEME, fontcolor=6),     # red
    Pcp.ArcTypePayload: dict(color=10, colorscheme=_ARCS_COLOR_SCHEME, fontcolor=10),     # purple
    Pcp.ArcTypeSpecialize: dict(color=12, colorscheme=_ARCS_COLOR_SCHEME, fontcolor=12),  # brown
})

_DESCRIPTION_LEGEND_IDS_KEY = 'legend_indices'
_DESCRIPTION_IDS_BY_LAYERS_KEY = 'indices_by_layers'
_DESCRIPTION_PATHS_BY_IDS_KEY = 'paths_by_indices'


@lru_cache(maxsize=None)
def _dot_exe():
    return shutil.which("dot")


@lru_cache(maxsize=None)
def _dot_2_svg(sourcepath):
    print(f"Creating svg for: {sourcepath}")
    targetpath = f"{sourcepath}.svg"
    dotargs = [_dot_exe(), sourcepath, "-Tsvg", "-o", targetpath]
    kwargs = {}
    if hasattr(subprocess, 'CREATE_NO_WINDOW'):  # not on linux
        kwargs.update(creationflags=subprocess.CREATE_NO_WINDOW)
    result = subprocess.run(dotargs, capture_output=True, **kwargs)
    error = result.stderr.decode() if result.returncode else None
    return error, targetpath


def _compute_layerstack_graph(prims, url_prefix):
    """Compute a layer stack graph for the provided prims

    Returns:
        nx_graph {int: <..., layer_stack: (Sdf.Layer,), prim_paths: {Sdf.Path}>}
    """
    @lru_cache(maxsize=None)
    def _layer_label(layer):
        return Path(layer.realPath).stem or layer.identifier

    def _walk_layer_tree(tree):
        tree_layer = tree.layer
        if tree_layer:
            yield tree_layer
        for childtree in tree.childTrees:
            yield from _walk_layer_tree(childtree)

    @lru_cache(maxsize=None)
    def _sublayers(stack):
        return tuple(layer for layer in _walk_layer_tree(stack.layerTree))

    def _add_node(pcp_node):
        layer_stack = pcp_node.layerStack
        root_layer = layer_stack.identifier.rootLayer
        try:
            return node_indices[root_layer]
        except KeyError:
            pass  # layerStack still not processed, let's add it
        node_indices[root_layer] = index = len(node_indices)
        sublayers = _sublayers(layer_stack)

        attrs = dict(style='"rounded,filled"', shape='record', href=f"{url_prefix}{index}")
        label = f"{{{_layer_label(root_layer)}"
        for layer in sublayers:
            indices_by_sublayers[layer].add(index)
            attrs['fillcolor'] = 'palegoldenrod' if layer.dirty else 'white'
            if layer != root_layer:  # root layer has been added at the start.
                label += f"|{_layer_label(layer)}"
        label += "}"
        ids = '\n'.join(f"{i}: {layer.realPath or layer.identifier}" for i, layer in enumerate(sublayers))
        # https://stackoverflow.com/questions/16671966/multiline-tooltip-for-pydot-graph
        tooltip = f"Layer Stack:\n{ids}".replace('\n', '&#10;'),
        graph.add_node(index, label=label, tooltip=tooltip, **attrs)
        return index

    @lru_cache(maxsize=None)
    def _compute_composition(_prim):
        query = Usd.PrimCompositionQuery(_prim)
        query.filter = query_filter
        affected_by = set()  # {int}  indices of nodes affecting this prim
        edges = defaultdict(set)  # {(source_int, target_int): {Pcp.ArcType...}}
        for arc in query.GetCompositionArcs():
            target_idx = _add_node(arc.GetTargetNode())
            affected_by.add(target_idx)
            if arc.GetIntroducingLayer():
                edges[_add_node(arc.GetIntroducingNode()), target_idx].add(arc.GetArcType())
        return affected_by, edges

    graph = nx.DiGraph(tooltip="LayerStack Composition")
    query_filter = Usd.PrimCompositionQuery.Filter()
    query_filter.hasSpecsFilter = Usd.PrimCompositionQuery.HasSpecsFilter.HasSpecs

    legend_node_ids = list()
    for arc_type, attributes in _ARCS_LEGEND.items():
        arc_node_indices = (len(legend_node_ids), len(legend_node_ids) + 1)
        graph.add_nodes_from(arc_node_indices, style='invis')
        graph.add_edge(*arc_node_indices, label=f" {arc_type.displayName}", **attributes)
        legend_node_ids.extend(arc_node_indices)

    node_indices = dict.fromkeys(legend_node_ids)  # {Sdf.Layer: int}
    indices_by_sublayers = defaultdict(set)  # {Sdf.Layer: {int,} }
    paths_by_node_idx = defaultdict(set)
    all_edges = defaultdict(set)  # {(int, int): {Pcp.ArcType..., }}
    for prim in prims:
        # use a forwarded prim in case of instanceability to avoid computing same stack more than once
        prim_path = prim.GetPath()
        forwarded_prim = UsdUtils.GetPrimAtPathWithForwarding(prim.GetStage(), prim_path)
        affected_by_indices, edges = _compute_composition(forwarded_prim)
        for edge_data, edge_arcs in edges.items():
            all_edges[edge_data].update(edge_arcs)
        for affected_by_idx in affected_by_indices:
            paths_by_node_idx[affected_by_idx].add(prim_path)

    def _freeze(dct):
        return MappingProxyType({k: tuple(sorted(v)) for k,v in dct.items()})

    @lru_cache(maxsize=None)
    def edge_attrs(edge_arcs):
        return dict(  # need to wrap color in quotes to allow multicolor
            color=f'"{":".join(str(_ARCS_LEGEND[arc]["color"]) for arc in edge_arcs)}"',
            colorscheme=_ARCS_COLOR_SCHEME
        )

    graph.add_edges_from((src, tgt, edge_attrs(tuple(v))) for (src, tgt), v in all_edges.items())
    graph.graph[_DESCRIPTION_IDS_BY_LAYERS_KEY] = _freeze(indices_by_sublayers)
    graph.graph[_DESCRIPTION_LEGEND_IDS_KEY] = tuple(legend_node_ids)
    graph.graph[_DESCRIPTION_PATHS_BY_IDS_KEY] = _freeze(paths_by_node_idx)
    return graph


class _Dot2SvgSignals(QtCore.QObject):
    error = QtCore.Signal(str)
    result = QtCore.Signal(str)


class _Dot2Svg(QtCore.QRunnable):
    def __init__(self, source_fp, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        # otherwise it seems invisible
        self.resize(QtCore.QSize(self.height() + 100, self.width()))

    def setDotPath(self, path):
        if self._dot2svg:  # forget about previous, unfinished runners
            self._dot2svg.signals.error.disconnect()
            self._dot2svg.signals.result.disconnect()

        self._dot2svg = dot2svg = _Dot2Svg(path, parent=self)
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


class _GraphViewer(_DotViewer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.urlChanged.connect(self._graph_url_changed)
        self.sticky_nodes = list()
        self._graph = None

    @property
    def url_id_prefix(self):
        return "_node_id_"

    def _graph_url_changed(self, url: QtCore.QUrl):
        node_uri = url.toString()
        node_uri_stem = node_uri.split("/")[-1]
        if node_uri_stem.startswith(self.url_id_prefix):
            index = node_uri_stem.split(self.url_id_prefix)[-1]
            if not index.isdigit():
                raise ValueError(f"Expected suffix of node URL ID to be a digit. Got instead '{index}' of type: {type(index)}.")
            self.view([int(index)])

    @lru_cache(maxsize=None)
    def _subgraph_dot_path(self, node_indices: tuple):
        print(f"Getting subgraph for: {node_indices}")
        graph = self.graph
        successors = chain.from_iterable(
            graph.successors(index) for index in node_indices)
        predecessors = chain.from_iterable(
            graph.predecessors(index) for index in node_indices)
        nodes_of_interest = list(self.sticky_nodes)  # sticky nodes are always visible
        nodes_of_interest.extend(chain(node_indices, successors, predecessors))
        subgraph = graph.subgraph(nodes_of_interest)

        fd, fp = tempfile.mkstemp()
        nx_pydot.write_dot(subgraph, fp)

        return fp

    def view(self, node_indices: list):
        dot_path = self._subgraph_dot_path(tuple(node_indices))
        self.setDotPath(dot_path)

    @property
    def graph(self):
        return self._graph

    @graph.setter
    def graph(self, graph):
        self._subgraph_dot_path.cache_clear()
        self.sticky_nodes.clear()
        self._graph = graph


class PrimComposition(QtWidgets.QDialog):
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
        tree.setColumnCount(len(self._COLUMNS))
        tree.setHeaderLabels([k for k in self._COLUMNS])
        tree.setAlternatingRowColors(True)
        self._dot_view = _DotViewer(parent=self)
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
            strings = [str(getter(arc)) for getter in self._COLUMNS.values()]
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


class LayerTableModel(_sheets.UsdObjectTableModel):
    @property
    def layers(self):
        return self._objects

    @layers.setter
    def layers(self, value):
        self.beginResetModel()
        self._objects = list(value)
        self.endResetModel()


class LayerStackComposition(QtWidgets.QDialog):
    _LAYERS_COLUMNS = (
        _sheets._Column(f"{_core._EMOJI.ID.value} Layer Identifier", operator.attrgetter('identifier')),
        _sheets._Column("🚧 Dirty", operator.attrgetter('dirty')),
    )

    _PRIM_COLUMNS = (
        _sheets._Column("🧩 Opinion on Prim Path", lambda prim: str(prim.GetPath())),
        _sheets._Column(f"{_core._EMOJI.NAME.value} Prim Name", Usd.Prim.GetName),
    )

    def __init__(self, stage=None, parent=None, **kwargs):
        super().__init__(parent=parent, **kwargs)
        options = _sheets._ColumnOptions.SEARCH
        layers_model = LayerTableModel(columns=self._LAYERS_COLUMNS)
        self._layers = _sheets._Spreadsheet(layers_model, self._LAYERS_COLUMNS, options)
        prims_model = _sheets.StageTableModel(self._PRIM_COLUMNS)
        self._prims = _sheets._Spreadsheet(prims_model, self._PRIM_COLUMNS, options)

        for each in self._layers, self._prims:
            each.layout().setContentsMargins(0,0,0,0)
            each.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        horizontal = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        horizontal.addWidget(self._layers)
        horizontal.addWidget(self._prims)

        self._graph_view = _GraphViewer(parent=self)

        vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        vertical.addWidget(horizontal)
        vertical.addWidget(self._graph_view)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(vertical)

        self.setLayout(layout)
        self.setStage(stage or Usd.Stage.CreateInMemory())
        self.setWindowTitle("Layer Stack Composition")

        selectionModel = self._layers.table.selectionModel()
        selectionModel.selectionChanged.connect(self._selectionChanged)
        self._paths = dict()

    def _selectionChanged(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection):
        node_ids = [index.data(_core._USD_DATA_ROLE) for index in self._layers.table.selectedIndexes()]
        node_indices = set(chain.from_iterable(self._graph_view.graph.graph[_DESCRIPTION_IDS_BY_LAYERS_KEY][layer] for layer in node_ids))
        paths = set(chain.from_iterable(
            self._graph_view.graph.graph[_DESCRIPTION_PATHS_BY_IDS_KEY][i] for i in node_indices)
        )

        def _filter_predicate(p):
            return p.GetPath() in paths

        prims_model = self._prims.model
        prims_model._traverse_predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
        prims_model._filter_predicate = _filter_predicate
        prims_model._root_paths = paths
        prims_model.stage = self._stage
        self._prims.table.resizeColumnsToContents()
        self._prims.table.horizontalHeader()._updateVisualSections(0)
        self._graph_view.view(node_indices)

    @_core.wait()
    def setStage(self, stage):
        """Sets the USD stage the spreadsheet is looking at."""
        self._stage = stage
        predicate = _sheets._traverse_predicate(instance_proxies=True)
        prims = Usd.PrimRange.Stage(stage, predicate)
        graph = _compute_layerstack_graph(prims, self._graph_view.url_id_prefix)
        self._graph_view.graph = graph
        self._graph_view.sticky_nodes.extend(sorted(graph.graph[_DESCRIPTION_LEGEND_IDS_KEY]))
        self._layers.model.layers = graph.graph[_DESCRIPTION_IDS_BY_LAYERS_KEY]

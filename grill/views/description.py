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

_ARCS_LEGEND = MappingProxyType({
    Pcp.ArcTypePayload: dict(color=10, colorscheme="paired12", fontcolor=10),     # purple
    Pcp.ArcTypeReference: dict(color=6, colorscheme="paired12", fontcolor=6),     # red
    Pcp.ArcTypeVariant: dict(color=8, colorscheme="paired12", fontcolor=8),       # yellow
    Pcp.ArcTypeSpecialize: dict(color=12, colorscheme="paired12", fontcolor=12),  # brown
    Pcp.ArcTypeInherit: dict(color=4, colorscheme="paired12", fontcolor=4),       # green
})

_DESCRIPTION_LEGEND_IDS_KEY = 'legend_indices'
_DESCRIPTION_IDS_BY_LAYERS_KEY = 'indices_by_layers'


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


def _compute_layerstack_graph(prims, url_id_prefix):
    """Compute a layer stack graph for the provided prims

    Returns:
        nx_graph {int: <..., layer_stack: (Sdf.Layer,), prim_paths: {Sdf.Path}>}
    """
    graph = nx.DiGraph(tooltip="LayerStack Composition")

    legend_node_ids = list()
    for arc_type, edge_attrs in _ARCS_LEGEND.items():
        label = f" {arc_type.displayName}"
        arc_node_indices = (len(legend_node_ids), len(legend_node_ids)+1)
        graph.add_nodes_from(arc_node_indices, style='invis')
        graph.add_edge(*arc_node_indices, label=label, **edge_attrs)
        legend_node_ids.extend(arc_node_indices)

    layer_stacks_by_node_idx = dict()
    stack_id_by_node_idx = dict.fromkeys(legend_node_ids)  # {42: layer.identifier}
    stack_index_by_root_layer = dict()
    stack_indices_by_sublayers = defaultdict(set)  # layer: {int,}

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
        if root_layer in stack_index_by_root_layer:
            return stack_index_by_root_layer[root_layer]
        stack_index = len(stack_id_by_node_idx)
        if "Kitchen_payload.usd" in root_layer.identifier:
            print(f">>>>>>>>>>>>>>>>>>>>>> {locals()}")
        # stack_indices_by_sublayers[root_layer].add(stack_index)
        stack_index_by_root_layer[root_layer] = stack_index
        print(f"1. Index: {stack_index}, root layer: {root_layer}")
        stack_id_by_node_idx[stack_index] = root_layer
        label = f"{{{_layer_label(root_layer)}"
        sublayers = _sublayers(layer_stack)

        layer_stacks_by_node_idx[stack_index] = sublayers
        fillcolor = 'white'
        for layer in sublayers:
            if layer.dirty:
                fillcolor = 'palegoldenrod'
            # stack_indices_by_sublayers[layer].add(stack_index)
            if "Kitchen_payload.usd" in layer.identifier:
                print(f">>>>>>>>>>>>>>>>>>>>>> {locals()}")
            if layer == root_layer:  # root layer has been added at the start.
                continue
            print(f"2. Root indices: {stack_indices_by_sublayers[layer]} with layer: {layer}")
            label += f"|{_layer_label(layer)}"
        label += "}"
        ids = '\n'.join(f"{i}: {layer.realPath or layer.identifier}" for i, layer in enumerate(sublayers))
        tooltip = f"Layer Stack:\n{ids}"
        graph.add_node(
            stack_index,
            style='"rounded,filled"',
            shape='record',
            label=label,
            # https://stackoverflow.com/questions/16671966/multiline-tooltip-for-pydot-graph
            tooltip=tooltip.replace('\n', '&#10;'),
            title='world',
            fillcolor=fillcolor,
            href=f"{url_id_prefix}{stack_index}",
            layer_stack=sublayers,
            prim_paths=set(),
        )
        return stack_index

    # only query arcs that have specs on our prims.
    qFilter = Usd.PrimCompositionQuery.Filter()
    qFilter.hasSpecsFilter = Usd.PrimCompositionQuery.HasSpecsFilter.HasSpecs

    @lru_cache(maxsize=None)
    def _compute_composition(prim):
        query = Usd.PrimCompositionQuery(prim)
        query.filter = qFilter
        affected_indices = set()
        unmatched = list()
        for arc in query.GetCompositionArcs():
            node_index = _add_node(arc.GetTargetNode())
            affected_indices.add(node_index)
            target = arc.GetTargetNode().layerStack.identifier.rootLayer
            target_stack_idx = stack_index_by_root_layer[target]
            intro = arc.GetIntroducingLayer()
            if intro:
                edge_attrs = _ARCS_LEGEND[arc.GetArcType()]
                if intro in _sublayers(arc.GetTargetNode().layerStack):
                    source_index = target_stack_idx
                else:
                    # source_index = stack_index_by_root_layer[intro]
                    try:
                        source_index = stack_index_by_root_layer[intro]
                    except KeyError:
                        print(f">>>    Could not find {intro} to connect to {target}")
                        unmatched.append((intro, target_stack_idx, edge_attrs))
                        continue
                # else:
                #     graph.add_edge(source_index, target_stack_idx, **edge_attrs)
                graph.add_edge(source_index, target_stack_idx, **edge_attrs)
                # source_indices = stack_indices_by_sublayers[intro]
                # for edge_id in source_indices:
                #     graph.add_edge(edge_id, target_stack_idx, **edge_attrs)
        return affected_indices, unmatched

    all_unmatched = list()
    for prim in prims:
        # use a forwarded prim in case of instanceability to avoid computing same stack more than once
        prim_path = prim.GetPath()
        forwarded_prim = UsdUtils.GetPrimAtPathWithForwarding(prim.GetStage(), prim_path)
        affected_indices, unlinked = _compute_composition(forwarded_prim)
        if unlinked:
            print(f"!!!!!!!!!!!! {forwarded_prim}")
        all_unmatched.extend(unlinked)
        for each in affected_indices:
            graph.nodes[each]["prim_paths"].add(prim_path)

    # by this time we should have all indices computed and existing
    for source_layer, target_index, attrs in all_unmatched:
        try:
            source_index = stack_index_by_root_layer[source_layer]
        except KeyError:
            # msg = f"ERROR:\n{source_layer},\n{target_index},\n{stack_index_by_root_layer[target_index]}"
            msg = f"ERROR:\n{source_layer},\n{target_index},\n"
            print(msg)
            from pprint import pp
            pp(stack_index_by_root_layer)
            raise ValueError(msg)
        graph.add_edge(source_index, target_index, **attrs)

    graph.graph[_DESCRIPTION_IDS_BY_LAYERS_KEY] = MappingProxyType(
        # {k: tuple(v) for k, v in stack_indices_by_sublayers.items()}
        {k: v for k, v in stack_index_by_root_layer.items()}
    )
    graph.graph[_DESCRIPTION_LEGEND_IDS_KEY] = tuple(legend_node_ids)
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
        # avoid failures by using a copy on selected nodes + removing composition attributes
        subgraph = graph.subgraph(nodes_of_interest).copy()
        for each in subgraph:
            subgraph.nodes[each].pop("prim_paths", None)
            subgraph.nodes[each].pop("layer_stack", None)
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
        _sheets._Column(f"{_core._EMOJI.ID.value} Identifier", operator.attrgetter('identifier')),
        _sheets._Column("🚧 Dirty", operator.attrgetter('dirty')),
    )

    _PRIM_COLUMNS = (
        _sheets._Column("🧩 Prim Path", lambda prim: str(prim.GetPath())),
        _sheets._Column("🧩 Name", Usd.Prim.GetName),
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
        # node_indices = set(chain.from_iterable(self._graph_view.graph.graph['indices_by_layers'][layer] for layer in node_ids))
        node_indices = set(self._graph_view.graph.graph['indices_by_layers'][layer] for layer in node_ids)
        paths = set(chain.from_iterable(self._graph_view.graph.nodes[i]['prim_paths'] for i in node_indices))

        def _filter_predicate(p):
            return p.GetPath() in paths

        prims_model = self._prims.model
        # prims_model._traverse_predicate = Usd.TraverseInstanceProxies()
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
        self._graph_view.sticky_nodes.extend(sorted(graph.graph['legend_indices']))
        self._layers.model.layers = graph.graph['indices_by_layers']

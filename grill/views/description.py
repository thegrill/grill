"""Views related to USD scene description"""
from __future__ import annotations

import shutil
import typing
import operator
import tempfile
import subprocess
import collections

from pathlib import Path
from itertools import chain
from functools import lru_cache
from collections import defaultdict
from types import MappingProxyType

import networkx as nx
from networkx.drawing import nx_pydot
from pxr import Sdf, Usd, Pcp, UsdUtils
from PySide2 import QtWidgets, QtCore, QtWebEngineWidgets

from . import sheets as _sheets, _core

_ARCS_LEGEND = MappingProxyType({
    Pcp.ArcTypeInherit: dict(color='mediumseagreen', fontcolor='mediumseagreen'),  # green
    Pcp.ArcTypeVariant: dict(color='orange', fontcolor='orange'),  # yellow
    Pcp.ArcTypeReference: dict(color='crimson', fontcolor='crimson'),  # red
    Pcp.ArcTypePayload: dict(color='darkslateblue', fontcolor='darkslateblue'),  # purple
    Pcp.ArcTypeSpecialize: dict(color='sienna', fontcolor='sienna'),  # brown
})


@lru_cache(maxsize=None)
def _edge_color(edge_arcs):
    return dict(  # need to wrap color in quotes to allow multicolor
        color=f'"{":".join(_ARCS_LEGEND[arc]["color"] for arc in edge_arcs)}"',
    )


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


def _compute_layerstack_graph(prims, url_prefix) -> _GraphInfo:
    """Compute layer stack graph info for the provided prims"""

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
    def _sublayers(layer_stack):  # {Sdf.Layer: int}
        return MappingProxyType({v: i for i, v in enumerate(_walk_layer_tree(layer_stack.layerTree))})

    def _add_node(pcp_node):
        layer_stack = pcp_node.layerStack
        root_layer = layer_stack.identifier.rootLayer
        sublayers = _sublayers(layer_stack)
        try:
            # thought: we could lru_cache here but need to test hashability of Pcp objects
            # for now, we use the root layers themselves
            return ids_by_root_layer[root_layer], sublayers
        except KeyError:
            pass  # layerStack still not processed, let's add it
        ids_by_root_layer[root_layer] = index = len(all_nodes)

        attrs = dict(style='"rounded,filled"', shape='record', href=f"{url_prefix}{index}", fillcolor="white", color="darkslategray")
        label = f"{{<0>{_layer_label(root_layer)}"
        tooltip = "Layer Stack:"
        for layer, layer_index in sublayers.items():
            indices_by_sublayers[layer].add(index)
            if layer.dirty:
                attrs['color'] = 'darkorange'  # can probably be dashed as well?
            # https://stackoverflow.com/questions/16671966/multiline-tooltip-for-pydot-graph
            tooltip += f"&#10;{layer_index}: {layer.realPath or layer.identifier}"
            if layer != root_layer:  # root layer has been added at the start.
                label += f"|<{layer_index}>{_layer_label(layer)}"
        label += "}"

        all_nodes[index] = dict(label=label, tooltip=tooltip, **attrs)
        return index, sublayers

    @lru_cache(maxsize=None)
    def _compute_composition(_prim):
        query = Usd.PrimCompositionQuery(_prim)
        query.filter = query_filter
        affected_by = set()  # {int}  indices of nodes affecting this prim
        prim_edges = defaultdict(lambda: defaultdict(dict))  # {(source_int, target_int): {Pcp.ArcType...}}
        for arc in query.GetCompositionArcs():
            target_idx, __ = _add_node(arc.GetTargetNode())
            affected_by.add(target_idx)
            source_layer = arc.GetIntroducingLayer()
            if source_layer:
                source_idx, source_layers = _add_node(arc.GetIntroducingNode())
                source_port = source_layers[source_layer]
                prim_edges[source_idx, target_idx][source_port, None][arc.GetArcType()] = {}  # TODO: probably include useful info here?
        return affected_by, prim_edges

    def _freeze(dct):
        return MappingProxyType({k: tuple(sorted(v)) for k,v in dct.items()})

    query_filter = Usd.PrimCompositionQuery.Filter()
    query_filter.hasSpecsFilter = Usd.PrimCompositionQuery.HasSpecsFilter.HasSpecs
    all_nodes = dict()  # {int: dict}

    all_edges = defaultdict(lambda: defaultdict(dict))  # {(int, int, int, int): {Pcp.ArcType: {}, ..., }}
    for arc_type, attributes in _ARCS_LEGEND.items():
        arc_label_node_ids = (len(all_nodes), len(all_nodes) + 1)
        all_nodes.update(dict.fromkeys(arc_label_node_ids, dict(style='invis')))
        all_edges[arc_label_node_ids][None, None][arc_type] = dict(label=f" {arc_type.displayName}", **attributes)

    legend_node_ids = tuple(all_nodes)
    ids_by_root_layer = dict()
    indices_by_sublayers = defaultdict(set)  # {Sdf.Layer: {int,} }
    paths_by_node_idx = defaultdict(set)
    for prim in prims:
        # use a forwarded prim in case of instanceability to avoid computing same stack more than once
        prim_path = prim.GetPath()
        forwarded_prim = UsdUtils.GetPrimAtPathWithForwarding(prim.GetStage(), prim_path)
        affected_by_indices, edges = _compute_composition(forwarded_prim)
        for edge_data, edge_arcs in edges.items():
            all_edges[edge_data].update(edge_arcs)
        for affected_by_idx in affected_by_indices:
            paths_by_node_idx[affected_by_idx].add(prim_path)

    return _GraphInfo(
        edges=MappingProxyType(all_edges),
        nodes=MappingProxyType(all_nodes),
        sticky_nodes=legend_node_ids,
        paths_by_ids=_freeze(paths_by_node_idx),
        ids_by_layers=_freeze(indices_by_sublayers),
    )


class _GraphInfo(typing.NamedTuple):
    sticky_nodes: tuple
    ids_by_layers: typing.Mapping
    edges: typing.Mapping
    nodes: typing.Mapping
    paths_by_ids: typing.Mapping


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
        self._viewing = frozenset()

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
        graph = self.graph
        successors = chain.from_iterable(graph.successors(index) for index in node_indices)
        predecessors = chain.from_iterable(graph.predecessors(index) for index in node_indices)
        nodes_of_interest = chain(self.sticky_nodes, node_indices, successors, predecessors)
        subgraph = graph.subgraph(nodes_of_interest)

        fd, fp = tempfile.mkstemp()
        nx_pydot.write_dot(subgraph, fp)
        return fp

    def view(self, node_indices: typing.Iterable):
        dot_path = self._subgraph_dot_path(tuple(node_indices))
        self._viewing = frozenset(node_indices)
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


class LayerTableModel(_sheets._ObjectTableModel):
    def data(self, index:QtCore.QModelIndex, role:int=...) -> typing.Any:
        if role == QtCore.Qt.ForegroundRole:
            layer = self.data(index, role=_core._QT_OBJECT_DATA_ROLE)
            color = _sheets._PrimTextColor.ARCS if layer.dirty else _sheets._PrimTextColor.NONE
            return color.value
        return super().data(index, role)

    def setLayers(self, value):
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
        self._prims = _sheets._StageSpreadsheet(columns=self._PRIM_COLUMNS, options=options)
        # TODO: better APIs for this default setup?
        self._prims.sorting_enabled.setVisible(False)
        self._prims._model_hierarchy.setChecked(False)
        for each in (self._prims._classes, self._prims._orphaned, self._prims._inactive):
            each.setChecked(True)
        self._prims._filters_logical_op.setCurrentIndex(1)
        for each in self._layers, self._prims:
            each.layout().setContentsMargins(0,0,0,0)

        horizontal = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        horizontal.addWidget(self._layers)
        horizontal.addWidget(self._prims)

        self._graph_view = _GraphViewer(parent=self)

        _graph_legend_controls = QtWidgets.QFrame()
        _graph_controls_layout = QtWidgets.QHBoxLayout()
        _graph_legend_controls.setLayout(_graph_controls_layout)
        self._graph_edge_include = _graph_edge_include = {}
        self._graph_precise_source_ports = QtWidgets.QCheckBox("Precise Source Layer")
        self._graph_precise_source_ports.setChecked(False)
        self._graph_precise_source_ports.clicked.connect(lambda: self._update_graph_from_graph_info(self._computed_graph_info))
        for arc, arc_details in _ARCS_LEGEND.items():
            arc_btn = QtWidgets.QCheckBox(arc.displayName.title())
            arc_btn.setStyleSheet(f"background-color: {arc_details['color']}; padding: 3px; border-width: 1px; border-radius: 3;")
            arc_btn.setChecked(True)
            _graph_controls_layout.addWidget(arc_btn)
            _graph_edge_include[arc] = arc_btn
            arc_btn.clicked.connect(lambda: self._update_graph_from_graph_info(self._computed_graph_info))
        _graph_controls_layout.addWidget(self._graph_precise_source_ports)
        _graph_controls_layout.addStretch(0)
        _graph_legend_controls.setFixedHeight(_graph_legend_controls.sizeHint().height())
        vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        vertical.addWidget(horizontal)
        vertical.addWidget(_graph_legend_controls)
        vertical.addWidget(self._graph_view)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(vertical)
        self.setLayout(layout)
        selectionModel = self._layers.table.selectionModel()
        selectionModel.selectionChanged.connect(self._selectionChanged)
        self._prim_paths_to_compute = set()
        self.setStage(stage or Usd.Stage.CreateInMemory())
        self.setWindowTitle("Layer Stack Composition")

    def _selectionChanged(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection):
        node_ids = [index.data(_core._QT_OBJECT_DATA_ROLE) for index in self._layers.table.selectedIndexes()]
        node_indices = set(chain.from_iterable(self._computed_graph_info.ids_by_layers[layer] for layer in node_ids))

        prims_model = self._prims.model
        prims_model._root_paths = paths = set(chain.from_iterable(
            # some layers from the layer stack might be on our selected indices but they wont be on the paths_by_ids
            self._computed_graph_info.paths_by_ids[i] for i in node_indices if i in self._computed_graph_info.paths_by_ids)
        )
        all_paths = set(chain.from_iterable(self._computed_graph_info.paths_by_ids.values()))
        self._prims._filter_predicate = lambda prim: prim.GetPath() in (paths or all_paths)
        self._prims._update_stage()
        self._graph_view.view(node_indices)

    @_core.wait()
    def setStage(self, stage):
        """Sets the USD stage the spreadsheet is looking at."""
        self._stage = stage
        predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
        prims = Usd.PrimRange.Stage(stage, predicate)
        if self._prim_paths_to_compute:
            prims = (p for p in prims if p.GetPath() in self._prim_paths_to_compute)

        graph_info = _compute_layerstack_graph(prims, self._graph_view.url_id_prefix)
        self._prims.setStage(stage)
        self._update_graph_from_graph_info(graph_info)
        self._selectionChanged(None, None)

    def setPrimPaths(self, value):
        self._prim_paths_to_compute = {p if isinstance(p, Sdf.Path) else Sdf.Path(p) for p in value}
        print(self._prim_paths_to_compute)

    def _update_graph_from_graph_info(self, graph_info: _GraphInfo):
        self._computed_graph_info = graph_info
        graph = nx.MultiDiGraph()
        graph.graph['graph'] = dict(tooltip="LayerStack Composition")
        graph.add_nodes_from(self._computed_graph_info.nodes.items())
        graph.add_edges_from(self._iedges(graph_info))
        self._graph_view.graph = graph
        self._graph_view.sticky_nodes.extend(graph_info.sticky_nodes)
        self._layers.model.setLayers(graph_info.ids_by_layers)
        # view intersection as we might be seeing nodes that no longer exist
        # self._graph_view.view(self._graph_view._viewing)  # TODO: check if this is better <- and reset _viewing somewhere else
        self._graph_view.view(self._graph_view._viewing.intersection(graph_info.nodes))

    def _iedges(self, graph_info: _GraphInfo):
        checked_arcs = {arc for arc, control in self._graph_edge_include.items() if control.isChecked()}
        precise_ports = self._graph_precise_source_ports.isChecked()
        for (src, tgt), edge_info in graph_info.edges.items():
            arc_ports = edge_info if precise_ports else {(None, None): collections.ChainMap(*edge_info.values())}
            for (src_port, tgt_port), arcs in arc_ports.items():
                visible_arcs = {arc: attrs for arc, attrs in arcs.items() if (arc in checked_arcs or {src, tgt}.issubset(graph_info.sticky_nodes))}
                if visible_arcs:
                    # Composition arcs target layer stacks, so we don't specify port on our target nodes
                    # since it does not change and visually helps for network layout.
                    ports = {"tailport": src_port, "headport":None} if precise_ports else {}
                    color = _edge_color(tuple(visible_arcs))
                    yield src, tgt, collections.ChainMap(ports, color, *visible_arcs.values())

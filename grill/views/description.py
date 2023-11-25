"""Views related to USD scene description"""
from __future__ import annotations

import re
import os
import typing
import weakref
import operator
import tempfile
import subprocess
import contextvars
import collections

from pathlib import Path
from itertools import chain
from collections import defaultdict
from functools import cache, partial
from types import MappingProxyType

import networkx as nx
from pxr import UsdUtils, UsdShade, Usd, Ar, Pcp, Sdf, Tf
from ._qt import QtWidgets, QtGui, QtCore, QtSvg

from .. import usd as _usd
from . import sheets as _sheets, _core, _graph
from ._core import _which


_USE_WEB_ENGINE = os.getenv("GRILL_GRAPH_VIEW_VIA_WEB_ENGINE")
# _USE_WEB_ENGINE = True
_color_attrs = lambda color: dict.fromkeys(("color", "fontcolor"), color)
_ARCS_LEGEND = MappingProxyType({
    Pcp.ArcTypeInherit: _color_attrs('mediumseagreen'),
    Pcp.ArcTypeVariant: _color_attrs('orange'),
    Pcp.ArcTypeReference: _color_attrs('crimson'),  # ~red
    Pcp.ArcTypePayload: _color_attrs('#9370db'),  # ~purple
    Pcp.ArcTypeSpecialize: _color_attrs('sienna'),  # ~brown
})
_BROWSE_CONTENTS_MENU_TITLE = 'Browse Contents'
_PALETTE = contextvars.ContextVar("_PALETTE", default=1)  # (0 == dark, 1 == light)
_HIGHLIGHT_COLORS = MappingProxyType(
    {name: (QtGui.QColor(dark), QtGui.QColor(light)) for name, (dark, light) in (
        ("comment", ("gray", "gray")),
        # A mix between:
        # https://en.wikipedia.org/wiki/Solarized#Colors
        # https://www.w3schools.com/colors/colors_palettes.asp
        *((key, ("#f7786b", "#d33682")) for key in ("specifier", "rel_op", "value_assignment", "references", "reference")),
        *((key, ("#f7cac9", "#f7786b")) for key in ("prim_name", "identifier_prim_path", "relationship", "apiSchemas")),
        *((key, ("#b5e7a0", "#859900")) for key in ("metadata", "interpolation_meta", "custom_meta")),
        *((key, ("#ffcc5c", "#b58900")) for key in ("identifier", "variantSets", "variantSet", "variants", "variant", "prop_name", "rel_name", "outline_details")),
        *((key, (_ARCS_LEGEND[Pcp.ArcTypeInherit]['color'], _ARCS_LEGEND[Pcp.ArcTypeInherit]['color'])) for key in ("inherit", "inherits")),
        *((key, ("#9a94bf", _ARCS_LEGEND[Pcp.ArcTypePayload]['color'])) for key in ("payload", "payloads")),
        *((key,  ("#c18f76", _ARCS_LEGEND[Pcp.ArcTypeSpecialize]['color'])) for key in ("specialize", "specializes")),
        ("list_op", ("#e3eaa7", "#2aa198")),
        *((key, ("#5b9aa0", "#5b9aa0")) for key in ("prim_type", "prop_type", "prop_array")),
        *((key, ("#87bdd8", "#034f84")) for key in ("set_string", "string_value")),
        ("collapsed", ("#92a8d1", "#36486b")),
        ("boolean", ("#b7d7e8", "#50394c")),
        ("number", ("#bccad6", "#667292")),
    )}
)
_HIGHLIGHT_PATTERN = re.compile(
    rf'(^(?P<comment>#.*$)|^( *(?P<specifier>def|over|class)( (?P<prim_type>\w+))? (?P<prim_name>\"\w+\")| +((?P<metadata>(?P<arc_selection>variants|payload)|{"|".join(_usd._metadata_keys())})|(?P<list_op>add|(ap|pre)pend|delete) (?P<arc>inherits|variantSets|references|payload|specializes|apiSchemas|rel (?P<rel_name>[\w:]+))|(?P<variantSet>variantSet) (?P<set_string>\"\w+\")|(?P<custom_meta>custom )?(?P<interpolation_meta>uniform )?(?P<prop_type>{"|".join(_usd._attr_value_type_names())}|dictionary|rel)(?P<prop_array>\[])? (?P<prop_name>[\w:.]+))( (\(|((?P<value_assignment>= )[\[(]?))|$))|(?P<string_value>\"[^\"]+\")|(?P<identifier>@[^@]+@)(?P<identifier_prim_path><[/\w]+>)?|(?P<relationship><[/\w:.]+>)|(?P<collapsed><< [^>]+ >>)|(?P<boolean>true|false)|(?P<number>-?[\d.]+))'
)

_OUTLINE_SDF_PATTERN = re.compile(  # this is a very minimal draft to have colors on the outline sdffilter mode.
    rf'^((?P<identifier_prim_path>(  )?</[/\w+.:{{}}=]*(\[[/\w+.:{{}}=]+])?>)( : (?P<specifier>\w+))?|(  )?(?P<metadata>\w+)(: ((?P<number>-?[\d.]+)|(?P<string_value>[\w:.]+)(?P<prop_array>\[])?|(?P<collapsed><< [^>]+ >>)|(\[ (?P<relationship>[\w /.:{{}}=]+) ])|(?P<outline_details>.+)))?)$'  # sad, last item is a dot, lazy atm
)

_TREE_PATTERN = re.compile(  # draft as well output of usdtree
    rf'^(?P<identifier_prim_path>([/`|\s:]+-+)(\w+)?)(\((?P<metadata>\w+)\)|(?P<prop_name>\.[\w:]+)|( \[(?P<specifier>def|over|class)( (?P<prim_type>\w+))?])( \((?P<custom_meta>[\w\s=]+)\))?)'
)

_USD_COMPOSITION_ARC_QUERY_METHODS = (
    Usd.CompositionArc.HasSpecs,
    Usd.CompositionArc.IsAncestral,
    Usd.CompositionArc.IsImplicit,
    Usd.CompositionArc.IsIntroducedInRootLayerPrimSpec,
    Usd.CompositionArc.IsIntroducedInRootLayerStack,
)
_USD_COMPOSITION_ARC_QUERY_KEYS = tuple(func.__name__ for func in _USD_COMPOSITION_ARC_QUERY_METHODS)
_USD_COMPOSITION_ARC_QUERY_DEFAULTS = lambda: dict.fromkeys(_USD_COMPOSITION_ARC_QUERY_KEYS, False)


def _run(args: list):
    if not args or not args[0]:
        raise ValueError(f"Expected arguments to contain an executable value on the first index. Got: {args}")
    kwargs = dict(capture_output=True)
    if hasattr(subprocess, 'CREATE_NO_WINDOW'):  # not on CentOS
        kwargs.update(creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        result = subprocess.run(args, **kwargs)
    except TypeError as exc:
        return str(exc), ""
    else:
        error = result.stderr.decode() if result.returncode else None
        return error, result.stdout.decode()


@cache
def _edge_color(edge_arcs):
    return dict(color=":".join(_ARCS_LEGEND[arc]["color"] for arc in edge_arcs))


@cache
def _dot_2_svg(sourcepath):
    print(f"Creating svg for: {sourcepath}")
    import datetime
    now = datetime.datetime.now()
    targetpath = f"{sourcepath}.svg"
    args = [_which("dot"), sourcepath, "-Tsvg", "-o", targetpath]
    error, __ = _run(args)
    total = datetime.datetime.now() - now
    print(f"{total=}")
    return error, targetpath


def _format_layer_contents(layer, output_type="pseudoLayer", paths=tuple(), output_args=tuple()):
    """Textual representation of a layer using ``sdffilter``."""
    with tempfile.TemporaryDirectory() as target_dir:
        name = Path(layer.realPath).stem if layer.realPath else "".join(c if c.isalnum() else "_" for c in layer.identifier)
        path = Path(target_dir) / f"{name}.usd"
        layer.Export(str(path))
        path_args = ("-p", "|".join(re.escape(str(p)) for p in paths)) if paths else tuple()
        if output_type == "usdtree":
            args = [_which("usdtree"), "-a", "-m", str(path)]
        else:
            args = [_which("sdffilter"), "--outputType", output_type, *output_args, *path_args, str(path)]
        return _run(args)


def _layer_label(layer):
    return layer.GetDisplayName() or layer.identifier


@cache
def _highlight_syntax_format(key, value):
    text_fmt = QtGui.QTextCharFormat()
    if key == "arc":
        key = "rel_op" if value.startswith("rel") else value
    elif key == "arc_selection":
        key = value
    elif key == "comment":
        text_fmt.setFontItalic(True)
    elif key == "specifier":
        if value == "over":
            text_fmt.setFontItalic(True)
        elif value == "class":
            text_fmt.setFontLetterSpacing(135)
    elif key == "identifier":
        text_fmt.setFontUnderline(True)
    text_fmt.setForeground(_HIGHLIGHT_COLORS[key][_PALETTE.get()])
    return text_fmt


def _compute_layerstack_graph(prims, url_prefix) -> _GraphInfo:
    """Compute layer stack graph info for the provided prims"""

    @cache
    def _sublayers(layer_stack):  # {Sdf.Layer: int}
        return MappingProxyType({v: i for i, v in enumerate(layer_stack.layers)})

    def _add_node(pcp_node):
        layer_stack = pcp_node.layerStack
        root_layer = layer_stack.identifier.rootLayer
        sublayers = _sublayers(layer_stack)
        try:  # lru_cache not compatible with Pcp objects, so we "cache" at the layer level
            return ids_by_root_layer[root_layer], sublayers
        except KeyError:
            pass  # layerStack still not processed, let's add it
        ids_by_root_layer[root_layer] = index = len(all_nodes)

        attrs = dict(style='rounded,filled', shape='record', href=f"{url_prefix}{index}", fillcolor="white", color="darkslategray")
        plugs = dict()
        label = '{'
        tooltip = 'Layer Stack:'
        for layer, layer_index in sublayers.items():
            indices_by_sublayers[layer].add(index)
            if layer.dirty:
                attrs['color'] = 'darkorange'  # can probably be dashed as well?
            # For new line: https://stackoverflow.com/questions/16671966/multiline-tooltip-for-pydot-graph
            # For Windows path sep: https://stackoverflow.com/questions/15094591/how-to-escape-forwardslash-character-in-html-but-have-it-passed-correctly-to-jav
            tooltip += f"&#10;{layer_index}: {(layer.realPath or layer.identifier)}".replace('\\', '&#47;')
            plugs[layer_index] = layer_index
            label += f"{'' if layer_index == 0 else '|'}<{layer_index}>{_layer_label(layer)}"
        label += '}'
        attrs['plugs'] = plugs
        attrs['active_plugs'] = set()  # all active connections, for GUI
        all_nodes[index] = dict(label=label, tooltip=tooltip, **attrs)
        return index, sublayers

    @cache
    def _compute_composition(_prim):
        query = Usd.PrimCompositionQuery(_prim)
        affected_by = set()  # {int}  indices of nodes affecting this prim
        for arc in query.GetCompositionArcs():
            target_idx, __ = _add_node(arc.GetTargetNode())
            affected_by.add(target_idx)
            source_layer = arc.GetIntroducingLayer()
            if source_layer:
                # Note: arc.GetIntroducingNode() is not guaranteed to be the same as
                # arc.GetTargetNode().origin nor arc.GetTargetNode().GetOriginRootNode()
                source_idx, source_layers = _add_node(arc.GetIntroducingNode())
                source_port = source_layers[source_layer]
                all_nodes[source_idx]['active_plugs'].add(source_port)  # all connections, for GUI
                all_edges[source_idx, target_idx][source_port][arc.GetArcType()].update(
                    {func.__name__:  is_fun for func in _USD_COMPOSITION_ARC_QUERY_METHODS if (is_fun := func(arc))}
                )

        return affected_by

    all_nodes = dict()  # {int: dict}
    all_edges = defaultdict(                            #   { (source_node: int, target_node: int):
        lambda: defaultdict(                            #       { source_port: int:
            lambda: defaultdict(                        #           { Pcp.ArcType:
                _USD_COMPOSITION_ARC_QUERY_DEFAULTS     #               { HasArcs: bool, IsImplicit: bool, ... }
            )                                           #           }
        )                                               #       }
    )                                                   #   }

    for arc_type, attributes in _ARCS_LEGEND.items():
        arc_label_node_ids = (len(all_nodes), len(all_nodes) + 1)
        all_nodes.update(dict.fromkeys(arc_label_node_ids, dict(style='invis')))
        all_edges[arc_label_node_ids][None][arc_type] = dict(label=f" {arc_type.displayName}", **attributes)

    legend_node_ids = tuple(all_nodes)
    ids_by_root_layer = dict()
    indices_by_sublayers = defaultdict(set)  # {Sdf.Layer: {int,} }
    paths_by_node_idx = defaultdict(set)

    for prim in prims:
        # use a forwarded prim in case of instanceability to avoid computing same stack more than once
        prim_path = prim.GetPath()
        for affected_by_idx in _compute_composition(UsdUtils.GetPrimAtPathWithForwarding(prim.GetStage(), prim_path)):
            paths_by_node_idx[affected_by_idx].add(prim_path)

    return _GraphInfo(
        edges=MappingProxyType(all_edges),
        nodes=MappingProxyType(all_nodes),
        sticky_nodes=legend_node_ids,
        paths_by_ids=paths_by_node_idx,
        ids_by_layers=indices_by_sublayers,
    )


def _graph_from_connections(prim: Usd.Prim) -> nx.MultiDiGraph:
    connections_api = UsdShade.ConnectableAPI(prim)
    graph = nx.MultiDiGraph()
    outline_color = "#4682B4"  # 'steelblue'
    background_color = "#F0FFFF"  # 'azure'
    graph.graph['graph'] = {'rankdir': 'LR'}

    graph.graph['node'] = {'shape': 'none', 'color': outline_color, 'fillcolor': background_color}  # color and fillcolor used for HTML view
    graph.graph['edge'] = {"color": 'crimson'}

    all_nodes = dict()  # {node_id: {graphviz_attr: value}}
    edges = list()  # [(source_node_id, target_node_id, {source_plug_name, target_plug_name, graphviz_attrs})]

    @cache
    def _get_node_id(api):
        return str(api.GetPrim().GetPath())

    @cache
    def _add_edges(src_node, src_name, tgt_node, tgt_name):
        tooltip = f"{src_node}.{src_name} -> {tgt_node}.{tgt_name}"
        edges.append((src_node, tgt_node, {"tailport": src_name, "headport": tgt_name, "tooltip": tooltip}))

    plug_colors = {
        UsdShade.Input: outline_color,  # blue
        UsdShade.Output: "#F08080"  # "lightcoral",  # pink
    }
    table_row = '<tr><td port="{port}" border="0" bgcolor="{color}" style="ROUNDED">{text}</td></tr>'

    def traverse(api: UsdShade.ConnectableAPI):
        node_id = _get_node_id(api.GetPrim())
        # label = f'<<table border="1" cellspacing="2" style="ROUNDED" bgcolor="white" color="{outline_color}">'
        label = f'<<table border="1" cellspacing="2" style="ROUNDED" bgcolor="{background_color}" color="{outline_color}">'
        label += table_row.format(port="", color="white", text=f'<font color="{outline_color}"><b>{api.GetPrim().GetName()}</b></font>')
        plugs = {"": 0}  # {graphviz port name: port index order}
        active_plugs = set()
        for index, plug in enumerate(chain(api.GetInputs(), api.GetOutputs()), start=1):  # we start at 1 because index 0 is the node itself
            plug_name = plug.GetBaseName()
            sources, __ = plug.GetConnectedSources()  # (valid, invalid): we care only about valid sources (index 0)
            color = plug_colors[type(plug)] if isinstance(plug, UsdShade.Output) or sources else background_color
            label += table_row.format(port=plug_name, color=color, text=plug_name)
            for source in sources:
                _add_edges(_get_node_id(source.source.GetPrim()), source.sourceName, node_id, plug_name)
                traverse(source.source)
            plugs[plug_name] = index
            active_plugs.add(plug_name)  # TODO: add only actual plugged properties, right now we're adding all of them
        label += '</table>>'
        all_nodes[node_id] = dict(label=label, plugs=plugs, active_plugs=active_plugs)

    traverse(connections_api)

    graph.add_nodes_from(all_nodes.items())
    graph.add_edges_from(edges)
    from pprint import pp
    pp(f"{_get_node_id.cache_info()=}")
    pp(f"{_add_edges.cache_info()=}")
    return graph


def _launch_content_browser(layers, parent, context, paths=tuple()):
    dialog = _start_content_browser(layers, parent, context, paths)
    dialog.show()


def _start_content_browser(layers, parent, context, paths=tuple()):
    dialog = QtWidgets.QDialog(parent=parent)
    dialog.setWindowTitle("Layer Content Browser")
    layout = QtWidgets.QVBoxLayout()
    vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
    for layer in layers:
        browser = _PseudoUSDBrowser(layer, parent=dialog, resolver_context=context, paths=paths)
        vertical.addWidget(browser)
    layout.addWidget(vertical)
    dialog.setLayout(layout)
    return dialog


class _GraphInfo(typing.NamedTuple):
    sticky_nodes: tuple
    ids_by_layers: typing.Mapping
    edges: typing.Mapping
    nodes: typing.Mapping
    paths_by_ids: typing.Mapping


class _Dot2SvgSignals(QtCore.QObject):
    error = QtCore.Signal(str)
    result = QtCore.Signal(str)


_DOT_ENVIRONMENT_ERROR = """In order to display composition arcs in a graph,
the 'dot' command must be available on the current environment.

Please make sure graphviz is installed and 'dot' available on the system's PATH environment variable.

For more details on installing graphviz, visit https://pygraphviz.github.io/documentation/stable/install.html
"""


@cache
def _nx_graph_edge_filter(*, has_specs=None, ancestral=None, implicit=None, introduced_in_root_layer_prim_spec=None, introduced_in_root_layer_stack=None):
    match = {
        key: value for key, value in (
            ("HasSpecs", has_specs),
            ("IsAncestral", ancestral),
            ("IsImplicit", implicit),
            ("IsIntroducedInRootLayerPrimSpec", introduced_in_root_layer_prim_spec),
            ("IsIntroducedInRootLayerStack", introduced_in_root_layer_stack),
        ) if value is not None
    }
    print(f"{match=}")
    if not match:
        return None
    return lambda edge_info: match.items() <= edge_info.items()


class _Dot2Svg(QtCore.QRunnable):
    def __init__(self, source_fp, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.signals = _Dot2SvgSignals()
        self.source_fp = source_fp

    @QtCore.Slot()
    def run(self):
        if not _which("dot"):
            self.signals.error.emit(_DOT_ENVIRONMENT_ERROR)
            return
        error, svg_fp = _dot_2_svg(self.source_fp)
        self.signals.error.emit(error) if error else self.signals.result.emit(svg_fp)


class _SvgPixmapViewport(_graph._GraphicsViewport):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        scene = QtWidgets.QGraphicsScene(self)
        self.setScene(scene)

    def load(self, filepath):
        scene = self.scene()
        scene.clear()

        renderer = QtSvg.QSvgRenderer(filepath)
        image = QtGui.QImage(renderer.defaultSize() * 1.5, QtGui.QImage.Format_ARGB32)
        image.fill(QtCore.Qt.transparent)

        painter = QtGui.QPainter(image)
        renderer.render(painter)
        painter.end()

        pixmap = QtGui.QPixmap.fromImage(image)
        self._svg_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        scene.addItem(self._svg_item)


_SVG_AS_PIXMAP = False
class _DotViewer(QtWidgets.QFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()
        # After some experiments, QWebEngineView brings nicer UX and speed than QGraphicsSvgItem and QSvgWidget
        if not _SVG_AS_PIXMAP:
            from PySide6 import QtWebEngineWidgets
            self._graph_view = QtWebEngineWidgets.QWebEngineView(parent=self)
            self.urlChanged = self._graph_view.urlChanged
        else:
            self._graph_view = _SvgPixmapViewport(parent=self)

        self._error_view = QtWidgets.QTextBrowser(parent=self)
        layout.addWidget(self._graph_view)
        layout.addWidget(self._error_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self._error_view.setVisible(False)
        self.setLayout(layout)
        self._dot2svg = None
        self._threadpool = QtCore.QThreadPool()
        if not _SVG_AS_PIXMAP:
            # otherwise it seems invisible
            self.setMinimumHeight(100)

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
        if not _SVG_AS_PIXMAP:
            filepath = QtCore.QUrl.fromLocalFile(filepath)
        self._graph_view.load(filepath)


class _GraphSVGViewer(_DotViewer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.urlChanged.connect(self._graph_url_changed)
        self.sticky_nodes = list()
        self._graph = None
        self._viewing = frozenset()
        self._filter_nodes = None
        self._filter_edges = None

    @property
    def filter_edges(self):
        return self._filter_edges

    @filter_edges.setter
    def filter_edges(self, value):
        if value == self._filter_edges:
            return
        self._subgraph_dot_path.cache_clear()
        if value:
            predicate = lambda *edge: value(*edge) or bool({edge[0], edge[1]}.intersection(self.sticky_nodes))
        else:
            predicate = None
        self._filter_edges = predicate

    @property
    def url_id_prefix(self):
        return "_node_id_"

    def _graph_url_changed(self, url: QtCore.QUrl):
        node_uri = url.toString()
        node_uri_stem = node_uri.split("/")[-1]
        if node_uri_stem.startswith(self.url_id_prefix):
            index = node_uri_stem.split(self.url_id_prefix)[-1]
            self.view([int(index)] if index.isdigit() else [index])

    @cache
    def _subgraph_dot_path(self, node_indices: tuple):
        graph = self.graph
        if not graph:
            raise RuntimeError(f"'graph' attribute not set yet on {self}. Can't view nodes {node_indices}")
        successors = chain.from_iterable(graph.successors(index) for index in node_indices)
        predecessors = chain.from_iterable(graph.predecessors(index) for index in node_indices)
        nodes_of_interest = chain(self.sticky_nodes, node_indices, successors, predecessors)
        subgraph = graph.subgraph(nodes_of_interest)

        filters = {}
        if self._filter_nodes:
            filters['filter_node'] = self._filter_nodes
        if self.filter_edges:
            print(f"{self.filter_edges=}")
            print("FILTERRRINNG")
            filters['filter_edge'] = self.filter_edges
        if filters:
            subgraph = nx.subgraph_view(subgraph, **filters)

        fd, fp = tempfile.mkstemp()
        try:
            nx.nx_agraph.write_dot(subgraph, fp)
        except ImportError as exc:
            error = f"{exc}\n\n{_DOT_ENVIRONMENT_ERROR}"
        else:
            error = ""
        return error, fp

    def view(self, node_indices: typing.Iterable):
        error, dot_path = self._subgraph_dot_path(tuple(node_indices))
        self._viewing = frozenset(node_indices)
        if error:
            self._on_dot_error(error)
        else:
            self.setDotPath(dot_path)

    @property
    def graph(self):
        return self._graph

    @graph.setter
    def graph(self, graph):
        self._subgraph_dot_path.cache_clear()
        self.sticky_nodes.clear()
        self._graph = graph


class _ConnectableAPIViewer(QtWidgets.QDialog):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self._graph_view = _GraphViewer(parent=self)
        vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        vertical.addWidget(self._graph_view)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(vertical)
        self.setLayout(layout)

    def setPrim(self, prim):
        if not prim:
            return
        self._graph_view.graph = graph = _graph_from_connections(prim)
        self._graph_view.view(graph.nodes.keys())


# Reminder: Inheriting does not bring QTreeView stylesheet (Stylesheet needs to target this class specifically).
class _Tree(_core._ColumnHeaderMixin, QtWidgets.QTreeView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expanded.connect(self._expand_all_children)
        self.collapsed.connect(self._collapse_all_children)

    def _expand_all_children(self, index):
        if QtWidgets.QApplication.keyboardModifiers() == QtCore.Qt.ShiftModifier:
            with QtCore.QSignalBlocker(self):
                self.expandRecursively(index)

    def _collapse_all_children(self, index):
        model = index.model()

        def _collapse_recursively(_index):  # No "self.collapseRecursively", Qt? ):
            self.setExpanded(_index, False)
            for row in range(model.rowCount(_index)):
                if child := model.index(row, 0, _index):
                    _collapse_recursively(child)

        if QtWidgets.QApplication.keyboardModifiers() == QtCore.Qt.ShiftModifier:
            with QtCore.QSignalBlocker(self):
                _collapse_recursively(index)

    def _connect_search(self, options, index, model):
        super()._connect_search(options, index, model)
        model.setRecursiveFilteringEnabled(True)
        options.filterChanged.connect(self.expandAll)


class PrimComposition(QtWidgets.QDialog):
    # TODO: See if columns need to be updated from dict to tuple[_core.Column]
    _COLUMNS = {
        "Target Layer": lambda arc: _layer_label(arc.GetTargetNode().layerStack.layerTree.layer),
        "Arc": lambda arc: arc.GetArcType().displayName,
        "#": lambda arc: arc.GetTargetNode().siblingNumAtOrigin,
        "Target Path": lambda arc: arc.GetTargetNode().path,
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
        self.index_box.setLineWrapMode(QtWidgets.QTextBrowser.NoWrap)
        self._composition_model = model = QtGui.QStandardItemModel()
        columns = tuple(_core._Column(k, v) for k, v in self._COLUMNS.items())
        options = _core._ColumnOptions.SEARCH
        self.composition_tree = tree = _Tree(model, columns, options)
        tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._exec_context_menu)
        tree.setAlternatingRowColors(True)
        tree.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self._dot_view = _DotViewer(parent=self)

        tree_controls = QtWidgets.QFrame()
        tree_controls_layout = QtWidgets.QHBoxLayout()
        tree_controls.setLayout(tree_controls_layout)
        self._prim = None  # TODO: see if we can remove this. Atm needed for "enabling layer stack" checkbox
        self._complete_target_layerstack = QtWidgets.QCheckBox("Complete Target LayerStack")
        self._complete_target_layerstack.setChecked(False)
        self._complete_target_layerstack.clicked.connect(lambda: self.setPrim(self._prim))
        tree_controls_layout.addWidget(self._complete_target_layerstack)
        tree_controls_layout.addStretch(0)
        tree_controls_layout.setContentsMargins(0,0,0,0)
        tree_controls.setContentsMargins(0,0,0,0)
        tree_controls.setFixedHeight(tree_controls.sizeHint().height())

        vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        vertical.addWidget(tree_controls)
        vertical.addWidget(tree)
        vertical.addWidget(self._dot_view)
        vertical.setStretchFactor(2, 1)
        horizontal = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        horizontal.addWidget(vertical)
        horizontal.addWidget(self.index_box)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(horizontal)
        self.setLayout(layout)
        self.setWindowTitle("Prim Composition")

    def clear(self):
        self._composition_model.clear()
        self.index_box.clear()

    def _exec_context_menu(self):
        # https://doc.qt.io/qtforpython-5/overviews/statemachine-api.html#the-state-machine-framework
        menu = QtWidgets.QMenu(tree:=self.composition_tree)
        selection = tree.selectedIndexes()
        if len(set(i.row() for i in selection) ) == 1:
            stage, edit_target, target_path = selection[0].data(QtCore.Qt.UserRole)
            menu.addAction("Set As Edit Target", partial(stage.SetEditTarget, edit_target))
            menu.addAction(_BROWSE_CONTENTS_MENU_TITLE, partial(_launch_content_browser, (edit_target.GetLayer(),), self, stage.GetPathResolverContext(), [target_path]))
        menu.exec_(QtGui.QCursor.pos())

    def setPrim(self, prim):
        self._prim = prim
        if not self._prim:
            self.clear()
            self.setWindowTitle("Prim Composition")
            return
        self.setWindowTitle(f"Prim Composition: {prim.GetName()} ({prim.GetPath()})")
        prim_index = prim.GetPrimIndex()
        self.index_box.setText(prim_index.DumpToString())
        fd, fp = tempfile.mkstemp()
        prim_index.DumpToDotGraph(fp)
        self._dot_view.setDotPath(fp)

        complete_target_layerstack = self._complete_target_layerstack.isChecked()
        # model.clear() resizes the columns. So we keep track of current sizes.
        header = self.composition_tree.header()
        sizes = {index: size for index in header.options_by_index if (size:=header.sectionSize(index))}

        tree = self.composition_tree
        model = self._composition_model
        model.clear()
        model.setHorizontalHeaderLabels([""] * len(self._COLUMNS))
        root_item = model.invisibleRootItem()

        query = Usd.PrimCompositionQuery(prim)
        items = dict()
        stage = prim.GetStage()
        arcs = query.GetCompositionArcs()
        for arc in arcs:
            values = [getter(arc) for getter in self._COLUMNS.values()]

            intro_node = arc.GetIntroducingNode()
            target_node = arc.GetTargetNode()
            target_path = target_node.path
            target_layer = target_node.layerStack.identifier.rootLayer

            # TODO: is there a better way than relying on str(node.site)???
            key = str(intro_node.site)
            parent = items[key] if key in items else root_item

            try:
                highlight_color = _HIGHLIGHT_COLORS[arc.GetArcType().displayName][_PALETTE.get()]
            except KeyError:
                highlight_color = None

            sublayers = target_node.layerStack.layers if complete_target_layerstack else (target_layer,)
            for each in sublayers:
                if each == target_layer:  # we're the root layer of the target node's stack
                    arc_items = [QtGui.QStandardItem(str(s)) for s in values]
                    items[str(target_node.site)] = arc_items[0]
                else:
                    has_specs = bool(each.GetObjectAtPath(target_path))
                    arc_items = [QtGui.QStandardItem(str(s)) for s in [_layer_label(each), values[1], values[2], values[3], str(has_specs)]]

                edit_target = Usd.EditTarget(each, target_node)
                for item in arc_items:
                    item.setData((stage, edit_target, target_path), QtCore.Qt.UserRole)
                    if highlight_color:
                        item.setData(highlight_color, QtCore.Qt.ForegroundRole)

                parent.appendRow(arc_items)

        tree.expandAll()
        tree._fixPositions()  # TODO: Houdini needs this. Why?
        for index, size in sizes.items():
            header.resizeSection(index, size)


class LayerTableModel(_core._ObjectTableModel):
    def data(self, index:QtCore.QModelIndex, role:int=...) -> typing.Any:
        if role == QtCore.Qt.ForegroundRole:
            layer = self.data(index, role=_core._QT_OBJECT_DATA_ROLE)
            # TODO: add a concrete color value for "dirty" layers?
            color = _sheets._PrimTextColor.ARCS if layer.dirty else _sheets._PrimTextColor.NONE
            return color.value
        return super().data(index, role)

    def setLayers(self, value):
        self.beginResetModel()
        self._objects = list(value)
        self.endResetModel()


class _Highlighter(QtGui.QSyntaxHighlighter):
    _pattern = _HIGHLIGHT_PATTERN

    def highlightBlock(self, text):
        for match in re.finditer(self._pattern, text):
            for syntax_group, value in match.groupdict().items():
                if not value:
                    continue
                start, end = match.span(syntax_group)
                self.setFormat(start, end-start, _highlight_syntax_format(syntax_group, value))


class _SdfOutlineHighlighter(_Highlighter):
    _pattern = _OUTLINE_SDF_PATTERN


class _TreeOutlineHighlighter(_Highlighter):
    _pattern = _TREE_PATTERN


class _LayersSheet(_sheets._Spreadsheet):
    def __init__(self, *args, resolver_context=Ar.GetResolver().CreateDefaultContext(), **kwargs):
        super().__init__(*args, **kwargs)
        self._resolver_context = resolver_context

    def contextMenuEvent(self, event):
        if not _which("sdffilter"):
            print(
                "In order to display layer contents, the 'sdffilter' command must be \n"
                "available on the current environment.\n\n"
                "Please ensure 'sdffilter' is on the system's PATH environment variable."
            )
            return  # ATM only appear if sdffilter is in the environment
        self.menu = QtWidgets.QMenu(self)
        self.menu.addAction(_BROWSE_CONTENTS_MENU_TITLE, self._display_contents)
        self.menu.popup(QtGui.QCursor.pos())

    def _display_contents(self, *_, **__):
        selected = self.table.selectedIndexes()
        layers = {index.data(_core._QT_OBJECT_DATA_ROLE) for index in selected}
        _launch_content_browser(layers, self, self._resolver_context)


class _PseudoUSDBrowser(QtWidgets.QTabWidget):
    def __init__(self, layer, *args, resolver_context=Ar.GetResolver().CreateDefaultContext(), paths=tuple(), **kwargs):
        super().__init__(*args, **kwargs)
        self._resolver_context = resolver_context
        self._browsers_by_layer = dict()  # {Sdf.Layer: _PseudoUSDTabBrowser}
        self._tab_layer_by_idx = list()  # {tab_idx: Sdf.Layer}
        self._addLayerTab(layer, paths)
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(lambda idx: self.removeTab(idx))

    def tabRemoved(self, index: int) -> None:
        del self._browsers_by_layer[self._tab_layer_by_idx.pop(index)]

    @_core.wait()
    def _addLayerTab(self, layer, paths=tuple()):
        layer_ref = weakref.ref(layer)
        try:
            focus_widget = self._browsers_by_layer[layer_ref]
        except KeyError:
            paths_in_layer = []
            for path in paths:
                if not layer.GetObjectAtPath(path):
                    print(f"{path=} does not exist on {layer=}")
                    continue
                if path.IsPropertyPath():
                    path = path.GetParentPath()
                paths_in_layer.append(path)
            error, text = _format_layer_contents(layer, paths=paths_in_layer)
            if error:
                QtWidgets.QMessageBox.warning(self, "Error Opening Contents", error)
                return

            outliner_columns = (_core._Column("Path", lambda path: path.name),)
            outline_model = QtGui.QStandardItemModel()
            outline_tree = _Tree(outline_model, outliner_columns, _core._ColumnOptions.SEARCH)
            outline_tree.setSelectionMode(outline_tree.SelectionMode.ExtendedSelection)
            outline_model.setHorizontalHeaderLabels([""] * len(outliner_columns))
            root_item = outline_model.invisibleRootItem()

            items = dict()  # {Sdf.Path: QtGui.QItem}

            def populate(spec_paths, *_, **__):
                for path in spec_paths:
                    if path.IsPropertyPath() or path.IsTargetPath():
                        continue
                    parent_key = path.GetParentPath()
                    variant_set, selection = path.GetVariantSelection()
                    if path.IsPrimVariantSelectionPath() and selection:  # place all variant selections under the variant set
                        parent_key = parent_key.AppendVariantSelection(variant_set, "")
                    highlight_color = _HIGHLIGHT_COLORS["variantSets"][_PALETTE.get()] if variant_set else None
                    parent = items[parent_key] if parent_key in items else root_item
                    new_items = [QtGui.QStandardItem(str(column.getter(path))) for column in outliner_columns]
                    if highlight_color:
                        for item in new_items:
                            item.setData(highlight_color, QtCore.Qt.ForegroundRole)
                    parent.appendRow(new_items)
                    new_items[0].setData(path, QtCore.Qt.UserRole)
                    items[path] = new_items[0]

            content_paths = list()
            layer.Traverse(layer.pseudoRoot.path, lambda path: content_paths.append(path))
            selection_model = outline_tree.selectionModel()
            highligther_cls = _Highlighter
            highlighters = {"pseudoLayer": _Highlighter, "outline": _SdfOutlineHighlighter, "usdtree": _TreeOutlineHighlighter}
            def _ensure_highligther(cls):
                nonlocal highligther_cls
                if highligther_cls != cls:
                    browser.setText("")  # clear contents before changing highlighting to avoid locks with huge contents
                    highligther_cls = cls
                    highligther_cls(browser)
                sorting_combo.setEnabled(cls == _SdfOutlineHighlighter)
                outline_valies_check.setEnabled(cls == _SdfOutlineHighlighter)

            def update_contents(*_, **__):
                format_choice = format_combo.currentText()
                output_args = []
                if format_choice == "pseudoLayer":
                    output_args += ["--arraySizeLimit", "6", "--timeSamplesSizeLimit", "6"]
                elif format_choice == "outline":
                    output_args += ["--sortBy", sorting_combo.currentText()]
                    if not outline_valies_check.isChecked():
                        output_args.append("--noValues")
                selected_indices = selection_model.selectedIndexes()
                paths = list()
                for each in selected_indices:
                    path = each.data(QtCore.Qt.UserRole)
                    variant_set, selection = path.GetVariantSelection()
                    if path.IsPrimVariantSelectionPath() and not selection:  # we're the "parent" variant. collect all variant paths as sdffilter does not math unselected variants ):
                        paths.extend([v.path for v in layer.GetObjectAtPath(path).variants.values()])
                    else:
                        paths.append(path)

                with QtCore.QSignalBlocker(browser):
                    _ensure_highligther(highlighters.get(format_choice, _Highlighter))
                    error, text = _format_layer_contents(layer, format_combo.currentText(), paths, output_args)
                    browser.setText(error if error else text)

            populate(sorted(content_paths))  # Sdf.Layer.Traverse collects paths from deepest -> highest. Sort from high -> deep

            if paths_in_layer:
                tree_model = outline_tree.model()
                with QtCore.QSignalBlocker(outline_tree):
                    for path in paths_in_layer:
                        proxy_index = tree_model.mapFromSource(outline_model.indexFromItem(items[path]))
                        selection_model.select(proxy_index, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
                        outline_tree.setCurrentIndex(proxy_index)  # possible to set multiple?
            else:
                outline_tree.expandRecursively(root_item.index(), 3)

            focus_widget = QtWidgets.QFrame(parent=self)
            focus_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            focus_splitter.addWidget(outline_tree)
            focus_layout = QtWidgets.QHBoxLayout()
            focus_layout.setContentsMargins(0, 0, 0, 0)

            options_layout = QtWidgets.QHBoxLayout()
            format_layout = QtWidgets.QFormLayout()
            format_combo = QtWidgets.QComboBox()
            format_combo.addItems(["pseudoLayer", "outline", "usdtree"])
            focus_widget._format_options = format_combo
            format_layout.addRow("Format", format_combo)
            options_layout.addLayout(format_layout)

            outline_sorting_layout = QtWidgets.QFormLayout()
            sorting_combo = QtWidgets.QComboBox()
            sorting_combo.addItems(["path", "field"])
            outline_sorting_layout.addRow("Sort By", sorting_combo)
            options_layout.addLayout(outline_sorting_layout)
            outline_valies_check = QtWidgets.QCheckBox("Values")
            outline_valies_check.setChecked(True)
            options_layout.addWidget(outline_valies_check)
            options_layout.addStretch()

            format_combo.setCurrentIndex(0)
            sorting_combo.setEnabled(False)
            outline_valies_check.setEnabled(False)

            browser_frame = QtWidgets.QFrame(parent=self)
            browser_layout = QtWidgets.QVBoxLayout()
            browser_layout.setContentsMargins(0, 0, 0, 0)
            browser_layout.addLayout(options_layout)

            self._line_filter = browser_line_filter = QtWidgets.QLineEdit()
            browser_line_filter.setPlaceholderText("Find")

            filter_layout = QtWidgets.QFormLayout()
            filter_layout.addRow(_core._EMOJI.SEARCH.value, browser_line_filter)
            browser_layout.addLayout(filter_layout)

            browser_frame.setLayout(browser_layout)
            for trigger in (
                    outline_valies_check.toggled,
                    selection_model.selectionChanged,
                    format_combo.currentIndexChanged,
                    sorting_combo.currentIndexChanged,
            ):
                trigger.connect(update_contents)

            focus_layout.addWidget(focus_splitter)
            focus_splitter.addWidget(browser_frame)
            focus_splitter.setStretchFactor(1, 2)
            focus_widget.setLayout(focus_layout)

            browser = _PseudoUSDTabBrowser(parent=self)
            browser.setLineWrapMode(QtWidgets.QTextBrowser.NoWrap)
            _Highlighter(browser)
            browser.identifier_requested.connect(partial(self._on_identifier_requested, weakref.proxy(layer)))
            browser.setText(text)

            def _find(text):
                if text and not browser.find(text):
                    browser.moveCursor(QtGui.QTextCursor.Start)  # try again from start
                    browser.find(text)

            browser_line_filter.textChanged.connect(_find)
            browser_line_filter.returnPressed.connect(lambda: _find(browser_line_filter.text()))

            browser_layout.addWidget(browser)

            tab_idx = self.addTab(focus_widget, _layer_label(layer))
            self._tab_layer_by_idx.append(layer_ref)
            assert len(self._tab_layer_by_idx) == (tab_idx+1)
            self._browsers_by_layer[layer_ref] = focus_widget
        self.setCurrentWidget(focus_widget)

    def _on_identifier_requested(self, anchor: Sdf.Layer, identifier: str):
        anchor = anchor.__repr__.__self__
        with Ar.ResolverContextBinder(self._resolver_context):
            try:
                if not (layer := Sdf.Layer.FindOrOpen(identifier)):
                    layer = Sdf.Layer.FindOrOpenRelativeToLayer(anchor, identifier)
            except Tf.ErrorException as exc:
                title = "Error Opening File"
                text = str(exc.args[0])
            else:
                if layer:
                    self._addLayerTab(layer)
                    return
                title = "Layer Not Found"
                text = f"Could not find layer with {identifier=} under resolver context {self._resolver_context} with {anchor=}"
            QtWidgets.QMessageBox.warning(self, title, text)


class _PseudoUSDTabBrowser(QtWidgets.QTextBrowser):
    # See: https://doc.qt.io/qt-5/qtextbrowser.html#navigation
    # The anchorClicked() signal is emitted when the user clicks an anchor.
    # we should be able to use anchor functionality but that does not seem to work with syntax highlighting ):
    # https://stackoverflow.com/questions/35858340/clickable-hyperlink-in-qtextedit/61722734#61722734
    # https://www.qtcentre.org/threads/26332-QPlainTextEdit-and-anchors
    # https://stackoverflow.com/questions/66931106/make-all-matches-links-by-pattern
    # https://fossies.org/dox/CuteMarkEd-0.11.3/markdownhighlighter_8cpp_source.html
    identifier_requested = QtCore.Signal(str)

    def mousePressEvent(self, event):
        cursor = self.cursorForPosition(event.pos())
        cursor.select(QtGui.QTextCursor.WordUnderCursor)
        word = cursor.selectedText()
        cursor.movePosition(QtGui.QTextCursor.StartOfLine, QtGui.QTextCursor.KeepAnchor)
        # Take advantage that identifiers in pseudo sdffilter come always in separate lines
        if f"{cursor.selectedText()}{word}".count('@') == 1 and (
                match := re.search(
                    rf"@(?P<identifier>[^@]*({re.escape(word.strip('@'))})[^@]*)@",
                    cursor.block().text()
                )
        ):
            self._target = match.group("identifier")
            QtWidgets.QApplication.setOverrideCursor(QtGui.Qt.PointingHandCursor)
        else:
            self._target = None
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._target:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.identifier_requested.emit(self._target)
            self._target = None
        else:
            super().mouseReleaseEvent(event)


class LayerStackComposition(QtWidgets.QDialog):
    # TODO: display total amount of layer stacks, and sites
    #       TOO SLOW!! (ALab workbench environment takes 7 seconds for the complete stage.)
    _LAYERS_COLUMNS = (
        _core._Column(f"{_core._EMOJI.ID.value} Layer Identifier", operator.attrgetter('identifier')),
        _core._Column("🚧 Dirty", operator.attrgetter('dirty')),
    )
    _PRIM_COLUMNS = (
        _core._Column("🧩 Opinion on Prim Path", lambda prim: str(prim.GetPath())),
        _core._Column(f"{_core._EMOJI.NAME.value} Prim Name", Usd.Prim.GetName),
    )

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent=parent, **kwargs)
        options = _core._ColumnOptions.SEARCH
        layers_model = LayerTableModel(columns=self._LAYERS_COLUMNS)
        self._layers = _LayersSheet(layers_model, self._LAYERS_COLUMNS, options)
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
        _graph_controls_layout = QtWidgets.QVBoxLayout()
        _graph_arcs_layout = QtWidgets.QHBoxLayout()

        _graph_controls_layout.addLayout(_graph_arcs_layout)
        _graph_legend_controls.setLayout(_graph_controls_layout)
        self._graph_edge_include = _graph_edge_include = {}
        self._graph_precise_source_ports = QtWidgets.QCheckBox("Precise Source Layer")
        self._graph_precise_source_ports.setChecked(False)
        self._graph_precise_source_ports.clicked.connect(lambda: self._update_graph_from_graph_info(self._computed_graph_info))
        for arc, arc_details in _ARCS_LEGEND.items():
            arc_btn = QtWidgets.QCheckBox(arc.displayName.title())
            arc_btn.setStyleSheet(f"background-color: {arc_details['color']}; padding: 3px; border-width: 1px; border-radius: 3;")
            arc_btn.setChecked(True)
            _graph_arcs_layout.addWidget(arc_btn)
            _graph_edge_include[arc] = arc_btn
            arc_btn.clicked.connect(lambda: self._update_graph_from_graph_info(self._computed_graph_info))
        _graph_arcs_layout.addWidget(self._graph_precise_source_ports)

        filters_layout = QtWidgets.QHBoxLayout()
        _graph_controls_layout.addLayout(filters_layout)
        # Arcs filters
        def _arc_filter(title, state=QtCore.Qt.CheckState.PartiallyChecked):
            widget = QtWidgets.QCheckBox(title)
            widget.setTristate(True)
            widget.setCheckState(state)
            widget.stateChanged.connect(self._edge_filter_changed)
            # widget.toggled
            filters_layout.addWidget(widget)
            return widget

        _graph_arcs_layout.addStretch(0)
        self._has_specs = _arc_filter("Has Specs", QtCore.Qt.CheckState.Checked)
        self._is_ancestral = _arc_filter("Is Ancestral")
        self._is_implicit = _arc_filter("Is Implicit")
        self._from_root_prim_spec = _arc_filter("From Root Layer Prim Spec")
        self._from_root_layer_stack = _arc_filter("From Root Layer Stack")
        filters_layout.addStretch(0)
        ##############


        # _graph_controls_layout.addStretch(0)
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
        self.setWindowTitle("Layer Stack Composition")

    def _edge_filter_changed(self, *args, **kwargs):
        state = lambda widget: None if widget.checkState() == QtCore.Qt.CheckState.PartiallyChecked else widget.isChecked()
        edge_data_filter = _nx_graph_edge_filter(
            has_specs=state(self._has_specs),
            ancestral=state(self._is_ancestral),
            implicit=state(self._is_implicit),
            introduced_in_root_layer_prim_spec=state(self._from_root_prim_spec),
            introduced_in_root_layer_stack=state(self._from_root_layer_stack),
        )
        graph = self._graph_view.graph
        # self._graph_view.filter_edges = (lambda *edge: edge_data_filter(graph.edges[edge])) if edge_data_filter else None
        from pprint import pp
        def actual(*edge):
            # edge_info = graph.edges[edge]
            # pp(edge_info)
            # print(f"{edge_data_filter=}")
            result = edge_data_filter(graph.edges[edge])
            # print(f"{result=}")
            return result

        self._graph_view.filter_edges = actual if edge_data_filter else None
        # self._graph_view._subgraph_dot_path.cache_clear()
        self._graph_view.view(self._graph_view._viewing)

    def _selectionChanged(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection):
        node_ids = {index.data(_core._QT_OBJECT_DATA_ROLE) for index in self._layers.table.selectedIndexes()}
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
        self._layers._resolver_context = stage.GetPathResolverContext()
        predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
        prims = Usd.PrimRange.Stage(stage, predicate)
        # prims = (prim for prim in prims if prim.IsActive())
        if self._prim_paths_to_compute:
            prims = (p for p in prims if p.GetPath() in self._prim_paths_to_compute)

        graph_info = _compute_layerstack_graph(prims, self._graph_view.url_id_prefix)
        self._prims.setStage(stage)
        # self._edge_filter_changed()
        self._update_graph_from_graph_info(graph_info)

    def setPrimPaths(self, value):
        self._prim_paths_to_compute = {p if isinstance(p, Sdf.Path) else Sdf.Path(p) for p in value}

    def _update_graph_from_graph_info(self, graph_info: _GraphInfo):
        print("~~~~~~~~~~~~~~~~~~~~~~")
        self._computed_graph_info = graph_info
        # https://stackoverflow.com/questions/33262913/networkx-move-edges-in-nx-multidigraph-plot
        graph = nx.MultiDiGraph()
        graph.graph['graph'] = dict(tooltip="LayerStack Composition")
        graph.add_nodes_from(self._computed_graph_info.nodes.items())
        graph.add_edges_from(self._iedges(graph_info))
        self._graph_view.graph = graph
        self._graph_view.sticky_nodes.extend(graph_info.sticky_nodes)
        self._layers.model.setLayers(graph_info.ids_by_layers)
        # view intersection as we might be seeing nodes that no longer exist
        # self._graph_view.view(self._graph_view._viewing)  # TODO: check if this is better <- and reset _viewing somewhere else
        ## NEW
        self._graph_view._viewing = self._graph_view._viewing.intersection(graph_info.nodes)
        self._edge_filter_changed()
        ## NEW END
        # self._graph_view.view(self._graph_view._viewing.intersection(graph_info.nodes))

    def _iedges(self, graph_info: _GraphInfo):
        checked_arcs = {arc for arc, control in self._graph_edge_include.items() if control.isChecked()}
        precise_ports = self._graph_precise_source_ports.isChecked()
        for (src, tgt), edge_info in graph_info.edges.items():
            arc_ports = edge_info if precise_ports else {None: collections.ChainMap(*edge_info.values())}
            for src_port, arcs in arc_ports.items():
                visible_arcs = {arc: attrs for arc, attrs in arcs.items() if (arc in checked_arcs or {src, tgt}.issubset(graph_info.sticky_nodes))}
                if visible_arcs:
                    # Composition arcs target layer stacks, so we don't specify port on our target nodes
                    ports = {"tailport": src_port} if precise_ports and src_port is not None else {}
                    color = _edge_color(tuple(visible_arcs))
                    yield src, tgt, collections.ChainMap(ports, color, *visible_arcs.values())


if _USE_WEB_ENGINE:
    _GraphViewer = _GraphSVGViewer
else:
    _GraphViewer = _graph.GraphView

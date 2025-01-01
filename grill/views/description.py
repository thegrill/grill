"""Views related to USD scene description"""
from __future__ import annotations

import re
import typing
import weakref
import logging
import operator
import tempfile
import contextvars
import collections

from pathlib import Path
from itertools import chain
from collections import defaultdict
from functools import cache, partial
from types import MappingProxyType

import networkx as nx
from pxr import UsdUtils, UsdShade, Usd, Ar, Pcp, Sdf, Tf
from ._qt import QtWidgets, QtGui, QtCore

from .. import usd as _usd
from . import sheets as _sheets, _core, _graph
from ._core import _which


_logger = logging.getLogger(__name__)

_color_attrs = lambda color: dict.fromkeys(("color", "fontcolor"), color)
_ARCS_LEGEND = MappingProxyType({
    Pcp.ArcTypeInherit: _color_attrs('mediumseagreen'),  # Pcp internal is 'green'
    Pcp.ArcTypeVariant: _color_attrs('orange'),
    Pcp.ArcTypeRelocate: _color_attrs('#b300b3'),  # Pcp internal is 'purple'
    Pcp.ArcTypeReference: _color_attrs('crimson'),  # Pcp internal is 'red'
    Pcp.ArcTypePayload: _color_attrs('#9370db'),  # Pcp internal is 'indigo'
    Pcp.ArcTypeSpecialize: _color_attrs('sienna'),
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
        *((key, ("#ff66ff", _ARCS_LEGEND[Pcp.ArcTypeRelocate]['color'])) for key in ("relocates", "relocate")),
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
    rf'(^(?P<comment>#.*$)|^( *(?P<specifier>def|over|class)( (?P<prim_type>\w+))? (?P<prim_name>\"\w+\")| +((?P<metadata>(?P<arc_selection>variants|payload|references|relocates)|{"|".join(_usd._metadata_keys())})|(?P<list_op>add|(ap|pre)pend|delete) (?P<arc>inherits|variantSets|references|payload|specializes|apiSchemas|rel (?P<rel_name>[\w:]+))|(?P<variantSet>variantSet) (?P<set_string>\"\w+\")|(?P<custom_meta>custom )?(?P<interpolation_meta>uniform )?(?P<prop_type>{"|".join(_usd._attr_value_type_names())}|dictionary|rel)(?P<prop_array>\[])? (?P<prop_name>[\w:.]+))( (\(|((?P<value_assignment>= )[\[(]?))|$))|(?P<string_value>\"[^\"]+\")|(?P<identifier>@[^@]+@)(?P<identifier_prim_path><[/\w]+>)?|(?P<relationship><[/\w:.]+>)|(?P<collapsed><< [^>]+ >>)|(?P<boolean>true|false)|(?P<number>-?[\d.]+))'
)

_OUTLINE_SDF_PATTERN = re.compile(  # this is a very minimal draft to have colors on the outline sdffilter mode.
    rf'^((?P<identifier_prim_path>(  )?</[/\w+.:{{}}=]*(\[[/\w+.:{{}}=]+])?>)( : (?P<specifier>\w+))?|(  )?(?P<metadata>\w+)(: ((?P<number>-?[\d.]+)|(?P<string_value>[\w:.]+)(?P<prop_array>\[])?|(?P<collapsed><< [^>]+ >>)|(\[ (?P<relationship>[\w /.:{{}}=]+) ])|(?P<outline_details>.+)))?)$'  # sad, last item is a dot, lazy atm
)

_TREE_PATTERN = re.compile(  # draft as well output of usdtree
    rf'^(?P<identifier_prim_path>([/`|\s:]+-+)(\w+)?)(\((?P<metadata>\w+)\)|(?P<prop_name>\.[\w:]+)|( \[(?P<specifier>def|over|class)( (?P<prim_type>\w+))?])( \((?P<custom_meta>[\w\s=]+)\))?)'
)

_PCP_DUMP_PATTERN = re.compile(
    r"^((?P<prim_name>Node \d+:)|\s+\w[ \w\#]+:(\s+((?P<boolean>TRUE|FALSE|NONE)|(?P<arc_selection>inherit|payload|reference|relocate|specialize|variant)|(?P<number>\d+)|(?P<string_value>\w[\w\-, ]+)))?)$|(?P<identifier_prim_path><[/\w{}=]+>)|(?P<identifier>@[^@]+@)|(?P<relationship>/[/\w]*)"
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


@cache
def _edge_color(edge_arcs):
    return dict(color=":".join(_ARCS_LEGEND[arc]["color"] for arc in edge_arcs))


def _format_layer_contents(layer, output_type="pseudoLayer", paths=tuple(), output_args=tuple()):
    """Textual representation of a layer using ``sdffilter``."""
    with tempfile.TemporaryDirectory() as target_dir:
        name = Path(layer.realPath).stem if layer.realPath else "".join(c if c.isalnum() else "_" for c in layer.identifier)
        path = Path(target_dir) / f"{name}.usd"
        try:
            layer.Export(str(path))
        except Tf.ErrorException:
            # Prefer crate export for performance, although it could fail to export non-standard layers.
            # When that fails, try export with original file format.
            # E.g. content that fails to export: https://github.com/PixarAnimationStudios/OpenUSD/blob/59992d2178afcebd89273759f2bddfe730e59aa8/pxr/usd/sdf/testenv/testSdfParsing.testenv/baseline/127_varyingRelationship.sdf#L9
            path = path.with_suffix(f".{layer.fileExtension}")
            layer.Export(str(path))
        path_args = ("-p", "|".join(re.escape(str(p)) for p in paths)) if paths else tuple()
        if output_type == "usdtree":
            args = [_which("usdtree"), "-a", "-m", str(path)]
        else:
            args = [_which("sdffilter"), "--outputType", output_type, *output_args, *path_args, str(path)]
        return _core._run(args)


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
        label = '{'
        tooltip = 'LayerStack:'
        for layer, layer_index in sublayers.items():
            indices_by_sublayers[layer].add(index)
            if layer.dirty:
                attrs['color'] = 'darkorange'  # can probably be dashed as well?
            # For new line: https://stackoverflow.com/questions/16671966/multiline-tooltip-for-pydot-graph
            # For Windows path sep: https://stackoverflow.com/questions/15094591/how-to-escape-forwardslash-character-in-html-but-have-it-passed-correctly-to-jav
            tooltip += f"&#10;{layer_index}: {(layer.realPath or layer.identifier)}".replace('\\', '&#47;')
            label += f"{'' if layer_index == 0 else '|'}<{layer_index}>{_layer_label(layer)}"
        label += '}'
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
                # implementation detail: convert source_port to a string since it's serialized as the label in graphviz
                all_edges[source_idx, target_idx][str(source_port)][arc.GetArcType()].update(
                    {func.__name__:  is_fun for func in _USD_COMPOSITION_ARC_QUERY_METHODS if (is_fun := func(arc))}
                )

        return affected_by

    all_nodes = dict()  # {int: dict}
    all_edges = defaultdict(                            #   { (source_node: int, target_node: int):
        lambda: defaultdict(                            #       { source_port: str:
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
    edges = list()  # [(source_node_id, target_node_id, {source_port_name, target_port_name, graphviz_attrs})]

    @cache
    def _get_node_id(api):
        return str(api.GetPrim().GetPath())

    @cache
    def _add_edges(src_node, src_name, tgt_node, tgt_name):
        tooltip = f"{src_node}.{src_name} -> {tgt_node}.{tgt_name}"
        edges.append((src_node, tgt_node, {"tailport": src_name, "headport": tgt_name, "tooltip": tooltip}))

    port_colors = {
        UsdShade.Input: outline_color,  # blue
        UsdShade.Output: "#F08080"  # "lightcoral",  # pink
    }
    table_row = '<tr><td port="{port}" border="0" bgcolor="{color}" style="ROUNDED">{text}</td></tr>'

    traversed_prims = set()
    def traverse(api: UsdShade.ConnectableAPI):
        current_prim = api.GetPrim()
        if current_prim in traversed_prims:
            return
        traversed_prims.add(current_prim)
        node_id = _get_node_id(current_prim)
        label = f'<<table border="1" cellspacing="2" style="ROUNDED" bgcolor="{background_color}" color="{outline_color}">'
        label += table_row.format(port="", color="white", text=f'<font color="{outline_color}"><b>{api.GetPrim().GetName()}</b></font>')
        ports = [""]  # port names for this node. Empty string is used to refer to the node itself (no port).
        for port in chain(api.GetInputs(), api.GetOutputs()):
            port_name = port.GetBaseName()
            sources, __ = port.GetConnectedSources()  # (valid, invalid): we care only about valid sources (index 0)
            color = port_colors[type(port)] if isinstance(port, UsdShade.Output) or sources else background_color
            label += table_row.format(port=port_name, color=color, text=f'<font color="#242828">{port_name}</font>')
            for source in sources:
                _add_edges(_get_node_id(source.source.GetPrim()), source.sourceName, node_id, port_name)
                traverse(source.source)
            ports.append(port_name)
        label += '</table>>'
        all_nodes[node_id] = dict(label=label, ports=ports)

    traverse(connections_api)

    graph.add_nodes_from(all_nodes.items())
    graph.add_edges_from(edges)
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
    if not match:
        return None
    return lambda edge_info: match.items() <= edge_info.items()


class _ConnectableAPIViewer(QtWidgets.QDialog):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent=parent, **kwargs)
        if nx.__version__.startswith("2"):
            # TODO: Remove this if-statement when Py-3.9 / networkx-2 support is dropped (starting Py-3.10)
            #   Use SVG when networkx-2 is in use, as there are fixes to pydot graph inspection which only exist in nx-3
            self._graph_view = _graph._GraphSVGViewer(parent=self)
        else:
            self._graph_view = _graph._GraphViewer(parent=self)
        vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        vertical.addWidget(self._graph_view)
        self.setFocusProxy(self._graph_view)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(vertical)
        self.setLayout(layout)

    def setPrim(self, prim):
        if not prim:
            return
        prim = prim.GetPrim()
        type_text = "" if not (type_name := prim.GetTypeName()) else f" {type_name}"
        self.setWindowTitle(f"Scene Graph Connections From{type_text}: {prim.GetName()} ({prim.GetPath()})")
        self._graph_view.graph = graph = _graph_from_connections(prim)
        if isinstance(self._graph_view, _graph._GraphSVGViewer):
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
        "Layer": lambda node: _layer_label(node.layerStack.layerTree.layer),
        "Arc": lambda node: node.arcType.displayName,
        "#": lambda node: node.siblingNumAtOrigin,
        "Path": lambda node: node.path,
        "Has Specs": lambda node: node.hasSpecs,
    }

    def __init__(self, *args, **kwargs):
        """For inspection and debug purposes, this widget makes primary use of:

            - Usd.PrimCompositionQuery  (similar to USDView's composition tab)
            - Pcp.PrimIndex.DumpToString
            - Pcp.PrimIndex.DumpToDotGraph  (when dot is available)
        """
        super().__init__(*args, **kwargs)
        self.index_box = QtWidgets.QTextBrowser()
        _PcpNodeDumpHighlighter(self.index_box)
        self.index_box.setLineWrapMode(QtWidgets.QTextBrowser.NoWrap)
        self._composition_model = model = QtGui.QStandardItemModel()
        columns = tuple(_core._Column(k, v) for k, v in self._COLUMNS.items())
        options = _core._ColumnOptions.SEARCH
        self.composition_tree = tree = _Tree(model, columns, options)
        tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._exec_context_menu)
        tree.setAlternatingRowColors(True)
        tree.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self._dot_view = _graph._DotViewer(parent=self)

        tree_controls = QtWidgets.QFrame()
        tree_controls_layout = QtWidgets.QHBoxLayout()
        tree_controls.setLayout(tree_controls_layout)
        self._prim = None  # TODO: see if we can remove this. Atm needed for "enabling layer stack" checkbox
        self._complete_target_layerstack = QtWidgets.QCheckBox("Complete LayerStack")
        self._complete_target_layerstack.setChecked(False)
        self._complete_target_layerstack.clicked.connect(lambda: self.setPrim(self._prim))

        self._compute_expanded_index = QtWidgets.QCheckBox("Expanded Prim Index")
        self._compute_expanded_index.setChecked(True)
        self._compute_expanded_index.clicked.connect(lambda: self.setPrim(self._prim))

        self._compute_expanded_index = QtWidgets.QCheckBox("Expanded Prim Index")
        self._compute_expanded_index.setChecked(True)
        self._compute_expanded_index.clicked.connect(lambda: self.setPrim(self._prim))

        # Inert nodes are discarded by UsdPrimCompositionQuery to avoid duplicates of some nodes
        # https://github.com/PixarAnimationStudios/OpenUSD/blob/9b0c13b2efa6233c8a4a4af411833628c5435bde/pxr/usd/usd/primCompositionQuery.cpp#L401
        # From the docs:
        #   An inert node never provides any opinions to a prim index.
        #   Such a node may exist purely as a marker to represent certain composition structure,
        #   but should never contribute opinions.
        self._include_inert_nodes = QtWidgets.QCheckBox("Include Inert Nodes")
        self._include_inert_nodes.setChecked(False)
        self._include_inert_nodes.clicked.connect(lambda: self.setPrim(self._prim))

        tree_controls_layout.addWidget(self._complete_target_layerstack)
        tree_controls_layout.addWidget(self._compute_expanded_index)
        tree_controls_layout.addWidget(self._include_inert_nodes)
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
        prim_index = prim.ComputeExpandedPrimIndex() if self._compute_expanded_index.isChecked() else prim.GetPrimIndex()

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

        stage = prim.GetStage()

        include_inert_nodes = self._include_inert_nodes.isChecked()

        def walk_composition(node):
            yield node
            for child in node.children:
                yield from walk_composition(child)

        root_node = prim_index.rootNode
        items = {str(root_node.site): root_item}

        def _find_parent_for_display(_node):
            if _parent := _node.parent:
                if not include_inert_nodes and _parent.isInert:
                    # if we're skipping inert nodes for display purposes, find the closes parent that is not inert
                    return _find_parent_for_display(_parent)
                return _parent

        for node_index, target_node in enumerate(walk_composition(root_node)):
            is_inert = target_node.isInert
            if is_inert and not include_inert_nodes:
                continue

            arc_type = target_node.arcType
            if parent_node := _find_parent_for_display(target_node):
                parent = items[str(parent_node.site)]
            else:
                parent = root_item

            target_id = str(target_node.site)
            values = [getter(target_node) for getter in self._COLUMNS.values()]

            target_path = target_node.path
            target_layer = target_node.layerStack.identifier.rootLayer

            try:
                highlight_color = _HIGHLIGHT_COLORS[arc_type.displayName][_PALETTE.get()]
            except KeyError:
                highlight_color = None

            sublayers = target_node.layerStack.layers if complete_target_layerstack else (target_layer,)

            for each in sublayers:
                if each == target_layer:  # we're the root layer of the target node's stack
                    arc_items = [QtGui.QStandardItem(f"{node_index} " + str(s)) for s in values]
                    items[target_id] = arc_items[0]
                else:
                    has_specs = bool(each.GetObjectAtPath(target_path))
                    arc_items = [QtGui.QStandardItem(f"{node_index} " + str(s)) for s in [_layer_label(each), values[1], values[2], values[3], str(has_specs)]]

                edit_target = Usd.EditTarget(each, target_node)
                for item in arc_items:
                    item.setData((stage, edit_target, target_path), QtCore.Qt.UserRole)
                    if highlight_color:
                        item.setData(highlight_color, QtCore.Qt.ForegroundRole)

                parent.appendRow(arc_items)

        prim_index.PrintStatistics()
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


class _PcpNodeDumpHighlighter(_Highlighter):
    _pattern = _PCP_DUMP_PATTERN


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
        self._tab_layer_by_idx = list()  # [tab_idx: Sdf.Layer]
        self._addLayerTab(layer, paths)
        self._resolved_layers = {layer}
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(lambda idx: self.removeTab(idx))

    def tabRemoved(self, index: int) -> None:
        item = self._tab_layer_by_idx[index]
        if isinstance(item, (Sdf.Layer, weakref.ref)):
            item = item.__repr__.__self__
            self._resolved_layers.discard(item)
        del self._browsers_by_layer[self._tab_layer_by_idx.pop(index)]

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton and (tab_index := self.tabBar().tabAt(event.pos())) != -1:
            self._menu_for_tab(tab_index).exec_(event.globalPos())

        super().mousePressEvent(event)

    def _menu_for_tab(self, tab_index):
        widget = self.widget(tab_index)
        clipboard = QtWidgets.QApplication.instance().clipboard()
        menu = QtWidgets.QMenu(self)
        menu.addAction("Copy Identifier", partial(clipboard.setText, widget._identifier))
        menu.addAction("Copy Resolved Path", partial(clipboard.setText, widget._resolved_path))
        menu.addSeparator()
        if tab_index < (max_tab_idx := len(self._tab_layer_by_idx)) - 1:
            menu.addAction("Close Tabs to the Right", partial(self._close_many, range(tab_index + 1, max_tab_idx + 1)))
        if tab_index > 0:
            menu.addAction("Close Tabs to the Left", partial(self._close_many, range(tab_index)))
        return menu

    def _close_many(self, indices: range):
        for index in reversed(indices):
            self.tabCloseRequested.emit(index)

    @_core.wait()
    def _addImageTab(self, path, *, identifier):
        try:
            focus_widget = self._browsers_by_layer[path]
        except KeyError:
            pixmap = QtGui.QPixmap(path)
            if pixmap.isNull():
                QtWidgets.QMessageBox.warning(self, "Error Opening Contents", f"Could not load {path}")
                return
            image_label = QtWidgets.QLabel(parent=self)
            image_label.setAlignment(QtCore.Qt.AlignCenter)
            image_label.resize(pixmap.size())
            image_label.setPixmap(pixmap)

            focus_widget = QtWidgets.QFrame(parent=self)
            focus_layout = QtWidgets.QHBoxLayout()
            focus_layout.setContentsMargins(0, 0, 0, 0)

            image_item = QtWidgets.QGraphicsPixmapItem(pixmap)
            viewport = _graph._GraphicsViewport(parent=self)
            scene = QtWidgets.QGraphicsScene()
            scene.addItem(image_item)
            viewport.setScene(scene)

            focus_layout.addWidget(viewport)
            focus_widget.setLayout(focus_layout)

            tab_idx = self.addTab(focus_widget, Path(path).name)

            focus_widget._resolved_path = path
            focus_widget._identifier = identifier
            self.setTabToolTip(tab_idx, path)

            self._tab_layer_by_idx.append(path)
            assert len(self._tab_layer_by_idx) == (tab_idx + 1)
            self._browsers_by_layer[path] = focus_widget

        self.setCurrentWidget(focus_widget)

    @_core.wait()
    def _addLayerTab(self, layer, paths=tuple(), *, identifier=None):
        layer_ref = weakref.ref(layer)
        try:
            focus_widget = self._browsers_by_layer[layer_ref]
        except KeyError:
            paths_in_layer = []
            for path in paths:
                if not layer.GetObjectAtPath(path):
                    _logger.debug(f"{path=} does not exist on {layer=}")
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
            outline_tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

            def show_outline_tree_context_menu(*args):
                if selected_indexes:= outline_tree.selectedIndexes():
                    content = "\n".join(str(index.data(QtCore.Qt.UserRole)) for index in selected_indexes if index.isValid())
                    menu = QtWidgets.QMenu(outline_tree)
                    menu.addAction("Copy Paths", partial(QtWidgets.QApplication.instance().clipboard().setText, content))
                    menu.exec_(QtGui.QCursor.pos())

            outline_tree.customContextMenuRequested.connect(show_outline_tree_context_menu)

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
                layer_ = layer_ref()
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
                        paths.extend([v.path for v in layer_.GetObjectAtPath(path).variants.values()])
                    else:
                        paths.append(path)

                with QtCore.QSignalBlocker(browser):
                    _ensure_highligther(highlighters.get(format_choice, _Highlighter))
                    error, text = _format_layer_contents(layer_, format_combo.currentText(), paths, output_args)
                    line_count = len(text.split("\n"))
                    line_counter.setText("\n".join(chain(map(str, range(1, line_count)), ["\n"] * 5)))
                    line_counter.setFixedWidth(12 + (len(str(line_count)) * 8))
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

            line_counter = QtWidgets.QTextBrowser()
            line_counter.setLineWrapMode(QtWidgets.QTextBrowser.NoWrap)
            line_counter.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            line_counter.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

            line_counter_doc = line_counter.document()
            line_text_option = line_counter_doc.defaultTextOption()
            line_text_option.setAlignment(QtCore.Qt.AlignRight)
            line_counter_doc.setDefaultTextOption(line_text_option)

            line_count = len(text.split("\n"))
            line_counter.setFixedWidth(12 + (len(str(line_count)) * 8))
            line_counter.setText("\n".join(chain(map(str, range(1, line_count)), ["\n"]*5)))
            line_counter.setEnabled(False)

            line_scrollbar = line_counter.verticalScrollBar()
            browser.verticalScrollBar().valueChanged.connect(line_scrollbar.setValue)
            browser._line_counter = line_counter

            browser_combined_layout = QtWidgets.QHBoxLayout()
            browser_combined_layout.addWidget(line_counter)
            browser_combined_layout.setSpacing(0)
            browser_combined_layout.setContentsMargins(0,0,0,0)
            browser_combined_layout.addWidget(browser)

            browser_layout.addLayout(browser_combined_layout)

            tab_idx = self.addTab(focus_widget, _layer_label(layer))
            focus_widget._resolved_path = str(layer.resolvedPath)
            focus_widget._identifier = identifier or layer.identifier
            self.setTabToolTip(tab_idx, str(layer.resolvedPath))

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
                resolved_path = str(Ar.GetResolver().Resolve(identifier)) or anchor.ComputeAbsolutePath(identifier)
                if resolved_path and Path(resolved_path).suffix[1:] in _image_formats_to_browse():
                    self._addImageTab(resolved_path, identifier=identifier)
                    return
                title = "Error Opening File"
                text = str(exc.args[0])
            else:
                if layer:
                    self._addLayerTab(layer, identifier=identifier)
                    self._resolved_layers.add(layer)
                    return
                title = "Layer Not Found"
                text = f"Could not find layer with {identifier=} under resolver context {self._resolver_context} with {anchor=}"
            QtWidgets.QMessageBox.warning(self, title, text)

@cache
def _image_formats_to_browse():
    return frozenset(str(fmt, 'utf-8') for fmt in QtGui.QImageReader.supportedImageFormats())

class _PseudoUSDTabBrowser(QtWidgets.QTextBrowser):
    # See: https://doc.qt.io/qt-5/qtextbrowser.html#navigation
    # The anchorClicked() signal is emitted when the user clicks an anchor.
    # we should be able to use anchor functionality but that does not seem to work with syntax highlighting ):
    # https://stackoverflow.com/questions/35858340/clickable-hyperlink-in-qtextedit/61722734#61722734
    # https://www.qtcentre.org/threads/26332-QPlainTextEdit-and-anchors
    # https://stackoverflow.com/questions/66931106/make-all-matches-links-by-pattern
    # https://fossies.org/dox/CuteMarkEd-0.11.3/markdownhighlighter_8cpp_source.html
    identifier_requested = QtCore.Signal(str)
    _line_counter = None

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

    def wheelEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier:
            method = operator.methodcaller("zoomIn" if event.angleDelta().y() > 0 else "zoomOut")
            method(self)
            if self._line_counter:
                method(self._line_counter)
        else:
            super().wheelEvent(event)


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

        self._graph_view = _graph._GraphViewer(parent=self)
        self.setFocusProxy(self._graph_view)
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
        # self._has_specs = _arc_filter("Has Specs", QtCore.Qt.CheckState.Checked)
        self._has_specs = _arc_filter("Has Specs")
        self._is_ancestral = _arc_filter("Is Ancestral")
        self._is_implicit = _arc_filter("Is Implicit")
        self._from_root_prim_spec = _arc_filter("From Root Layer Prim Spec")
        self._from_root_layer_stack = _arc_filter("From Root LayerStack")
        filters_layout.addStretch(0)
        ##############

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
        self.setWindowTitle("LayerStack Composition")

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
        if isinstance(self._graph_view, _graph._GraphSVGViewer):
            self._graph_view._subgraph_dot_path.cache_clear()
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
            self._prims._filter_predicate = lambda prim: prim.GetPath() in self._prim_paths_to_compute

        graph_info = _compute_layerstack_graph(prims, self._graph_view.url_id_prefix)
        self._prims.setStage(stage)
        # self._edge_filter_changed()
        self._update_graph_from_graph_info(graph_info)

    def setPrimPaths(self, value):
        self._prim_paths_to_compute = {p if isinstance(p, Sdf.Path) else Sdf.Path(p) for p in value}

    def _update_graph_from_graph_info(self, graph_info: _GraphInfo):
        self._computed_graph_info = graph_info
        # https://stackoverflow.com/questions/33262913/networkx-move-edges-in-nx-multidigraph-plot
        graph = nx.MultiDiGraph()
        graph.graph['graph'] = dict(tooltip="LayerStack Composition")
        graph.add_nodes_from(self._computed_graph_info.nodes.items())
        graph.add_edges_from(self._iedges(graph_info))
        self._graph_view._graph = graph
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


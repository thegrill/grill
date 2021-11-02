"""Views related to USD scene description"""
from __future__ import annotations

import re
import shutil
import typing
import operator
import tempfile
import subprocess
import contextvars
import collections

from pathlib import Path
from itertools import chain
from collections import defaultdict
from functools import lru_cache, partial
from types import MappingProxyType

import networkx as nx
from networkx.drawing import nx_pydot
from pxr import Ar, Sdf, Usd, UsdUtils, Pcp, Tf
# from PySide6 import QtWidgets, QtGui, QtCore, QtWebEngineWidgets
from ._qt import QtWidgets, QtGui, QtCore, QtWebEngineWidgets

import grill.usd as _usd
from . import sheets as _sheets, _core

_ARCS_LEGEND = MappingProxyType({
    Pcp.ArcTypeInherit: dict(color='mediumseagreen', fontcolor='mediumseagreen'),  # green
    Pcp.ArcTypeVariant: dict(color='orange', fontcolor='orange'),  # yellow
    Pcp.ArcTypeReference: dict(color='crimson', fontcolor='crimson'),  # red
    Pcp.ArcTypePayload: dict(color='darkslateblue', fontcolor='darkslateblue'),  # purple
    Pcp.ArcTypeSpecialize: dict(color='sienna', fontcolor='sienna'),  # brown
})
_BROWSE_CONTENTS_MENU_TITLE = 'Browse Contents'
_PALETTE = contextvars.ContextVar("_PALETTE", default=1)  # (0 == dark, 1 == light)
_HIGHLIGHT_COLORS = MappingProxyType(
    {name: (QtGui.QColor(dark), QtGui.QColor(light)) for name, (dark, light) in (
        ("comment", ("gray", "gray")),
        # A mix between:
        # https://en.wikipedia.org/wiki/Solarized#Colors
        # https://www.w3schools.com/colors/colors_palettes.asp
        *((key, ("#f7786b", "#d33682")) for key in ("specifier", "rel_op", "value_assignment", "references")),
        *((key, ("#f7cac9", "#f7786b")) for key in ("prim_name", "identifier_prim_path", "relationship", "apiSchemas")),
        *((key, ("#b5e7a0", "#859900")) for key in ("metadata", "interpolation_meta", "custom_meta")),
        *((key, ("#ffcc5c", "#b58900")) for key in ("identifier", "variantSets", "variantSet", "variants", "prop_name", "rel_name")),
        ("inherits", (_ARCS_LEGEND[Pcp.ArcTypeInherit]['color'], _ARCS_LEGEND[Pcp.ArcTypeInherit]['color'])),
        ("payload", ("#6c71c4", _ARCS_LEGEND[Pcp.ArcTypePayload]['color'])),
        ("specializes", ("#bd5734", _ARCS_LEGEND[Pcp.ArcTypeSpecialize]['color'])),
        ("list_op", ("#e3eaa7", "#2aa198")),
        *((key, ("#5b9aa0", "#5b9aa0")) for key in ("prim_type", "prop_type", "prop_array")),
        *((key, ("#87bdd8", "#034f84")) for key in ("set_string", "string_value")),
        ("collapsed", ("#92a8d1", "#36486b")),
        ("boolean", ("#b7d7e8", "#50394c")),
        ("number", ("#bccad6", "#667292")),
    )}
)
_HIGHLIGHT_PATTERN = re.compile(
    rf'(^(?P<comment>#.*$)|^( *(?P<specifier>def|over|class)( (?P<prim_type>\w+))? (?P<prim_name>\"\w+\")| +((?P<metadata>(?P<arc_selection>variants|payload)|{"|".join(_usd._metadata_keys())})|(?P<list_op>add|(ap|pre)pend|delete) (?P<arc>inherits|variantSets|references|payload|specializes|apiSchemas|rel (?P<rel_name>\w+))|(?P<variantSet>variantSet) (?P<set_string>\"\w+\")|(?P<custom_meta>custom )?(?P<interpolation_meta>uniform )?(?P<prop_type>{"|".join(_usd._attr_value_type_names())}|dictionary|rel)(?P<prop_array>\[])? (?P<prop_name>[\w:.]+))( (\(|((?P<value_assignment>= )[\[(]?))|$))|(?P<string_value>\"[^\"]+\")|(?P<identifier>@[^@]+@)(?P<identifier_prim_path><[/\w]+>)?|(?P<relationship><[/\w:.]+>)|(?P<collapsed><< [^>]+ >>)|(?P<boolean>true|false)|(?P<number>-?[\d.]+))'
)


@lru_cache(maxsize=None)
def _which(what):
    return shutil.which(what)


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


@lru_cache(maxsize=None)
def _edge_color(edge_arcs):
    return dict(  # need to wrap color in quotes to allow multicolor
        color=f'"{":".join(_ARCS_LEGEND[arc]["color"] for arc in edge_arcs)}"',
    )


@lru_cache(maxsize=None)
def _dot_2_svg(sourcepath):
    print(f"Creating svg for: {sourcepath}")
    targetpath = f"{sourcepath}.svg"
    args = [_which("dot"), sourcepath, "-Tsvg", "-o", targetpath]
    error, __ = _run(args)
    return error, targetpath


def _pseudo_layer(layer):
    # TODO: Houdini does not provide sdffilter ): so can't test it there atm
    with tempfile.TemporaryDirectory() as target_dir:
        name = Path(layer.realPath).stem if layer.realPath else "".join(c if c.isalnum() else "_" for c in layer.identifier)
        path = Path(target_dir) / f"{name}.usd"
        layer.Export(str(path))
        args = [_which("sdffilter"), "--outputType", "pseudoLayer", "--arraySizeLimit", "6", "--timeSamplesSizeLimit", "6", str(path)]
        return _run(args)


def _layer_label(layer):
    return Path(layer.realPath).stem or layer.identifier


@lru_cache(maxsize=None)
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

    @lru_cache(maxsize=None)
    def _cached_layer_label(layer):
        return _layer_label(layer)

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
        try:  # lru_cache not compatible with Pcp objects, so we "cache" at the layer level
            return ids_by_root_layer[root_layer], sublayers
        except KeyError:
            pass  # layerStack still not processed, let's add it
        ids_by_root_layer[root_layer] = index = len(all_nodes)

        attrs = dict(style='"rounded,filled"', shape='record', href=f"{url_prefix}{index}", fillcolor="white", color="darkslategray")
        label = f"{{<0>{_cached_layer_label(root_layer)}"
        tooltip = "Layer Stack:"
        for layer, layer_index in sublayers.items():
            indices_by_sublayers[layer].add(index)
            if layer.dirty:
                attrs['color'] = 'darkorange'  # can probably be dashed as well?
            # https://stackoverflow.com/questions/16671966/multiline-tooltip-for-pydot-graph
            tooltip += f"&#10;{layer_index}: {layer.realPath or layer.identifier}"
            if layer != root_layer:  # root layer has been added at the start.
                label += f"|<{layer_index}>{_cached_layer_label(layer)}"
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


def _launch_content_browser(layers, parent, context):
    dialog = QtWidgets.QDialog(parent=parent)
    dialog.setWindowTitle("Layer Content Browser")
    layout = QtWidgets.QVBoxLayout()
    vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
    for layer in layers:
        browser = _PseudoUSDBrowser(layer, parent=dialog, resolver_context=context)
        vertical.addWidget(browser)
    layout.addWidget(vertical)
    dialog.setLayout(layout)
    dialog.show()


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
        if not _which("dot"):
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
        self._error_view = QtWidgets.QTextBrowser(parent=self)
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
            # TODO: add a concrete color value for "dirty" layers?
            color = _sheets._PrimTextColor.ARCS if layer.dirty else _sheets._PrimTextColor.NONE
            return color.value
        return super().data(index, role)

    def setLayers(self, value):
        self.beginResetModel()
        self._objects = list(value)
        self.endResetModel()


class _Highlighter(QtGui.QSyntaxHighlighter):
    def highlightBlock(self, text):
        for match in re.finditer(_HIGHLIGHT_PATTERN, text):
            for syntax_group, value in match.groupdict().items():
                if not value:
                    continue
                start, end = match.span(syntax_group)
                self.setFormat(start, end-start, _highlight_syntax_format(syntax_group, value))


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
        self.menu.addAction(_BROWSE_CONTENTS_MENU_TITLE, lambda: self._display_contents(event))
        self.menu.popup(QtGui.QCursor.pos())

    def _display_contents(self, *args, **kwargs):
        selected = self.table.selectedIndexes()
        layers = {index.data(_core._QT_OBJECT_DATA_ROLE) for index in selected}
        _launch_content_browser(layers, self, self._resolver_context)


class _PseudoUSDBrowser(QtWidgets.QTabWidget):
    def __init__(self, layer, *args, resolver_context=Ar.GetResolver().CreateDefaultContext(), **kwargs):
        super(_PseudoUSDBrowser, self).__init__(*args, **kwargs)
        self._resolver_context = resolver_context
        self._browsers_by_layer = dict()
        self._addLayerTab(layer)

    @_core.wait()
    def _addLayerTab(self, layer):
        try:
            focus_widget = self._browsers_by_layer[layer]
        except KeyError:
            error, text = _pseudo_layer(layer)
            if error:
                QtWidgets.QMessageBox.warning(self, "Error Opening Contents", error)
                return
            browser_frame = QtWidgets.QFrame(parent=self)
            browser_layout = QtWidgets.QVBoxLayout()
            browser_layout.setContentsMargins(0, 0, 0, 0)

            self._line_filter = browser_line_filter = QtWidgets.QLineEdit()
            browser_line_filter.setPlaceholderText("Find")

            filter_layout = QtWidgets.QFormLayout()
            filter_layout.addRow(_core._EMOJI.SEARCH.value, browser_line_filter)
            browser_layout.addLayout(filter_layout)

            browser_frame.setLayout(browser_layout)
            browser = _PseudoUSDTabBrowser(parent=self)
            browser.setLineWrapMode(browser.NoWrap)
            _Highlighter(browser)
            browser.identifier_requested.connect(partial(self._on_identifier_requested, layer))
            browser.setText(text)

            def _find(text):
                if not text:  # nothing to search.
                    return
                if not browser.find(text):
                    browser.moveCursor(QtGui.QTextCursor.Start)  # try again from start
                    browser.find(text)

            browser_line_filter.textChanged.connect(_find)
            browser_line_filter.returnPressed.connect(lambda: _find(browser_line_filter.text()))

            browser_layout.addWidget(browser)

            self.addTab(browser_frame, _layer_label(layer))
            self._browsers_by_layer[layer] = browser_frame
            focus_widget = browser_frame
        self.setCurrentWidget(focus_widget)

    def _on_identifier_requested(self, anchor: Sdf.Layer, identifier: str):
        def _resolve():
            # Fallback mechanism not available in Maya-2022 atm.
            layer = Sdf.Layer.FindOrOpen(identifier)
            if not layer:
                relmethod = getattr(Sdf.Layer, "FindOrOpenRelativeToLayer", None)
                if relmethod:
                    layer = relmethod(anchor, identifier)
            return layer

        with Ar.ResolverContextBinder(self._resolver_context):
            print(f"Adding tab for {identifier} and {anchor}")
            try:
                layer = _resolve()
            except Tf.ErrorException as exc:
                title = "Error Opening File"
                text = str(exc.args[0])
            else:
                if layer:
                    self._addLayerTab(layer)
                    return
                title = "Layer Not Found"
                text = f"Could not find layer with {identifier} under resolver context {self._resolver_context}"
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
        cursor.select(cursor.WordUnderCursor)
        word = cursor.selectedText()
        cursor.movePosition(cursor.StartOfLine, cursor.KeepAnchor)
        text_before = f"{cursor.selectedText()}{word}"
        # Take advantage that identifiers in pseudo sdffilter come always in separate lines
        pattern = rf"@(?P<identifier>[^@]*({re.escape(word.strip('@'))})[^@]*)@"
        match = re.search(pattern, cursor.block().text())
        if match and text_before.count('@') == 1:  # TODO: Flip order in PY-3.8+
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
        # WARNING: Maya returns None for stage.GetPathResolverContext() . WHY ): is it AR2.0?
        self._layers._resolver_context = stage.GetPathResolverContext()
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

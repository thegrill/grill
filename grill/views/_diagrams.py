"""
TODO:
 - Compute all ports upon Node initialization
 - Include all upstream dependencies ports in MID, even if they are not expanded yet
 - perfrig and assembly fragments from the stoat display artifacts on plugged ports when switching LODs
 - Internal edges
 - Button for autolayout
 - ensure initializing the graph as "low" > "mid" > "high" works OK

"""
import collections
from pprint import pformat
from itertools import count
from functools import partial

import networkx as nx

from pxr import Pcp, Sdf, Ar, Tf

from ._qt import QtWidgets, QtCore
from . import _graph, description


_TOTAL_SPAN = _graph._TOTAL_SPAN
_BORDER_COLOR = _graph._BORDER_COLOR
_BG_SPACE_COLOR = _graph._BG_SPACE_COLOR
_BG_CELL_COLOR = _graph._BG_CELL_COLOR

_EDGE_COLORS = {
    "subLayers": description._color_attrs("gray"),
    Sdf.ReferenceListOp: description._ARCS_LEGEND[Pcp.ArcTypeReference],
    Sdf.PayloadListOp: description._ARCS_LEGEND[Pcp.ArcTypePayload],
    "specializes": description._ARCS_LEGEND[Pcp.ArcTypeSpecialize],
    "inheritPaths": description._ARCS_LEGEND[Pcp.ArcTypeInherit],
    "variantSetNames": description._ARCS_LEGEND[Pcp.ArcTypeVariant],
    "variantSelection": description._ARCS_LEGEND[Pcp.ArcTypeVariant],
}


def _find_layer(path, anchor, resolver_context):
    with Ar.ResolverContextBinder(resolver_context):
        try:
            if not (layer := Sdf.Layer.FindOrOpen(path)):
                layer = Sdf.Layer.FindOrOpenRelativeToLayer(anchor, path)
        except Tf.ErrorException as exc:
            print(f"Error opening {path} from {anchor=}: {exc}")
        else:
            return layer



class _AssetStructureGraph(nx.MultiDiGraph):
    node_attr_dict_factory = lambda self: _graph.DynamicNodeAttributes({}, {}, {})

    def __init__(self, *args, resolver_context=Ar.GetResolver().CreateDefaultContext(), **kwargs):
        super().__init__(*args, **kwargs)
        self.graph['graph'] = {'rankdir': 'LR'}
        self.graph['node'] = {
            'shape': 'none',
            # 'color': outline_color,
            # 'fillcolor': background_color,
        }  # color and fillcolor used for HTML view
        self._resolver_context = resolver_context
        self._node_by_layer_mapping = {}  # SdfLayer: node_index

    def _expand_dependencies(self, keys, *, recursive=False):
        resolver_context = self._resolver_context
        edges = list()
        current_nodes = set(self.nodes)
        nodes_added = set()
        def _add_edges(src_node, src_port, tgt_node, tgt_port, attrs):
            edges.append((src_node, tgt_node, {
                "tailport": f"C1R{src_port}",
                "headport": f"C0R{tgt_port}" if tgt_port is not None else None,
                **attrs,
            }))

        def _handle_upstream_dependency(anchor, spec_index, asset_path, spec_path, edge_attrs):
            if not (dependency_layer := _find_layer(asset_path, anchor, resolver_context)):
                print(f"-------> Could not find dependency {asset_path} to traverse from {anchor}")
                return
            node_added = self._add_node_from_layer(dependency_layer)
            nodes_added.add(node_added)
            if recursive:
                nodes_added.update(self._expand_dependencies({node_added}, recursive=True))
            _add_edges(
                key,
                spec_index,
                node_added,
                self.nodes[node_added]._data['visited_layer_spec_path_ports'][
                    spec_path or dependency_layer.defaultPrim
                    ],
                edge_attrs
            )

        for key in keys:
            anchor = self.nodes[key]._data['layer']
            dependencies = self.nodes[key]._data['dependencies']
            for port_with_dependency, port_dependencies in dependencies.items():
                for dependency_info in port_dependencies:
                    _handle_upstream_dependency(anchor, port_with_dependency, *dependency_info)

        self.add_edges_from(edges)
        for node in nodes_added - current_nodes:
            self._prepare_for_display(node)
        return nodes_added

    def _add_node_from_layer(self, layer):
        """Add a node with LOD capabilities to the current graph from a given USD layer, then return the node ID.

        If layer has been added, do nothing else other than returning the node ID.
        """
        if layer in (loaded_layers := self._node_by_layer_mapping):
            return loaded_layers[layer]

        loaded_layers[layer] = node_id = len(loaded_layers)

        item_counter = count()
        # TODO: add edges when target node is self (arcs without an asset path)
        edges = list()  # [(source_node_id, target_node_id, {source_port_name, target_port_name, graphviz_attrs})]
        port_by_spec_path = {}  # {SdfPath: int}
        upstream_dependencies = dict()  # port_id: [(asset_path, prim_path, color)]

        # TODO: have item entries declare their LOD level, rather than 3 lists
        all_items = []  # [(LOD, ...)]

        def item_collector(path):
            """Increase counter and add collected path to port_by_spec_path when:
            1. Handling prims
            2. Handling pseudoRoot
               a. Handling defaultPrim
            """
            # do early exits here
            if path.IsTargetPath():
                return

            spec = layer.GetObjectAtPath(path)

            fontcolor = "#8F8F8F"
            attrs = {
                "bgcolor": _BG_CELL_COLOR,
                "fontcolor": fontcolor,
            }

            prefixes = path.GetPrefixes()
            if path.IsPrimPropertyPath():
                padding = len(prefixes) - 1  # we are the parent one
                attrs['bgcolor'] = "#FAFDF3"  # nvidia's almost white
            else:
                padding = len(prefixes)

            def _add_separator(items, LOD):
                items.append(_graph._TableItem(LOD, 0, next(item_counter), "", _TOTAL_SPAN, {'bgcolor': _BG_SPACE_COLOR}))

            if path.IsPrimPath():
                port_by_spec_path[path] = this_spec_index = next(item_counter)  # layer_ID: {path: int}
                typeName = ' - '
                for info_key in spec.ListInfoKeys():
                    if info_key in {"comment", "documentation"}:
                        continue
                    info_value = spec.GetInfo(info_key)
                    if info_key == "typeName":
                        typeName = info_value
                    elif info_key == "specifier":
                        ... # change font?
                    elif isinstance(info_value, str):
                        all_items.append(
                            _graph._TableItem(_graph._NodeLOD.HIGH, padding, next(item_counter), info_key, info_value, attrs)
                        )
                    elif isinstance(info_value, (Sdf.ReferenceListOp, Sdf.PayloadListOp)):
                        port_index = next(item_counter)
                        color = _EDGE_COLORS[type(info_value)]
                        info_attrs = collections.ChainMap(color, attrs)
                        all_items.append(_graph._TableItem(_graph._NodeLOD.MID, padding, port_index, info_key, "@...@", info_attrs))
                        for dependency_arc in info_value.GetAddedOrExplicitItems():
                            dependency_path = dependency_arc.assetPath
                            if not dependency_path:
                                # TODO: handle internal dependency, add edges
                                continue
                            upstream_dependencies.setdefault(port_index, []).append((dependency_path, dependency_arc.primPath, color))
                    elif isinstance(info_value, (Sdf.TokenListOp, Sdf.StringListOp)):
                        if items := info_value.GetAddedOrExplicitItems():
                            if info_key == "variantSetNames":
                                info_attrs = collections.ChainMap(dict(fontcolor=_EDGE_COLORS[info_key]['color']), attrs)
                            else:
                                info_attrs = attrs
                            all_items.append(_graph._TableItem(_graph._NodeLOD.HIGH, padding, next(item_counter), info_key, ", ".join(items), info_attrs))
                    elif isinstance(info_value, Sdf.PathListOp):
                        color = {"fontcolor": fontcolor,}
                        if info_key in _EDGE_COLORS:
                            color = _EDGE_COLORS[info_key]
                        if items:=info_value.GetAddedOrExplicitItems():
                            info_attrs = collections.ChainMap(color, attrs)
                            all_items.append(_graph._TableItem(_graph._NodeLOD.HIGH, padding, next(item_counter), info_key, "\n".join(map(str, items)), info_attrs))
                    elif isinstance(info_value, dict):
                        if info_key == "variantSelection":
                            info_attrs = collections.ChainMap(dict(fontcolor=_EDGE_COLORS[info_key]['color']), attrs)
                        else:
                            info_attrs = attrs
                        display_overrides = {}
                        display_dict = collections.ChainMap(display_overrides, info_value)
                        if "identifier" in info_value:
                            display_overrides['identifier'] = "..."  # identifiers may have the same name as our top row and are long
                        all_items.append(_graph._TableItem(_graph._NodeLOD.HIGH, padding, next(item_counter), info_key, pformat(dict(display_dict)), info_attrs))
                    elif isinstance(info_value, list):
                        all_items.append(_graph._TableItem(_graph._NodeLOD.HIGH, padding, next(item_counter), info_key, f"[{len(info_value)} entries]", attrs))
                    else:
                        all_items.append(_graph._TableItem(_graph._NodeLOD.HIGH, padding, next(item_counter), info_key, (str(info_value)), attrs))
                prim_attrs = {
                    'bgcolor': "#76B900",  # nvidia's green
                    'fontcolor': _BG_CELL_COLOR,  # white
                }
                all_items.append(_graph._TableItem(_graph._NodeLOD.MID, padding, this_spec_index, spec.name, str(typeName), prim_attrs))

            elif path.IsAbsoluteRootPath():
                pseudoRoot = layer.pseudoRoot
                if set(infoKeys:=pseudoRoot.ListInfoKeys())-{"subLayerOffsets", "comment", "documentation"}:
                    # wrap layer metadata with empty spaces
                    _add_separator(all_items, _graph._NodeLOD.MID)
                    for info_key in infoKeys:
                        if info_key in {"subLayerOffsets", "comment", "documentation"}:
                            continue
                        try:
                            info_value = pseudoRoot.GetInfo(info_key)
                        except TypeError as exc:
                            print(f"Could not retrieve {info_key} from pseudoRoot: {exc}")
                            continue
                        if info_key == "subLayers":
                            this_index = next(item_counter)
                            all_items.append(_graph._TableItem(_graph._NodeLOD.MID, 0, this_index, info_key, f"@...@", {
                                    "bgcolor": _BG_CELL_COLOR,
                                    "fontcolor": "#8F8F8F",
                                }))
                            edge_color = _EDGE_COLORS[info_key]
                            for sublayer in info_value:
                                upstream_dependencies.setdefault(this_index, []).append((sublayer, path, edge_color))
                        elif isinstance(info_value, list):
                            all_items.append(_graph._TableItem(_graph._NodeLOD.HIGH, padding, next(item_counter), info_key, f"[{len(info_value)} entries]", {
                                "bgcolor": _BG_CELL_COLOR,
                                "fontcolor": "#8F8F8F",
                            }))
                        else:
                            this_index = next(item_counter)
                            all_items.append(_graph._TableItem(_graph._NodeLOD.HIGH, 0, this_index, info_key, str(info_value), {
                                    "bgcolor": _BG_CELL_COLOR,
                                    "fontcolor": "#8F8F8F",
                                }))
                            if info_key == "defaultPrim":
                                port_by_spec_path[layer.defaultPrim] = this_index  # layer_ID: {path: int}
                    _add_separator(all_items, _graph._NodeLOD.MID)

                this_spec_index = next(item_counter)
                all_items.append(_graph._TableItem(_graph._NodeLOD.LOW, 0, this_spec_index, layer.GetDisplayName(), _TOTAL_SPAN, {
                    'bgcolor':_BG_SPACE_COLOR,
                    'fontcolor': "#6C6C6C",
                }))

                port_by_spec_path[path] = this_spec_index  # layer_ID: {path: int}

        layer.Traverse(layer.pseudoRoot.path, item_collector)

        self.add_node(node_id)
        self.add_edges_from(edges)  # internal edges
        self.nodes[node_id]._data.update(
            layer=layer,
            items=all_items,
            dependencies=upstream_dependencies,
            visited_layer_spec_path_ports=port_by_spec_path,
        )
        return node_id

    def _prepare_for_display(self, node_id):
        if node_id not in self.nodes:
            raise RuntimeError(locals())
        all_items = self.nodes[node_id]._data['items']
        upstream_dependencies = self.nodes[node_id]._data['dependencies']

        high_lod_label = f'<<table BORDER="4" COLOR="{_BORDER_COLOR}" bgcolor="{_BG_SPACE_COLOR}" CELLSPACING="0">'
        for row in _graph._to_table(list(reversed(all_items))):
            high_lod_label += row
        high_lod_label += '</table>>'

        ports_of_interest = set()
        for predecessor in self.predecessors(node_id):
            # headport is what we need to keep (as it belongs to this node)
            for port_idx, data in self.adj[predecessor][node_id].items():
                headport_key = data['headport']
                if isinstance(headport_key, str) and headport_key.startswith("C0R"):
                    headport_key = int(headport_key.removeprefix("C0R"))
                ports_of_interest.add(headport_key)

        mid_items = [i for i in all_items if ((i.lod in _graph._NodeLOD.LOW | _graph._NodeLOD.MID) and (i.port_index in upstream_dependencies)) or (i.value == _TOTAL_SPAN) or i.port_index in ports_of_interest]
        mid_lod_label = f'<<table BORDER="4" COLOR="{_BORDER_COLOR}" bgcolor="{_BG_SPACE_COLOR}" CELLSPACING="0">'
        for row in _graph._to_table(list(reversed(mid_items))):
            mid_lod_label += row
        mid_lod_label += '</table>>'

        low_items = [i for i in all_items if i.lod == _graph._NodeLOD.LOW]
        low_lod_label = f'<<table BORDER="4" COLOR="{_BORDER_COLOR}" bgcolor="{_BG_SPACE_COLOR}" CELLSPACING="0">'
        for row in _graph._to_table(list(reversed(low_items))):
            low_lod_label += row
        low_lod_label += '</table>>'

        # high: full asset structure
        self.nodes[node_id]._lods[_graph._NodeLOD.HIGH].update(
            label=high_lod_label,
            ports=list(reversed([x.port_index for x in all_items])),  # all rows in the entries
            layer='',
            items='',
            dependencies='',
            visited_layer_spec_path_ports='',
        )
        # mid: only items with plugs
        self.nodes[node_id]._lods[_graph._NodeLOD.MID].update(
            label=mid_lod_label,
            ports=list(reversed([x.port_index for x in mid_items])),
            layer='',
            items='',
            dependencies='',
            visited_layer_spec_path_ports='',
        )
        # low: only layer label
        self.nodes[node_id]._lods[_graph._NodeLOD.LOW].update(
            label=low_lod_label,
            ports=list(reversed([x.port_index for x in low_items])),
            layer='',
            items='',
            dependencies='',
            visited_layer_spec_path_ports='',
        )


def _launch_asset_structure_browser(root_layer, parent, resolver_context, recursive=False):
    print(f"Loading asset structure, {locals()}")
    graph = _AssetStructureGraph(resolver_context=resolver_context)
    root_node = graph._add_node_from_layer(root_layer)
    graph._prepare_for_display(root_node)
    root_nodes = [root_node]
    widget = QtWidgets.QDialog(parent=parent)
    widget.setWindowTitle("Asset Structure Diagram")
    splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

    def _expand_dependencies(graph_view, recursive):
        selection = set(graph_view.scene().selectedItems())
        selection_keys = set(k for k, v in graph_view._nodes_map.items() if v in selection)
        print(f"{selection_keys=}")
        if selection_keys:
            nodes_added = graph._expand_dependencies(selection_keys, recursive=recursive)
            if recursive:
                print(f"{recursive=}, {nodes_added=}")
                selection_keys.update(nodes_added)
        next_to_view = set(graph_view._viewing).union(selection_keys)
        graph_view.view(next_to_view)

    def _set_lod(graph_view, lod):
        selection = set(graph_view.scene().selectedItems())
        selection_keys = set(k for k, v in graph_view._nodes_map.items() if v in selection)
        print(f"{selection_keys=}")
        if selection_keys:
            graph_view.setLOD(selection_keys, lod)
            for node_id in selection_keys:
                graph_view._nodes_map[node_id].setSelected(True)

    def _export_svg(graph_view):
        _graph._GraphSVGViewer._subgraph_dot_path.cache_clear()
        error, dot_path = _graph._GraphSVGViewer._subgraph_dot_path(graph_view, graph_view._viewing)
        if error:
            raise RuntimeError(error)
        error, svg_fp = _graph._dot_2_svg(dot_path)
        if error:
            raise RuntimeError(error)
        print(f"Exported to {svg_fp}")

    # for cls in _graph.GraphView, _graph._GraphSVGViewer:
    for cls in _graph.GraphView,:
        child = cls(parent=widget)
        child._graph = graph
        if cls == _graph._GraphSVGViewer:
            nodes_to_view = graph.nodes
            widget_on_splitter = child
        else:
            widget_on_splitter = QtWidgets.QFrame()
            graph_controls_frame = QtWidgets.QFrame()
            graph_controls_layout = QtWidgets.QHBoxLayout()
            high_btn = QtWidgets.QPushButton("As High")
            high_btn.clicked.connect(partial(_set_lod, child, _graph._NodeLOD.HIGH))

            mid_btn = QtWidgets.QPushButton("As Mid")
            mid_btn.clicked.connect(partial(_set_lod, child, _graph._NodeLOD.MID))

            low_btn = QtWidgets.QPushButton("As Low")
            low_btn.clicked.connect(partial(_set_lod, child, _graph._NodeLOD.LOW))
            graph_controls_layout.addWidget(low_btn)
            graph_controls_layout.addWidget(mid_btn)
            graph_controls_layout.addWidget(high_btn)
            graph_controls_layout.addStretch()
            expand_next_dependencies_btn = QtWidgets.QPushButton("Expand Next Dependencies")
            expand_next_dependencies_btn.clicked.connect(partial(_expand_dependencies, child, recursive=False))
            graph_controls_layout.addWidget(expand_next_dependencies_btn)
            expand_all_dependencies_btn = QtWidgets.QPushButton("Expand All Dependencies")
            expand_all_dependencies_btn.clicked.connect(partial(_expand_dependencies, child, recursive=True))
            graph_controls_layout.addWidget(expand_all_dependencies_btn)
            graph_controls_layout.addStretch()
            export_svg_btn = QtWidgets.QPushButton("Export SVG")
            export_svg_btn.clicked.connect(partial(_export_svg, child))
            graph_controls_layout.addWidget(export_svg_btn)
            graph_controls_frame.setLayout(graph_controls_layout)
            widget_on_splitter_layout = QtWidgets.QVBoxLayout()
            widget_on_splitter_layout.addWidget(graph_controls_frame)
            widget_on_splitter_layout.addWidget(child)
            widget_on_splitter.setLayout(widget_on_splitter_layout)
            if recursive:
                graph._expand_dependencies(root_nodes, recursive=recursive)
                nodes_to_view = graph.nodes
            else:
                nodes_to_view = root_nodes
            # nodes_to_view = graph.nodes
        child.view(nodes_to_view)
        child.setMinimumWidth(150)
        splitter.addWidget(widget_on_splitter)

    layout = QtWidgets.QHBoxLayout()
    layout.addWidget(splitter)
    print("Showing window")
    widget.setLayout(layout)
    widget.show()
    return widget


if __name__ == "__main__":
    import sys
    # print(f"{len(sys.argv)=}")
    print(sys.argv)
    if len(sys.argv) > 1:
        rootpath = sys.argv[-1]
        print(f"Opening {rootpath}")
        layer = Sdf.Layer.FindOrOpen(rootpath)
    else:
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-Model-Country-rnd-main-Inherits-lead-base-whole.1.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\grill\tests\mini_test_bed\Catalogue-world-test.1.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-Model-Place-rnd-main-GoldenKroneHotel-lead-base-whole.1.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-abc-entity-rnd-main-atom-lead-base-whole.1.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\fragment\geo\modelling\book_magazine01\geo_modelling_book_magazine01.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\mini_test_bed\main-Taxonomy-test.1.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:/write/code/git/easy-edgedb/chapter10/assets/dracula-3d-Model-City-rnd-main-Bistritz-lead-base-whole.1.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entity\lab_workbench01\lab_workbench01.usda")
        layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entity\stoat01\stoat01.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entity\stoat_outfit01\modelling\stoat_outfit01_modelling.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entity\stoat_outfit01\stoat_outfit01.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\ALab\ALab\fragment\geo\modelling\stoat_outfit01\geo_modelling_stoat_outfit01.usda")

        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entry.usda")
        # 26.200 <module>  grill\views\_diagrams.py:1
        # ├─ 13.613 GraphView.view  grill\views\_graph.py:580
        # │  └─ 13.603 GraphView._load_graph  grill\views\_graph.py:622
        # │     ├─ 12.551 _add_node  grill\views\_graph.py:656
        # │     │  └─ 12.460 _Node.__init__  grill\views\_graph.py:124
        # │     │     ├─ 12.110 _Node.setHtml  <built-in>
        # │     │     └─ 0.265 [self]  grill\views\_graph.py
        # │     └─ 0.809 _Edge.__init__  grill\views\_graph.py:229
        # │        ├─ 0.441 _Edge.adjust  grill\views\_graph.py:305
        # │        └─ 0.267 [self]  grill\views\_graph.py
        # ├─ 8.312 _GraphSVGViewer.view  grill\views\_graph.py:894
        # │  └─ 8.311 _GraphSVGViewer._subgraph_dot_path  grill\views\_graph.py:867
        # │     └─ 8.299 func  networkx\utils\decorators.py:787
        # │           [13 frames hidden]  <class 'networkx, networkx, pydot, <b...
        # ├─ 3.761 _asset_structure_graph  grill\views\_diagrams.py:109

        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entry.usda")
        # before lazy loading:
        # 13.936 <module>  grill\views\_diagrams.py:1
        # ├─ 9.501 _asset_structure_graph  grill\views\_diagrams.py:118
        # │  └─ 9.479 traverse  grill\views\_diagrams.py:144
        # │     └─ 9.478 item_collector  grill\views\_diagrams.py:152
        # │        └─ 9.478 _handle_upstream_dependency  grill\views\_diagrams.py:158
        # │           └─ 9.470 traverse  grill\views\_diagrams.py:144
        # │              └─ 9.470 item_collector  grill\views\_diagrams.py:152
        # │                 └─ 9.470 _handle_upstream_dependency  grill\views\_diagrams.py:158
        # │                    └─ 9.442 traverse  grill\views\_diagrams.py:144
        # │                       └─ 9.419 item_collector  grill\views\_diagrams.py:152
        # │                          └─ 9.399 _handle_upstream_dependency  grill\views\_diagrams.py:158
        # │                             ├─ 8.043 traverse  grill\views\_diagrams.py:144
        # │                             │  └─ 8.036 item_collector  grill\views\_diagrams.py:152
        # │                             │     └─ 8.036 _handle_upstream_dependency  grill\views\_diagrams.py:158
        # │                             │        ├─ 4.427 traverse  grill\views\_diagrams.py:144
        # │                             │        │  └─ 4.331 item_collector  grill\views\_diagrams.py:152
        # │                             │        │     └─ 4.300 _handle_upstream_dependency  grill\views\_diagrams.py:158
        # │                             │        │        ├─ 2.471 _find_layer  grill\views\_diagrams.py:103
        # │                             │        │        └─ 1.824 traverse  grill\views\_diagrams.py:144
        # │                             │        │           └─ 1.782 item_collector  grill\views\_diagrams.py:152
        # │                             │        │              └─ 1.769 _handle_upstream_dependency  grill\views\_diagrams.py:158
        # │                             │        │                 └─ 1.763 _find_layer  grill\views\_diagrams.py:103
        # │                             │        └─ 3.609 _find_layer  grill\views\_diagrams.py:103
        # │                             └─ 1.348 _find_layer  grill\views\_diagrams.py:103
        # ├─ 3.519 _GraphSVGViewer.view  grill\views\_graph.py:1008
        # │  └─ 3.518 _GraphSVGViewer._subgraph_dot_path  grill\views\_graph.py:981
        # │     └─ 3.512 argmap_write_dot_1  <class 'networkx.utils.decorators.argmap'> compilation 5:1
        # │           [13 frames hidden]  networkx, pydot, <built-in>
        # ├─ 0.626 GraphView.view  grill\views\_graph.py:607
        # │  └─ 0.623 GraphView._load_graph  grill\views\_graph.py:710
        # │     └─ 0.467 graphviz_layout  networkx\drawing\nx_pydot.py:241
        # │           [74 frames hidden]  networkx, pydot, pyparsing
        # └─ 0.249 QFrame.show  <built-in>

        # After lazy loading:
        # 0.699 <module>  grill\views\_diagrams.py:1
        # ├─ 0.616 GraphView.view  grill\views\_graph.py:591
        # │  └─ 0.616 _AssetStructureGraph._load_graph  grill\views\_graph.py:671
        # │     ├─ 0.360 _add_node  grill\views\_graph.py:708
        # │     │  └─ 0.360 _Node.__init__  grill\views\_graph.py:132
        # │     │     └─ 0.360 _Node.setHtml  <built-in>
        # │     └─ 0.253 graphviz_layout  networkx\drawing\nx_pydot.py:239
        # │           [83 frames hidden]  networkx, pydot, pyparsing, <built-in...
        # └─ 0.080 QFrame.show  <built-in>
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QtWidgets.QApplication([])

    # print("Loading asset structure")
    # from pyinstrument import Profiler
    # profiler = Profiler()
    # profiler.start()
    # graph, root_nodes = _asset_structure_graph(layer)

    # widget = QtWidgets.QFrame()
    # splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
    # print("Starting views")
    # nx_pydot.graphviz_layout takes ~12 seconds due to pydot/dot_parser.py:497 parse_dot_data (~11.5 seconds)
    # 12.727 <module>  grill\views\_diagrams.py:1
    # ├─ 12.225 GraphView.view  grill\views\_graph.py:554
    # │  └─ 12.225 GraphView._load_graph  grill\views\_graph.py:596
    # │     ├─ 11.849 graphviz_layout  networkx\drawing\nx_pydot.py:241
    # │     │     [212 frames hidden]  networkx, pydot, pyparsing, subproces...
    # │     └─ 0.326 _add_node  grill\views\_graph.py:628
    # │        └─ 0.326 _Node.__init__  grill\views\_graph.py:100
    # │           └─ 0.322 _Node.setHtml  <built-in>
    # ├─ 0.194 _GraphSVGViewer.view  grill\views\_graph.py:865
    # │  └─ 0.194 _GraphSVGViewer._subgraph_dot_path  grill\views\_graph.py:838
    # │     └─ 0.190 func  networkx\utils\decorators.py:787
    # │           [10 frames hidden]  <class 'networkx, networkx, pydot
    # └─ 0.180 QFrame.show  <built-in>

    # without the interactive graph (and therefore not using graphviz_layout, we take
    # 0.504 <module>  grill\views\_diagrams.py:1
    # ├─ 0.233 QFrame.show  <built-in>
    # ├─ 0.168 _GraphSVGViewer.view  grill\views\_graph.py:865
    # │  └─ 0.168 _GraphSVGViewer._subgraph_dot_path  grill\views\_graph.py:838
    # │     └─ 0.165 func  networkx\utils\decorators.py:787
    # │           [16 frames hidden]  <class 'networkx, networkx, pydot, <b...
    # ├─ 0.065 _asset_structure_graph  grill\views\_diagrams.py:109

    # Good opportunity to:
    # 1. Enable "lazy" navigation of the interactive graph, where we start from visible layers that have been selected
    # 2. Add a "collapsed", "expanded" view of the nodes
    # 3. Visible nodes as a starting point:
    #       1. Root layers (in expanded mode)
    #           Expand all plugs into original positions
    #       2. Neighbors (as collapsed)
    #           Collapse all plugs into the first one
    # 4. All nodes / edges need to be computed for SVG
    # 5. Only on demand nodes / edges to be computed for interactive graph  # next milestone?
    # widget = _launch_asset_structure_browser(layer, None, None, recursive=True)
    widget = _launch_asset_structure_browser(layer, None, None, recursive=False)
    # widget.
    # profiler.stop()
    # profiler.print()
    # import pathlib
    # profiler.write_html(pathlib.Path(__file__).parent / "instrument.html")
    app.exec_()

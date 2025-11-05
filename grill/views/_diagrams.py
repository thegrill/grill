"""
TODO:
 - Internal edges
 - Button for autolayout
 - Tricky due to edge keys in networkx: Avoid graphviz warnings when nodes are collapsed about unrecognized ports

"""
import enum
import collections
from pprint import pformat
from itertools import count, chain
from functools import partial, cache

import networkx as nx

from pxr import Pcp, Sdf, Ar, Tf

from ._qt import QtWidgets, QtCore
from . import _graph, description, _core


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


class _DependencyStatus(enum.Flag):
    RESOLVED = enum.auto()
    UNRESOLVED = enum.auto()


class _AssetStructureGraph(nx.MultiDiGraph):
    BG_CELL_ATTRS = {}
    node_attr_dict_factory = lambda self: _graph.DynamicLODAttributes()

    def __init__(self, *args, resolver_context=Ar.GetResolver().CreateDefaultContext(), **kwargs):
        super().__init__(*args, **kwargs)
        self.graph['graph'] = {'rankdir': 'LR'}
        self.graph['node'] = {
            'shape': 'none',
        }
        self._resolver_context = resolver_context
        self._node_by_root_layer = {}  # SdfLayer: node_index

    def _find_nodeid_for_dependency(self, anchor_layer, source_node_key, source_port_key, layer, dependency_info):
        try:
            return self._node_by_root_layer[layer]
        except KeyError:
            return None

    def _expand_dependencies(self, keys, *, recursive=False):
        resolver_context = self._resolver_context

        def _handle_upstream_dependency(anchor_layer, dependency_info, source_node_key, source_port_key, lod):
            asset_path, spec_path, edge_attrs, dependency_type = dependency_info
            if not (dependency_layer := _find_layer(asset_path, anchor_layer, resolver_context)):
                print(f"-------> Could not find dependency {asset_path} to traverse from {anchor_layer}")
                return

            target_key = self._find_nodeid_for_dependency(anchor_layer, source_node_key, source_port_key, dependency_layer, dependency_info)
            nodes_added = set()
            if target_key is None:  # new node needs to be created
                node_added = self._add_node_from_layer(dependency_layer)
                assert self.nodes[node_added].lod
                self.nodes[node_added].lod = lod
                nodes_added.add(node_added)
            else:  # an upstream node for this dependency already exists, update it directly
                current_items = self.nodes[target_key]._data['items']
                current_items_size = len(current_items)
                self._update_node_from_layer(target_key, dependency_layer)
                if current_items_size < len(current_items):
                    nodes_added.add(target_key)

            if nodes_added:
                target_key = next(iter(nodes_added))
                target_port = self.nodes[target_key]._data['visited_layer_spec_path_ports'][dependency_layer].get(
                    spec_path or dependency_layer.defaultPrim)
                if target_port is not None:
                    self._add_edge(source_node_key, source_port_key, target_key, target_port, edge_attrs)

            return nodes_added

        nodes_to_process = set(keys)
        visited_nodes = set()
        updated_nodes = set()
        while nodes_to_process:
            key = nodes_to_process.pop()
            if key in visited_nodes:
                continue

            source_node_lod = self.nodes[key].lod
            dependencies = self.nodes[key]._data['dependencies']
            unresolved = dependencies[_DependencyStatus.UNRESOLVED]
            resolved = dependencies[_DependencyStatus.RESOLVED]

            while unresolved:
                port, port_dependencies = unresolved.popitem()
                for upstream_layer, dependencies in port_dependencies.items():
                    for dependency in dependencies:
                        updated_nodes.update(_handle_upstream_dependency(upstream_layer, dependency, key, port, source_node_lod))
                resolved.setdefault(port, {}).update(port_dependencies)

            visited_nodes.add(key)
            if recursive:
                nodes_to_process.update(updated_nodes)

        for node in updated_nodes:  # Prepare all nodes modified, clients must report modified nodes
            self._prepare_for_display(node)
        return updated_nodes

    def _add_node_from_layer(self, layer):
        # the provided layer will be the "root" layer of the node
        if layer in (loaded_layers := self._node_by_root_layer):
            return loaded_layers[layer]
        loaded_layers[layer] = node_id = len(loaded_layers)
        self.add_node(node_id)
        self.nodes[node_id]._data.update(
            # layer=layer,
            items=dict(),
            dependencies={
                _DependencyStatus.RESOLVED: dict(),
                _DependencyStatus.UNRESOLVED: dict(),
            },
            visited_layer_spec_path_ports=dict(),  # dict[layer, dict[path, port]]
        )
        self._update_node_from_layer(node_id, layer)
        return node_id

    def _attributes(self, obj):
        if isinstance(obj, Sdf.Layer):
            return {'bgcolor': _BG_SPACE_COLOR, 'fontcolor': "#6C6C6C"}
        return {}

    @cache
    def _update_node_from_layer(self, node_id, layer):
        port_by_spec_path = self.nodes[node_id]._data['visited_layer_spec_path_ports'].setdefault(layer, {})
        current_items = self.nodes[node_id]._data['items']  # NodePort: TableItem
        new_items = dict()
        dependencies = self.nodes[node_id]._data['dependencies']

        item_counter = count(start=max(current_items, default=-1) + 1)
        BG_CELL_ATTRS = self.BG_CELL_ATTRS
        # BG_CELL_ATTRS = {}

        def _add_item(lod, prefix, key, value, attrs=BG_CELL_ATTRS):
            idx = next(item_counter)
            new_items[idx] = _graph._TableItem(lod, prefix, key, value, attrs)
            return idx

        internal_dependencies = dict()

        def _add_dependency(port_index, dependant_layer, asset_path, prim_path, color, dependency_type):
            dependencies[_DependencyStatus.UNRESOLVED].setdefault(port_index, {}).setdefault(dependant_layer, []).append(
                (asset_path, prim_path, color, dependency_type)
            )

        def _traverse(path):
            if path.IsTargetPath():
                return

            spec = layer.GetObjectAtPath(path)
            depth = len(path.GetPrefixes())
            if path.IsPrimPath():
                # Store the spec index first
                port_by_spec_path[path] = this_spec_index = next(item_counter)
                attrs = {}
                # attrs = self._attributes(spec)
                info_keys = spec.ListInfoKeys()
                for info_key in info_keys:
                    info = spec.GetInfo(info_key)
                    if info_key in {"references", "payload"}:
                        port_index = _add_item(_graph._LOD.MID, depth, info_key, "@...@", collections.ChainMap(_EDGE_COLORS[type(info)], attrs))
                        for dependency_arc in info.GetAddedOrExplicitItems():
                            dependency_path = dependency_arc.assetPath
                            color = _EDGE_COLORS[type(info)]
                            if dependency_path:
                                _add_dependency(port_index, layer, dependency_path, dependency_arc.primPath, color, type(info))
                            else:
                                internal_dependencies.setdefault(port_index, []).append((dependency_arc.primPath, color))

                    elif isinstance(info, Sdf.PathListOp):
                        if items := info.GetAddedOrExplicitItems():
                            color = _EDGE_COLORS.get(info_key, {"fontcolor": "gray"})
                            port_index = _add_item(_graph._LOD.HIGH, depth, info_key, "\n".join(map(str, items)), collections.ChainMap(color, attrs))
                            for each_item in items:
                                internal_dependencies.setdefault(port_index, []).append((each_item, color))

                typeName = ':)'
                prim_attrs = self._attributes(spec)
                new_items[this_spec_index] = _graph._TableItem(_graph._LOD.MID, depth, spec.name, str(typeName),
                                                               prim_attrs)
            elif path.IsAbsoluteRootPath():
                spec = layer.pseudoRoot
                info_keys = spec.ListInfoKeys()
                for info_key in info_keys:
                    if info_key not in {"subLayers", "defaultPrim"}:
                        continue
                    info = spec.GetInfo(info_key)
                    if info_key == "subLayers":
                        edge_color = _EDGE_COLORS[info_key]
                        this_index = _add_item(_graph._LOD.MID, depth, info_key, f"@...@", collections.ChainMap(edge_color, {'bgcolor': _BG_CELL_COLOR}))
                        for dependency_path in info:
                            _add_dependency(this_index, layer, dependency_path, path, _EDGE_COLORS[info_key], info_key)
                    if info_key == "defaultPrim":
                        this_index = _add_item(_graph._LOD.HIGH, depth, info_key, info, BG_CELL_ATTRS)
                        port_by_spec_path[layer.defaultPrim] = this_index

        layer.Traverse(layer.pseudoRoot.path, _traverse)
        layer_attrs = self._attributes(layer)
        this_spec_index = _add_item(_graph._LOD.LOW, 0, layer.GetDisplayName(), _TOTAL_SPAN, layer_attrs)
        port_by_spec_path[layer.pseudoRoot.path] = this_spec_index

        for source_port, dependencies in internal_dependencies.items():
            for spec_path, color in dependencies:
                if spec_path not in port_by_spec_path:
                    continue
                target_port = port_by_spec_path[spec_path]
                self._add_edge(node_id, source_port, node_id, target_port, color)

        current_items.update(reversed(new_items.items()))

    def _add_edge(self, src_node, src_port, tgt_node, tgt_port, attrs):
        rankdir = self.graph['graph']['rankdir']
        headport_col_index, tailport_col_index = _graph._columns_for_edge(rankdir, src_node, tgt_node)
        tailport = f"C{tailport_col_index}R{src_port}"
        headport = f"C{headport_col_index}R{tgt_port}" if tgt_port is not None else None
        self.add_edge(src_node, tgt_node, key=(src_port, tgt_port), tailport=tailport, headport=headport, **attrs)

    def _add_node_from_layer_old(self, layer):
        """Add a node with LOD capabilities to the current graph from a given USD layer, then return the node ID.

        If layer has been added, do nothing else other than returning the node ID.
        """
        # TODO: add layer, dependencies tuple
        if layer in (loaded_layers := self._node_by_layer_mapping):
            return loaded_layers[layer]

        loaded_layers[layer] = node_id = len(loaded_layers)

        item_counter = count()
        edges = list()
        port_by_spec_path = {}
        upstream_dependencies = dict()
        internal_dependencies = dict()
        all_items = {}

        BG_CELL_ATTRS = {"bgcolor": _BG_CELL_COLOR, "fontcolor": "#8F8F8F"}
        FONT_COLOR_GRAY = "#8F8F8F"
        NVIDIA_GREEN = "#76B900"
        WHITE_BG = _BG_CELL_COLOR

        is_target_path = Sdf.Path.IsTargetPath
        get_object_at_path = layer.GetObjectAtPath
        list_info_keys = Sdf.Spec.ListInfoKeys
        get_info = Sdf.Spec.GetInfo

        def _add_item(lod, prefix, key, value, attrs=BG_CELL_ATTRS):
            idx = next(item_counter)
            all_items[idx] = _graph._TableItem(lod, prefix, key, value, attrs)
            return idx

        def _add_separator(LOD):
            _add_item(LOD, 0, "", _TOTAL_SPAN, {'bgcolor': _BG_SPACE_COLOR})

        def item_collector(path):
            """Increase counter and add collected path to port_by_spec_path when:
            1. Handling prims
            2. Handling pseudoRoot
            """
            if is_target_path(path):
                return

            spec = get_object_at_path(path)

            attrs = dict(BG_CELL_ATTRS)  # will be modified below

            prefixes = path.GetPrefixes()
            if path.IsPrimPropertyPath():
                depth = len(prefixes) +1 - 1  # nvidia places properties under the prim's depth
                attrs['bgcolor'] = "#FAFDF3"  # nvidia's almost white
            else:
                depth = len(prefixes) +1

            if path.IsPrimPath():
                # Store the spec index first
                port_by_spec_path[path] = this_spec_index = next(item_counter)

                typeName = ' - '
                for info_key in list_info_keys(spec):
                    if info_key in {"comment", "documentation"}:
                        continue

                    try:
                        info_value = get_info(spec, info_key)
                    except Tf.ErrorException:
                        continue

                    if info_key == "typeName":
                        typeName = info_value
                    elif info_key == "specifier":
                        pass
                    elif isinstance(info_value, str):
                        _add_item(_graph._LOD.HIGH, depth, info_key, info_value, attrs)
                    elif isinstance(info_value, (Sdf.ReferenceListOp, Sdf.PayloadListOp)):
                        port_index = _add_item(_graph._LOD.MID, depth, info_key, "@...@",
                                               collections.ChainMap(_EDGE_COLORS[type(info_value)], attrs))
                        for dependency_arc in info_value.GetAddedOrExplicitItems():
                            dependency_path = dependency_arc.assetPath
                            if not dependency_path:
                                # TODO: handle internal dependency
                                continue
                            upstream_dependencies.setdefault(port_index, []).append(
                                (layer, (dependency_path, dependency_arc.primPath, _EDGE_COLORS[type(info_value)], type(info_value)))
                            )
                    elif isinstance(info_value, (Sdf.TokenListOp, Sdf.StringListOp)):
                        if items := info_value.GetAddedOrExplicitItems():
                            info_attrs = collections.ChainMap(
                                dict(fontcolor=_EDGE_COLORS.get(info_key, {}).get('color', FONT_COLOR_GRAY)), attrs)
                            _add_item(_graph._LOD.HIGH, depth, info_key, ", ".join(items), info_attrs)
                    elif isinstance(info_value, Sdf.PathListOp):
                        if items := info_value.GetAddedOrExplicitItems():
                            color = _EDGE_COLORS.get(info_key, {"fontcolor": FONT_COLOR_GRAY})
                            port_index = _add_item(_graph._LOD.HIGH, depth, info_key, "\n".join(map(str, items)),
                                                   collections.ChainMap(color, attrs))
                            for each_item in items:
                                internal_dependencies.setdefault(port_index, []).append((each_item, color))
                    elif isinstance(info_value, dict):
                        info_attrs = collections.ChainMap(
                            dict(fontcolor=_EDGE_COLORS.get(info_key, {}).get('color', FONT_COLOR_GRAY)), attrs)
                        display_overrides = {}
                        display_dict = collections.ChainMap(display_overrides, info_value)
                        if "identifier" in info_value:
                            display_overrides['identifier'] = "..."
                        _add_item(_graph._LOD.HIGH, depth, info_key, pformat(dict(display_dict)), info_attrs)
                    elif isinstance(info_value, list):
                        _add_item(_graph._LOD.HIGH, depth, info_key, f"[{len(info_value)} entries]", attrs)
                    else:
                        _add_item(_graph._LOD.HIGH, depth, info_key, (str(info_value)), attrs)

                prim_attrs = {'bgcolor': NVIDIA_GREEN, 'fontcolor': WHITE_BG}
                all_items[this_spec_index] = _graph._TableItem(_graph._LOD.MID, depth, spec.name, str(typeName),
                                                               prim_attrs)

            elif path.IsAbsoluteRootPath():
                pseudoRoot = layer.pseudoRoot
                infoKeys = pseudoRoot.ListInfoKeys()
                if set(infoKeys) - {"subLayerOffsets", "comment", "documentation"}:
                    _add_separator(_graph._LOD.MID)

                    for info_key in infoKeys:
                        if info_key in {"subLayerOffsets", "comment", "documentation"}:
                            continue

                        try:
                            info_value = pseudoRoot.GetInfo(info_key)
                        except TypeError as exc:
                            print(f"Could not retrieve {info_key} from pseudoRoot: {exc}")
                            continue

                        if info_key == "subLayers":
                            edge_color = _EDGE_COLORS[info_key]
                            this_index = _add_item(_graph._LOD.MID, depth, info_key, f"@...@",
                                                   collections.ChainMap(edge_color, {'bgcolor': _BG_CELL_COLOR}))
                            for sublayer in info_value:
                                upstream_dependencies.setdefault(this_index, []).append(
                                    (layer, (sublayer, path, edge_color, info_key))
                                )
                        elif isinstance(info_value, list):
                            _add_item(_graph._LOD.HIGH, depth, info_key, f"[{len(info_value)} entries]",
                                      BG_CELL_ATTRS)
                        else:
                            this_index = _add_item(_graph._LOD.HIGH, depth, info_key, str(info_value), BG_CELL_ATTRS)
                            if info_key == "defaultPrim":
                                port_by_spec_path[layer.defaultPrim] = this_index

                    _add_separator(_graph._LOD.MID)

                # Add the main Layer label (LOW LOD)
                this_spec_index = _add_item(_graph._LOD.LOW, depth, layer.GetDisplayName(), _TOTAL_SPAN,
                                            {'bgcolor': _BG_SPACE_COLOR, 'fontcolor': "#6C6C6C"})
                port_by_spec_path[path] = this_spec_index

        layer.Traverse(layer.pseudoRoot.path, item_collector)
        self.add_node(node_id)

        def _add_edge(src_node, src_port, tgt_node, tgt_port, attrs):
            tailport = f"C1R{src_port}"
            headport = f"C0R{tgt_port}" if tgt_port is not None else None
            self.add_edge(src_node, tgt_node, key=(src_port, tgt_port), tailport=tailport, headport=headport, **attrs)

        for source_port, dependencies in internal_dependencies.items():
            for spec_path, color in dependencies:
                if spec_path not in port_by_spec_path:
                    continue
                target_port = port_by_spec_path[spec_path]
                _add_edge(node_id, source_port, node_id, target_port, color)

        self.add_edges_from(edges)
        # self.nodes[node_id]._data.update(
        #     # layer=layer,
        #     items=dict(reversed(all_items.items())),
        #     dependencies=upstream_dependencies,
        #     visited_layer_spec_path_ports=port_by_spec_path,
        # )
        return node_id

    def _prepare_for_display(self, node_id):
        if node_id not in self.nodes:
            raise RuntimeError(locals())

        node_data = self.nodes[node_id]._data
        all_items = node_data['items']  # dict[NodePort, Item]

        def _to_table(items, filter_fun=None):
            ports = dict()
            label = f'<<table BORDER="4" COLOR="{_BORDER_COLOR}" bgcolor="{_BG_SPACE_COLOR}" CELLSPACING="0">'
            if filter_fun:
                items = {k: v for k, v in items.items() if filter_fun((k, v))}
            for row_index, (port_id, row) in enumerate(_graph._to_table(items)):
                ports[port_id] = row_index
                label += row
            label += '</table>>'
            return label, ports

        high_lod_label, high_ports = _to_table(
            all_items,
            # collections.ChainMap(
            #     all_items,
            #     {
            #         max(all_items, default=0) + 1: _graph._TableItem(
            #             lod=_graph._LOD.HIGH,
            #             depth=0,
            #             key=f"{node_id} {_graph._LOD.HIGH} ",
            #             value=_graph._TOTAL_SPAN,
            #             display_attributes={},
            #         )
            #     }
            # ),
        )

        ports_with_dependencies = set(chain.from_iterable(node_data['dependencies'].values()))
        ports_of_interest = set()
        rankdir = self.graph['graph']['rankdir']
        for predecessor in self.predecessors(node_id):
            # headport is what we need to keep (as it belongs to this node)
            headport_col_index, tailport_col_index = _graph._columns_for_edge(rankdir, predecessor, node_id)
            for port_idx, data in self.adj[predecessor][node_id].items():
                headport_key = data['headport']
                if isinstance(headport_key, str) and headport_key.startswith(f"C{headport_col_index}R"):
                    headport_key = int(headport_key.removeprefix(f"C{headport_col_index}R"))
                ports_of_interest.add(headport_key)

        def mid_filter(item_entry):
            port_id, item = item_entry
            return (
                ((item.lod in _graph._LOD.LOW | _graph._LOD.MID) and (port_id in ports_with_dependencies))
                or (item.value == _TOTAL_SPAN)
                or port_id in ports_of_interest
            )

        mid_lod_label, mid_ports = _to_table(
            all_items,
            # collections.ChainMap(
            #     all_items,
            #     {
            #         max(all_items, default=0)  + 1: _graph._TableItem(
            #             lod=_graph._LOD.MID,
            #             depth=0,
            #             key=f"{node_id} {_graph._LOD.MID} ",
            #             value=_graph._TOTAL_SPAN,
            #             display_attributes={},
            #         )
            #     }
            # ),
            mid_filter,
        )
        low_ports = dict.fromkeys(mid_ports, 0)  # mid ports has all external connectsion, low collapses all of them
        low_items = {index: item for index, item in all_items.items() if item.lod == _graph._LOD.LOW}
        def low_filter(item_entry):
            port_id, item = item_entry
            return item.lod == _graph._LOD.LOW

        low_lod_label, __ = _to_table(
            all_items,
            # collections.ChainMap(
            #     all_items,
            #     {
            #         max(all_items, default=0)  + 1: _graph._TableItem(
            #             lod=_graph._LOD.LOW,
            #             depth=0,
            #             key=f"{node_id} {_graph._LOD.LOW} ",
            #             value=_graph._TOTAL_SPAN,
            #             display_attributes={},
            #         )
            #     }
            # ),
            low_filter,
        )

        self.nodes[node_id]._data.update(
            ports={
                _graph._LOD.HIGH: high_ports,
                _graph._LOD.MID: mid_ports,
                _graph._LOD.LOW: low_ports,
            }
        )
        # high: full asset structure
        self.nodes[node_id]._lods[_graph._LOD.HIGH].update(
            label=high_lod_label,
            ports='',
            items='',
            dependencies='',
            visited_layer_spec_path_ports='',
        )
        # mid: only items with plugs
        self.nodes[node_id]._lods[_graph._LOD.MID].update(
            label=mid_lod_label,
            ports='',
            items='',
            dependencies='',
            visited_layer_spec_path_ports='',
        )
        # low: only layer label
        self.nodes[node_id]._lods[_graph._LOD.LOW].update(
            label=low_lod_label,
            ports='',
            items='',
            dependencies='',
            visited_layer_spec_path_ports='',
        )


class _AssetStructureGraphNVidia(_AssetStructureGraph):
    BG_CELL_ATTRS = {"bgcolor": _BG_CELL_COLOR, "fontcolor": "#8F8F8F"}

    def _attributes(self, spec):
        NVIDIA_GREEN = "#76B900"
        WHITE_BG = _BG_CELL_COLOR
        if isinstance(spec, Sdf.PrimSpec):
            return {'bgcolor': NVIDIA_GREEN, 'fontcolor': WHITE_BG}
        return {}


class _AssetStructureGraphNAS(_AssetStructureGraph):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.graph['graph'] = {'rankdir': 'RL'}


    def _find_nodeid_for_dependency(self, anchor_layer, source_node_key, source_port_key, layer, dependency_info):
        # TODO: make LOD 1 be root layer only, LOD2 layerstack only, LOD3 layerstack + scene description
        # TODO: upon recursive init, cycle edges are drawn like a triangle, should be hidden (gets fixed after swapping lod back and forth)
        # TODO: sublayers should be added last to their parent, instead of at the end of the node
        # TODO: fragments with only default prims miss last cell of blue background
        # print(f"Checking ----------------------------------- {locals()}")
        asset_path, spec_path, edge_attrs, dependency_type = dependency_info
        if dependency_type == "subLayers":
            return source_node_key
        if "fragment" in anchor_layer.identifier and "entity" not in asset_path:
            return source_node_key
        try:
            return self._node_by_root_layer[layer]
        except KeyError:
            return None

    def _attributes(self, obj):
        if isinstance(obj, Sdf.Layer):
            if "entity" in obj.identifier:
                id_parts = pathlib.Path(obj.identifier.split("entity/")[-1]).parts
                if len(id_parts) > 2:
                    # domain layer
                    return {'bgcolor': "#fdecea"}
                else:
                    return {'bgcolor': "#eb4030", 'fontcolor': "#F0FFFF"}
            elif "fragment" in obj.identifier:
                id_parts = pathlib.Path(obj.identifier.split("fragment/")[-1]).parts
                if len(id_parts)<5:
                    return {'bgcolor': "#4097f6", 'fontcolor': "#F0FFFF"}
                else:
                    return {'bgcolor': "#ecf5fe"}
            else:
                return {}

        return {}

def _launch_asset_structure_browser(root_layer, parent, resolver_context, recursive=False):
    widget = _AssetStructureBrowser(root_layer, resolver_context, recursive=recursive, parent=parent)
    widget.show()
    return widget

def _launch_asset_structure_browser_nas(root_layer, parent, resolver_context, recursive=False):
    widget = _AssetStructureBrowserNAS(root_layer, resolver_context, recursive=recursive, parent=parent)
    widget.show()
    return widget

def _launch_asset_structure_browser_nvidia(root_layer, parent, resolver_context, recursive=False):
    widget = _AssetStructureBrowserNVidia(root_layer, resolver_context, recursive=recursive, parent=parent)
    widget.show()
    return widget


class _AssetStructureGraphView(_graph.GraphView):
    def keyPressEvent(self, event):
        selection = set(self.scene().selectedItems())
        if event.key() == QtCore.Qt.Key_X:
            self._expand_dependencies(False)
            event.accept()
        else:
            super().keyPressEvent(event)

    def _expand_dependencies(self, recursive):
        with _core.wait():
            selection = set(self.scene().selectedItems())
            selection_keys = set(k for k, v in self._nodes_map.items() if v in selection)
            if selection_keys:
                updated_nodes = self._graph._expand_dependencies(selection_keys, recursive=recursive)
                if recursive:
                    selection_keys.update(updated_nodes)
                if not updated_nodes:
                    print("Nothing new to view")
                    return
                next_to_view = set(self._viewing) | selection_keys | updated_nodes
                self.view(next_to_view)

    def _set_lod(self, lod):
        selection = set(self.scene().selectedItems())
        selection_keys = set(k for k, v in self._nodes_map.items() if v in selection)
        if selection_keys:
            self.setLOD(selection_keys, lod)
            for node_id in selection_keys:
                self._nodes_map[node_id].setSelected(True)

    def _export_svg(self):
        _graph._GraphSVGViewer._subgraph_dot_path.cache_clear()
        error, dot_path = _graph._GraphSVGViewer._subgraph_dot_path(self, self._viewing)
        if error:
            raise RuntimeError(error)
        error, svg_fp = _graph._dot_2_svg(dot_path)
        if error:
            raise RuntimeError(error)
        print(f"Exported to {svg_fp}")


class _AssetStructureBrowser(QtWidgets.QDialog):
    _graph_cls = _AssetStructureGraph
    def __init__(self, root_layer, resolver_context, recursive=False, parent=None):
        super().__init__(parent)
        print(f"Loading asset structure, {locals()}")
        self._graph = graph = type(self)._graph_cls(resolver_context=resolver_context)
        root_node = graph._add_node_from_layer(root_layer)
        graph._prepare_for_display(root_node)
        root_nodes = [root_node]
        self.setWindowTitle(f"Asset Structure Diagram {type(self)}")
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        if recursive:
            graph._expand_dependencies(root_nodes, recursive=recursive)
            nodes_to_view = graph.nodes
        else:
            nodes_to_view = root_nodes
        # for cls in _graph.GraphView, _graph._GraphSVGViewer:
        # for cls in _graph.GraphView,:
        # for cls in _graph._GraphSVGViewer,:
        # for cls in _AssetStructureGraphView, _graph._GraphSVGViewer, _graph.GraphView,:
        for cls in _AssetStructureGraphView,:
            # for cls in _graph.GraphView,:
            print(f"initializing {cls}")
            child = cls(parent=self)
            child._graph = graph
            self.setFocusProxy(child)
            if isinstance(child, _AssetStructureGraphView):
                widget_on_splitter = QtWidgets.QFrame()
                graph_controls_frame = QtWidgets.QFrame()
                graph_controls_layout = QtWidgets.QHBoxLayout()
                high_btn = QtWidgets.QPushButton("⩩")
                high_btn.clicked.connect(partial(child._set_lod, _graph._LOD.HIGH))

                mid_btn = QtWidgets.QPushButton("═")
                mid_btn.clicked.connect(partial(child._set_lod, _graph._LOD.MID))

                low_btn = QtWidgets.QPushButton("─")
                low_btn.clicked.connect(partial(child._set_lod, _graph._LOD.LOW))
                graph_controls_layout.addWidget(low_btn)
                graph_controls_layout.addWidget(mid_btn)
                graph_controls_layout.addWidget(high_btn)
                graph_controls_layout.addStretch()
                expand_next_dependencies_btn = QtWidgets.QPushButton("Expand Next Dependencies")
                # expand_next_dependencies_btn.clicked.connect(partial(_expand_dependencies, child, recursive=False))
                expand_next_dependencies_btn.clicked.connect(partial(child._expand_dependencies, recursive=False))
                graph_controls_layout.addWidget(expand_next_dependencies_btn)
                expand_all_dependencies_btn = QtWidgets.QPushButton("Expand All Dependencies")
                expand_all_dependencies_btn.clicked.connect(partial(child._expand_dependencies, recursive=True))
                graph_controls_layout.addWidget(expand_all_dependencies_btn)
                graph_controls_layout.addStretch()
                export_svg_btn = QtWidgets.QPushButton("Export SVG")
                export_svg_btn.clicked.connect(child._export_svg)
                graph_controls_layout.addWidget(export_svg_btn)
                graph_controls_frame.setLayout(graph_controls_layout)
                widget_on_splitter_layout = QtWidgets.QVBoxLayout()
                widget_on_splitter_layout.addWidget(graph_controls_frame)
                widget_on_splitter_layout.addWidget(child)
                widget_on_splitter.setLayout(widget_on_splitter_layout)
            else:
                widget_on_splitter = child
            print(f"Viewing {len(nodes_to_view)}")
            child.view(nodes_to_view)
            print(f"finished initializing {cls}")
            child.setMinimumWidth(150)
            splitter.addWidget(widget_on_splitter)
            continue
            # # TODO: make the below a test
            if hasattr(child, "setLOD"):
                child.setLOD(root_nodes, _graph._LOD.LOW)
            # nodes_added = graph._expand_dependencies(root_nodes, recursive=False)
            # new_nodes_to_view = set(root_nodes).union(nodes_added)
            # child.view(new_nodes_to_view)
            # child.setLOD(new_nodes_to_view, _graph._LOD.LOW)
            #
            # continue
            # # breakpoint()
            # child.view(new_nodes_to_view)
            # continue
            #
            # #### TEST recursive and lod
            nodes_added = graph._expand_dependencies(root_nodes, recursive=True)
            new_nodes_to_view = set(root_nodes).union(nodes_added)
            child.view(new_nodes_to_view)

            # child.setLOD(root_nodes, _graph._LOD.MID)
            continue
            # # new_nodes_to_view = child._expand_dependencies(True)
            # # print(f"{new_nodes_to_view=}")
            # # continue
            # #######
            # nodes_added = graph._expand_dependencies(root_nodes, recursive=False)
            # new_nodes_to_view = set(root_nodes).union(nodes_added)
            #
            # # TODO: update view once dependencies have been updated from code
            # nodes_added = graph._expand_dependencies(nodes_added, recursive=False)
            # new_nodes_to_view = set(new_nodes_to_view).union(nodes_added)
            #
            # child.view(new_nodes_to_view)  # calling this after setLOD fails
            # if hasattr(child, "setLOD"):
            #     child.setLOD([1], _graph._LOD.LOW)
            #     child.setLOD(nodes_added, _graph._LOD.MID)
            #
            # nodes_added = graph._expand_dependencies(new_nodes_to_view, recursive=False)
            # new_nodes_to_view = set(new_nodes_to_view).union(nodes_added)
            # child.view(new_nodes_to_view)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(splitter)
        self.setLayout(layout)


class _AssetStructureBrowserNAS(_AssetStructureBrowser):
    _graph_cls = _AssetStructureGraphNAS


class _AssetStructureBrowserNVidia(_AssetStructureBrowser):
    _graph_cls = _AssetStructureGraphNVidia


if __name__ == "__main__":
    # Run python -X utf8 -m grill.views._diagrams for unicode characters in diagramms (or set PYTHONUTF8=1)
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
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-abc-entity-rnd-main-atom-lead-base-whole.1.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entity\stoat01\rigging\stoat01_rigging.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entity\stoat_outfit01\modelling\stoat_outfit01_modelling.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entity\stoat_outfit01\stoat_outfit01.usda")
        # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\ALab\ALab\fragment\geo\modelling\stoat_outfit01\geo_modelling_stoat_outfit01.usda")

        layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entry.usda")

    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QtWidgets.QApplication([])

    print("Loading asset structure")
    from pyinstrument import Profiler
    profiler = Profiler()
    profiler.start()
    # graph, root_nodes = _asset_structure_graph(layer)

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
    widget = _launch_asset_structure_browser_nas(layer, None, None, recursive=False)
    widget = _launch_asset_structure_browser_nvidia(layer, None, None, recursive=False)
    # widget.
    profiler.stop()
    profiler.print()
    import pathlib
    profiler.write_html(pathlib.Path(__file__).parent / "instrument.html")
    print(_graph._cached_escape.cache_info())
    print(_graph._format_display_cell.cache_info())
    app.exec_()

    # python=8.8 GB RAM
    #   7.7 GB AssetStructure Diagram
    #   1.0 GB QtWebEngine Process

    # ================ 2025/10/19 py-3.13 usd-25.11 ==========================
    # LOW
    # pygraphviz
    #
    # -------------- 2025 / 10 / 28 ----------------
    #
    #   _     ._   __/__   _ _  _  _ _/_   Recorded: 20:28:32  Samples:  7728
    #  /_//_/// /_\ / //_// / //_'/ //     Duration: 12.113    CPU time: 12.016
    # /   _/                      v5.0.1
    #
    # Profile at A:\write\code\git\grill\grill\views\_diagrams.py:638
    #
    # 12.113 <module>  A:\write\code\git\grill\grill\views\_diagrams.py:1
    # └─ 12.113 _launch_asset_structure_browser  A:\write\code\git\grill\grill\views\_diagrams.py:385
    #    └─ 11.997 _AssetStructureBrowser.__init__  A:\write\code\git\grill\grill\views\_diagrams.py:437
    #       ├─ 7.946 _AssetStructureGraphView.view  A:\write\code\git\grill\grill\views\_graph.py:906
    #       │  └─ 7.935 _AssetStructureGraphView._load_graph  A:\write\code\git\grill\grill\views\_graph.py:948
    #       │     ├─ 3.991 graphviz_layout  networkx\drawing\nx_agraph.py:226
    #       │     │     [6 frames hidden]  networkx, pygraphviz, threading
    #       │     │        2.975 _ThreadHandle.join  <built-in>
    #       │     ├─ 2.572 _add_node  A:\write\code\git\grill\grill\views\_graph.py:987
    #       │     │  └─ 2.535 _Node.__init__  A:\write\code\git\grill\grill\views\_graph.py:138
    #       │     │     ├─ 1.941 _Node.setHtml  <built-in>
    #       │     │     └─ 0.397 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #       │     └─ 1.096 _Edge.__init__  A:\write\code\git\grill\grill\views\_graph.py:431
    #       │        ├─ 0.709 _Edge.adjust  A:\write\code\git\grill\grill\views\_graph.py:561
    #       │        │  ├─ 0.439 _Node._activatePort  A:\write\code\git\grill\grill\views\_graph.py:379
    #       │        │  │  ├─ 0.157 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #       │        │  │  └─ 0.142 __build_class__  <built-in>
    #       │        │  └─ 0.218 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #       │        └─ 0.254 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #       └─ 3.997 _AssetStructureGraph._expand_dependencies  A:\write\code\git\grill\grill\views\_diagrams.py:60
    #          ├─ 3.222 _handle_upstream_dependency  A:\write\code\git\grill\grill\views\_diagrams.py:71
    #          │  ├─ 2.240 _find_layer  A:\write\code\git\grill\grill\views\_diagrams.py:37
    #          │  ├─ 0.725 _AssetStructureGraph._add_node_from_layer  A:\write\code\git\grill\grill\views\_diagrams.py:138
    #          │  │  ├─ 0.505 item_collector  A:\write\code\git\grill\grill\views\_diagrams.py:173
    #          │  │  └─ 0.134 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    #          │  └─ 0.191 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    #          └─ 0.714 _AssetStructureGraph._prepare_for_display  A:\write\code\git\grill\grill\views\_diagrams.py:312
    #             ├─ 0.402 _to_table  A:\write\code\git\grill\grill\views\_graph.py:1279
    #             └─ 0.139 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    # pydot!!!!
    #   _     ._   __/__   _ _  _  _ _/_   Recorded: 19:47:31  Samples:  70981
    #  /_//_/// /_\ / //_// / //_'/ //     Duration: 78.931    CPU time: 80.156
    # /   _/                      v5.0.1
    #
    # Profile at A:\write\code\git\grill\grill\views\_diagrams.py:638
    #
    # 78.930 <module>  A:\write\code\git\grill\grill\views\_diagrams.py:1
    # └─ 78.930 _launch_asset_structure_browser  A:\write\code\git\grill\grill\views\_diagrams.py:385
    #    └─ 78.824 _AssetStructureBrowser.__init__  A:\write\code\git\grill\grill\views\_diagrams.py:437
    #       ├─ 74.796 _AssetStructureGraphView.view  A:\write\code\git\grill\grill\views\_graph.py:906
    #       │  └─ 74.786 _AssetStructureGraphView._load_graph  A:\write\code\git\grill\grill\views\_graph.py:948
    #       │     ├─ 70.264 graphviz_layout  networkx\drawing\nx_pydot.py:241
    #       │     │     [234 frames hidden]  networkx, pydot, pyparsing, subproces...
    #       │     ├─ 2.867 _add_node  A:\write\code\git\grill\grill\views\_graph.py:988
    #       │     │  └─ 2.817 _Node.__init__  A:\write\code\git\grill\grill\views\_graph.py:138
    #       │     │     └─ 1.943 _Node.setHtml  <built-in>
    #       │     └─ 1.347 _Edge.__init__  A:\write\code\git\grill\grill\views\_graph.py:431
    #       │        └─ 0.963 _Edge.adjust  A:\write\code\git\grill\grill\views\_graph.py:561
    #       └─ 3.972 _AssetStructureGraph._expand_dependencies  A:\write\code\git\grill\grill\views\_diagrams.py:60
    #          └─ 3.190 _handle_upstream_dependency  A:\write\code\git\grill\grill\views\_diagrams.py:71
    #             └─ 2.264 _find_layer  A:\write\code\git\grill\grill\views\_diagrams.py:37
    #
    # MID
    # pygraphviz
    #   _     ._   __/__   _ _  _  _ _/_   Recorded: 20:31:56  Samples:  9249
    #  /_//_/// /_\ / //_// / //_'/ //     Duration: 15.877    CPU time: 15.594
    # /   _/                      v5.0.1
    #
    # Profile at A:\write\code\git\grill\grill\views\_diagrams.py:638
    #
    # 15.876 <module>  A:\write\code\git\grill\grill\views\_diagrams.py:1
    # └─ 15.876 _launch_asset_structure_browser  A:\write\code\git\grill\grill\views\_diagrams.py:385
    #    └─ 15.757 _AssetStructureBrowser.__init__  A:\write\code\git\grill\grill\views\_diagrams.py:437
    #       ├─ 11.685 _AssetStructureGraphView.view  A:\write\code\git\grill\grill\views\_graph.py:906
    #       │  └─ 11.674 _AssetStructureGraphView._load_graph  A:\write\code\git\grill\grill\views\_graph.py:948
    #       │     ├─ 5.123 _add_node  A:\write\code\git\grill\grill\views\_graph.py:987
    #       │     │  └─ 4.788 _Node.__init__  A:\write\code\git\grill\grill\views\_graph.py:138
    #       │     │     ├─ 3.423 _Node.setHtml  <built-in>
    #       │     │     ├─ 0.761 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #       │     │     └─ 0.295 _Node.itemChange  A:\write\code\git\grill\grill\views\_graph.py:372
    #       │     ├─ 4.882 graphviz_layout  networkx\drawing\nx_agraph.py:226
    #       │     │     [6 frames hidden]  networkx, pygraphviz, threading
    #       │     │        3.823 _ThreadHandle.join  <built-in>
    #       │     ├─ 1.090 _Edge.__init__  A:\write\code\git\grill\grill\views\_graph.py:431
    #       │     │  ├─ 0.713 _Edge.adjust  A:\write\code\git\grill\grill\views\_graph.py:561
    #       │     │  │  ├─ 0.455 _Node._activatePort  A:\write\code\git\grill\grill\views\_graph.py:379
    #       │     │  │  └─ 0.213 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #       │     │  └─ 0.241 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #       │     └─ 0.172 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #       └─ 4.014 _AssetStructureGraph._expand_dependencies  A:\write\code\git\grill\grill\views\_diagrams.py:60
    #          ├─ 3.268 _handle_upstream_dependency  A:\write\code\git\grill\grill\views\_diagrams.py:71
    #          │  ├─ 2.300 _find_layer  A:\write\code\git\grill\grill\views\_diagrams.py:37
    #          │  ├─ 0.709 _AssetStructureGraph._add_node_from_layer  A:\write\code\git\grill\grill\views\_diagrams.py:138
    #          │  │  └─ 0.508 item_collector  A:\write\code\git\grill\grill\views\_diagrams.py:173
    #          │  └─ 0.196 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    #          └─ 0.689 _AssetStructureGraph._prepare_for_display  A:\write\code\git\grill\grill\views\_diagrams.py:312
    #             └─ 0.375 _to_table  A:\write\code\git\grill\grill\views\_graph.py:1279
    # pydot!!!
    #   _     ._   __/__   _ _  _  _ _/_   Recorded: 20:48:50  Samples:  171957
    #  /_//_/// /_\ / //_// / //_'/ //     Duration: 188.783   CPU time: 185.938
    # /   _/                      v5.0.1
    #
    # Profile at A:\write\code\git\grill\grill\views\_diagrams.py:638
    #
    # 188.782 <module>  A:\write\code\git\grill\grill\views\_diagrams.py:1
    # └─ 188.782 _launch_asset_structure_browser  A:\write\code\git\grill\grill\views\_diagrams.py:385
    #    └─ 188.668 _AssetStructureBrowser.__init__  A:\write\code\git\grill\grill\views\_diagrams.py:437
    #       ├─ 184.167 _AssetStructureGraphView.view  A:\write\code\git\grill\grill\views\_graph.py:906
    #       │  └─ 184.157 _AssetStructureGraphView._load_graph  A:\write\code\git\grill\grill\views\_graph.py:948
    #       │     ├─ 175.796 graphviz_layout  networkx\drawing\nx_pydot.py:241
    #       │     │     [198 frames hidden]  networkx, pydot, pyparsing, subproces...
    #       │     └─ 6.095 _add_node  A:\write\code\git\grill\grill\views\_graph.py:988
    #       │        └─ 5.881 _Node.__init__  A:\write\code\git\grill\grill\views\_graph.py:138
    #       │           └─ 4.891 _Node.setHtml  <built-in>
    #       └─ 4.442 _AssetStructureGraph._expand_dependencies  A:\write\code\git\grill\grill\views\_diagrams.py:60
    #          └─ 3.591 _handle_upstream_dependency  A:\write\code\git\grill\grill\views\_diagrams.py:71
    #             └─ 2.483 _find_layer  A:\write\code\git\grill\grill\views\_diagrams.py:37
    #
    # HIGH
    # pygraphviz
    #   _     ._   __/__   _ _  _  _ _/_   Recorded: 20:33:10  Samples:  9582
    #  /_//_/// /_\ / //_// / //_'/ //     Duration: 23.578    CPU time: 20.594
    # /   _/                      v5.0.1
    #
    # Profile at A:\write\code\git\grill\grill\views\_diagrams.py:638
    #
    # 23.578 <module>  A:\write\code\git\grill\grill\views\_diagrams.py:1
    # └─ 23.578 _launch_asset_structure_browser  A:\write\code\git\grill\grill\views\_diagrams.py:385
    #    └─ 23.458 _AssetStructureBrowser.__init__  A:\write\code\git\grill\grill\views\_diagrams.py:437
    #       ├─ 19.357 _AssetStructureGraphView.view  A:\write\code\git\grill\grill\views\_graph.py:906
    #       │  └─ 19.347 _AssetStructureGraphView._load_graph  A:\write\code\git\grill\grill\views\_graph.py:948
    #       │     ├─ 10.249 _add_node  A:\write\code\git\grill\grill\views\_graph.py:987
    #       │     │  └─ 10.247 _Node.__init__  A:\write\code\git\grill\grill\views\_graph.py:138
    #       │     │     └─ 10.231 _Node.setHtml  <built-in>
    #       │     ├─ 7.682 graphviz_layout  networkx\drawing\nx_agraph.py:226
    #       │     │     [5 frames hidden]  networkx, pygraphviz, threading
    #       │     │        6.430 _ThreadHandle.join  <built-in>
    #       │     └─ 1.159 _Edge.__init__  A:\write\code\git\grill\grill\views\_graph.py:431
    #       │        ├─ 0.639 _Edge.adjust  A:\write\code\git\grill\grill\views\_graph.py:561
    #       │        │  └─ 0.463 _Node._activatePort  A:\write\code\git\grill\grill\views\_graph.py:379
    #       │        └─ 0.349 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #       └─ 4.047 _AssetStructureGraph._expand_dependencies  A:\write\code\git\grill\grill\views\_diagrams.py:60
    #          ├─ 3.283 _handle_upstream_dependency  A:\write\code\git\grill\grill\views\_diagrams.py:71
    #          │  ├─ 2.280 _find_layer  A:\write\code\git\grill\grill\views\_diagrams.py:37
    #          │  └─ 0.743 _AssetStructureGraph._add_node_from_layer  A:\write\code\git\grill\grill\views\_diagrams.py:138
    #          │     └─ 0.473 item_collector  A:\write\code\git\grill\grill\views\_diagrams.py:173
    #          └─ 0.715 _AssetStructureGraph._prepare_for_display  A:\write\code\git\grill\grill\views\_diagrams.py:312
    #             └─ 0.367 _to_table  A:\write\code\git\grill\grill\views\_graph.py:1279
    # pydot!!!
    #   _     ._   __/__   _ _  _  _ _/_   Recorded: 20:37:30  Samples:  318547
    #  /_//_/// /_\ / //_// / //_'/ //     Duration: 349.521   CPU time: 343.656
    # /   _/                      v5.0.1
    #
    # Profile at A:\write\code\git\grill\grill\views\_diagrams.py:638
    #
    # 349.520 <module>  A:\write\code\git\grill\grill\views\_diagrams.py:1
    # └─ 349.520 _launch_asset_structure_browser  A:\write\code\git\grill\grill\views\_diagrams.py:385
    #    └─ 349.384 _AssetStructureBrowser.__init__  A:\write\code\git\grill\grill\views\_diagrams.py:437
    #       ├─ 345.173 _AssetStructureGraphView.view  A:\write\code\git\grill\grill\views\_graph.py:906
    #       │  └─ 345.162 _AssetStructureGraphView._load_graph  A:\write\code\git\grill\grill\views\_graph.py:948
    #       │     ├─ 331.483 graphviz_layout  networkx\drawing\nx_pydot.py:241
    #       │     │     [171 frames hidden]  networkx, pydot, pyparsing, subproces...
    #       │     └─ 11.037 _add_node  A:\write\code\git\grill\grill\views\_graph.py:988
    #       │        └─ 11.036 _Node.__init__  A:\write\code\git\grill\grill\views\_graph.py:138
    #       │           └─ 11.003 _Node.setHtml  <built-in>
    #       └─ 4.156 _AssetStructureGraph._expand_dependencies  A:\write\code\git\grill\grill\views\_diagrams.py:60
    #
    #
    # SVG Viewer
    # pydot
    #   _     ._   __/__   _ _  _  _ _/_   Recorded: 19:58:15  Samples:  10766
    #  /_//_/// /_\ / //_// / //_'/ //     Duration: 11.530    CPU time: 14.203
    # /   _/                      v5.0.1
    #
    # Profile at A:\write\code\git\grill\grill\views\_diagrams.py:578
    #
    # 11.530 <module>  A:\write\code\git\grill\grill\views\_diagrams.py:1
    # └─ 11.530 _launch_asset_structure_browser  A:\write\code\git\grill\grill\views\_diagrams.py:385
    #    ├─ 11.346 _AssetStructureBrowser.__init__  A:\write\code\git\grill\grill\views\_diagrams.py:437
    #    │  ├─ 7.311 _GraphSVGViewer.view  A:\write\code\git\grill\grill\views\_graph.py:1200
    #    │  │  └─ 7.310 _GraphSVGViewer._subgraph_dot_path  A:\write\code\git\grill\grill\views\_graph.py:1163
    #    │  │     └─ 7.239 argmap_write_dot_1  <class 'networkx.utils.decorators.argmap'> compilation 5:1
    #    │  │           [16 frames hidden]  networkx, pydot, <built-in>
    #    │  │              5.423 <genexpr>  pydot\core.py:321
    #    │  │              └─ 3.325 [self]  pydot\core.py
    #    │  └─ 4.004 _AssetStructureGraph._expand_dependencies  A:\write\code\git\grill\grill\views\_diagrams.py:60
    #    │     ├─ 3.252 _handle_upstream_dependency  A:\write\code\git\grill\grill\views\_diagrams.py:71
    #    │     │  ├─ 2.302 _find_layer  A:\write\code\git\grill\grill\views\_diagrams.py:37
    #    │     │  ├─ 0.682 _AssetStructureGraph._add_node_from_layer  A:\write\code\git\grill\grill\views\_diagrams.py:138
    #    │     │  │  ├─ 0.480 item_collector  A:\write\code\git\grill\grill\views\_diagrams.py:173
    #    │     │  │  └─ 0.117 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    #    │     │  └─ 0.202 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    #    │     └─ 0.691 _AssetStructureGraph._prepare_for_display  A:\write\code\git\grill\grill\views\_diagrams.py:312
    #    │        ├─ 0.365 _to_table  A:\write\code\git\grill\grill\views\_graph.py:1280
    #    │        └─ 0.159 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    #    └─ 0.184 _AssetStructureBrowser.show  <built-in>
    # pygraphviz
    #   _     ._   __/__   _ _  _  _ _/_   Recorded: 19:56:41  Samples:  4526
    #  /_//_/// /_\ / //_// / //_'/ //     Duration: 5.364     CPU time: 8.797
    # /   _/                      v5.0.1
    #
    # Profile at A:\write\code\git\grill\grill\views\_diagrams.py:578
    #
    # 5.363 <module>  A:\write\code\git\grill\grill\views\_diagrams.py:1
    # └─ 5.363 _launch_asset_structure_browser  A:\write\code\git\grill\grill\views\_diagrams.py:385
    #    ├─ 5.179 _AssetStructureBrowser.__init__  A:\write\code\git\grill\grill\views\_diagrams.py:437
    #    │  ├─ 4.069 _AssetStructureGraph._expand_dependencies  A:\write\code\git\grill\grill\views\_diagrams.py:60
    #    │  │  ├─ 3.335 _handle_upstream_dependency  A:\write\code\git\grill\grill\views\_diagrams.py:71
    #    │  │  │  ├─ 2.248 _find_layer  A:\write\code\git\grill\grill\views\_diagrams.py:37
    #    │  │  │  ├─ 0.777 _AssetStructureGraph._add_node_from_layer  A:\write\code\git\grill\grill\views\_diagrams.py:138
    #    │  │  │  │  ├─ 0.558 item_collector  A:\write\code\git\grill\grill\views\_diagrams.py:173
    #    │  │  │  │  ├─ 0.132 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    #    │  │  │  │  └─ 0.064 _AssetStructureGraph.add_node  networkx\classes\digraph.py:439
    #    │  │  │  └─ 0.246 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    #    │  │  └─ 0.682 _AssetStructureGraph._prepare_for_display  A:\write\code\git\grill\grill\views\_diagrams.py:312
    #    │  │     ├─ 0.362 _to_table  A:\write\code\git\grill\grill\views\_graph.py:1279
    #    │  │     │  ├─ 0.199 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #    │  │     │  └─ 0.065 _format_display_cell  A:\write\code\git\grill\grill\views\_graph.py:1251
    #    │  │     │     └─ 0.057 str.format  <built-in>
    #    │  │     ├─ 0.142 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    #    │  │     └─ 0.094 _LOD.__or__  enum.py:1592
    #    │  └─ 1.079 _GraphSVGViewer.view  A:\write\code\git\grill\grill\views\_graph.py:1199
    #    │     └─ 1.078 _GraphSVGViewer._subgraph_dot_path  A:\write\code\git\grill\grill\views\_graph.py:1163
    #    │        └─ 1.065 write_dot  networkx\drawing\nx_agraph.py:183
    #    │              [22 frames hidden]  networkx, pygraphviz, <frozen _collec...
    #    └─ 0.184 _AssetStructureBrowser.show  <built-in>

    # 2025/11/02
    #
    #   _     ._   __/__   _ _  _  _ _/_   Recorded: 11:47:03  Samples:  4969
    #  /_//_/// /_\ / //_// / //_'/ //     Duration: 6.948     CPU time: 7.922
    # /   _/                      v5.0.1
    #
    # Profile at A:\write\code\git\grill\grill\views\_diagrams.py:1351
    #
    # 6.948 <module>  A:\write\code\git\grill\grill\views\_diagrams.py:1
    # └─ 6.948 _launch_asset_structure_browser_nas  A:\write\code\git\grill\grill\views\_diagrams.py:1153
    #    └─ 6.911 _AssetStructureBrowserNAS.__init__  A:\write\code\git\grill\grill\views\_diagrams.py:1206
    #       ├─ 3.730 _AssetStructureGraphView.view  A:\write\code\git\grill\grill\views\_graph.py:788
    #       │  └─ 3.723 _AssetStructureGraphView._load_graph  A:\write\code\git\grill\grill\views\_graph.py:830
    #       │     ├─ 2.256 _add_node  A:\write\code\git\grill\grill\views\_graph.py:869
    #       │     │  └─ 2.219 _Node.__init__  A:\write\code\git\grill\grill\views\_graph.py:138
    #       │     │     ├─ 2.027 _Node.setHtml  <built-in>
    #       │     │     └─ 0.116 [self]  A:\write\code\git\grill\grill\views\_graph.py
    #       │     └─ 1.398 graphviz_layout  networkx\drawing\nx_agraph.py:226
    #       │           [6 frames hidden]  networkx, pygraphviz, threading, <bui...
    #       └─ 3.127 _AssetStructureGraphNAS._expand_dependencies  A:\write\code\git\grill\grill\views\_diagrams.py:174
    #          ├─ 2.730 _handle_upstream_dependency  A:\write\code\git\grill\grill\views\_diagrams.py:180
    #          │  ├─ 1.964 _find_layer  A:\write\code\git\grill\grill\views\_diagrams.py:37
    #          │  └─ 0.716 _AssetStructureGraphNAS._add_node_from_layer  A:\write\code\git\grill\grill\views\_diagrams.py:233
    #          │     ├─ 0.342 _traverse  A:\write\code\git\grill\grill\views\_diagrams.py:266
    #          │     ├─ 0.208 [self]  A:\write\code\git\grill\grill\views\_diagrams.py
    #          │     └─ 0.121 _AssetStructureGraphNAS.add_node  networkx\classes\digraph.py:439
    #          ├─ 0.297 _AssetStructureGraphNAS._prepare_for_display  A:\write\code\git\grill\grill\views\_diagrams.py:543
    #          │  └─ 0.243 _to_table  A:\write\code\git\grill\grill\views\_diagrams.py:549
    #          │     └─ 0.174 _to_table  A:\write\code\git\grill\grill\views\_graph.py:1178
    #          └─ 0.074 set.update  <built-in>
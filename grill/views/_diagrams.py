import html
from pxr import Pcp, Sdf, Ar, Tf

from ._qt import QtWidgets, QtCore
from . import _graph, description


def _to_table(items):
    span = max(x[0] for x in items) + 2
    width = 50
    for index, (padding, internal_index, key, value, attrs) in enumerate(items):
        key_port = f"C0R{internal_index}"
        value_port = f"C1R{internal_index}"

        more_attrs = ''
        if bgcolor:=attrs.get("bgcolor"):
            more_attrs+= f' BGCOLOR="{bgcolor}"'
        font_entry = ''
        font_closure = ''
        if fontcolor:=attrs.get("fontcolor"):
            font_entry = f'<FONT COLOR="{fontcolor}">'
            font_closure = '</FONT>'
        fontstyle_entry = ''
        fontstyle_closure = ''
        # if attrs.get("fontstyle") == 'bold':
        #     fontstyle_entry = '<B>'
        #     fontstyle_closure = '</B>'

        safe_key = html.escape(key)
        # zero based + 2 for each side: key and value
        span_in_row = ((span-2) * 3) if value is _TOTAL_SPAN else span
        if value is _TOTAL_SPAN:
            if not key:
                display_cell_template = '<TD HEIGHT="10" BORDER="0" COLOR="{_BORDER_COLOR}" COLSPAN="{span_in_row}" PORT="{port}" WIDTH="{width}" {more_attrs}>{font_entry}{fontstyle_entry}{safe_entry}{fontstyle_closure}{font_closure}</TD>'
            else:
                display_cell_template = '<TD BORDER="0" COLOR="{_BORDER_COLOR}" COLSPAN="{span_in_row}" PORT="{port}" WIDTH="{width}" {more_attrs}>{font_entry}{fontstyle_entry}{safe_entry}{fontstyle_closure}{font_closure}</TD>'
        else:
            display_cell_template = '<TD BORDER="1" COLOR="{_BORDER_COLOR}" COLSPAN="{span_in_row}" PORT="{port}" WIDTH="{width}" {more_attrs}>{font_entry}{fontstyle_entry}{safe_entry}{fontstyle_closure}{font_closure}</TD>'

        key_entry = display_cell_template.format(
            _BORDER_COLOR=_BORDER_COLOR,
            span_in_row=span_in_row,
            port=key_port,
            width=width,
            more_attrs=more_attrs,
            font_entry=font_entry,
            fontstyle_entry=fontstyle_entry,
            safe_entry=safe_key,
            fontstyle_closure=fontstyle_closure,
            font_closure=font_closure,
        )
        if value is _TOTAL_SPAN:
            identation_entry = ''
            tail_entry = ''
            value_entry = ''
        else:
            span_entry = f'<TD BORDER="0" BGCOLOR="{_BG_SPACE_COLOR}"></TD>'
            identation_entry = span_entry * padding
            tail_entry = span_entry * (span - padding - 1)
            safe_value = html.escape(value).replace("\n", "<br/>")
            value_entry = display_cell_template.format(
                _BORDER_COLOR=_BORDER_COLOR,
                span_in_row=span_in_row,
                port=value_port,
                width=width,
                more_attrs=more_attrs,
                font_entry=font_entry,
                fontstyle_entry=fontstyle_entry,
                safe_entry=safe_value,
                fontstyle_closure=fontstyle_closure,
                font_closure=font_closure,
            )
        display_entry = f'{key_entry}{value_entry}'
        row = f'<TR>{identation_entry}{display_entry}{tail_entry}</TR>'
        yield row


import networkx as nx

_TOTAL_SPAN = object()
_BORDER_COLOR = "#E0E0E0"
_BG_SPACE_COLOR = "#FAFAFA"

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

def _asset_structure_graph(root_layer, resolver_context=Ar.GetResolver().CreateDefaultContext()):
    graph = nx.MultiDiGraph()
    graph.graph['graph'] = {'rankdir': 'LR'}

    graph.graph['node'] = {
        'shape': 'none',
        # 'color': outline_color,
        # 'fillcolor': background_color,
    }  # color and fillcolor used for HTML view

    all_nodes = dict()  # {node_id: {graphviz_attr: value}}
    edges = list()  # [(source_node_id, target_node_id, {source_port_name, target_port_name, graphviz_attrs})]

    visited_layers = {}  # layer: idx

    visited_layer_spec_path_ports = {}  # layer_ID: {path: int}

    def _add_edges(src_node, src_port, tgt_node, tgt_port, attrs):
        edges.append((src_node, tgt_node, {
            "tailport": f"C1R{src_port}",
            "headport": f"C0R{tgt_port}" if tgt_port is not None else None,
            **attrs,
        }))

    def traverse(layer):
        if layer in visited_layers:
            return
        visited_layers[layer] = node_id = len(visited_layers)
        layer_items = []

        def item_collector(path):
            # do early exits here
            if path.IsTargetPath():
                # print(f"Ignoring target path: {path}")
                return

            def _handle_upstream_dependency(spec_index, asset_path, spec_path, edge_attrs):
                if not (dependency_layer:=_find_layer(asset_path, layer, resolver_context)):
                    print(f"-------> Could not find dependency {asset_path} to traverse from {layer}")
                    return
                traverse(dependency_layer)
                _add_edges(
                    visited_layers[layer],
                    spec_index,
                    visited_layers[dependency_layer],
                    visited_layer_spec_path_ports[visited_layers[dependency_layer]][
                        # spec_path or dependency_layer.pseudoRoot.GetPrimAtPath(dependency_layer.defaultPrim).path],
                        spec_path or dependency_layer.defaultPrim
                    ],
                    edge_attrs
                )

            spec = layer.GetObjectAtPath(path)
            attrs = {}

            prefixes = path.GetPrefixes()
            key = spec.name

            if path.IsPrimPropertyPath():
                padding = len(prefixes) - 1  # we are the parent one
                attrs['bgcolor'] = "#FAFDF3"  # nvidia's almost white
            else:
                padding = len(prefixes)

            if path.IsPrimPath():
                this_spec_index = next(counter)
                visited_layer_spec_path_ports.setdefault(node_id, {})[path] = this_spec_index  # layer_ID: {path: int}
                typeName = ' - '
                for _key in spec.ListInfoKeys():
                    _value = spec.GetInfo(_key)
                    fontcolor = "#8F8F8F"
                    if _key in {"comment",}:
                        continue
                    elif _key == "typeName":
                        typeName = _value
                    elif _key == "specifier":
                        ... # change font?
                    elif isinstance(_value, str):
                        layer_items.append((padding, next(counter), _key, _value, {
                            "bgcolor": "#FFFFFF",
                            "fontcolor": fontcolor,
                        }))
                    elif isinstance(_value, (Sdf.ReferenceListOp, Sdf.PayloadListOp)):
                        port_index = next(counter)
                        color = _EDGE_COLORS[type(_value)]
                        layer_items.append((padding, port_index, _key, "@...@", {
                            "bgcolor": "#FFFFFF",
                            **color,
                        }))
                        for dependency_arc in _value.GetAddedOrExplicitItems():
                            dependency_path = dependency_arc.assetPath
                            if not dependency_path:
                                continue
                            _handle_upstream_dependency(port_index, dependency_path, dependency_arc.primPath, color)
                    elif isinstance(_value, (Sdf.TokenListOp, Sdf.StringListOp)):
                        if items:=_value.GetAddedOrExplicitItems():
                            if _key=="variantSetNames":
                                fontcolor=_EDGE_COLORS[_key]['color']
                            layer_items.append((padding, next(counter), _key, ", ".join(items), {
                                "bgcolor": "#FFFFFF",
                                "fontcolor": fontcolor,
                            }))
                    elif isinstance(_value, Sdf.PathListOp):
                        # breakpoint()
                        color = {"fontcolor": fontcolor,}
                        if _key in _EDGE_COLORS:
                            color = _EDGE_COLORS[_key]
                        if items:=_value.GetAddedOrExplicitItems():
                            layer_items.append((padding, next(counter), _key, "\n".join(map(str, items)), {
                                "bgcolor": "#FFFFFF",
                                **color
                            }))
                    elif isinstance(_value, dict):
                        from pprint import pformat
                        from collections import ChainMap
                        if _key=="variantSelection":
                            fontcolor=_EDGE_COLORS[_key]['color']
                        display_overrides = {}
                        display_dict = ChainMap(display_overrides, _value)
                        if "identifier" in _value:
                            display_overrides['identifier'] = "..."  # identifiers may have the same name as our top row and are long
                        layer_items.append((padding, next(counter), _key, pformat(dict(display_dict)), {
                            "bgcolor": "#FFFFFF",
                            "fontcolor": fontcolor,
                        }))
                    elif isinstance(_value, list):
                        layer_items.append((padding, next(counter), _key, f"[{len(_value)} entries]", {
                            "bgcolor": "#FFFFFF",
                            "fontcolor": fontcolor,
                        }))
                    else:
                        layer_items.append((padding, next(counter), _key, (str(_value)), {
                            "bgcolor": "#FFFFFF",
                            "fontcolor": fontcolor,
                        }))

                attrs['bgcolor'] = "#76B900"  # nvidia's green
                attrs['fontcolor'] = "#ffffff"  # white
                layer_items.append((padding, this_spec_index, key, str(typeName), attrs))

            def _add_separator():
                layer_items.append((0, next(counter), "", _TOTAL_SPAN, {'bgcolor': _BG_SPACE_COLOR}))

            if path.IsAbsoluteRootPath():
                pseudoRoot = layer.pseudoRoot
                if infoKeys:=pseudoRoot.ListInfoKeys():
                    # wrap layer metadata with empty spaces
                    _add_separator()
                    for _key in infoKeys:
                        if _key in {"subLayerOffsets", "comment"}:
                            continue
                        try:
                            _value = pseudoRoot.GetInfo(_key)
                        except TypeError as exc:
                            print(f"Could not retrieve {_key} from pseudoRoot: {exc}")
                            continue
                        if _key == "subLayers":
                            this_index = next(counter)
                            layer_items.append((0, this_index, _key, f"@...@", {
                                    "bgcolor": "#FFFFFF",
                                    "fontcolor": "#8F8F8F",
                                }))
                            edge_color = _EDGE_COLORS[_key]
                            for sublayer in _value:
                                _handle_upstream_dependency(this_index, sublayer, path, edge_color)
                        elif isinstance(_value, list):
                            layer_items.append((padding, next(counter), _key, f"[{len(_value)} entries]", {
                                "bgcolor": "#FFFFFF",
                                "fontcolor": "#8F8F8F",
                            }))
                        else:
                            this_index = next(counter)
                            layer_items.append((0, this_index, _key, str(_value), {
                                    "bgcolor": "#FFFFFF",
                                    "fontcolor": "#8F8F8F",
                                }))
                            if _key == "defaultPrim":
                                visited_layer_spec_path_ports.setdefault(node_id, {})[layer.defaultPrim] = this_index  # layer_ID: {path: int}
                    _add_separator()

                this_spec_index = next(counter)
                layer_items.append((0, this_spec_index, layer.GetDisplayName(), _TOTAL_SPAN, {
                    'bgcolor':_BG_SPACE_COLOR,
                    'fontcolor': "#6C6C6C",
                }))
                visited_layer_spec_path_ports.setdefault(node_id, {})[path] = this_spec_index  # layer_ID: {path: int}

        from itertools import count
        counter = count()
        layer.Traverse(layer.pseudoRoot.path, item_collector)

        # TODO: confirm that Traverse always yields the deepest path first
        label = f'<<table BORDER="4" COLOR="{_BORDER_COLOR}" bgcolor="{_BG_SPACE_COLOR}" CELLSPACING="0">'
        for row in _to_table(list(reversed(layer_items))):
            label += row
        label += '</table>>'
        all_nodes[node_id] = dict(label=label, ports=list(reversed([x[1] for x in layer_items])))

    traverse(root_layer)
    graph.add_nodes_from(all_nodes.items())
    graph.add_edges_from(edges)
    return graph


def _launch_asset_structure_browser(root_layer, parent, resolver_context):
    print("Loading asset structure")
    graph = _asset_structure_graph(root_layer, resolver_context)
    widget = QtWidgets.QDialog(parent=parent)
    widget.setWindowTitle("Asset Structure Diagram")
    splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

    for cls in _graph.GraphView, _graph._GraphSVGViewer:
        child = cls(parent=widget)
        child._graph = graph
        child.view(graph.nodes)
        child.setMinimumWidth(150)
        splitter.addWidget(child)

    layout = QtWidgets.QHBoxLayout()
    layout.addWidget(splitter)
    print("Showing window")
    widget.setLayout(layout)
    widget.show()


if __name__ == "__main__":
    layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-Model-Country-rnd-main-Inherits-lead-base-whole.1.usda")
    layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\grill\tests\mini_test_bed\Catalogue-world-test.1.usda")
    layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-Model-Place-rnd-main-GoldenKroneHotel-lead-base-whole.1.usda")
    layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-abc-entity-rnd-main-atom-lead-base-whole.1.usda")
    # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\fragment\geo\modelling\book_magazine01\geo_modelling_book_magazine01.usda")
    # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\mini_test_bed\main-Taxonomy-test.1.usda")
    # layer = Sdf.Layer.FindOrOpen(r"A:/write/code/git/easy-edgedb/chapter10/assets/dracula-3d-Model-City-rnd-main-Bistritz-lead-base-whole.1.usda")
    # layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\entity\lab_workbench01\lab_workbench01.usda")

    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QtWidgets.QApplication([])

    print("Loading asset structure")
    graph = _asset_structure_graph(layer)
    widget = QtWidgets.QFrame()
    splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
    print("Starting views")
    for cls in _graph.GraphView, _graph._GraphSVGViewer:
        for pixmap_enabled in ((True, False) if cls == _graph._GraphSVGViewer else (False,)):
            _graph._GraphViewer = cls
            _graph._USE_SVG_VIEWPORT = pixmap_enabled

            child = cls(parent=widget)
            child._graph = graph
            child.view(graph.nodes)
            child.setMinimumWidth(150)
            splitter.addWidget(child)

    layout = QtWidgets.QHBoxLayout()
    layout.addWidget(splitter)
    print("Showing window")
    widget.setLayout(layout)
    widget.show()

    app.exec_()

import html
from pxr import Sdf

layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-Model-Country-rnd-main-Inherits-lead-base-whole.1.usda")
layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\grill\tests\mini_test_bed\Catalogue-world-test.1.usda")
layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-Model-Place-rnd-main-GoldenKroneHotel-lead-base-whole.1.usda")
layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-abc-entity-rnd-main-atom-lead-base-whole.1.usda")
# layer = Sdf.Layer.FindOrOpen(r"A:\write\code\git\USDALab\ALab\fragment\geo\modelling\book_magazine01\geo_modelling_book_magazine01.usda")

def _to_table(items):
    span = max(x[0] for x in items)
    print(f"{span=}")
    max_identation = span * 2  # 2 for each side: key and value
    width = 50
    for index, (padding, internal_index, key, value, attrs) in enumerate(items):
        print(f"{internal_index=}")
        key_port = f"C0R{internal_index}"
        value_port = f"C1R{internal_index}"
        safe_key = html.escape(key)
        safe_value = html.escape(value)
        span_entry = '<TD BORDER="0"></TD>'
        identation_entry = span_entry*padding
        tail_entry = span_entry*(span-padding-1)
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

        row = f'<TR>{identation_entry}<TD COLSPAN="{span}" PORT="{key_port}" WIDTH="{width}" {more_attrs}>{font_entry}{fontstyle_entry}{safe_key}{fontstyle_closure}{font_closure}</TD><TD COLSPAN="{span}" PORT="{value_port}" WIDTH="{width}" {more_attrs}>{font_entry}{fontstyle_entry}{safe_value}{fontstyle_closure}{font_closure}</TD>{tail_entry}</TR>'
        # row = f'<TR><TD WIDTH="{width}">{safe_key}</TD><TD WIDTH="{width}">{safe_value}</TD></TR>'
        yield row


import networkx as nx

from functools import cache

def _asset_structure_graph(root_layer):
    graph = nx.MultiDiGraph()
    # outline_color = "#4682B4"  # 'steelblue'
    # background_color = "#F0FFFF"  # 'azure'
    graph.graph['graph'] = {'rankdir': 'LR'}

    graph.graph['node'] = {
        'shape': 'none',
        # 'color': outline_color,
        # 'fillcolor': background_color,
    }  # color and fillcolor used for HTML view
    # graph.graph['edge'] = {"color": 'crimson'}

    all_nodes = dict()  # {node_id: {graphviz_attr: value}}
    edges = list()  # [(source_node_id, target_node_id, {source_port_name, target_port_name, graphviz_attrs})]

    all_items = []
    visited_layers = {}  # layer: idx

    visited_layer_spec_path_ports = {}  # layer_ID: {path: int}

    @cache
    def _add_edges(src_node, src_port, tgt_node, tgt_port):
        # tooltip = f"{src_node}.{src_port} -> {tgt_node}.{tgt_port}"
        # edges.append((src_node, tgt_node, {"tailport": src_port, "headport": tgt_port, "tooltip": tooltip}))
        edges.append((src_node, tgt_node, {"tailport": f"C1R{src_port}", "headport": f"C0R{tgt_port}" if tgt_port is not None else None}))

    def traverse(layer):
        if layer in visited_layers:
            return
        print(f"~~~~~~~~~~~~~~~~~~~~~~ TRAVERSING {layer}")
        visited_layers[layer] = node_id = len(visited_layers)

        from functools import partial
        layer_items = []
        upstream_dependencies = {}
        # layer_fun = partial(fun, layer, layer_items, upstream_dependencies)

        # def layer_fun(layer, visited, downstream_dependencies, path, **kwargs):

        # def _add_row(spec):
        #     index = next(counter)

        paddings = set()

        def item_collector(path):
            # do early exits here
            if path.IsTargetPath():
                print(f"Ignoring target path: {path}")
                return

            spec = layer.GetObjectAtPath(path)
            attrs = {}

            prefixes = path.GetPrefixes()
            key = spec.name
            value = 's'

            # parent_key = path.GetParentPath()
            # variant_set, selection = path.GetVariantSelection()
            # if path.IsPrimVariantSelectionPath() and selection:  # place all variant selections under the variant set
            #     parent_key = parent_key.AppendVariantSelection(variant_set, "")

            if path.IsPrimPropertyPath():
                padding = len(prefixes) - 1  # we are the parent one
                attrs['bgcolor'] = "#FAFDF3"  # nvidia's almost white
            else:
                padding = len(prefixes)

            if not paddings:
                paddings.add(padding)
                print(f"Collected paddings for the first time: {padding}")
            if padding > max(paddings):
                print(f"-->>>>>>>> PADDING WAS NOT MAX: {max(paddings)}, this padding: {padding}")
            paddings.add(len(prefixes))

            if path.IsPrimPath():
                this_spec_index = next(counter)
                visited_layer_spec_path_ports.setdefault(node_id, {})[path] = this_spec_index  # layer_ID: {path: int}
                # breakpoint()
                # attrs['fontstyle'] = 'bold'
                value = spec.typeName or ' '
                #### metadata
                if spec.HasKind():
                    layer_items.append((padding, next(counter), 'instanceable', str(spec.instanceable), {
                        "bgcolor": "#FAFDF3"
                    }))
                if spec.HasInstanceable():
                    layer_items.append((padding, next(counter), 'kind', spec.kind, {
                        "bgcolor": "#FAFDF3"
                    }))

                if references := spec.referenceList.GetAddedOrExplicitItems():
                    this_index = next(counter)
                    # breakpoint()
                    for reference in references:
                        dependency_path = reference.assetPath
                        if not dependency_path:
                            continue
                        dependency_layer = Sdf.Layer.FindOrOpen(dependency_path) or Sdf.Layer.FindOrOpen(layer.ComputeAbsolutePath(dependency_path))
                        if not dependency_layer:
                            print(f"-------> Could not find dependency {dependency_path} to traverse from {layer}")
                            continue
                        layer_items.append((padding, this_index, "reference", "ASSETS", {}))
                        traverse(dependency_layer)
                        # downstream_dependencies.setdefault(reference.assetPath, {}).setdefault(reference.primPath,
                        #                                                                        set()).add(path)
                        # try:
                        _add_edges(
                            visited_layers[layer],
                            this_index,

                            visited_layers[dependency_layer],
                            visited_layer_spec_path_ports[visited_layers[dependency_layer]][reference.primPath or dependency_layer.pseudoRoot.GetPrimAtPath(dependency_layer.defaultPrim).path],
                        )

                if references := spec.payloadList.GetAddedOrExplicitItems():
                    this_index = next(counter)
                    # breakpoint()
                    for reference in references:
                        dependency_path = reference.assetPath
                        if not dependency_path:
                            continue
                        dependency_layer = Sdf.Layer.FindOrOpen(dependency_path) or Sdf.Layer.FindOrOpen(
                            layer.ComputeAbsolutePath(dependency_path))
                        if not dependency_layer:
                            print(
                                f"-------> Could not find dependency {dependency_path} to traverse from {layer}")
                            continue
                        layer_items.append((padding, this_index, "reference", "ASSETS", {}))
                        traverse(dependency_layer)
                        # downstream_dependencies.setdefault(reference.assetPath, {}).setdefault(reference.primPath,
                        #                                                                        set()).add(path)
                        # try:
                        _add_edges(
                            visited_layers[layer],
                            this_index,

                            visited_layers[dependency_layer],
                            visited_layer_spec_path_ports[visited_layers[dependency_layer]][
                                reference.primPath or dependency_layer.pseudoRoot.GetPrimAtPath(
                                    dependency_layer.defaultPrim).path],
                        )
                        # except KeyError:
                        #     breakpoint()
                        #     raise

                attrs['bgcolor'] = "#76B900"  # nvidia's green
                attrs['fontcolor'] = "#ffffff"  # white
                # breakpoint()

                layer_items.append((padding, this_spec_index, key, value, attrs))
            # all_items.extend(items)
            # all_items.append(path.name, path)
            # print(spec)


        # label = f'<<table border="1" cellspacing="2" style="ROUNDED" bgcolor="{background_color}" color="{outline_color}">'
        from itertools import count
        counter = count()
        this_index = next(counter)
        layer_items.append((0, this_index, "sublayerszz", "SOMEASS", {}))
        for sublayer in layer.subLayerPaths:
            print(sublayer)
            dependency_layer = Sdf.Layer.FindOrOpen(sublayer) or Sdf.Layer.FindOrOpen(
                layer.ComputeAbsolutePath(sublayer))
            if not dependency_layer:
                print(
                    f"-------> Could not find dependency {sublayer} to traverse from {layer}")
                continue
            traverse(dependency_layer)
            _add_edges(
                visited_layers[layer],
                this_index,

                visited_layers[dependency_layer],
                None,
            )
        layer.Traverse(layer.pseudoRoot.path, item_collector)
        # TODO: confirm that Traverse always yields the deepest path first
        label = f'<<table BORDER="10"  cellspacing="0"                 bgcolor="#FAFAFA"            color="#E0E0E0"         cellborder="1"  TITLE="value">'
        for row in _to_table(list(reversed(layer_items))):
            label += row
        # label += '''<TR><TD COLSPAN="4" PORT="C0K0" WIDTH="50" >/</TD><TD COLSPAN="4" PORT="C1K0" WIDTH="50" >s</TD><TD BORDER="0"></TD><TD BORDER="0"></TD><TD BORDER="0"></TD></TR>
        # <TR><TD BORDER="0"></TD><TD COLSPAN="4" PORT="C0K1" WIDTH="50"  BGCOLOR="#76B900"><FONT COLOR="#ffffff">Catalogue</FONT></TD><TD COLSPAN="4" PORT="C1K1" WIDTH="50"  BGCOLOR="#76B900"><FONT COLOR="#ffffff"> </FONT></TD><TD BORDER="0"></TD><TD BORDER="0"></TD></TR>
        # '''
        label += '</table>>'
        # print(label)
        ports = []
        # all_nodes[node_id] = dict(label=label, ports=ports)
        all_nodes[node_id] = dict(label=label)

        # for dependency_path, dependants in upstream_dependencies.items():
        #     dependency_layer = Sdf.Layer.FindOrOpen(dependency_path) or Sdf.Layer.FindOrOpen(layer.ComputeAbsolutePath(dependency_path))
        #     if not dependency_layer:
        #         print(f"-------> Could not find dependency {dependency_path} to traverse from {layer}")
        #         continue
        #     traverse(dependency_layer)

    traverse(root_layer)

    graph.add_nodes_from(all_nodes.items())
    # breakpoint()
    # graph.add_nodes_from(["A", "B"])
    graph.add_edges_from(edges)
    return graph


if __name__ == "__main__":
    ...

    from grill.views._qt import QtWidgets, QtCore

    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    # python -m grill.views._graph
    app = QtWidgets.QApplication([])

    from grill.views import _graph

    graph = _asset_structure_graph(layer)
    # print(f"{graph=}")
    print(len(graph.nodes))
    # graph = nx.MultiDiGraph()
    # _graph_view = _graph._GraphViewer(parent=None)
    # _graph_view.graph = graph
    # _graph_view.view(graph.nodes)

    widget = QtWidgets.QFrame()
    splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)


    for cls in _graph.GraphView, _graph._GraphSVGViewer:
        for pixmap_enabled in ((True, False) if cls == _graph._GraphSVGViewer else (False,)):
            _graph._GraphViewer = cls
            _graph._USE_SVG_VIEWPORT = pixmap_enabled
            # stack.show()

            child = cls(parent=widget)
            child._graph = graph
            child.view(graph.nodes)
            child.setMinimumWidth(150)
            splitter.addWidget(child)
            print(f"Added {child}")
            # viewer = description._ConnectableAPIViewer()
            # viewer.setPrim(material)
            # splitter.addWidget(viewer)


    # splitter.addWidget(_graph_view)
    layout = QtWidgets.QHBoxLayout()
    layout.addWidget(splitter)

    widget.setLayout(layout)
    widget.show()

    app.exec_()

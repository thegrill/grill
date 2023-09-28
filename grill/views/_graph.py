# Learnt from https://doc.qt.io/qtforpython-6/examples/example_external_networkx.html
from __future__ import annotations

import math
import networkx as nx
from itertools import chain

from networkx import drawing

from . import _core
from ._qt import QtCore, QtGui, QtWidgets
_core._ensure_dot()

_IS_QT5 = QtCore.qVersion().startswith("5")

# TODO:
#   - Cleanup Edge adjust and paint logic
#   - Context menu items
#   - Dark mode to respect arcs color
#   - USDView missing tri-state style
#   - Ability to move further in canvas after Nodes don't exist
#   - Focus with F
#   - Taxonomy graph is LR and should go from center to center (edges)

_NO_PEN = QtGui.QPen(QtCore.Qt.NoPen)


def _convert_graphviz_to_html_label(label):
    # TODO: these checks below rely on internals from the grill (layer stack composition uses record shapes, connection viewer uses html)
    if label.startswith("{"):  # We're a record. Split the label into individual fields
        fields = label.strip("{}").split("|")
        label = '<table>'
        for index, field in enumerate(fields):
            port, text = field.strip("<>").split(">", 1)
            bgcolor = "white" if index % 2 == 0 else "#f0f6ff"  # light blue
            label += f"<tr><td port='{port}' bgcolor='{bgcolor}'>{text}</td></tr>"
        label += "</table>"
    elif label.startswith("<"):
        # Contract: HTML graphviz labels start with a double <<, additionally, ROUNDED is internal to graphviz
        # QGraphicsTextItem seems to have trouble with HTML rounding, so we're controlling this via paint + custom style
        label = label.removeprefix("<").removesuffix(">").replace('table border="1" cellspacing="2" style="ROUNDED"', "table")
    return label


class _Node(QtWidgets.QGraphicsTextItem):

    def __init__(self, parent=None, label="", color="", fillcolor="", plugs=None, visible=True, active_plugs: set = frozenset()):
        super().__init__(parent)
        self._edges = []
        self._plugs = plugs or {}

        plug_items = {}
        radius = 4
        def _plug_item():
            item = QtWidgets.QGraphicsEllipseItem(-radius, -radius, 2 * radius, 2 * radius)
            item.setPen(_NO_PEN)
            return item
        self._active_plugs = active_plugs
        self._active_plugs_by_side = dict()
        for plug_index in active_plugs:
            plug_items[plugs[plug_index]] = (_plug_item(), _plug_item())
            self._active_plugs_by_side[plugs[plug_index]] = {0: dict(), 1: dict()}
        self._plug_items = plug_items
        self._pen = QtGui.QPen(QtGui.QColor(color), 1, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        self._fillcolor = QtGui.QColor(fillcolor)
        self.setHtml("<style>th, td {text-align: center;padding: 3px}</style>" + _convert_graphviz_to_html_label(label))
        # Temp measure: allow PySide6 interaction, but not in PySide2 as this causes a crash on windows:
        # https://stackoverflow.com/questions/67264846/pyqt5-program-crashes-when-editable-qgraphicstextitem-is-clicked-with-right-mo
        # https://bugreports.qt.io/browse/QTBUG-89563
        self._default_text_interaction = QtCore.Qt.LinksAccessibleByMouse if _IS_QT5 else QtCore.Qt.TextBrowserInteraction
        if visible:
            self.setTextInteractionFlags(self._default_text_interaction)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)
            self.setAcceptHoverEvents(True)
        else:
            self.setVisible(False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)

    def _overrideCursor(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier:
            self.setCursor(QtGui.Qt.PointingHandCursor)
        elif event.modifiers() == QtCore.Qt.AltModifier:
            self.setCursor(QtGui.Qt.ClosedHandCursor)
            self.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        else:
            self.setTextInteractionFlags(self._default_text_interaction)
            self.setCursor(QtGui.Qt.ArrowCursor)

    def hoverMoveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._overrideCursor(event)
        super().hoverMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and event.modifiers() == QtCore.Qt.ControlModifier:
            self.linkActivated.emit("")
        else:
            super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        self._overrideCursor(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(QtGui.Qt.ArrowCursor)
        self.setTextInteractionFlags(self._default_text_interaction)
        super().hoverLeaveEvent(event)

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionGraphicsItem, widget: QtWidgets.QWidget) -> None:
        painter.setRenderHints(QtGui.QPainter.Antialiasing)
        painter.setPen(self._pen)
        rect_path = QtGui.QPainterPath()
        roundness = 6
        rect_path.addRoundedRect(self.boundingRect().adjusted(1, 1, -1, -1), roundness, roundness)
        painter.fillPath(rect_path, self._fillcolor)
        painter.drawRoundedRect(self.boundingRect().adjusted(1, 1, -1, -1), roundness, roundness)
        return super().paint(painter, option, widget)

    def add_edge(self, edge: _Edge):
        self._edges.append(edge)

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            for edge in self._edges:
                edge.adjust()
        elif change == QtWidgets.QGraphicsItem.ItemSelectedChange:
            ...
        return super().itemChange(change, value)

    def _activatePlug(self, edge, plug_index, side):
        plugs_by_side = self._active_plugs_by_side[plug_index]
        plugs_by_side[side][edge] = True
        other_side = bool(not side)
        inactive_plugs = plugs_by_side[other_side]
        inactive_plugs.pop(edge, None)
        plug_items = self._plug_items[plug_index]
        if not inactive_plugs:
            plug_items[other_side].setVisible(False)
        this_item = plug_items[side]
        this_item.setVisible(True)
        this_item.setBrush(edge._brush)


class _Edge(QtWidgets.QGraphicsItem):
    def __init__(self, source: _Node, dest: _Node, parent: QtWidgets.QGraphicsItem = None, color="#2BB53C", label="", source_plug=None, target_plug=None, is_bidirectional=False):
        super().__init__(parent)
        self._source = source
        self._dest = dest
        self._is_cycle = source == dest
        self._source_plug = source_plug
        self._target_plug = target_plug
        self._bidirectional_shift = 20 if is_bidirectional else 0

        self._tickness = 1.5
        self._colors = color.split(":")
        self._color = self._colors[0]
        self._arrow_size = 15

        self._source.add_edge(self)
        self._dest.add_edge(self)

        self._line = QtCore.QLineF()
        self.setZValue(-1)

        self._pen = QtGui.QPen(QtGui.QColor(self._color), self._tickness, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        self._brush = QtGui.QBrush(self._color)
        if _IS_QT5:
            self._brush.setStyle(QtGui.Qt.SolidPattern)
            self._brush.setColor(self._color)

        if label:
            self._label_text = QtWidgets.QGraphicsTextItem(label, self)
            self._label_text.setDefaultTextColor(self._color)
            self._label_text.setHtml(f"<b>{label}</b>")
        else:
            self._label_text = None

        self.adjust()

    def boundingRect(self) -> QtCore.QRectF:
        """Override from QtWidgets.QGraphicsItem

        Returns:
            QRect: Return node bounding rect
        """
        if self._is_cycle:
            top_left = self._cycle_start_position
            bottom_right = top_left + QtCore.QPointF(50, 50)
        else:
            top_left, bottom_right = self._line.p1(), self._line.p2()

        return QtCore.QRectF(top_left, bottom_right).normalized().adjusted(
            -self._tickness - self._arrow_size,
            -self._tickness - self._arrow_size,
            self._tickness + self._arrow_size,
            self._tickness + self._arrow_size,
        )

    @property
    def _cycle_start_position(self):
        if self._source_plug is None:
            source = self._source
            source_bounds = source.boundingRect()
            shift_x = source_bounds.right() - 5
            shift_y = source_bounds.height() / 2 - 20
            return source.pos() + QtCore.QPointF(shift_x, shift_y)

        return self._line.p1() + QtCore.QPointF(-3, -31)

    def adjust(self):
        """
        Update edge position from source and destination node.
        This method is called from Node::itemChange
        """
        self.prepareGeometryChange()
        source_pos = self._source.pos()
        dest_pos = self._dest.pos()
        dest_port_size = self._dest.boundingRect().height() / (len(self._dest._plugs)) if self._dest._plugs else 0
        dest_shift = dest_port_size/2
        source_port_size = self._source.boundingRect().height() / (len(self._source._plugs)) if self._source._plugs else 0
        source_shift = source_port_size / 2
        source_bounds = self._source.boundingRect()
        active_source_plug_index = 1  # right, by default
        active_target_plug_index = 0  # left, by default

        # where is our source position?
        if self._source_plug is not None:
            source_before = source_bounds.center().x() + source_pos.x() < self._dest.boundingRect().center().x() + dest_pos.x()
            source_x = source_pos.x() + source_bounds.right()
            source_y = source_pos.y() + (source_bounds.y()) + (((self._source_plug or 0) * source_port_size) + source_shift)
            if self._is_cycle:
                active_target_plug_index = 1  # right
            elif not source_before:
                active_source_plug_index = 0  # left
                active_target_plug_index = 1  # right
                source_x = source_pos.x()
            source_point_position = QtCore.QPointF(source_x, source_y)
        else:
            source_point_position = source_pos + source_bounds.center()

        # where is our target position?
        if self._target_plug is not None:  # Connection viewer
            dest_x = self._dest.boundingRect().x() if source_before else self._dest.boundingRect().x() + self._dest.boundingRect().right()
            dest_y = self._dest.boundingRect().y() + ((self._target_plug * dest_port_size) + dest_shift)
            target_point_position = self._dest.pos() + QtCore.QPointF(dest_x, dest_y)
        else:
            line = QtCore.QLineF(source_point_position, self._dest.pos() + self._dest.boundingRect().center())
            if self._bidirectional_shift:  # offset in case of bidirectional connections
                line = _parallel_line(line, distance=self._bidirectional_shift, head_offset=0)

            # Check if there is an intersection
            if _IS_QT5:
                intersect_method = line.intersect
                bounded_intersection = QtCore.QLineF.IntersectType.BoundedIntersection
            else:
                intersect_method = line.intersects
                bounded_intersection = QtCore.QLineF.IntersectionType.BoundedIntersection

            dest_rect = self._dest.boundingRect()
            topLeft, topRight, bottomLeft, bottomRight = dest_rect.topLeft(), dest_rect.topRight(), dest_rect.bottomLeft(), dest_rect.bottomRight()
            dest_pos = self._dest.pos()
            for each in (
                    QtCore.QLineF(topLeft + dest_pos, topRight + dest_pos),  # top
                    QtCore.QLineF(topLeft + dest_pos, bottomLeft + dest_pos),  # left
                    QtCore.QLineF(bottomLeft + dest_pos, bottomRight + dest_pos),  # bottom
                    QtCore.QLineF(bottomRight + dest_pos, topRight + dest_pos),  # right
            ):  # TODO: how to make this more efficient?
                intersection, intersection_point = intersect_method(each)
                if intersection == bounded_intersection:
                    target_point_position = intersection_point
                    break
            else:
                target_point_position = line.p2()

        self._line = QtCore.QLineF(source_point_position, target_point_position)
        self._active_source_plug_index = active_source_plug_index
        self._active_target_plug_index = active_target_plug_index
        if self._source_plug is not None:
            self._source._activatePlug(self, self._source_plug, active_source_plug_index)
            self._source._plug_items[self._source_plug][active_source_plug_index].setPos(source_point_position)
        if self._target_plug is not None:
            self._dest._activatePlug(self, self._target_plug, active_target_plug_index)
            self._dest._plug_items[self._target_plug][active_target_plug_index].setPos(target_point_position)

        if self._label_text:
            # Calculate the position for the label (average of horizontal and vertical positions)
            source = self._line.p1()
            dest = self._line.p2()
            avg_x = (source.x() + dest.x()) / 2
            avg_y = (source.y() + dest.y()) / 2
            self._label_text.setPos(avg_x, avg_y)

    def _draw_arrow(self, painter: QtGui.QPainter, start: QtCore.QPointF, end: QtCore.QPointF):
        """Draw arrow from start point to end point.

        Args:
            painter (QtGui.QPainter)
            start (QtCore.QPointF): start position
            end (QtCore.QPointF): end position
        """
        def point_in_direction(start: QtCore.QPointF, end: QtCore.QPointF, distance: float) -> QtCore.QPointF:
            direction = QtGui.QVector2D(end - start)
            direction.normalize()
            new_point = start + direction.toPointF() * distance
            return new_point

        brush = self._brush
        painter.setBrush(brush)

        line = QtCore.QLineF(end, start)

        _arrow_head_tilt = 3
        angle = math.atan2(-line.dy(), line.dx())
        arrow_p1 = line.p1() + QtCore.QPointF(
            math.sin(angle + math.pi / _arrow_head_tilt) * self._arrow_size,
            math.cos(angle + math.pi / _arrow_head_tilt) * self._arrow_size,
        )
        arrow_p2 = line.p1() + QtCore.QPointF(
            math.sin(angle + math.pi - math.pi / _arrow_head_tilt) * self._arrow_size,
            math.cos(angle + math.pi - math.pi / _arrow_head_tilt) * self._arrow_size,
        )

        arrow_head = QtGui.QPolygonF()
        arrow_head.clear()
        arrow_head.append(line.p1())
        arrow_head.append(arrow_p1)
        arrow_head.append(point_in_direction(end, start, 10))
        arrow_head.append(arrow_p2)
        painter.drawPolygon(arrow_head)

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionGraphicsItem, widget=None):
        """Override from QtWidgets.QGraphicsItem

        Draw Edge. This method is called from Edge.adjust()

        Args:
            painter (QtGui.QPainter)
            option (QtWidgets.QStyleOptionGraphicsItem)
        """
        painter.setRenderHints(QtGui.QPainter.Antialiasing)
        painter.setPen(self._pen)

        if self._is_cycle:
            self._draw_rounded_arrow(painter, self._cycle_start_position)

        else:
            total_colors = enumerate(self._colors)
            next(total_colors)  # draw first without offset and with current color
            painter.drawLine(self._line)
            for index, color in total_colors:
                shift = int((index+1)/2) * 1.5 * 3
                side = shift if index % 2 == 0 else -shift
                self._pen.setColor(QtGui.QColor(color))
                painter.setPen(self._pen)
                painter.drawLine(_parallel_line(self._line, side, head_offset=11))
            self._pen.setColor(self._color)
            painter.setPen(self._pen)

            self._draw_arrow(painter, self._line.p1(), self._line.p2())

            if self._label_text:
                source_point = self._line.p1()
                target_point = self._line.p2()
                avg_x = (source_point.x() + target_point.x()) / 2
                avg_y = (source_point.y() + target_point.y()) / 2
                self._label_text.setPos(avg_x, avg_y)

    def _draw_rounded_arrow(self, painter: QtGui.QPainter, source_pos: QtCore.QPointF):
        # painter.drawRect(self.boundingRect())  # for debugging purposes
        center_x, center_y = source_pos.toTuple()

        for index, color in enumerate(self._colors):
            self._pen.setColor(QtGui.QColor(color))
            painter.setPen(self._pen)
            arc_offset = index * 1.5
            box_y = center_y + (1.5 * index)
            radius = 20 - arc_offset
            box_size = radius * 2
            start_angle = 135 - (5 * index)
            finish_angle = -270 + arc_offset
            arrow_path = QtGui.QPainterPath()
            arrow_path.arcMoveTo(center_x, box_y, box_size, box_size, start_angle)
            arrow_path.arcTo(center_x, box_y, box_size, box_size, start_angle, finish_angle)
            painter.drawPath(arrow_path)

        self._pen.setColor(self._color)
        painter.setPen(self._pen)

        start = QtCore.QPointF(center_x+7, center_y+6)
        end = QtCore.QPointF(center_x+4, center_y+9)
        self._draw_arrow(painter, start, end)


def _parallel_line(line, distance, head_offset=0):
    direction = line.unitVector()

    # Calculate the perpendicular vector by rotating the direction vector by 90 degrees
    perpendicular = QtCore.QPointF(-direction.dy(), direction.dx())

    # Calculate the offset points for the new line
    offset1 = line.p1() + perpendicular * (distance / 2)
    offset2 = line.p2() + perpendicular * (distance / 2)

    parallel_line = QtCore.QLineF(offset1, offset2)
    if head_offset:
        parallel_line.setLength(parallel_line.length() - head_offset)
    return parallel_line


class GraphView(QtWidgets.QGraphicsView):
    def __init__(self, graph: nx.DiGraph = None, parent=None):
        """GraphView constructor

        This widget can display a directed graph

        Args:
            graph (nx.DiGraph): a networkx directed graph
        """
        super().__init__()
        self._filter_nodes = None
        self._filter_edges = None
        self._graph = graph
        self._scene = QtWidgets.QGraphicsScene()
        self.setScene(self._scene)

        # Used to add space between nodes
        self._graph_scale = 1

        # Map node name to Node object {str=>Node}
        self._nodes_map = {}

        self._load_graph(None)
        #############
        self._zoom = 0
        # ~~~~~~~~~~~~
        self.sticky_nodes = list()
        self._viewing = set()
        self.url_id_prefix = ""

        ################
        self.dragging = False
        self.last_pan_pos = None

    def wheelEvent(self, event):
        modifiers = event.modifiers()

        if modifiers == QtCore.Qt.ControlModifier:
            zoom_factor = 1.2 if event.angleDelta().y() > 0 else 0.8
            self.scale(zoom_factor, zoom_factor)
        elif modifiers == QtCore.Qt.AltModifier:
            self.horizontal_pan(event)
        else:
            # Pan vertically when no modifier key is pressed
            self.vertical_pan(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self.dragging = True
            QtWidgets.QApplication.setOverrideCursor(QtGui.Qt.ClosedHandCursor)
            self.last_pan_pos = event.globalPosition().toPoint()
            event.accept()

        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self.dragging = False
            QtWidgets.QApplication.restoreOverrideCursor()
            event.accept()

        return super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() == QtCore.Qt.MiddleButton:
            # Pan the scene when middle mouse button is held down
            delta = event.globalPosition().toPoint() - self.last_pan_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self.last_pan_pos = event.globalPosition().toPoint()
            return
        return super().mouseMoveEvent(event)

    def horizontal_pan(self, event):
        delta = event.angleDelta().x()
        scroll_bar = self.horizontalScrollBar()
        scroll_bar.setValue(scroll_bar.value() - delta)

    def vertical_pan(self, event):
        delta = event.angleDelta().y()
        scroll_bar = self.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.value() - delta)

    def _graph_url_changed(self, *_, **__):
        sender = self.sender()
        key = next((k for k, v in self._nodes_map.items() if v==sender), None)
        if key is None:
            raise LookupError(f"Could not find sender {sender} in nodes map")

        self.view((key,))

    def set_nx_layout(self, graph):
        if not graph:
            return

        positions = drawing.nx_agraph.graphviz_layout(graph, prog='dot')
        # positions = drawing.nx_agraph.graphviz_layout(graph)
        # SVG and dot seem to have inverted coordinates, let's flip Y
        max_y = max(pos[1] for pos in positions.values())
        adjusted_positions = {node: (x, max_y - y) for node, (x, y) in positions.items()}

        for node, pos in adjusted_positions.items():
            x, y = pos
            x *= self._graph_scale
            y *= self._graph_scale
            item = self._nodes_map[node]
            item.setPos(x, y)

    def view(self, node_indices: tuple):
        self._viewing = frozenset(node_indices)
        graph = self._graph
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

        self._load_graph(subgraph)

    @property
    def graph(self):
        return self._graph

    @property
    def filter_edges(self):
        return self._filter_edges

    @filter_edges.setter
    def filter_edges(self, value):
        if value == self._filter_edges:
            return
        # self._subgraph_dot_path.cache_clear()
        if value:
            predicate = lambda *edge: value(*edge) or bool({edge[0], edge[1]}.intersection(self.sticky_nodes))
        else:
            predicate = None
        self._filter_edges = predicate

    @graph.setter
    def graph(self, graph):
        self._graph = graph
        self._load_graph(graph)

    def _load_graph(self, graph):
        """Load graph into QtWidgets.QGraphicsScene using Node class and Edge class"""
        if not graph:
            return
        print("LOADING GRAPH")
        self.scene().clear()
        self.viewport().update()
        self._nodes_map.clear()
        edge_color = graph.graph.get('edge', {}).get("color", "")

        def _add_node(nx_node):
            node_data = graph.nodes[nx_node]
            item = _Node(
                label=node_data.get('label', str(nx_node)),
                color=graph.graph.get('node', {}).get("color", ""),
                fillcolor=graph.graph.get('node', {}).get("fillcolor", "white"),
                plugs=node_data.get('plugs', {}),
                visible=node_data.get('style', "") != "invis",
                active_plugs=node_data.get('active_plugs', set()),
            )
            item.linkActivated.connect(self._graph_url_changed)
            self.scene().addItem(item)
            for each_plug in chain.from_iterable(item._plug_items.values()):
                self.scene().addItem(each_plug)
            return item

        for nx_node in graph:
            self._nodes_map[nx_node] = _add_node(nx_node)

        # Add edges
        kwargs = dict()
        if len(next(iter(graph.edges), [])) == 3:
            for a, b, port in graph.edges:
                source = self._nodes_map[a]
                dest = self._nodes_map[b]
                is_bidirectional = graph.has_edge(b, a)
                edge_data = graph.edges[(a, b, port)]
                if port is None:
                    raise ValueError(f"{source=}\n{dest=}")
                color = edge_data.get('color', edge_color)
                label = edge_data.get('label', '')
                if source._plugs == {} and dest._plugs == {}:
                    ...
                else:
                    kwargs['target_plug'] = dest._plugs[edge_data['headport']] if edge_data.get('headport') is not None else None
                    kwargs['source_plug'] = source._plugs[edge_data['tailport']] if edge_data.get('tailport') is not None else None
                edge = _Edge(source, dest, color=color, label=label, is_bidirectional=is_bidirectional, **kwargs)
                self.scene().addItem(edge)

        else:
            for a, b in graph.edges:
                source = self._nodes_map[a]
                dest = self._nodes_map[b]
                color = graph.edges[(a, b)].get('color', '')
                label = graph.edges[(a, b)].get('label', '')
                edge = _Edge(source, dest, color=color, label=label)
                self.scene().addItem(edge)
        self.set_nx_layout(graph)


def main():
    from . import description
    old_comp = description.LayerStackComposition()
    # old_comp._graph_precise_source_ports.setChecked(True)
    old_comp.setStage(stage)

    from . import create
    old_tax = create.TaxonomyEditor()
    old_tax.setStage(stage)

    comp_graph = old_comp._graph_view.graph
    main_widget = QtWidgets.QWidget()
    main_layout = QtWidgets.QVBoxLayout()
    comp_stack = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
    comp_stack.addWidget(old_comp)

    conn_stack = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

    tax_stack = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

    con_stage = Usd.Stage.Open(r"R:\al\alab-v2.0.1\entity\book_encyclopedia01\book_encyclopedia01.usda")
    con_prim = con_stage.GetPrimAtPath("/root/MATERIAL/usd_proxy")
    con_prim = con_stage.GetPrimAtPath("/root/MATERIAL/usd_full")
    con_graph = description._graph_from_connections(con_prim)
    con_old = description._ConnectableAPIViewer()
    con_old.setPrim(con_prim)
    conn_stack.addWidget(con_old)
    tax_stack.addWidget(old_tax)
    description._GraphViewer = GraphView
    new_comp = description.LayerStackComposition()
    # new_comp._graph_precise_source_ports.setChecked(True)
    new_comp.setStage(stage)
    new_tax = create.TaxonomyEditor()
    new_tax.setStage(stage)
    con_new = description._ConnectableAPIViewer()
    con_new.setPrim(con_prim)
    conn_stack.addWidget(con_new)
    tax_stack.addWidget(new_tax)
    v_split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
    comp_stack.addWidget(new_comp)
    v_split.addWidget(comp_stack)
    v_split.addWidget(conn_stack)
    v_split.addWidget(tax_stack)
    main_layout.addWidget(v_split)
    main_widget.setLayout(main_layout)
    return main_widget, comp_graph, con_graph


if __name__ == "__main__":
    # stage = Usd.Stage.Open(r"R:\al\ALab\entity\lab_workbench01\lab_workbench01.usda")  # 11 seconds on both
    # stage = Usd.Stage.Open(r"R:\al\ALab\entry.usda")  # 10 minutes???
    from pxr import Usd
    stage = Usd.Stage.Open(r"A:\write\code\git\easy-edgedb\chapter10\test_updates\assets\dracula-3d-abc-Taxonomy-rnd-main-atom-lead-base-whole.1.usda")
    stage = Usd.Stage.Open(r"A:\write\code\git\easy-edgedb\chapter10\test_updates\assets\dracula-3d-abc-entity-rnd-main-atom-lead-base-whole.1.usda")
    # stage = Usd.Stage.Open(r"A:\write\code\git\easy-edgedb\chapter10\assets\dracula-3d-abc-entity-rnd-main-atom-lead-base-whole.1.usda")
    # stage = Usd.Stage.Open(r"C:\Users\Christian\OneDrive\write\proyectos\self\instances\broadcast_nested_instances\City-Entry-Assembly.1.usda")
    # stage = Usd.Stage.Open(r"R:\al\ALab\entity\book_encyclopedia01\book_encyclopedia01.usda")
    # stage = Usd.Stage.Open(r"R:\al\ALab\entity\stoat01\stoat01.usda")
    # prim = stage.GetPrimAtPath("/root/MATERIAL/usd_full")
    import datetime
    import cProfile
    from pathlib import Path
    import sys
    app = QtWidgets.QApplication(sys.argv)
    start = datetime.datetime.now()
    pr = cProfile.Profile()
    pr.enable()
    w, g1, g2 = pr.runcall(main)
    w.show()
    pr.disable()
    pr.dump_stats(str(Path(__file__).parent / "stats_no_init_name_another.log"))
    end = datetime.datetime.now()
    print(f"Total time: {end - start}")

    sys.exit(app.exec_())

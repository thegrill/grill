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
#   - Context menu items
#   - Ability to move further in canvas after Nodes don't exist
#   - Focus with F

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

    def __init__(self, parent=None, label="", color="", fillcolor="", plugs=None, active_plugs: set = frozenset(), visible=True):
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
        round_args = self.boundingRect().adjusted(1, 1, -1, -1), 6, 6
        rect_path.addRoundedRect(*round_args)
        painter.fillPath(rect_path, self._fillcolor)
        painter.drawRoundedRect(*round_args)
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

    def _activatePlug(self, edge, plug_index, side, position):
        if plug_index is None:
            return  # we're at the center, nothing to draw nor activate
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
        self._plug_items[plug_index][side].setPos(position)


class _Edge(QtWidgets.QGraphicsItem):
    def __init__(self, source: _Node, target: _Node, *, source_plug=None, target_plug=None, label="", color="", is_bidirectional=False, parent: QtWidgets.QGraphicsItem = None):
        super().__init__(parent)
        source.add_edge(self)
        target.add_edge(self)
        self._source = source
        self._target = target
        self._source_plug = source_plug
        self._target_plug = target_plug
        self._is_source_plugged = source_plug is not None
        self._is_target_plugged = target_plug is not None
        self._is_cycle = is_cycle = source == target

        self._plug_positions = plug_positions = {}
        for node, plug in (source, source_plug), (target, target_plug):
            bounds = node.boundingRect()
            if plug is None:
                plug_positions[node, plug] = {None: QtCore.QPointF(bounds.right() - 5, bounds.height() / 2 - 20) if is_cycle else bounds.center()}
                continue
            port_size = bounds.height() / len(node._plugs) if node._plugs else 0
            y_pos = plug * port_size + port_size / 2
            plug_positions[node, plug] = {
                0: QtCore.QPointF(0, y_pos),  # left
                1: QtCore.QPointF(bounds.right(), y_pos),  # right
            }

        self._width = 1.5
        self._arrow_size = 15
        self._bidirectional_shift = 20 if is_bidirectional else 0
        self._line = QtCore.QLineF()
        self.setZValue(-1)

        self._spline_path = QtGui.QPainterPath() if (self._is_source_plugged or self._is_target_plugged) else None

        self._colors = colors = color.split(":")
        main_color = QtGui.QColor(colors[0])
        if label:
            self._label_text = QtWidgets.QGraphicsTextItem(label, self)
            self._label_text.setDefaultTextColor(main_color)
            self._label_text.setHtml(f"<b>{label}</b>")
        else:
            self._label_text = None
        self._pen = QtGui.QPen(main_color, self._width, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        self._brush = QtGui.QBrush(main_color)
        if _IS_QT5:
            self._brush.setStyle(QtGui.Qt.SolidPattern)
            self._brush.setColor(main_color)

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

        width, arrow_size = self._width, max(self._arrow_size, 50)
        top_shift, bottom_shift = -width - arrow_size, width + arrow_size
        return QtCore.QRectF(top_left, bottom_right).normalized().adjusted(top_shift, top_shift, bottom_shift, bottom_shift)

    @property
    def _cycle_start_position(self):
        if not self._is_source_plugged:
            return self._source.pos() + self._plug_positions[self._source, self._source_plug][None]

        return self._line.p1() + QtCore.QPointF(-3, -31)

    def adjust(self):
        """Update edge position from source and target node following Node::itemChange."""
        self.prepareGeometryChange()
        source_pos = self._source.pos()
        target_pos = self._target.pos()
        target_bounds = self._target.boundingRect()

        source_on_left = self._is_cycle or (self._source.boundingRect().center().x() + source_pos.x() < target_bounds.center().x() + target_pos.x())

        is_source_plugged = self._is_source_plugged
        is_target_plugged = self._is_target_plugged
        source_side = source_on_left if is_source_plugged else None
        target_side = not source_side if is_target_plugged else None
        source_point = source_pos + self._plug_positions[self._source, self._source_plug][source_side]
        target_point = target_pos + self._plug_positions[self._target, self._target_plug][target_side]

        if not is_target_plugged:
            line = QtCore.QLineF(source_point, target_point)
            if self._bidirectional_shift and source_point != target_point:  # offset in case of bidirectional connections
                line = _parallel_line(line, distance=self._bidirectional_shift, head_offset=0)

            # Check if there is an intersection on the target node to know where to draw the arrow
            if _IS_QT5:
                intersect_method = line.intersect
                bounded_intersection = QtCore.QLineF.IntersectType.BoundedIntersection
            else:
                intersect_method = line.intersects
                bounded_intersection = QtCore.QLineF.IntersectionType.BoundedIntersection

            for each in (
                    QtCore.QLineF((topLeft:=target_bounds.topLeft()) + target_pos, (topRight:=target_bounds.topRight()) + target_pos),  # top
                    QtCore.QLineF(topLeft + target_pos, (bottomLeft:=target_bounds.bottomLeft()) + target_pos),  # left
                    QtCore.QLineF(bottomLeft + target_pos, (bottomRight:=target_bounds.bottomRight()) + target_pos),  # bottom
                    QtCore.QLineF(bottomRight + target_pos, topRight + target_pos),  # right
            ):  # TODO: how to make this more efficient?
                intersection, intersection_point = intersect_method(each)
                if intersection == bounded_intersection:
                    target_point = intersection_point
                    break
            else:
                target_point = line.p2()

        self._line = line = QtCore.QLineF(source_point, target_point)
        if self._spline_path:
            length = line.length()
            falloff = (length / 100) ** 2 if length < 100 else 1
            control_point_shift = (1 if source_on_left else -1) * 75 * falloff

            control_point1 = source_point + QtCore.QPointF(control_point_shift, 0) if is_source_plugged else source_point
            control_point2 = target_point + QtCore.QPointF(-control_point_shift, 0) if is_target_plugged else target_point

            self._spline_path = QtGui.QPainterPath()
            self._spline_path.moveTo(source_point)
            self._spline_path.cubicTo(control_point1, control_point2, target_point)

        self._source._activatePlug(self, self._source_plug, source_side, source_point)
        self._target._activatePlug(self, self._target_plug, target_side, target_point)
        if self._label_text:
            self._label_text.setPos((source_point + target_point) / 2)

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionGraphicsItem, widget=None):
        """Draw Edge following ``Edge.adjust(...)``"""
        painter.setRenderHints(QtGui.QPainter.Antialiasing)
        painter.setPen(self._pen)
        if self._is_cycle:
            self._paint_cyclic_arrow(painter, self._cycle_start_position)
        else:
            total_colors = enumerate(self._colors)
            __, main_color = next(total_colors)  # draw first without offset and with current color

            if self._spline_path:
                arrow_head_end_point = self._spline_path.pointAtPercent(1)
                arrow_head_start_point = self._spline_path.pointAtPercent(.95)
                parallel_paths = []
                for i, color in reversed(list(total_colors)):
                    stroker = QtGui.QPainterPathStroker()
                    stroker.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                    stroker.setWidth(i*5)
                    parallel_paths.append((color, stroker.createStroke(self._spline_path)))

                painter.drawPath(self._spline_path)
                for color, parallel_path in parallel_paths:
                    self._pen.setColor(color)
                    painter.setPen(self._pen)  # Set the color and thickness
                    painter.drawPath(parallel_path)
            else:
                arrow_head_start_point = self._line.p1()
                arrow_head_end_point = self._line.p2()

                painter.drawLine(self._line)
                for index, color in total_colors:
                    self._pen.setColor(color)
                    shift = int((index+1)/2) * 1.5 * 3
                    painter.setPen(self._pen)
                    painter.drawLine(_parallel_line(self._line, shift if index % 2 == 0 else -shift, head_offset=11))

            self._pen.setColor(main_color)
            painter.setPen(self._pen)
            self._draw_arrow_head(painter, arrow_head_start_point, arrow_head_end_point)

    def _paint_cyclic_arrow(self, painter: QtGui.QPainter, source_pos: QtCore.QPointF):
        center_x, center_y = source_pos.toTuple()

        for index, color in enumerate(self._colors):
            self._pen.setColor(color)
            painter.setPen(self._pen)
            arc_offset = index * 1.5
            box_y = center_y + (1.5 * index)
            box_size = (20 - arc_offset) * 2
            start_angle = 135 - (5 * index)
            finish_angle = -270 + arc_offset
            arrow_path = QtGui.QPainterPath()
            arrow_path.arcMoveTo(center_x, box_y, box_size, box_size, start_angle)
            arrow_path.arcTo(center_x, box_y, box_size, box_size, start_angle, finish_angle)
            painter.drawPath(arrow_path)

        self._pen.setColor(self._colors[0])
        painter.setPen(self._pen)
        start = QtCore.QPointF(center_x+7, center_y+6)
        end = QtCore.QPointF(center_x+4, center_y+9)
        self._draw_arrow_head(painter, start, end)

    def _draw_arrow_head(self, painter: QtGui.QPainter, start: QtCore.QPointF, end: QtCore.QPointF):
        """Draw arrow from start point to end point."""

        def point_in_direction(start: QtCore.QPointF, end: QtCore.QPointF, distance: float) -> QtCore.QPointF:
            direction = QtGui.QVector2D(end - start)
            direction.normalize()
            return start + direction.toPointF() * distance

        brush = self._brush
        painter.setBrush(brush)

        line = QtCore.QLineF(end, start)

        head_tilt = math.pi / 3
        arrow_size = self._arrow_size
        angle = math.atan2(-line.dy(), line.dx())
        left_tilt, right_tilt = angle + head_tilt, angle + math.pi - head_tilt
        arrow_p1 = line.p1() + QtCore.QPointF(math.sin(left_tilt) * arrow_size, math.cos(left_tilt) * arrow_size)
        arrow_p2 = line.p1() + QtCore.QPointF(math.sin(right_tilt) * arrow_size, math.cos(right_tilt) * arrow_size)

        arrow_head = QtGui.QPolygonF()
        arrow_head.append(line.p1())
        arrow_head.append(arrow_p1)
        arrow_head.append(point_in_direction(end, start, 10))
        arrow_head.append(arrow_p2)
        painter.drawPolygon(arrow_head)


def _parallel_line(line, distance, head_offset=0):
    direction = line.unitVector()
    # Calculate the perpendicular vector by rotating the direction vector by 90 degrees, then the offset
    perpendicular = QtCore.QPointF(-direction.dy(), direction.dx()) * (distance / 2)
    parallel_line = QtCore.QLineF(line.p1() + perpendicular, line.p2() + perpendicular)
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
        self._filter_edges = None
        self._graph = graph
        self._scene = QtWidgets.QGraphicsScene()
        self.setScene(self._scene)

        self._nodes_map = {}  # {str: Node}

        self._load_graph(None)

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
        max_y = max(pos[1] for pos in positions.values())
        for node, (x, y) in positions.items():
            # SVG and dot seem to have inverted coordinates, let's flip Y
            self._nodes_map[node].setPos(x, max_y - y)

    def view(self, node_indices: tuple):
        self._viewing = frozenset(node_indices)
        graph = self._graph
        successors = chain.from_iterable(graph.successors(index) for index in node_indices)
        predecessors = chain.from_iterable(graph.predecessors(index) for index in node_indices)
        nodes_of_interest = chain(self.sticky_nodes, node_indices, successors, predecessors)
        subgraph = graph.subgraph(nodes_of_interest)

        filters = {}
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
                target = self._nodes_map[b]
                is_bidirectional = graph.has_edge(b, a)
                edge_data = graph.edges[(a, b, port)]
                if port is None:
                    raise ValueError(f"{source=}\n{target=}")
                color = edge_data.get('color', edge_color)
                label = edge_data.get('label', '')
                if source._plugs == {} and target._plugs == {}:
                    ...
                else:
                    kwargs['target_plug'] = target._plugs[edge_data['headport']] if edge_data.get('headport') is not None else None
                    kwargs['source_plug'] = source._plugs[edge_data['tailport']] if edge_data.get('tailport') is not None else None
                edge = _Edge(source, target, color=color, label=label, is_bidirectional=is_bidirectional, **kwargs)
                self.scene().addItem(edge)

        else:
            for a, b in graph.edges:
                source = self._nodes_map[a]
                target = self._nodes_map[b]
                color = graph.edges[(a, b)].get('color', '')
                label = graph.edges[(a, b)].get('label', '')
                edge = _Edge(source, target, color=color, label=label)
                self.scene().addItem(edge)
        self.set_nx_layout(graph)

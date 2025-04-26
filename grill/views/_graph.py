# Learnt from https://doc.qt.io/qtforpython-6/examples/example_external_networkx.html
from __future__ import annotations

import os
import math
import enum
import typing
import logging
import tempfile
import configparser
import networkx as nx
from itertools import chain
from functools import cache
from collections import ChainMap, deque

from networkx import drawing

from . import _core
from ._qt import QtCore, QtGui, QtWidgets, QtSvg

_logger = logging.getLogger(__name__)

_env_config = configparser.ConfigParser()
_env_config.read_dict(
    {
        "graph_view": {
            "via_svg": os.environ.get("GRILL_GRAPH_VIEW_VIA_SVG", 0),
            "svg_as_pixmap": os.environ.get("GRILL_SVG_VIEW_AS_PIXMAP", 0),
        }
    }
)
_GRAPHV_VIEW_VIA_SVG = _env_config.getboolean('graph_view', 'via_svg')
_USE_SVG_VIEWPORT = _env_config.getboolean('graph_view', 'svg_as_pixmap')

_IS_QT5 = QtCore.qVersion().startswith("5")

# TODO:
#   - Should toggling "precise source layer" on LayerStack compostiion view preserve node position for _GraphViewer?
#   - Tooltip on nodes for _GraphViewer
#   - Context menu items
#   - Ability to move further in canvas after Nodes don't exist
#   - when switching a node left to right with precise source layers, the source node ports do not refresh if we're moving the target node
#   - refactor conditionals for _GraphSVGViewer from the description module


_NO_PEN = QtGui.QPen(QtCore.Qt.NoPen)

_DOT_ENVIRONMENT_ERROR = """In order to display content in this graph view,
the 'dot' command must be available on the current environment.

Please make sure graphviz is installed and 'dot' available on the system's PATH environment variable.

For more details on installing graphviz, visit:
 - https://graphviz.org/download/ or 
 - https://grill.readthedocs.io/en/latest/install.html#conda-environment-example
"""


def _adjust_graphviz_html_table_label(label):
    # TODO: these checks below rely on internals from the grill (layer stack composition uses record shapes, connection viewer uses html)
    if label.startswith("<"):
        # Contract: HTML graphviz labels start with a double <<, additionally, ROUNDED is internal to graphviz
        # QGraphicsTextItem seems to have trouble with HTML rounding, so we're controlling this via paint + custom style
        if label.startswith('<<table BORDER="4"'):
            label = label.removeprefix("<").removesuffix(">").replace('table BORDER="4"', 'table')
        else:
            label = label.removeprefix("<").removesuffix(">").replace('table border="1" cellspacing="2" style="ROUNDED"', "table")
    return label


def _get_html_table_from_ports(**ports):
    label = '<table>'
    for index, (name, text) in enumerate(ports.items()):
        bgcolor = "white" if index % 2 == 0 else "#f0f6ff"  # light blue
        text = f'<font color="#242828">{text}</font>'
        label += f"<tr><td port='{name}' bgcolor='{bgcolor}'>{text}</td></tr>"
    label += "</table>"
    return label


def _get_ports_from_label(label) -> dict[str, str]:
    if not label.startswith("{"):  # Only for record labels.
        raise ValueError(f"Label needs to start with '{{' to extract ports from it, for example: '{{<port1>item|<port2>another_item}}'. Got label: '{label}'")
    # see https://graphviz.org/doc/info/shapes.html#record
    fields = label.strip("{}").split("|")
    return dict(field.strip("<>").split(">", 1) for field in fields)


@cache
def _dot_2_svg(sourcepath):
    print(f"Creating svg for: {sourcepath}")
    targetpath = f"{sourcepath}.svg"
    args = [_core._which("dot"), sourcepath, "-Tsvg", "-o", targetpath]
    error, __ = _core._run(args)
    return error, targetpath


class _NodeLOD(enum.Flag):
    LOW = enum.auto()
    MID = enum.auto()
    HIGH = enum.auto()


class DynamicNodeAttributes(ChainMap):
    def __init__(self, high, mid, low):
        super().__init__(high, mid, low)
        self._lods = {
            _NodeLOD.HIGH: high,
            _NodeLOD.MID: mid,
            _NodeLOD.LOW: low,
        }
        self._currentLOD = _NodeLOD.HIGH
        self._data = ChainMap({}, {})
        self.maps = deque(chain(self._lods.values(), [self._data]))


    @property
    def lod(self):
        return self._currentLOD

    @lod.setter
    def lod(self, value: _NodeLOD):
        map = self._lods[value]
        self._currentLOD = value
        self.maps.remove(map)
        self.maps.appendleft(map)


class _Node(QtWidgets.QGraphicsTextItem):

    def __repr__(self):
        return f"{type(self).__name__}({self._name})"

    # Note: keep 'label' as an argument to use as much as possible as-is for clients to provide their own HTML style
    def __init__(self, node_name, node_data, parent=None):
        """
        ports: Tuple of graphviz port names
        """
        super().__init__(parent)
        self._name = node_name
        ports = node_data.get('ports', ())
        if hasattr(node_data, "_lods"):
            # these are all the possible ports, while _ports may have only
            ports = node_data._lods[_NodeLOD.HIGH]['ports']
        else:
            ports = node_data.get('ports', ())
        # nodes_attrs = ChainMap(node_data, graph_node_attrs)
        if (shape := node_data.get('shape')) == 'record':
            try:
                label = node_data['label']
            except KeyError:
                raise ValueError(
                    f"'label' must be supplied when 'record' shape is set for node: '{node_name}' with data: {node_data}")
            if ports:
                raise ValueError(
                    f"record 'shape' and 'ports' are mutually exclusive, pick one for node: '{node_name}' with data: {node_data}")
            try:
                ports = _get_ports_from_label(label)
            except ValueError as exc:
                raise ValueError(
                    f"In order to use the 'record' shape, a record 'label' in the form of: '{{<port1>text1|<port2>text2}}' must be used") from exc
            label = _get_html_table_from_ports(**ports)
        else:
            label = node_data.get('label')
            if shape in {'none', 'plaintext'}:
                if not label:
                    raise ValueError(
                        f"A label must be provided for when using 'none' or 'plaintext' shapes for {node_name}, {node_data=}")
                label = _adjust_graphviz_html_table_label(label)
            elif not label:
                label = str(node_name)

        color=node_data.get("color", "")
        fillcolor=node_data.get("fillcolor", "white")
        visible=node_data.get('style', "") != "invis"

        self._data = node_data
        self._edges = {}  # {Edge: port_identifier}
        self._ports = dict(zip(ports, range(len(ports)))) or {}  # {port_graphviz_identifier: index_for_edge_connectivity}
        self._active_ports_by_side = dict()  # {port_name: {left[int]: {}, right[int]: {}}
        self._port_items = {}  # {port_name: (QEllipse, QEllipse)}
        self._pen = QtGui.QPen(QtGui.QColor(color), 1, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        self._fillcolor = QtGui.QColor(fillcolor)
        self.setHtml("<style>th, td {text-align: center;padding: 3px}</style>" + label)
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
        painter.setPen(QtGui.QPen(QtGui.QColor("#E0E0E0"), 0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        rect_path = QtGui.QPainterPath()
        # round_args = self.boundingRect().adjusted(1, 1, -1, -1), 6, 6
        round_args = self.boundingRect(), 0, 0
        rect_path.addRoundedRect(*round_args)
        # painter.fillPath(rect_path, self._fillcolor)
        painter.fillPath(rect_path, QtGui.QColor("#E0E0E0"))
        painter.drawRoundedRect(*round_args)
        return super().paint(painter, option, widget)

    def add_edge(self, edge: _Edge, port):
        if hasattr(self._data, "_lods"):
            # these are all the possible ports, while _ports may have only
            ports = self._data._lods[_NodeLOD.HIGH]['ports']
        else:
            ports = self._ports

        if port is not None and port not in ports:
            raise KeyError(f"{port=} does not exist on {ports=}")
        self._edges[edge] = port

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            for edge in self._edges:
                edge.adjust()
        return super().itemChange(change, value)

    def _activatePort(self, edge, port, side, position):
        if port is None:
            return  # we're at the center, nothing to draw nor activate

        try:
            ports_by_side = self._active_ports_by_side[port]  # {port_name: {left[int]: {}, right[int]: {}}
        except KeyError:  # first time we're activating a port, so add a visual ellipse for it
            radius = 4

            def _add_port_item(this_side):
                class PortPlugItem(QtWidgets.QGraphicsEllipseItem):
                    def __repr__(this):
                        return f"Item({self}, {port=}, {this_side})"
                item = PortPlugItem(-radius, -radius, 2 * radius, 2 * radius)
                item.setPen(_NO_PEN)
                item.setZValue(self.zValue())
                self.scene().addItem(item)
                return item

            self._port_items[port] = (_add_port_item("left"), _add_port_item("right"))
            self._active_ports_by_side[port] = ports_by_side = {0: dict(), 1: dict()}

        ports_by_side[side][edge] = True
        other_side = bool(not side)
        inactive_ports = ports_by_side[other_side]
        inactive_ports.pop(edge, None)
        port_items = self._port_items[port]  # {index: (QEllipse, QEllipse)}
        if not inactive_ports:
            port_items[other_side].setVisible(False)
        this_item = port_items[side]
        this_item.setVisible(True)
        this_item.setBrush(edge._brush)
        port_items[side].setPos(position)


class _Edge(QtWidgets.QGraphicsItem):
    def __repr__(self):
        return f"{type(self).__name__}(source={self._source}, target={self._target}, source_port={self._source_port}, target_port={self._target_port})"

    def __init__(self, source: _Node, target: _Node, *, source_port: int = None, target_port: int = None, label="", color="", is_bidirectional=False, parent: QtWidgets.QGraphicsItem = None):
        """Source port: index of the source node to connect to"""
        super().__init__(parent)
        source.add_edge(self, source_port)
        target.add_edge(self, target_port)
        self._source = source
        self._target = target
        self._source_port = source_port
        self._target_port = target_port
        self._is_source_port_used = source_port is not None
        self._is_target_port_used = target_port is not None
        self._is_cycle = source == target

        self._port_positions = {}

        for node, port in (source, source_port), (target, target_port):
            self._update_port_position(node, port)

        self._width = 1.5
        self._arrow_size = 15
        self._bidirectional_shift = 20 if is_bidirectional else 0
        self._line = QtCore.QLineF()
        self.setZValue(-1)

        self._spline_path = QtGui.QPainterPath() if (self._is_source_port_used or self._is_target_port_used) else None

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

    def _update_port_position(self, node, port):
        # TODO: this is the main reason of why Node._ports has {port: index}. See if it can be removed
        is_cycle = self._is_cycle
        bounds = node.boundingRect()
        port_positions = self._port_positions
        if port is None:
            port_positions[node, port] = {
                None: QtCore.QPointF(bounds.right() - 5, bounds.height() / 2 - 20) if is_cycle else bounds.center()
            }
            return

        outer_shift = 10  # surrounding rect has ~5 px top and bottom
        max_port_idx = len(node._ports)

        if len(node._ports) == 1:
            port_index = next(iter(node._ports.values()))
        else:
            port_index = node._ports[port]

        port_size = (bounds.height() - outer_shift) / max_port_idx
        y_pos = (port_index * port_size) + (port_size / 2) + (outer_shift / 2)
        port_positions[node, port] = {
            0: QtCore.QPointF(0, y_pos),  # left
            1: QtCore.QPointF(bounds.right(), y_pos),  # right
        }

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
        if not self._is_source_port_used:
            return self._source.pos() + self._port_positions[self._source, self._source_port][None]

        return self._line.p1() + QtCore.QPointF(-3, -31)

    def adjust(self):
        """Update edge position from source and target node following Node::itemChange."""
        self.prepareGeometryChange()
        source_pos = self._source.pos()
        target_pos = self._target.pos()
        target_bounds = self._target.boundingRect()

        source_on_left = self._is_cycle or (self._source.boundingRect().center().x() + source_pos.x() < target_bounds.center().x() + target_pos.x())

        is_source_port_used = self._is_source_port_used
        is_target_port_used = self._is_target_port_used
        source_side = source_on_left if is_source_port_used else None
        target_side = not source_side if is_target_port_used else None
        source_point = source_pos + self._port_positions[self._source, self._source_port][source_side]
        target_point = target_pos + self._port_positions[self._target, self._target_port][target_side]

        if not is_target_port_used:
            line = QtCore.QLineF(source_point, target_point)
            if not self._spline_path and self._bidirectional_shift and source_point != target_point:
                # offset in case of bidirectional connections when we are not using splines (as lines would overlap)
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

            control_point1 = source_point + QtCore.QPointF(control_point_shift, 0) if is_source_port_used else source_point
            control_point2 = target_point + QtCore.QPointF(-control_point_shift, 0) if is_target_port_used else target_point

            self._spline_path = QtGui.QPainterPath()
            self._spline_path.moveTo(source_point)
            self._spline_path.cubicTo(control_point1, control_point2, target_point)

        self._source._activatePort(self, self._source_port, source_side, source_point)
        self._target._activatePort(self, self._target_port, target_side, target_point)
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
            else:  # painting as a straight line
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


_EVENT_POSITION_FUNC = QtGui.QMouseEvent.globalPos if _IS_QT5 else lambda event: event.globalPosition().toPoint()


class _GraphicsViewport(QtWidgets.QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dragging = False
        self._last_pan_pos = QtCore.QPoint()
        self._rubber_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self._start_rubber_band_pos = QtCore.QPoint()

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
            self._dragging = True
            QtWidgets.QApplication.setOverrideCursor(QtGui.Qt.ClosedHandCursor)
            self._last_pan_pos = _EVENT_POSITION_FUNC(event)
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton and event.modifiers() == QtCore.Qt.NoModifier:
            self._start_rubber_band_pos = event.pos()
            self._rubber_band.setGeometry(QtCore.QRect(self._start_rubber_band_pos, QtCore.QSize()))
            self._rubber_band.show()

        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._dragging = False
            QtWidgets.QApplication.restoreOverrideCursor()
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton and event.modifiers() == QtCore.Qt.NoModifier:
            self._rubber_band.hide()
            print("\nSELECTED:")
            for item in self._get_items_in_rubber_band():
                item.setSelected(True)
                print(item)
            if clicked_item:=self.itemAt(event.pos()):
                clicked_item.setSelected(True)
                print(clicked_item)

        return super().mouseReleaseEvent(event)

    def _get_items_in_rubber_band(self):
        rubber_band_rect = self._rubber_band.geometry()
        scene_rect = self.mapToScene(rubber_band_rect).boundingRect()
        return self.scene().items(scene_rect)

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() == QtCore.Qt.MiddleButton:
            # Pan the scene when middle mouse button is held down
            delta = _EVENT_POSITION_FUNC(event) - self._last_pan_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._last_pan_pos = _EVENT_POSITION_FUNC(event)
            return
        elif event.buttons() == QtCore.Qt.LeftButton and event.modifiers() == QtCore.Qt.NoModifier:
            self._rubber_band.setGeometry(QtCore.QRect(self._start_rubber_band_pos, event.pos()).normalized())
        return super().mouseMoveEvent(event)

    def horizontal_pan(self, event):
        delta = event.angleDelta().x()
        scroll_bar = self.horizontalScrollBar()
        scroll_bar.setValue(scroll_bar.value() - delta)

    def vertical_pan(self, event):
        delta = event.angleDelta().y()
        scroll_bar = self.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.value() - delta)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_F:
            self._focus_view_requested()
        return super().keyPressEvent(event)

    def _focus_view_requested(self):
        if selected_items := self.scene().selectedItems():
            bounding_rect = QtCore.QRectF()
            for item in selected_items:
                bounding_rect |= item.sceneBoundingRect()
        else:  # if no items have been selected, focus on all items
            bounding_rect = self.scene().itemsBoundingRect()

        self.fitInView(bounding_rect, QtCore.Qt.KeepAspectRatio)


class GraphView(_GraphicsViewport):
    def __init__(self, graph: nx.DiGraph = None, parent=None):
        super().__init__(parent=parent)
        self._filter_edges = None
        self._graph = graph
        self._scene = QtWidgets.QGraphicsScene()
        self.setScene(self._scene)

        self._nodes_map = {}  # {str: Node}

        self._load_graph(None)

        self.sticky_nodes = list()
        self._viewing = set()
        self.url_id_prefix = ""

    def _graph_url_changed(self, *_, **__):
        sender = self.sender()
        key = next((k for k, v in self._nodes_map.items() if v==sender), None)
        if key is None:
            raise LookupError(f"Could not find sender {sender} in nodes map")

        self.view((key,))

    def setLOD(self, node_indices, lod: _NodeLOD):
        print(f"Setting LOD")
        print(f"{locals()}")
        nodes_map = self._nodes_map
        graph = self._graph
        for node_id in node_indices:
            qnode = nodes_map[node_id]
            # keep track of current ports in qnode
            # edge ports are the actual KEYS
            current_ports = qnode._ports

            node_data = graph.nodes[node_id]
            assert node_data.lod
            node_data.lod = lod

            new_ports = node_data['ports']
            if len(new_ports) == 1:
                qnode._ports = new_ports_dict = dict.fromkeys(new_ports, 0)
            else:
                qnode._ports = new_ports_dict = dict(zip(new_ports, range(len(new_ports))))

            label = node_data['label']
            label = _adjust_graphviz_html_table_label(label)
            qnode.setHtml("<style>th, td {text-align: center;padding: 3px}</style>" + label)

            old_active_ports_by_side = dict(qnode._active_ports_by_side)
            old_port_items = dict(qnode._port_items)

            ports_to_move = dict()  # old: new

            qt_edges = qnode._edges

            for edge in qnode._edges:
                for neighbor, port in (
                        (edge._source, edge._source_port),
                        (edge._target, edge._target_port),
                ):
                    if qnode is neighbor:
                        ports_to_move.setdefault(edge, []).append(port)

            for edge, ports in ports_to_move.items():
                for each_port in ports:
                    edge._update_port_position(qnode, each_port)

            for edge in qnode._edges:
                edge.adjust()

    def view(self, node_indices: tuple):
        self._viewing = frozenset(node_indices)
        graph = self._graph
        if not graph:
            return
        successors = chain.from_iterable(graph.successors(index) for index in node_indices)
        predecessors = chain.from_iterable(graph.predecessors(index) for index in node_indices)
        nodes_of_interest = chain(self.sticky_nodes, node_indices, successors, predecessors)
        subgraph = graph.subgraph(nodes_of_interest)

        filters = {}
        if self.filter_edges:
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
        if not graph:
            return
        self.scene().clear()
        self.viewport().update()

        _default_text_interaction = QtCore.Qt.LinksAccessibleByMouse if _IS_QT5 else QtCore.Qt.TextBrowserInteraction

        if not _core._which("dot"):  # dot has not been installed
            print(_DOT_ENVIRONMENT_ERROR)
            text_item = QtWidgets.QGraphicsTextItem()
            text_item.setPlainText(_DOT_ENVIRONMENT_ERROR)
            text_item.setTextInteractionFlags(_default_text_interaction)
            self.scene().addItem(text_item)
            return

        try:  # exit early if pydot is not installed, needed for positions
            positions = drawing.nx_pydot.graphviz_layout(graph, prog='dot')
        except ImportError as exc:
            message = f"{exc}\n\n{_DOT_ENVIRONMENT_ERROR}"
            print(message)
            text_item = QtWidgets.QGraphicsTextItem()
            text_item.setPlainText(message)
            text_item.setTextInteractionFlags(_default_text_interaction)
            self.scene().addItem(text_item)
            return

        print("LOADING GRAPH")
        self._nodes_map.clear()
        edge_color = graph.graph.get('edge', {}).get("color", "")
        graph_node_attrs = graph.graph.get('node', {})

        def _add_node(nx_node):
            node_data = graph.nodes[nx_node]
            if isinstance(node_data, DynamicNodeAttributes):
                node_data._data.maps.append(graph_node_attrs)
                nodes_attrs = node_data
            else:
                nodes_attrs = ChainMap(node_data, graph_node_attrs)
            item = _Node(node_name=nx_node, node_data=nodes_attrs)
            item.linkActivated.connect(self._graph_url_changed)
            self.scene().addItem(item)
            return item

        max_y = max(pos[1] for pos in positions.values())
        for nx_node in graph:
            self._nodes_map[nx_node] = node = _add_node(nx_node)
            node.setZValue(len(self._nodes_map))
            print(f"{node.zValue()=}")
            x_pos, y_pos = positions[nx_node]
            # SVG and dot have inverted coordinates, let's flip Y
            y_pos = max_y - y_pos
            bounds = node.boundingRect()
            # x, y refer to the node's center. Calculate the node position now (top left corner is 0,0)
            node.setPos(x_pos - bounds.width() / 2, y_pos - bounds.height() / 2)

        if isinstance(graph, nx.MultiDiGraph):
            edges = graph.edges
            edge_data_getter = lambda source, target, port: graph.edges[source, target, port]
        else:
            edges = ((source, target, None) for source, target in graph.edges)
            edge_data_getter = lambda source, target, port: graph.edges[source, target]

        for source_id, target_id, port in edges:
            source = self._nodes_map[source_id]
            target = self._nodes_map[target_id]
            is_bidirectional = graph.has_edge(target_id, source_id)
            edge_data = edge_data_getter(source_id, target_id, port)
            color = edge_data.get('color', edge_color)
            label = edge_data.get('label', '')
            kwargs = dict()
            if source._ports or target._ports:
                if (headport_key:=edge_data.get('headport')) is not None:
                    # TODO: this is for asset structure tables with 2 columns. Assess on how to handle this better
                    if isinstance(headport_key, str) and headport_key.startswith("C0R"):
                        headport_key = int(headport_key.removeprefix("C0R"))
                    kwargs['target_port'] = headport_key
                if (tailport_key := edge_data.get('tailport')) is not None:
                    if isinstance(tailport_key, str) and tailport_key.startswith("C1R"):
                        tailport_key = int(tailport_key.removeprefix("C1R"))
                    kwargs['source_port'] = tailport_key

            edge = _Edge(source, target, color=color, label=label, is_bidirectional=is_bidirectional, **kwargs)
            self.scene().addItem(edge)


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
        if not _core._which("dot"):
            self.signals.error.emit(_DOT_ENVIRONMENT_ERROR)
            return
        error, svg_fp = _dot_2_svg(self.source_fp)
        self.signals.error.emit(error) if error else self.signals.result.emit(svg_fp)


class _SvgPixmapViewport(_GraphicsViewport):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        scene = QtWidgets.QGraphicsScene(self)
        self.setScene(scene)

    def load(self, filepath):
        filepath = filepath.toLocalFile() if isinstance(filepath, QtCore.QUrl) else filepath
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


class _DotViewer(QtWidgets.QFrame):
    _svg_viewport_placeholder_signal = QtCore.Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QtWidgets.QVBoxLayout()
        # After some experiments, QWebEngineView brings nicer UX and speed than QGraphicsSvgItem and QSvgWidget
        if not _USE_SVG_VIEWPORT:
            if QtWidgets.__package__ == "PySide6":
                # PySide-6.6.0 and 6.6.1 freeze when QtWebEngineWidgets is imported in Python-3.12 so inlining here until fixed
                # Newest working combination for me in Windows is 3.11 + PySide-6.5.3 as of Feb 3rd 2024
                from PySide6 import QtWebEngineWidgets
            else:
                from PySide2 import QtWebEngineWidgets
            self._graph_view = QtWebEngineWidgets.QWebEngineView(parent=self)
            self.urlChanged = self._graph_view.urlChanged
        else:
            self.urlChanged = self._svg_viewport_placeholder_signal
            self._graph_view = _SvgPixmapViewport(parent=self)

        self._error_view = QtWidgets.QTextBrowser(parent=self)
        layout.addWidget(self._graph_view)
        layout.addWidget(self._error_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self._error_view.setVisible(False)
        self._error_view.setLineWrapMode(QtWidgets.QTextBrowser.NoWrap)
        self.setLayout(layout)
        self._dot2svg = None
        self._threadpool = QtCore.QThreadPool()
        if not _USE_SVG_VIEWPORT:
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
        if not _USE_SVG_VIEWPORT:
            filepath = QtCore.QUrl.fromLocalFile(filepath)
        self._graph_view.load(filepath)


class _GraphSVGViewer(_DotViewer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.urlChanged.connect(self._graph_url_changed)
        self.sticky_nodes = list()
        self._graph = None
        self._viewing = frozenset()
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
        if self.filter_edges:
            print(f"{self.filter_edges=}")
            filters['filter_edge'] = self.filter_edges
        if filters:
            subgraph = nx.subgraph_view(subgraph, **filters)

        fd, fp = tempfile.mkstemp()
        try:
            with open(fp, "w", encoding="utf-8") as fobj:
                nx.nx_pydot.write_dot(subgraph, fobj)
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



####
import html
_TOTAL_SPAN = object()
_BORDER_COLOR = "#E0E0E0"
_BG_SPACE_COLOR = "#FAFAFA"
_BG_CELL_COLOR = "#FFFFFF"

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _TableItem:
    lod: _NodeLOD.HIGH
    padding: int
    port_index: int
    key: str
    value: str
    display_attributes: dict


def _to_table(items: list[_TableItem]):
    span = max(x.padding for x in items) + 2
    width = 50
    # for index, (LOD, padding, internal_index, key, value, attrs) in enumerate(items):
    for index, item in enumerate(items):
        LOD = item.lod
        padding = item.padding
        internal_index = item.port_index
        key = item.key
        value = item.value
        attrs = item.display_attributes
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
###

if _GRAPHV_VIEW_VIA_SVG:
    _GraphViewer = _GraphSVGViewer
else:
    _GraphViewer = GraphView

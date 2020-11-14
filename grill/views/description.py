"""Views related to USD scene description"""

import shutil
import tempfile
import subprocess
from functools import lru_cache

from pxr import Usd
from PySide2 import QtWidgets, QtGui, QtCore


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


@lru_cache(maxsize=None)
def _dot_exe():
    return shutil.which("dot")


class _Dot2SvgSignals(QtCore.QObject):
    error = QtCore.Signal(str)
    result = QtCore.Signal(str)


class _Dot2Svg(QtCore.QRunnable):
    def __init__(self, source_fp, target_fp):
        super().__init__()
        self.signals = _Dot2SvgSignals()
        self.source_fp = source_fp
        self.target_fp = target_fp

    @QtCore.Slot()
    def run(self):
        dot = _dot_exe()
        if not dot:
            self.signals.error.emit(
                "In order to display composition arcs in a graph,\n"
                "the 'dot' command must be available on the current environment.\n\n"
                "Please make sure graphviz is installed and 'dot' available \n"
                "on the system's PATH environment variable."
            )
        else:
            dotargs = [dot, self.source_fp, "-Tsvg", "-o", self.target_fp]
            result = subprocess.run(dotargs, capture_output=True)
            if result.returncode:  # something went wrong
                self.signals.error.emit(result.stderr.decode())
            else:
                self.signals.result.emit(self.target_fp)


class PrimComposition(QtWidgets.QDialog):
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
        tree.setColumnCount(len(_COLUMNS))
        tree.setHeaderLabels([k for k in _COLUMNS])
        tree.setAlternatingRowColors(True)
        self.index_graph = QtWidgets.QLabel()
        self._threadpool = QtCore.QThreadPool()
        self._dot2svg = None
        index_graph_scroll = QtWidgets.QScrollArea()
        index_graph_scroll.setWidget(self.index_graph)
        vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        vertical.addWidget(tree)
        vertical.addWidget(index_graph_scroll)
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
        self.index_graph.clear()

    def setPrim(self, prim):
        prim_index = prim.GetPrimIndex()
        self.index_box.setText(prim_index.DumpToString())
        tree = self.composition_tree
        tree.clear()
        query = Usd.PrimCompositionQuery(prim)
        tree_items = dict()  # Sdf.Layer: QTreeWidgetItem
        for arc in query.GetCompositionArcs():
            strings = [str(getter(arc)) for getter in _COLUMNS.values()]
            intro_layer = arc.GetIntroducingLayer()
            if intro_layer and intro_layer in tree_items:
                parent = tree_items[intro_layer]
            else:
                parent = tree
            target_layer = arc.GetTargetNode().layerStack.identifier.rootLayer
            tree_items[target_layer] = QtWidgets.QTreeWidgetItem(parent, strings)

        tree.expandAll()
        self.index_graph.setAutoFillBackground(False)
        fd, fp = tempfile.mkstemp()
        prim_index.DumpToDotGraph(fp)
        svg = f"{fp}.svg"
        if self._dot2svg:  # forget about previous, unfinished runners
            self._dot2svg.signals.error.disconnect()
            self._dot2svg.signals.result.disconnect()
        self._dot2svg = dot2svg = _Dot2Svg(fp, svg)
        dot2svg.signals.error.connect(self._on_dot_error)
        dot2svg.signals.result.connect(self._on_dot_result)
        self._threadpool.start(dot2svg)

    def _on_dot_error(self, message):
        self.index_graph.setText(message)
        self.index_graph.resize(self.index_graph.minimumSizeHint())

    def _on_dot_result(self, filepath):
        index_graph = QtGui.QPixmap(filepath)
        self.index_graph.setPixmap(index_graph)
        self.index_graph.resize(index_graph.size())


if __name__ == "__main__":
    import sys
    stage = Usd.Stage.Open(r"B:\read\cg\downloads\Kitchen_set\Kitchen_set\Kitchen_set.usd")
    app = QtWidgets.QApplication(sys.argv)
    description = PrimComposition()
    prim = stage.GetPrimAtPath(r"/Kitchen_set/Props_grp/DiningTable_grp/TableTop_grp/CerealBowl_grp/BowlD_1")
    description.setPrim(prim.GetChildren()[0])
    description.show()
    sys.exit(app.exec_())

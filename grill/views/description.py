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
def _dot_available():
    return shutil.which("dot")


class PrimDescription(QtWidgets.QDialog):
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
            parent = tree_items[intro_layer] if intro_layer else tree
            target_layer = arc.GetTargetNode().layerStack.identifier.rootLayer
            tree_items[target_layer] = QtWidgets.QTreeWidgetItem(parent, strings)

        if not _dot_available():
            self.index_graph.setText(
                "In order to display composition arcs in a graph,\n"
                "'dot' must be available on the current environment."
            )
            self.index_graph.resize(self.index_graph.minimumSizeHint())
            return
        # move this to a thread next.
        fd, fp = tempfile.mkstemp()
        prim_index.DumpToDotGraph(fp)
        svg = f"{fp}.svg"
        dotargs = ["dot", fp, "-Tsvg", "-o", svg]
        result = subprocess.run(dotargs, capture_output=True, shell=True)
        if result.returncode:  # something went wrong
            self.index_graph.setText(result.stderr.decode())
            self.index_graph.resize(self.index_graph.minimumSizeHint())
        else:
            index_graph = QtGui.QPixmap(svg)
            self.index_graph.setPixmap(index_graph)
            self.index_graph.resize(index_graph.size())


if __name__ == "__main__":
    import sys
    stage = Usd.Stage.Open(r"B:\read\cg\downloads\Kitchen_set\Kitchen_set\Kitchen_set.usd")
    app = QtWidgets.QApplication(sys.argv)
    description = PrimDescription()
    prim = stage.GetPrimAtPath(r"/Kitchen_set/Props_grp/DiningTable_grp/TableTop_grp/CerealBowl_grp/BowlD_1")
    description.setPrim(prim.GetChildren()[0])
    description.show()
    sys.exit(app.exec_())

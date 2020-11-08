"""Views related to USD scene description"""

import os
import tempfile
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
        tree.setHeaderLabels(_COLUMNS)
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

        fd, fp = tempfile.mkstemp()
        prim_index.DumpToDotGraph(fp)
        svg = f"{fp}.svg"
        # move this to a thread next
        os.system(f"dot {fp} -Tsvg -o {svg}")
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

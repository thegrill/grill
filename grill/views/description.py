"""Views related to USD scene description"""
import os
import tempfile
from pxr import Usd
from PySide2 import QtWidgets, QtCore, QtGui

composition_query_headers = ("Arc Type", "Introducing Layer")


class PrimDescription(QtWidgets.QDialog):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.index_box = QtWidgets.QTextBrowser()
        self.index_box.setLineWrapMode(self.index_box.NoWrap)
        self.query_table = query_table = QtWidgets.QTableWidget(len(composition_query_headers), 2)
        horizontal = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        horizontal.addWidget(query_table)
        horizontal.addWidget(self.index_box)
        vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        index_graph_scroll = QtWidgets.QScrollArea()
        self.index_graph = QtWidgets.QLabel("Graph Index")
        index_graph_scroll.setWidget(self.index_graph)
        vertical.addWidget(horizontal)
        vertical.addWidget(index_graph_scroll)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(vertical)
        self.setLayout(layout)

    def setPrim(self, prim):
        query = Usd.PrimCompositionQuery(prim)
        prim_index = prim.GetPrimIndex()
        self.index_box.setText(prim_index.DumpToString())
        query_table = self.query_table
        query_table.clear()
        query_table.setHorizontalHeaderLabels(composition_query_headers)
        arcs = list(enumerate(query.GetCompositionArcs()))
        query_table.setRowCount(len(arcs))
        for row, arc in arcs:
            query_table.setItem(row, 0, QtWidgets.QTableWidgetItem(arc.GetArcType().name))
            query_table.setItem(row, 1, QtWidgets.QTableWidgetItem(arc.GetIntroducingLayer().identifier if arc.GetIntroducingLayer() else ""))

        fd, fp = tempfile.mkstemp()
        prim_index.DumpToDotGraph(fp)
        svg = f"{fp}.svg"
        # move this to a thread next
        os.system(f"dot {fp} -Tsvg -o {svg}")
        index_graph = QtGui.QPixmap(svg)
        self.index_graph.setPixmap(index_graph)
        self.index_graph.resize(index_graph.size())


if __name__ == "__main__":
    # stage = Usd.Stage.CreateInMemory()
    # sphere = UsdGeom.Sphere.Define(stage, "/hi/sphere")
    stage = Usd.Stage.Open(r"B:\read\cg\downloads\Kitchen_set\Kitchen_set\Kitchen_set.usd")
    import sys

    app = QtWidgets.QApplication(sys.argv)
    description = PrimDescription()
    prim = stage.GetPrimAtPath(r"/Kitchen_set/Props_grp/DiningTable_grp/TableTop_grp/CerealBowl_grp/BowlD_1")
    description.setPrim(prim.GetChildren()[0])
    # description.setPrim(stage.GetPrimAtPath(r"/Kitchen_set/Props_grp/DiningTable_grp/TableTop_grp/CerealBowl_grp"))
    description.show()
    sys.exit(app.exec_())

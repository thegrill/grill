import tempfile
from pathlib import Path
from itertools import chain
from functools import partial, lru_cache

import networkx
from pxr import Usd
from grill import write
from PySide2 import QtWidgets, QtCore, QtGui
from networkx.drawing import nx_pydot

from . import sheets as _sheets, description as _description


class _CreatePrims(QtWidgets.QDialog):
    def __init__(self, columns, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form_l = QtWidgets.QFormLayout()
        layout = QtWidgets.QVBoxLayout()
        form = QtWidgets.QFrame()
        form.setLayout(form_l)
        form_l.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(form)
        self._amount = QtWidgets.QSpinBox()
        self._display_le = QtWidgets.QLineEdit()
        form_l.addRow('📚 Amount:', self._amount)
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        self.sheet = sheet = _sheets._Spreadsheet(columns, _sheets._ColumnOptions.NONE)
        sheet.model.setHorizontalHeaderLabels([''] * len(columns))
        self._amount.valueChanged.connect(sheet.model.setRowCount)
        sheet.layout().setContentsMargins(0, 0, 0, 0)

        self._amount.setValue(1)
        self._amount.setMinimum(1)
        self._amount.setMaximum(500)
        self._splitter = splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setSizePolicy(QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding))
        splitter.addWidget(sheet)
        layout.addWidget(splitter)
        layout.addWidget(button_box)
        self.setLayout(layout)
        size = sheet.table.viewportSizeHint()
        size.setWidth(size.width() + 65)  # sensible size at init time
        size.setHeight(self.sizeHint().height())
        self.resize(size)

    @staticmethod
    def _setRepositoryPath(parent=None, caption="Select a repository path"):
        dirpath = QtWidgets.QFileDialog.getExistingDirectory(parent=parent, caption=caption)
        if dirpath:
            token = write.repo.set(Path(dirpath))
            print(f"Repository path set to: {dirpath}, token: {token}")
        return dirpath


class CreateAssets(_CreatePrims):
    def __init__(self, *args, **kwargs):
        self._taxon_options = []
        def _taxon_combobox(parent, option, index):
            combobox = QtWidgets.QComboBox(parent=parent)
            combobox.addItems(sorted(self._taxon_options))
            return combobox
        identity = lambda x: x
        _columns = (
            _sheets._Column("🧬 Taxon", identity, editor=_taxon_combobox),
            _sheets._Column("🔖 Name", identity),
            _sheets._Column("🏷 Label", identity),
            _sheets._Column("📜 Description", identity),
        )
        super().__init__(_columns, *args, **kwargs)
        self.accepted.connect(self._create)
        self.setWindowTitle("Create Assets")

    @_sheets.wait()
    def _create(self):
        if not write.repo.get(None):
            if not self._setRepositoryPath(self, "Select a repository path to create assets on"):
                msg = "A repository path must be selected in order to create assets."
                QtWidgets.QMessageBox.warning(self, "Repository path not set", msg)
                return
        # TODO: check for "write._TAXONOMY_ROOT_PATH" existence and handle missing
        root = self._stage.GetPrimAtPath(write._TAXONOMY_ROOT_PATH)
        model = self.sheet.table.model()
        for row in range(model.rowCount()):
            taxon_name = model.data(model.index(row, 0))
            taxon = root.GetPrimAtPath(taxon_name)
            asset_name = model.data(model.index(row, 1))
            if not asset_name:
                # TODO: validate and raise error dialog to user. For now we ignore.
                print(f"An asset name is required! Missing on row: {row}")
                continue
            label = model.data(model.index(row, 2))
            write.create(taxon, asset_name, label)

    def setStage(self, stage):
        self._stage = stage
        root = stage.GetPrimAtPath(write._TAXONOMY_ROOT_PATH)
        self._taxon_options = [child.GetName() for child in root.GetFilteredChildren(Usd.PrimIsAbstract)] if root else []

class TaxonomyEditor(_CreatePrims):

    def __init__(self, *args, **kwargs):
        # 1. Read only list of existing taxonomy
        # 2. Place to create new taxon groups
        #    - name | references | id_fields
        self._taxon_options = []

        class ReferenceSelection(QtWidgets.QDialog):
            def __init__(self, parent=None):
                super().__init__(parent=parent)
                layout = QtWidgets.QVBoxLayout()
                self._options = options = QtWidgets.QListWidget()
                options.setSelectionMode(options.SelectionMode.ExtendedSelection)

                def list_context_menu(__):
                    menu = self._create_context_menu()
                    menu.exec_(QtGui.QCursor.pos())

                options.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
                options.customContextMenuRequested.connect(list_context_menu)
                layout.addWidget(options)
                button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
                button_box.accepted.connect(self.accept)
                button_box.rejected.connect(self.reject)
                layout.addWidget(button_box)
                self.setLayout(layout)
                self.setWindowTitle("Extend From...")

            def _create_context_menu(self):
                def set_check_status(status):
                    for each in self._options.selectedItems():
                        each.setCheckState(status)

                menu = QtWidgets.QMenu(self._options)
                for title, status in (
                        ("Check Selected", QtCore.Qt.Checked),
                        ("Uncheck Selected", QtCore.Qt.Unchecked),
                ):
                    action = menu.addAction(title)
                    action.triggered.connect(partial(set_check_status, status))
                return menu

            def showEvent(self, *args, **kwargs):
                result = super().showEvent(*args, **kwargs)
                # hack? wihout this, we appear off screen (or on top of it)
                self.adjustPosition(self.parent())
                return result

            def property(self, name):  # override ourselves yeahhh
                if name == 'value':
                    return self._value()
                return super().property(name)

            def _value(self):
                return [
                    each.text()
                    for each in self._options.findItems("*", QtCore.Qt.MatchWildcard)
                    if each.checkState() == QtCore.Qt.Checked
                ]

        def _reference_selector(parent, option, index):
            inter = ReferenceSelection(parent=parent)
            inter.setModal(True)
            idata = index.data()
            checked_items = set()
            if idata:
                checked_items.update(idata.split("\n"))

            for taxon in self._taxon_options:
                item = QtWidgets.QListWidgetItem(inter._options)
                item.setText(taxon)
                item.setCheckState(QtCore.Qt.Checked if taxon in checked_items else QtCore.Qt.Unchecked)

            return inter

        def _reference_setter(editor: ReferenceSelection, model: _sheets._ProxyModel, index:QtCore.QModelIndex):
            return model.setData(index, "\n".join(editor._value()))

        identity = lambda x: x
        _columns = (
            _sheets._Column("🧬 New Name", identity),
            _sheets._Column(
                "🔗 References",
                identity,
                editor=_reference_selector,
                model_setter=_reference_setter
            ),
            _sheets._Column("🕵 ID Fields", identity),
        )
        super().__init__(_columns, *args, **kwargs)
        self.setWindowTitle("Taxonomy Editor")

        existing_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self._existing = existing = _sheets._Spreadsheet(
            # Existing label just a bit to the right (Above the search bar)
            (_sheets._Column("        🧬 Existing", identity),),
            _sheets._ColumnOptions.SEARCH
        )
        existing.layout().setContentsMargins(0, 0, 0, 0)
        existing_splitter.addWidget(existing)

        self._dot_view = _description._DotViewer(parent=self)
        self._dot_view.urlChanged.connect(self._graph_url_changed)

        existing_splitter.addWidget(self._dot_view)

        selectionModel = existing.table.selectionModel()
        selectionModel.selectionChanged.connect(self._selectionChanged)

        self._splitter.insertWidget(0, existing_splitter)
        self._splitter.setStretchFactor(0, 2)
        self._splitter.setStretchFactor(1, 3)

        self.accepted.connect(self._create)

    def _selectionChanged(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection):
        node_ids = [index.data() for index in self._existing.table.selectedIndexes()]
        # node_indices = [self._node_index_by_id[i] for i in node_ids]
        self._update_node_graph_view(node_ids)

    def _graph_url_changed(self, url: QtCore.QUrl):
        node_uri = url.toString()
        node_uri_stem = node_uri.split("/")[-1]
        if node_uri_stem.startswith("node_id_"):
            node_index = node_uri_stem.split("node_id_")[-1]
            self._update_node_graph_view([node_index])

    def _update_node_graph_view(self, node_indices: list):
        dot_path = self._subgraph_dot_path(tuple(node_indices))
        self._dot_view.setDotPath(dot_path)

    @lru_cache(maxsize=None)
    def _subgraph_dot_path(self, node_indices: tuple):
        print(f"Getting subgraph for: {node_indices}")
        successors = chain.from_iterable(
            self._graph.successors(index) for index in node_indices)
        predecessors = chain.from_iterable(
            self._graph.predecessors(index) for index in node_indices)
        nodes_of_interest = list(range(10))  # needs to be label nodes
        nodes_of_interest.extend(chain(node_indices, successors, predecessors))
        subgraph = self._graph.subgraph(nodes_of_interest)

        fd, fp = tempfile.mkstemp()
        nx_pydot.write_dot(subgraph, fp)
        return fp

    def setStage(self, stage):
        self._stage = stage
        root = stage.GetPrimAtPath(write._TAXONOMY_ROOT_PATH)
        self._taxon_options = [child.GetName() for child in root.GetFilteredChildren(Usd.PrimIsAbstract)] if root else []
        existing_model = self._existing.model
        existing_model.setHorizontalHeaderLabels([''])
        existing_model.setRowCount(len(self._taxon_options))
        existing_model.blockSignals(True)
        for row_index, taxon in enumerate(self._taxon_options):
            item = QtGui.QStandardItem()
            item.setData(taxon, QtCore.Qt.DisplayRole)
            item.setData(taxon, QtCore.Qt.UserRole)
            existing_model.setItem(row_index, 0, item)
        existing_model.blockSignals(False)
        self._existing._setColumnLocked(0, True)

        self._graph = graph = networkx.DiGraph(tooltip="My label")
        graph.graph['graph'] = {'rankdir': 'LR'}
        for taxon in stage.GetPrimAtPath(write._TAXONOMY_ROOT_PATH).GetFilteredChildren(Usd.PrimIsAbstract):
            taxon_name = taxon.GetName()
            taxa = taxon.GetCustomDataByKey(write._PRIM_GRILL_KEY)['taxa']
            for node_name in taxa:
                if not graph.has_node(node_name):
                    graph.add_node(node_name, style='rounded', shape='record',
                                   label=node_name, tooltip=node_name, title=node_name,
                                   href=f"node_id_{node_name}")
            taxa.pop(taxon_name)
            for edge in taxa:
                graph.add_edge(edge, taxon_name)

    @_sheets.wait()
    def _create(self):
        if not write.repo.get(None):
            if not self._setRepositoryPath(self, "Select a repository path to create assets on"):
                msg = "A repository path must be selected in order to create assets."
                QtWidgets.QMessageBox.warning(self, "Repository path not set", msg)
                return
        # TODO: check for "write._TAXONOMY_ROOT_PATH" existence and handle missing
        root = self._stage.GetPrimAtPath(write._TAXONOMY_ROOT_PATH)
        model = self.sheet.table.model()
        for row in range(model.rowCount()):
            taxon_name = model.data(model.index(row, 0))
            if not taxon_name:
                # TODO: validate and raise error dialog to user. For now we ignore.
                print(f"An asset name is required! Missing on row: {row}")
                continue
            reference_names = (model.data(model.index(row, 1)) or '').split("\n")
            references = (root.GetPrimAtPath(ref_name) for ref_name in reference_names if ref_name)
            write.define_taxon(self._stage, taxon_name, references=references)

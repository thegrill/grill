from pathlib import Path
from functools import partial

import networkx
from pxr import Usd
from grill import cook

from ._qt import QtWidgets, QtCore, QtGui
from . import sheets as _sheets, description as _description, _core


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
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Apply | QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        apply_btn = button_box.button(QtWidgets.QDialogButtonBox.Apply)
        self._applied = apply_btn.clicked

        model = _core.EmptyTableModel(columns=columns)
        self.sheet = sheet = _sheets._Spreadsheet(model, columns, _core._ColumnOptions.NONE)
        self._amount.valueChanged.connect(sheet.model.setRowCount)
        sheet.layout().setContentsMargins(0, 0, 0, 0)

        self._amount.setValue(1)
        self._amount.setMinimum(1)
        self._amount.setMaximum(1000)
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
            token = cook.Repository.set(Path(dirpath))
            print(f"Repository path set to: {dirpath}, token: {token}")
        return dirpath


class CreateAssets(_CreatePrims):
    def __init__(self, *args, **kwargs):
        def _taxon_combobox(parent, option, index):
            combobox = QtWidgets.QComboBox(parent=parent)
            options = sorted(self._taxon_options, key=Usd.Prim.GetName)
            combobox.addItems([p.GetName() for p in options])
            return combobox
        _columns = (
            _core._Column("🧬 Taxon", editor=_taxon_combobox),
            _core._Column("🔖 Name"),
            _core._Column("🏷 Label"),
            _core._Column("📜 Description"),  # TODO: STILL UNUSED
        )

        existing_columns = (_core._Column("🧬 Existing", Usd.Prim.GetName),)
        existing_model = _sheets.StageTableModel(columns=existing_columns)
        existing_model._root_paths = {cook._TAXONOMY_ROOT_PATH}
        existing_model._filter_predicate = lambda prim: prim.GetAssetInfoByKey(cook._ASSETINFO_TAXA_KEY)
        # TODO: turn this into a method to lock all columns?
        existing_model._locked_columns = list(range(len(existing_columns)))
        self._existing_model = existing_model

        super().__init__(_columns, *args, **kwargs)
        self.accepted.connect(self._create)
        self._applied.connect(self._apply)
        self.setWindowTitle("Create Assets")

    @property
    def _taxon_options(self):
        return self._existing_model._objects

    @_core.wait()
    def _create(self):
        if not cook.Repository.get(None):
            if not self._setRepositoryPath(self, "Select a repository path to create assets on"):
                msg = "A repository path must be selected in order to create assets."
                QtWidgets.QMessageBox.warning(self, "Repository path not set", msg)
                return
        # TODO: check for "write._TAXONOMY_ROOT_PATH" existence and handle missing
        root = self._stage.GetPrimAtPath(cook._TAXONOMY_ROOT_PATH)
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
            cook.create_unit(taxon, asset_name, label)

    def setStage(self, stage):
        self._stage = stage
        self._existing_model.stage = stage

    def _apply(self):
        """Apply current changes and keep dialog open."""
        # TODO: move this to the base _CreatePrims class
        self._create()
        self.setStage(self._stage)


class TaxonomyEditor(_CreatePrims):

    def __init__(self, *args, **kwargs):
        # 1. Read only list of existing taxonomy
        # 2. Place to create new taxon groups
        #    - name | references | id_fields

        class ReferenceSelection(QtWidgets.QDialog):
            def __init__(self, parent=None):
                super().__init__(parent=parent)
                layout = QtWidgets.QVBoxLayout()
                self._options = options = QtWidgets.QListWidget()
                options.setSelectionMode(options.SelectionMode.ExtendedSelection)
                options.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
                options.customContextMenuRequested.connect(lambda: self._create_context_menu().exec_(QtGui.QCursor.pos()))
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
                    menu.addAction(title, partial(set_check_status, status))
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
                taxon = taxon.GetName()
                item = QtWidgets.QListWidgetItem(inter._options)
                item.setText(taxon)
                item.setCheckState(QtCore.Qt.Checked if taxon in checked_items else QtCore.Qt.Unchecked)

            return inter

        def _reference_setter(editor: ReferenceSelection, model: _core._ProxyModel, index:QtCore.QModelIndex):
            return model.setData(index, "\n".join(editor._value()))

        identity = lambda x: x
        _columns = (
            _core._Column("🧬 New Name", identity),
            _core._Column(
                "🔗 References",
                identity,
                editor=_reference_selector,
                setter=_reference_setter
            ),
            _core._Column(f"{_core._EMOJI.ID.value} ID Fields", identity),
        )
        super().__init__(_columns, *args, **kwargs)
        self.setWindowTitle("Taxonomy Editor")

        existing_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        existing_columns = (_core._Column("🧬 Existing", Usd.Prim.GetName),)
        existing_model = _sheets.StageTableModel(columns=existing_columns)
        existing_model._root_paths = {cook._TAXONOMY_ROOT_PATH}
        existing_model._filter_predicate = lambda prim: prim.GetAssetInfoByKey(cook._ASSETINFO_TAXA_KEY)
        # TODO: turn this into a method to lock all columns?
        existing_model._locked_columns = list(range(len(existing_columns)))
        self._existing = existing = _sheets._Spreadsheet(
            existing_model,
            # TODO: see if columns "should" be passed always to the model. If so, then
            #   we can avoid passing it here.
            existing_columns,
            _core._ColumnOptions.SEARCH,
        )
        existing.layout().setContentsMargins(0, 0, 0, 0)
        existing_splitter.addWidget(existing)

        self._graph_view = _description._GraphViewer(parent=self)
        existing_splitter.addWidget(self._graph_view)

        selectionModel = existing.table.selectionModel()
        selectionModel.selectionChanged.connect(self._existingSelectionChanged)
        self._ids_by_taxa = dict()

        self._splitter.insertWidget(0, existing_splitter)
        self._splitter.setStretchFactor(0, 2)
        self._splitter.setStretchFactor(1, 3)

        self.accepted.connect(self._create)
        self._applied.connect(self._apply)

    def _apply(self):
        """Apply current changes and keep dialog open."""
        # TODO: move this to the base _CreatePrims class
        self._create()
        self.setStage(self._stage)

    def _existingSelectionChanged(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection):
        prims = (index.data(_core._QT_OBJECT_DATA_ROLE) for index in self._existing.table.selectedIndexes())
        node_ids = [self._ids_by_taxa[prim.GetName()] for prim in prims]
        self._graph_view.view(node_ids)

    @property
    def _taxon_options(self):
        return self._existing.model._objects

    def setStage(self, stage):
        self._stage = stage
        self._existing.model.stage = stage
        existing_taxa = self._taxon_options
        self._graph_view.graph = graph = networkx.DiGraph(tooltip="Taxonomy Graph")
        graph.graph['graph'] = {'rankdir': 'LR'}
        self._ids_by_taxa = _ids_by_taxa = dict()  # {"taxon1": 42}
        for index, taxon in enumerate(existing_taxa):
            # TODO: ensure to guarantee taxa will be unique (no duplicated short names)
            taxon_name = taxon.GetName()
            graph.add_node(
                index,
                label=taxon_name,
                tooltip=taxon_name,
                href=f"{self._graph_view.url_id_prefix}{index}",
                shape="box",
                fillcolor="lightskyblue1",
                color="dodgerblue4",
                style='"filled,rounded"',
            )
            _ids_by_taxa[taxon_name] = index

        # TODO: in 3.9 use topological sorting for a single for loop. in the meantime, loop twice (so that all taxa have been added to the graph)
        for taxon in existing_taxa:
            taxa = taxon.GetAssetInfoByKey(cook._ASSETINFO_TAXA_KEY)
            taxon_name = taxon.GetName()
            taxa.pop(taxon_name)
            for ref_taxon in taxa:
                graph.add_edge(_ids_by_taxa[ref_taxon], _ids_by_taxa[taxon_name])

    @_core.wait()
    def _create(self):
        if not cook.Repository.get(None):
            if not self._setRepositoryPath(self, "Select a repository path to create assets on"):
                msg = "A repository path must be selected in order to create assets."
                QtWidgets.QMessageBox.warning(self, "Repository path not set", msg)
                return
        # TODO: check for "write._TAXONOMY_ROOT_PATH" existence and handle missing
        # TODO: make data point to the actual existing prims from the start.
        #   So that we don't need to call GetPRimAtPath.
        root = self._stage.GetPrimAtPath(cook._TAXONOMY_ROOT_PATH)
        model = self.sheet.table.model()
        for row in range(model.rowCount()):
            taxon_name = model.data(model.index(row, 0))
            if not taxon_name:
                # TODO: validate and raise error dialog to user. For now we ignore.
                print(f"An asset name is required! Missing on row: {row}")
                continue
            reference_names = (model.data(model.index(row, 1)) or '').split("\n")
            references = (root.GetPrimAtPath(ref_name) for ref_name in reference_names if ref_name)
            cook.define_taxon(self._stage, taxon_name, references=references)

from pathlib import Path

from pxr import Usd
from grill import write
from PySide2 import QtWidgets

from . import sheets as _sheets


class CreateAssets(QtWidgets.QDialog):
    def __init__(self, *args, **kwargs):
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

        self.sheet = sheet = _sheets._Spreadsheet(_columns, _sheets._ColumnOptions.NONE)
        sheet.model.setHorizontalHeaderLabels([''] * len(_columns))
        self._amount.valueChanged.connect(sheet.model.setRowCount)
        sheet.layout().setContentsMargins(0, 0, 0, 0)

        self._amount.setValue(1)
        self._amount.setMinimum(1)
        self._amount.setMaximum(500)
        layout.addWidget(sheet)
        layout.addWidget(button_box)
        self.setLayout(layout)
        self.accepted.connect(self._create)
        self.setWindowTitle("Create Assets")
        size = sheet.table.viewportSizeHint()
        size.setWidth(size.width() + 65)  # sensible size at init time
        size.setHeight(self.sizeHint().height())
        self.resize(size)

    @_sheets.wait()
    def _create(self):
        if not write.repo.get(None):
            if not self._setRepositoryPath(self, "Select a repository path to create assets on"):
                msg = "A repository path must be selected in order to create assets."
                QtWidgets.QMessageBox.warning(self, "Repository path not set", msg)
                return
        # TODO: check for "write._CATEGORY_ROOT_PATH" existence and handle missing
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

    @staticmethod
    def _setRepositoryPath(parent=None, caption="Select a repository path"):
        dirpath = QtWidgets.QFileDialog.getExistingDirectory(parent=parent, caption=caption)
        if dirpath:
            token = write.repo.set(Path(dirpath))
            print(f"Repository path set to: {dirpath}, token: {token}")
        return dirpath

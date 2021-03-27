from pxr import Usd
from PySide2 import QtWidgets

from grill import write
from . import spreadsheet as _spreadsheet


class CreateAsset(QtWidgets.QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        form = QtWidgets.QFormLayout()
        type_options = self._type_options = QtWidgets.QComboBox()
        form.addRow('Type:', type_options)
        self._name_le = QtWidgets.QLineEdit()
        self._amount = QtWidgets.QSpinBox()
        self._amount.setValue(1)
        self._amount.setMaximum(100)
        form.addRow('Name:', self._name_le)
        self._display_le = QtWidgets.QLineEdit()
        form.addRow('Display Name:', self._display_le)
        form.addRow('Amount:', self._amount)
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        form.addWidget(button_box)
        self.setLayout(form)
        self.accepted.connect(self._create)

    @_spreadsheet.wait()
    def _create(self):
        types_root = self._stage.GetPrimAtPath("/DBTypes")
        current_selection = self._type_options.currentText()
        current_prim = types_root.GetPrimAtPath(current_selection)
        name = self._name_le.text()
        display_name = self._display_le.text()
        if self._amount.value() > 1:
            for i in range(1, self._amount.value() + 1):
                write.create(self._stage, current_prim, f"{name}{i}", display_name)
        else:
            write.create(self._stage, current_prim, name, display_name)

    def setStage(self, stage):
        self._stage = stage
        self._type_options.clear()
        types_root = stage.GetPrimAtPath("/DBTypes")
        print(types_root)
        if types_root:
            self._type_options.addItems([child.GetName() for child in types_root.GetFilteredChildren(Usd.PrimIsAbstract)])


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    view = CreateAsset()
    # url = QUrl("quickview.qml")

    # view.setSource(url)
    view.show()
    app.exec_()

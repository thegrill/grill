import numpy as np
from pxr import UsdGeom, Sdf
from functools import partial

import grill.usd as _usd

from ._qt import QtWidgets, QtGui


def _hsv_to_rgb(hsv):
    # taken directly from https://github.com/matplotlib/matplotlib/blob/f6e0ee49c598f59c6e6cf4eefe473e4dc634a58a/lib/matplotlib/colors.py#L1898-L1977
    # but don't want to depend on matplotlib for only it. Might change it the future.
    """Convert hsv values to rgb. All values assumed to be in range [0, 1]"""
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    r, g, b = np.empty_like(h), np.empty_like(h), np.empty_like(h)

    i = (h * 6.0).astype(int)
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))

    idx = i % 6 == 0
    r[idx] = v[idx]
    g[idx] = t[idx]
    b[idx] = p[idx]

    idx = i == 1
    r[idx] = q[idx]
    g[idx] = v[idx]
    b[idx] = p[idx]

    idx = i == 2
    r[idx] = p[idx]
    g[idx] = v[idx]
    b[idx] = t[idx]

    idx = i == 3
    r[idx] = p[idx]
    g[idx] = q[idx]
    b[idx] = v[idx]

    idx = i == 4
    r[idx] = t[idx]
    g[idx] = p[idx]
    b[idx] = v[idx]

    idx = i == 5
    r[idx] = v[idx]
    g[idx] = p[idx]
    b[idx] = q[idx]

    idx = s == 0
    r[idx] = v[idx]
    g[idx] = v[idx]
    b[idx] = v[idx]
    rgb = np.stack([r, g, b], axis=-1)
    return rgb.reshape(hsv.shape)


def _random_colors(amount):
    return np.random.dirichlet(np.ones(3), size=amount)


def _color_spectrum(start: QtGui.QColor, end: QtGui.QColor, amount):
    *start_hsv, start_alpha = start.getHsvF()
    *end_hsv, end_alpha = end.getHsvF()
    return _hsv_to_rgb(np.linspace(start_hsv, end_hsv, amount))


class _DisplayColorEditor(QtWidgets.QFrame):
    # TODO: support alpha update
    # TODO: still experimental
    def __init__(self, primvar: UsdGeom.Primvar, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._primvar = primvar

        def _pick_color(parent, launcher):
            result = QtWidgets.QColorDialog.getColor(launcher._color, parent, options=QtWidgets.QColorDialog.ShowAlphaChannel)
            if result.isValid():
                launcher._color = result
                launcher.setStyleSheet(f"background-color: rgb{result.getRgb()}")
                self._update_value()

        layout = QtWidgets.QVBoxLayout()
        options_layout = QtWidgets.QFormLayout()
        # If constant:
        #   Show single color option
        # Else:
        #   Show color range (start, finish) OR Random
        wavelength_layout = QtWidgets.QHBoxLayout()
        wavelength_options = QtWidgets.QButtonGroup()
        spectrum = QtWidgets.QRadioButton("Spectrum")
        spectrum.setChecked(True)
        self._random = random = QtWidgets.QRadioButton("Random")
        wavelength_options.addButton(spectrum)
        wavelength_options.addButton(random)

        for button in wavelength_options.buttons():
            wavelength_layout.addWidget(button)
        options_layout.addRow("Wavelength:", wavelength_layout)

        stackedWidget = QtWidgets.QStackedWidget()
        interpolation_options_box = QtWidgets.QComboBox()

        def _color_option_changed(*__):
            current_idx = int(bool(interpolation_options_box.currentIndex()))
            if random.isChecked():
                current_idx = 2
            stackedWidget.setCurrentIndex(current_idx)
            self._update_value()

        wavelength_options.buttonClicked.connect(_color_option_changed)

        if primvar and (value := primvar.Get()):
            start_color = QtGui.QColor.fromRgbF(*value[0])
            end_color = QtGui.QColor.fromRgbF(*value[-1])
        else:
            start_color = QtGui.QColor.fromHsv(359, 255, 255)
            end_color = QtGui.QColor.fromHsv(0, 255, 255)

        self._color_launchers = _color_launchers = {}
        for label, colors in (
                ("Color", (start_color, )),
                ("Range", (start_color, end_color)),  # GUI goes from 359 to 0 ):
        ):
            range_layout = QtWidgets.QHBoxLayout()
            range_layout.addStretch()
            _color_launchers[label] = []
            for color in colors:
                launcher = QtWidgets.QPushButton()
                _color_launchers[label].append(launcher)
                launcher._color = color
                launcher.setStyleSheet(f"background-color: rgb{color.getRgb()}")
                launcher.clicked.connect(partial(_pick_color, self, launcher))
                range_layout.addWidget(launcher)
            range_frame = QtWidgets.QFrame()
            range_layout.setContentsMargins(0, 0, 0, 0)
            range_frame.setLayout(range_layout)
            stackedWidget.addWidget(range_frame)

        random_layout = QtWidgets.QHBoxLayout()
        random_layout.addStretch()
        random_new = QtWidgets.QPushButton("New")
        random_new.clicked.connect(_color_option_changed)
        random_layout.addWidget(random_new)
        random_frame = QtWidgets.QFrame()
        random_layout.setContentsMargins(0, 0, 0, 0)
        random_frame.setLayout(random_layout)
        stackedWidget.addWidget(random_frame)
        for primvar_info in _usd._GeomPrimvarInfo:
            interpolation_options_box.addItem(primvar_info.interpolation())

        if primvar:
            interpolation_options_box.setCurrentText(primvar.GetInterpolation())
            stackedWidget.setCurrentIndex(int(bool(interpolation_options_box.currentIndex())))

        options_layout.addRow("Interpolation:", interpolation_options_box)
        layout.addLayout(options_layout)
        layout.addWidget(stackedWidget)
        self._interpolation_options_box = interpolation_options_box
        for button in wavelength_options.buttons():
            button.clicked.connect(_color_option_changed)
        interpolation_options_box.currentIndexChanged.connect(_color_option_changed)
        self.setLayout(layout)

    @property
    def _interpolation(self):
        return self._interpolation_options_box.currentText()

    @property
    def _size(self):
        if not self._primvar:
            return 1
        for i in _usd._GeomPrimvarInfo:
            if i.interpolation() == self._interpolation:
                return i.size(self._primvar.GetAttr().GetPrim())

    @property
    def _value(self):
        amount = self._size
        if self._random.isChecked():
            return _random_colors(amount)

        if self._interpolation == _usd._GeomPrimvarInfo.CONSTANT.interpolation():
            start = end = self._color_launchers["Color"][0]._color
        else:
            start, end = [pb._color for pb in self._color_launchers["Range"]]
        return _color_spectrum(start, end, amount)

    def _update_value(self, *__):
        if primvar := self._primvar:
            with Sdf.ChangeBlock():
                # Warning, when changing interpolation type in USDView, Hydra does not
                # seem to respect re-computation of the changed primvar for GlSl shader.
                # Workaround:
                # 1. Change draw mode to cards
                # 2. Change interpolation
                # 3. Change colors as desired!
                primvar.SetInterpolation(self._interpolation)
                primvar.SetElementSize(self._size)
                primvar.Set(self._value)

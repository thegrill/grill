try:  # only while transition from PySide2 to PySide6 happens
    from PySide6 import QtWidgets, QtGui, QtCore, QtWebEngineWidgets
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore, QtWebEngineWidgets

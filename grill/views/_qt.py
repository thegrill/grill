try:  # only while transition from PySide2 to PySide6 happens
    from PySide6 import QtWidgets, QtGui, QtCore, QtWebEngineWidgets, QtCharts
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore, QtWebEngineWidgets
    try:
        from PySide2.QtCharts import QtCharts
    except ImportError:
        # Maya-2023.3 and Houdini-19.5.534 bundle PySide2, but their versions fail to bring QtCharts :c
        pass

try:  # only while transition from PySide2 to PySide6 happens
    from PySide6 import QtWidgets, QtGui, QtCore, QtCharts, QtSvg
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore, QtSvg
    if not hasattr(QtCore, "__enter__"):
        class SignalBlocker(QtCore.QSignalBlocker):
            def __enter__(self):
                yield

            def __exit__(self, exc_type, exc_value, exc_traceback):
                self.unblock()

        QtCore.QSignalBlocker = SignalBlocker
    try:
        from PySide2.QtCharts import QtCharts
    except ImportError:
        # Maya-2023.3 and Houdini-19.5.534 bundle PySide2, but their versions fail to bring QtCharts :c
        pass

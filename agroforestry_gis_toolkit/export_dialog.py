# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QMessageBox,
)
from qgis.PyQt.QtCore import pyqtSignal
from qgis.gui import QgsMapLayerComboBox
from qgis.core import QgsMapLayerProxyModel

from .exporter import export_layer, EXPORT_FORMATS


class ExportDialog(QWidget):
    TITLE = "Export Data (Excel / GeoJSON / CSV)"
    finished = pyqtSignal()
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layer_box = QGroupBox("Select layer")
        layer_layout = QVBoxLayout(layer_box)
        self.combo_layer = QgsMapLayerComboBox()
        self.combo_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        layer_layout.addWidget(self.combo_layer)
        layout.addWidget(layer_box)

        format_box = QGroupBox("Export format")
        format_layout = QHBoxLayout(format_box)
        self.radio_buttons = {}
        self.format_group = QButtonGroup(self)
        for label in EXPORT_FORMATS:
            rb = QRadioButton(label)
            self.radio_buttons[label] = rb
            self.format_group.addButton(rb)
            format_layout.addWidget(rb)
        self.radio_buttons["CSV"].setChecked(True)
        layout.addWidget(format_box)

        out_box = QGroupBox("Save as")
        out_layout = QHBoxLayout(out_box)
        self.txt_output = QLineEdit()
        btn_browse = QPushButton("...")
        btn_browse.clicked.connect(self._browse_output)
        out_layout.addWidget(self.txt_output)
        out_layout.addWidget(btn_browse)
        layout.addWidget(out_box)

        self.btn_run = QPushButton("Export")
        self.btn_run.clicked.connect(self._run)
        layout.addWidget(self.btn_run)

    def _selected_format(self):
        for label, rb in self.radio_buttons.items():
            if rb.isChecked():
                return label
        return "CSV"

    def _browse_output(self):
        fmt = self._selected_format()
        _, ext = EXPORT_FORMATS[fmt]
        path, _ = QFileDialog.getSaveFileName(self, "Save export result", "", f"{fmt} (*.{ext})")
        if path:
            self.txt_output.setText(path)

    def _run(self):
        layer = self.combo_layer.currentLayer()
        if layer is None:
            QMessageBox.warning(self, "Warning", "Select the layer to export.")
            return
        output_path = self.txt_output.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Warning", "Specify where to save the export.")
            return

        fmt = self._selected_format()
        try:
            self.btn_run.setEnabled(False)
            result_path = export_layer(layer, fmt, output_path)
            QMessageBox.information(self, "Done", f"Data exported successfully to:\n{result_path}")
            self.finished.emit()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Failed to export data:\n{exc}")
        finally:
            self.btn_run.setEnabled(True)

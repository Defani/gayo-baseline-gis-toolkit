# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QLineEdit,
    QLabel,
    QFileDialog,
    QMessageBox,
    QCheckBox,
)
from qgis.PyQt.QtCore import pyqtSignal
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox
from qgis.core import QgsMapLayerProxyModel

from .gpx_processor import export_to_gpx


class GpxDialog(QWidget):
    TITLE = "Export to GPX (Garmin)"
    finished = pyqtSignal()
    """Export the active layer (point/line/polygon) to a GPX file for Garmin."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Convert 1 active vector layer into a .gpx file that can be opened\n"
            "on a Garmin device (point, line, or polygon - polygons will\n"
            "automatically be converted into boundary lines)."
        ))

        layer_box = QGroupBox("Select layer")
        layer_layout = QVBoxLayout(layer_box)
        self.combo_layer = QgsMapLayerComboBox()
        self.combo_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.combo_layer.layerChanged.connect(self._on_layer_changed)
        layer_layout.addWidget(self.combo_layer)
        layout.addWidget(layer_box)

        name_box = QGroupBox("Feature name on Garmin")
        name_layout = QVBoxLayout(name_box)

        self.chk_use_field = QCheckBox("Take the per-feature name from an attribute column (don't merge into one)")
        self.chk_use_field.toggled.connect(self._on_mode_toggled)
        name_layout.addWidget(self.chk_use_field)

        self.combo_field = QgsFieldComboBox()
        self.combo_field.setLayer(self.combo_layer.currentLayer())
        self.combo_field.setEnabled(False)
        name_layout.addWidget(self.combo_field)

        self.txt_display_name = QLineEdit("Display Name")
        self.txt_display_name.setPlaceholderText("Display name (used when all features are merged into one)")
        name_layout.addWidget(self.txt_display_name)

        layout.addWidget(name_box)

        out_box = QGroupBox("Save as (.gpx)")
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

    def _on_layer_changed(self, layer):
        self.combo_field.setLayer(layer)

    def _on_mode_toggled(self, checked):
        self.combo_field.setEnabled(checked)
        self.txt_display_name.setEnabled(not checked)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save GPX file", "", "GPX files (*.gpx)")
        if path:
            self.txt_output.setText(path)

    def _run(self):
        layer = self.combo_layer.currentLayer()
        if layer is None:
            QMessageBox.warning(self, "Warning", "Select the layer to export.")
            return
        output_path = self.txt_output.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Warning", "Specify where to save the .gpx file.")
            return

        name_field = self.combo_field.currentField() if self.chk_use_field.isChecked() else None
        display_name = self.txt_display_name.text().strip() or "Display Name"

        try:
            self.btn_run.setEnabled(False)
            result_path = export_to_gpx(layer, display_name, name_field, output_path)
            QMessageBox.information(self, "Done", f"GPX file created successfully:\n{result_path}")
            self.finished.emit()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Failed to export GPX:\n{exc}")
        finally:
            self.btn_run.setEnabled(True)

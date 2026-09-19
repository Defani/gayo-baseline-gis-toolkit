# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
    QSpinBox,
    QPushButton,
    QFileDialog,
    QMessageBox,
)
from qgis.PyQt.QtCore import pyqtSignal
from qgis.gui import QgsMapLayerComboBox
from qgis.core import (
    QgsMapLayerProxyModel,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsVectorLayer,
    QgsProject,
)

from .grid_index_algorithm import GridIndexAlgorithm


class GridIndexDialog(QWidget):
    TITLE = "Grid Index"
    finished = pyqtSignal()
    """Build a cartographically-aware grid index for map series and atlases,
    with advanced labeling options. Works on vector and raster layers, in
    both projected and geographic coordinate systems."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(460)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Creates a grid of rectangular page-index polygons covering the\n"
            "extent of the selected layer, keeping only the cells that\n"
            "intersect it (works with vector or raster layers)."
        ))

        # --- Input layer ---
        layer_box = QGroupBox("Intersection layer")
        layer_layout = QVBoxLayout(layer_box)
        self.combo_layer = QgsMapLayerComboBox()
        self.combo_layer.setFilters(QgsMapLayerProxyModel.VectorLayer | QgsMapLayerProxyModel.RasterLayer)
        layer_layout.addWidget(self.combo_layer)
        layout.addWidget(layer_box)

        # --- Cell size ---
        size_box = QGroupBox("Grid cell size (in the layer's map units)")
        size_layout = QHBoxLayout(size_box)
        size_layout.addWidget(QLabel("Width"))
        self.spin_width = QDoubleSpinBox()
        self.spin_width.setRange(0.000001, 1_000_000_000)
        self.spin_width.setDecimals(4)
        self.spin_width.setValue(500.0)
        size_layout.addWidget(self.spin_width)
        size_layout.addWidget(QLabel("Height"))
        self.spin_height = QDoubleSpinBox()
        self.spin_height.setRange(0.000001, 1_000_000_000)
        self.spin_height.setDecimals(4)
        self.spin_height.setValue(500.0)
        size_layout.addWidget(self.spin_height)
        layout.addWidget(size_box)

        # --- Labeling ---
        label_box = QGroupBox("Labeling")
        label_layout = QVBoxLayout(label_box)

        self.chk_absolute_naming = QCheckBox("Use absolute grid position for Page Names")
        self.chk_absolute_naming.setToolTip(
            "If checked, names are based on the overall grid column (e.g., C5).\n"
            "If unchecked, they are numbered sequentially within each row (e.g., C1, C2...)."
        )
        label_layout.addWidget(self.chk_absolute_naming)

        origin_row = QHBoxLayout()
        origin_row.addWidget(QLabel("Labeling starts from"))
        self.combo_origin = QComboBox()
        self.combo_origin.addItems(["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"])
        origin_row.addWidget(self.combo_origin)
        label_layout.addLayout(origin_row)

        layout.addWidget(label_box)

        # --- Overrides ---
        override_box = QGroupBox("Overrides (optional)")
        override_layout = QHBoxLayout(override_box)
        override_layout.addWidget(QLabel("Rows"))
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(0, 100000)
        self.spin_rows.setSpecialValueText("Auto")
        override_layout.addWidget(self.spin_rows)
        override_layout.addWidget(QLabel("Columns"))
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(0, 100000)
        self.spin_cols.setSpecialValueText("Auto")
        override_layout.addWidget(self.spin_cols)
        override_layout.addWidget(QLabel("Start page"))
        self.spin_start_page = QSpinBox()
        self.spin_start_page.setRange(1, 1_000_000)
        self.spin_start_page.setValue(1)
        override_layout.addWidget(self.spin_start_page)
        layout.addWidget(override_box)

        # --- Output ---
        out_box = QGroupBox("Save grid index as")
        out_layout = QHBoxLayout(out_box)
        self.txt_output = QLineEdit()
        btn_browse = QPushButton("...")
        btn_browse.clicked.connect(self._browse_output)
        out_layout.addWidget(self.txt_output)
        out_layout.addWidget(btn_browse)
        layout.addWidget(out_box)

        # --- Run ---
        self.btn_run = QPushButton("Create Grid Index")
        self.btn_run.clicked.connect(self._run)
        layout.addWidget(self.btn_run)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save grid index", "", "GeoPackage (*.gpkg)")
        if path:
            if not path.lower().endswith(".gpkg"):
                path += ".gpkg"
            self.txt_output.setText(path)

    def _run(self):
        layer = self.combo_layer.currentLayer()
        if layer is None:
            QMessageBox.warning(self, "Warning", "Select the intersection layer first.")
            return
        output_path = self.txt_output.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Warning", "Specify where to save the grid index.")
            return

        params = {
            GridIndexAlgorithm.INPUT_LAYER: layer,
            GridIndexAlgorithm.CELL_WIDTH: self.spin_width.value(),
            GridIndexAlgorithm.CELL_HEIGHT: self.spin_height.value(),
            GridIndexAlgorithm.USE_ABSOLUTE_NAMING: self.chk_absolute_naming.isChecked(),
            GridIndexAlgorithm.LABEL_ORIGIN: self.combo_origin.currentIndex(),
            GridIndexAlgorithm.NUM_ROWS: self.spin_rows.value(),
            GridIndexAlgorithm.NUM_COLS: self.spin_cols.value(),
            GridIndexAlgorithm.START_PAGE: self.spin_start_page.value(),
            GridIndexAlgorithm.OUTPUT: output_path,
        }

        try:
            self.btn_run.setEnabled(False)
            self.btn_run.setText("Processing...")

            algorithm = GridIndexAlgorithm()
            algorithm.initAlgorithm()
            context = QgsProcessingContext()
            context.setProject(QgsProject.instance())
            feedback = QgsProcessingFeedback()

            result = algorithm.processAlgorithm(params, context, feedback)
            dest_id = result.get(GridIndexAlgorithm.OUTPUT) if result else None
            if not dest_id:
                raise RuntimeError("The grid index could not be created (no output produced).")

            layer_out = QgsVectorLayer(output_path, "Grid_Index", "ogr")
            if layer_out.isValid():
                QgsProject.instance().addMapLayer(layer_out)

            QMessageBox.information(self, "Done", f"Grid index created successfully:\n{output_path}")
            self.finished.emit()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Failed to create grid index:\n{exc}")
        finally:
            self.btn_run.setEnabled(True)
            self.btn_run.setText("Create Grid Index")

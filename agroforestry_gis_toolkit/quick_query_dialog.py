# -*- coding: utf-8 -*-
"""Embedded "Quick Query" page for the Agroforestry sidebar panel.

Three small tools on one page, all working on the layer picked at the top:

  1. Cari & zoom - free-text search on one field, selects + zooms to matches.
  2. Filter cepat - dropdown field/value, applies a subset string filter.
  3. QC cepat - preset checks matching the fieldwork QC step (empty geometry,
     duplicate IDs, suspiciously small area, empty required field, overlapping
     polygons) - each just selects the offending features and zooms to them.

Nothing here replaces the full Attribute Table / Field Calculator; it's a
shortcut for the handful of queries that come up constantly during fieldwork
and QC.
"""
from qgis.core import (
    QgsExpression,
    QgsFeatureRequest,
    QgsMapLayerProxyModel,
    QgsSpatialIndex,
    QgsWkbTypes,
)
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Unique values shown in the filter combo are capped so a huge layer doesn't
# freeze the UI while populating the dropdown.
_MAX_UNIQUE_VALUES = 300

# Anything smaller than this (map units, expected to be meters on a projected
# layer) counts as a real overlap rather than two polygons merely touching.
_MIN_OVERLAP_AREA = 1e-6


def _is_blank(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


class QuickQueryDialog(QWidget):
    """Sidebar page: quick search, quick filter, and QC preset queries."""

    TITLE = "Quick Query"
    finished = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(400)
        self._build_ui()
        self._on_layer_changed(self.combo_layer.currentLayer())

    # --- UI ---

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layer_row = QHBoxLayout()
        layer_row.addWidget(QLabel("Layer:"))
        self.combo_layer = QgsMapLayerComboBox()
        self.combo_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.combo_layer.layerChanged.connect(self._on_layer_changed)
        layer_row.addWidget(self.combo_layer, 1)
        layout.addLayout(layer_row)

        layout.addWidget(self._build_search_box())
        layout.addWidget(self._build_filter_box())
        layout.addWidget(self._build_qc_box())
        layout.addStretch()

    def _build_search_box(self):
        box = QGroupBox("Cari & zoom")
        v = QVBoxLayout(box)

        row = QHBoxLayout()
        self.combo_search_field = QComboBox()
        row.addWidget(self.combo_search_field, 1)
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("cth: ID kebun, nama, desa...")
        self.txt_search.returnPressed.connect(self._do_search)
        row.addWidget(self.txt_search, 2)
        btn = QPushButton("Cari")
        btn.clicked.connect(self._do_search)
        row.addWidget(btn)
        v.addLayout(row)

        self.lbl_search_status = QLabel("")
        self.lbl_search_status.setWordWrap(True)
        v.addWidget(self.lbl_search_status)
        return box

    def _build_filter_box(self):
        box = QGroupBox("Filter cepat")
        v = QVBoxLayout(box)

        row = QHBoxLayout()
        self.combo_filter_field = QComboBox()
        self.combo_filter_field.currentTextChanged.connect(self._refresh_filter_values)
        row.addWidget(self.combo_filter_field, 1)
        self.combo_filter_value = QComboBox()
        self.combo_filter_value.setEditable(True)
        row.addWidget(self.combo_filter_value, 1)
        v.addLayout(row)

        btn_row = QHBoxLayout()
        btn_apply = QPushButton("Terapkan Filter")
        btn_apply.clicked.connect(self._apply_filter)
        btn_row.addWidget(btn_apply)
        btn_clear = QPushButton("Hapus Filter")
        btn_clear.clicked.connect(self._clear_filter)
        btn_row.addWidget(btn_clear)
        v.addLayout(btn_row)

        self.lbl_filter_status = QLabel("")
        self.lbl_filter_status.setWordWrap(True)
        v.addWidget(self.lbl_filter_status)
        return box

    def _build_qc_box(self):
        box = QGroupBox("QC cepat")
        v = QVBoxLayout(box)

        self.btn_qc_empty_geom = QPushButton("Geometri kosong / tanpa koordinat")
        self.btn_qc_empty_geom.clicked.connect(self._qc_empty_geometry)
        v.addWidget(self.btn_qc_empty_geom)

        dup_row = QHBoxLayout()
        self.combo_id_field = QComboBox()
        dup_row.addWidget(self.combo_id_field, 1)
        btn_dup = QPushButton("Cari ID Duplikat")
        btn_dup.clicked.connect(self._qc_duplicate_ids)
        dup_row.addWidget(btn_dup)
        v.addLayout(dup_row)

        area_row = QHBoxLayout()
        area_row.addWidget(QLabel("Luas < "))
        self.spin_min_area = QDoubleSpinBox()
        self.spin_min_area.setRange(0, 1_000_000)
        self.spin_min_area.setValue(10)
        self.spin_min_area.setSuffix(" m² (unit layer)")
        area_row.addWidget(self.spin_min_area)
        self.btn_qc_small_area = QPushButton("Cari Luas Meragukan")
        self.btn_qc_small_area.clicked.connect(self._qc_small_area)
        area_row.addWidget(self.btn_qc_small_area)
        v.addLayout(area_row)

        req_row = QHBoxLayout()
        self.combo_required_field = QComboBox()
        req_row.addWidget(self.combo_required_field, 1)
        btn_req = QPushButton("Cari Field Kosong")
        btn_req.clicked.connect(self._qc_empty_field)
        req_row.addWidget(btn_req)
        v.addLayout(req_row)

        self.btn_qc_overlap = QPushButton("Cari Overlap Antar Polygon")
        self.btn_qc_overlap.clicked.connect(self._qc_overlap)
        v.addWidget(self.btn_qc_overlap)

        self.lbl_qc_status = QLabel("")
        self.lbl_qc_status.setWordWrap(True)
        v.addWidget(self.lbl_qc_status)
        return box

    # --- layer / field bookkeeping ---

    def _on_layer_changed(self, layer):
        for combo in (
            self.combo_search_field,
            self.combo_filter_field,
            self.combo_id_field,
            self.combo_required_field,
        ):
            combo.clear()
        self.combo_filter_value.clear()
        self.lbl_search_status.setText("")
        self.lbl_filter_status.setText("")
        self.lbl_qc_status.setText("")

        if layer is None:
            return

        names = layer.fields().names()
        for combo in (
            self.combo_search_field,
            self.combo_filter_field,
            self.combo_id_field,
            self.combo_required_field,
        ):
            combo.addItems(names)

        is_polygon = QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry
        self.btn_qc_small_area.setEnabled(is_polygon)
        self.btn_qc_overlap.setEnabled(is_polygon)

        current_subset = layer.subsetString()
        if current_subset:
            self.lbl_filter_status.setText(f"Filter aktif: {current_subset}")

        self._refresh_filter_values(self.combo_filter_field.currentText())

    def _refresh_filter_values(self, field_name):
        self.combo_filter_value.clear()
        layer = self.combo_layer.currentLayer()
        if layer is None or not field_name:
            return
        idx = layer.fields().indexFromName(field_name)
        if idx < 0:
            return
        values = [v for v in layer.uniqueValues(idx) if not _is_blank(v)]
        values = sorted(values, key=lambda v: str(v))[:_MAX_UNIQUE_VALUES]
        self.combo_filter_value.addItems([str(v) for v in values])

    def _current_layer_or_warn(self):
        layer = self.combo_layer.currentLayer()
        if layer is None:
            QMessageBox.warning(self, "Belum ada layer", "Pilih layer vector dulu.")
        return layer

    def _select_and_zoom(self, layer, ids, status_label, empty_msg, found_msg):
        layer.removeSelection()
        if not ids:
            status_label.setText(empty_msg)
            return
        layer.selectByIds(ids)
        self.iface.mapCanvas().setCurrentLayer(layer)
        self.iface.mapCanvas().zoomToSelected(layer)
        status_label.setText(found_msg.format(n=len(ids)))

    @staticmethod
    def _escape(value):
        return value.replace("'", "''")

    # --- Cari & zoom ---

    def _do_search(self):
        layer = self._current_layer_or_warn()
        if layer is None:
            return
        field = self.combo_search_field.currentText()
        value = self.txt_search.text().strip()
        if not field or not value:
            self.lbl_search_status.setText("Isi kata kunci pencarian dulu.")
            return

        expr = QgsExpression(
            f'lower("{field}") LIKE lower(\'%{self._escape(value)}%\')'
        )
        if expr.hasParserError():
            self.lbl_search_status.setText(f"Ekspresi error: {expr.parserErrorString()}")
            return
        ids = [f.id() for f in layer.getFeatures(QgsFeatureRequest(expr))]
        self._select_and_zoom(
            layer, ids, self.lbl_search_status,
            "Tidak ada fitur yang cocok.",
            "{n} fitur cocok, sudah di-select & zoom.",
        )

    # --- Filter cepat ---

    def _apply_filter(self):
        layer = self._current_layer_or_warn()
        if layer is None:
            return
        field = self.combo_filter_field.currentText()
        value = self.combo_filter_value.currentText().strip()
        if not field or not value:
            self.lbl_filter_status.setText("Pilih field dan nilai filter dulu.")
            return
        subset = f'"{field}" = \'{self._escape(value)}\''
        if not layer.setSubsetString(subset):
            self.lbl_filter_status.setText("Gagal menerapkan filter (cek tipe data field).")
            return
        self.lbl_filter_status.setText(
            f"Filter aktif: {subset} - {layer.featureCount()} fitur tampil."
        )

    def _clear_filter(self):
        layer = self._current_layer_or_warn()
        if layer is None:
            return
        layer.setSubsetString("")
        self.lbl_filter_status.setText("Filter dihapus, semua fitur tampil lagi.")

    # --- QC cepat ---

    def _qc_empty_geometry(self):
        layer = self._current_layer_or_warn()
        if layer is None:
            return
        ids = [
            f.id() for f in layer.getFeatures()
            if f.geometry() is None or f.geometry().isEmpty()
        ]
        self._select_and_zoom(
            layer, ids, self.lbl_qc_status,
            "Tidak ada geometri kosong.",
            "{n} fitur tanpa geometri/koordinat.",
        )

    def _qc_duplicate_ids(self):
        layer = self._current_layer_or_warn()
        if layer is None:
            return
        field = self.combo_id_field.currentText()
        if not field:
            self.lbl_qc_status.setText("Pilih field ID unik dulu.")
            return
        seen = {}
        for f in layer.getFeatures():
            v = f[field]
            if _is_blank(v):
                continue
            seen.setdefault(v, []).append(f.id())
        dup_ids = [fid for fids in seen.values() if len(fids) > 1 for fid in fids]
        self._select_and_zoom(
            layer, dup_ids, self.lbl_qc_status,
            f"Tidak ada nilai '{field}' yang duplikat.",
            "{n} fitur dengan ID duplikat ditemukan.",
        )

    def _qc_small_area(self):
        layer = self._current_layer_or_warn()
        if layer is None:
            return
        if layer.crs().isGeographic():
            QMessageBox.information(
                self,
                "CRS layer geografis",
                "Layer ini pakai CRS geografis (derajat), jadi nilai luas di sini "
                "bukan m². Reproject dulu ke CRS meter (mis. UTM) untuk hasil yang "
                "valid.",
            )
        threshold = self.spin_min_area.value()
        ids = [
            f.id() for f in layer.getFeatures()
            if f.geometry() and not f.geometry().isEmpty()
            and f.geometry().area() < threshold
        ]
        self._select_and_zoom(
            layer, ids, self.lbl_qc_status,
            f"Tidak ada polygon dengan luas < {threshold}.",
            "{n} kebun dengan luas mencurigakan (< " + str(threshold) + ").",
        )

    def _qc_empty_field(self):
        layer = self._current_layer_or_warn()
        if layer is None:
            return
        field = self.combo_required_field.currentText()
        if not field:
            self.lbl_qc_status.setText("Pilih field yang mau dicek dulu.")
            return
        ids = [f.id() for f in layer.getFeatures() if _is_blank(f[field])]
        self._select_and_zoom(
            layer, ids, self.lbl_qc_status,
            f"Tidak ada '{field}' yang kosong.",
            "{n} fitur dengan '" + field + "' kosong.",
        )

    def _qc_overlap(self):
        layer = self._current_layer_or_warn()
        if layer is None:
            return

        feats = {f.id(): f for f in layer.getFeatures() if f.geometry() and not f.geometry().isEmpty()}
        if not feats:
            self.lbl_qc_status.setText("Tidak ada geometri untuk dicek.")
            return

        index = QgsSpatialIndex()
        for f in feats.values():
            index.insertFeature(f)

        overlap_ids = set()
        checked_pairs = set()
        for fid, f in feats.items():
            geom = f.geometry()
            for cid in index.intersects(geom.boundingBox()):
                if cid == fid:
                    continue
                pair = (min(fid, cid), max(fid, cid))
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)
                other_geom = feats[cid].geometry()
                if geom.intersects(other_geom):
                    inter = geom.intersection(other_geom)
                    if inter and not inter.isEmpty() and inter.area() > _MIN_OVERLAP_AREA:
                        overlap_ids.add(fid)
                        overlap_ids.add(cid)

        self._select_and_zoom(
            layer, list(overlap_ids), self.lbl_qc_status,
            "Tidak ada polygon yang overlap.",
            "{n} fitur terlibat overlap dengan polygon lain.",
        )

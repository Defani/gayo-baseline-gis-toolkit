# -*- coding: utf-8 -*-
"""Halaman sidebar "Distance Analysis": jarak titik (mis. dari Kobo) ke
kawasan hutan terdekat + status kawasannya."""
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsMapLayerProxyModel, QgsMapLayerType, QgsWkbTypes
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox

from . import distance_processor as dp
from .add_layer_dialog import VectorServiceDialog, _add_file_layers

# Tebakan otomatis nama field di layer kawasan hutan (huruf kecil).
_STATUS_GUESS = ["fungsitap_nama", "fungsi_nama", "fungsi_kws", "fungsi", "status", "fungsitap"]
_NAME_GUESS = ["nkws", "nama_kws", "namobj", "nama", "name"]


class DistanceDialog(QWidget):
    TITLE = "Distance Analysis (Titik ke Kawasan Hutan)"
    finished = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(380)
        self._build_ui()
        self._on_forest_changed()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        pt_box = QGroupBox("Layer titik (mis. hasil Kobo Connect)")
        pl = QVBoxLayout(pt_box)
        self.combo_points = QgsMapLayerComboBox()
        self.combo_points.setFilters(QgsMapLayerProxyModel.PointLayer)
        pl.addWidget(self.combo_points)
        layout.addWidget(pt_box)

        fr_box = QGroupBox("Layer kawasan hutan (poligon)")
        fl = QVBoxLayout(fr_box)
        self.combo_forest = QgsMapLayerComboBox()
        self.combo_forest.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.combo_forest.layerChanged.connect(self._on_forest_changed)
        fl.addWidget(self.combo_forest)
        src_row = QHBoxLayout()
        btn_file = QPushButton("+ Dari file...")
        btn_file.setToolTip("File apa saja: shp, gpkg, geojson, kml, gdb, dxf, dll.")
        btn_file.clicked.connect(self._add_forest_from_file)
        btn_web = QPushButton("+ Dari layanan web...")
        btn_web.setToolTip("WFS atau ArcGIS REST (FeatureServer / MapServer)")
        btn_web.clicked.connect(self._add_forest_from_web)
        src_row.addWidget(btn_file)
        src_row.addWidget(btn_web)
        fl.addLayout(src_row)
        note = QLabel(
            "Daftar di atas = semua layer poligon di proyek (file apa saja, WFS, ArcGIS REST). "
            "Layer WMS / XYZ / WMTS berupa gambar tanpa geometri, jadi tidak bisa dipakai untuk "
            "mengukur jarak; pakai WFS / ArcGIS REST atau file dari layanan yang sama."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 10px;")
        fl.addWidget(note)
        self.chk_limit = QCheckBox("Ambil kawasan hanya di sekitar titik (untuk layer web yang besar)")
        self.chk_limit.setWordWrap(True)
        fl.addWidget(self.chk_limit)
        lim_row = QHBoxLayout()
        lim_row.addWidget(QLabel("Radius dari extent titik"))
        self.spin_limit = QDoubleSpinBox()
        self.spin_limit.setRange(1, 2000)
        self.spin_limit.setValue(50)
        self.spin_limit.setSuffix(" km")
        lim_row.addWidget(self.spin_limit)
        lim_row.addStretch()
        fl.addLayout(lim_row)
        fl.addWidget(QLabel("Field status kawasan yang diambil"))
        self.combo_status = QgsFieldComboBox()
        fl.addWidget(self.combo_status)
        fl.addWidget(QLabel("Field nama kawasan (opsional)"))
        self.combo_name = QgsFieldComboBox()
        self.combo_name.setAllowEmptyFieldName(True)
        fl.addWidget(self.combo_name)
        layout.addWidget(fr_box)

        unit_box = QGroupBox("Satuan jarak")
        ul = QHBoxLayout(unit_box)
        self.rb_km = QRadioButton("Kilometer (km)")
        self.rb_m = QRadioButton("Meter (m)")
        self.rb_km.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_km)
        grp.addButton(self.rb_m)
        ul.addWidget(self.rb_km)
        ul.addWidget(self.rb_m)
        layout.addWidget(unit_box)

        out_box = QGroupBox("Hasil")
        ol = QVBoxLayout(out_box)
        self.chk_line = QCheckBox("Buat layer garis jarak baru (titik \u2192 batas kawasan terdekat)")
        self.chk_line.setChecked(True)
        self.chk_fields = QCheckBox(
            "Tambah field ke layer titik: jarak ke kawasan hutan terdekat, status, posisi "
            "(mengubah layer titik langsung)"
        )
        self.chk_fields.setWordWrap(True)
        self.chk_fields.setChecked(True)
        ol.addWidget(self.chk_line)
        ol.addWidget(self.chk_fields)
        layout.addWidget(out_box)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.btn_run = QPushButton("Hitung Jarak")
        self.btn_run.setMinimumHeight(32)
        self.btn_run.clicked.connect(self._run)
        layout.addWidget(self.btn_run)

        self.lbl_result = QLabel("")
        self.lbl_result.setWordWrap(True)
        layout.addWidget(self.lbl_result)
        layout.addStretch()

    # ------------------------------------------------------------------
    def _add_forest_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Pilih file kawasan hutan", "", "Semua file (*)")
        if not path:
            return
        layers = []
        try:
            n, err = _add_file_layers(path, collect=layers)
        except Exception as exc:  # noqa: BLE001
            n, err = 0, str(exc)
        if not n:
            QMessageBox.warning(self, "Gagal", f"File tidak bisa dibuka: {err}")
            return
        polys = [
            l for l in layers
            if l.type() == QgsMapLayerType.VectorLayer
            and l.geometryType() == QgsWkbTypes.PolygonGeometry
        ]
        if not polys:
            QMessageBox.warning(
                self, "Bukan poligon",
                "File ditambahkan ke peta, tapi tidak berisi layer poligon "
                "(raster / garis / titik tidak bisa dipakai sebagai kawasan hutan).",
            )
            return
        self.combo_forest.setLayer(polys[0])
        if len(polys) > 1:
            QMessageBox.information(
                self, "Info",
                f"File punya {len(polys)} layer poligon; dipilih '{polys[0].name()}'. "
                "Ganti lewat daftar kalau perlu.",
            )

    def _add_forest_from_web(self):
        dlg = VectorServiceDialog(self)
        if dlg.exec_() != VectorServiceDialog.Accepted or dlg.layer is None:
            return
        layer = dlg.layer
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            QMessageBox.warning(self, "Bukan poligon", "Layer ini bukan poligon, tidak bisa jadi kawasan hutan.")
            return
        self.combo_forest.setLayer(layer)

    def _on_forest_changed(self, *_args):
        layer = self.combo_forest.currentLayer()
        self.combo_status.setLayer(layer)
        self.combo_name.setLayer(layer)
        if layer is None:
            return
        if dp.is_web_layer(layer):
            self.chk_limit.setChecked(True)
        lower = {f.name().lower(): f.name() for f in layer.fields()}
        for guess in _STATUS_GUESS:
            if guess in lower:
                self.combo_status.setField(lower[guess])
                break
        self.combo_name.setField("")
        for guess in _NAME_GUESS:
            if guess in lower:
                self.combo_name.setField(lower[guess])
                break

    def _run(self):
        pts = self.combo_points.currentLayer()
        forest = self.combo_forest.currentLayer()
        if pts is None:
            QMessageBox.warning(self, "Warning", "Pilih layer titik dulu.")
            return
        if forest is None:
            QMessageBox.warning(
                self, "Warning",
                "Pilih layer kawasan hutan dulu (tambahkan lewat menu Add Layer kalau belum ada).",
            )
            return
        if not (self.chk_line.isChecked() or self.chk_fields.isChecked()):
            QMessageBox.warning(self, "Warning", "Centang minimal satu hasil (layer garis dan/atau field).")
            return
        status_field = self.combo_status.currentField() or None
        name_field = self.combo_name.currentField() or None
        unit = "km" if self.rb_km.isChecked() else "m"

        self.btn_run.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            results, info = dp.compute_distances(
                pts, forest, status_field, name_field, progress=self._on_progress,
                search_km=self.spin_limit.value() if self.chk_limit.isChecked() else None,
            )
            if not results:
                QMessageBox.warning(self, "Info", "Tidak ada titik yang bisa dihitung (geometri kosong?).")
                return

            msgs = [dp.summarize(results, unit)]
            if info["beyond"]:
                msgs.append(
                    f"{info['beyond']} titik jaraknya melebihi radius pengambilan kawasan; "
                    "jaraknya bisa lebih besar dari yang sebenarnya. Perbesar radius atau matikan pembatasan."
                )
            if info["skipped"]:
                msgs.append(f"{info['skipped']} titik dilewati (geometri kosong / gagal transformasi).")

            if self.chk_line.isChecked():
                dp.create_line_layer(pts, results, unit, with_name=bool(name_field))
                msgs.append("Layer garis jarak ditambahkan ke peta.")
            if self.chk_fields.isChecked():
                layer, copied = dp.add_fields_to_points(pts, results, unit, with_name=bool(name_field))
                fn = dp.field_names(unit)
                if copied:
                    msgs.append(
                        f"Layer titik tidak bisa diubah, dibuat salinan '{layer.name()}' "
                        f"dengan field {fn['dist']}, {fn['status']}, {fn['pos']}."
                    )
                else:
                    msgs.append(f"Field {fn['dist']}, {fn['status']}, {fn['pos']} ditambahkan ke '{layer.name()}'.")

            text = "\n".join(msgs)
            self.lbl_result.setText(text)
            QMessageBox.information(self, "Selesai", text)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal menghitung jarak:\n{exc}")
        finally:
            QApplication.restoreOverrideCursor()
            self.progress.setVisible(False)
            self.btn_run.setEnabled(True)

    def _on_progress(self, done, total):
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        QApplication.processEvents()

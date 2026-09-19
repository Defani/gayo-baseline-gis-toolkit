# -*- coding: utf-8 -*-
"""Halaman sidebar "GEE Connect": hubungkan Google Earth Engine, cari dataset,
lalu tambahkan sebagai layer tiles ke peta atau impor tabel sebagai vektor."""
import json
import os

from qgis.PyQt.QtCore import QDate, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRasterLayer,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.gui import QgsMapLayerComboBox

from . import gee_connector as gee
from . import ows_utils

_SETTINGS_PROJECT = "AgroforestryGisToolkit/gee_project"
_LAYER_PROP = "agroforestry_gee"   # custom property di layer: parameter untuk "Segarkan"
_MAX_LIST = 300

# Preset visualisasi (bands, min, max, palette)
VIS_PRESETS = [
    ("(default / isi sendiri)", {}),
    ("Sentinel-2 True Color", {"bands": "B4,B3,B2", "min": "0", "max": "3000", "palette": ""}),
    ("Sentinel-2 False Color (NIR)", {"bands": "B8,B4,B3", "min": "0", "max": "4000", "palette": ""}),
    ("Elevasi (DEM, 1 band)", {"bands": "", "min": "0", "max": "3000",
                               "palette": "006633,E5FFCC,662A00,D8D8D8,F5F5F5"}),
]

KIND_ITEMS = [("Otomatis", None), ("Image", "image"),
              ("ImageCollection", "image_collection"), ("Tabel / FeatureCollection", "table")]


class GeeDialog(QWidget):
    TITLE = "GEE Connect (Google Earth Engine)"
    finished = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(400)
        self._connected = False
        self._build_ui()
        if gee.ee_available():
            self._fill_list("")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        if not gee.ee_available():
            warn = QLabel(gee.INSTALL_HINT)
            warn.setWordWrap(True)
            warn.setTextInteractionFlags(Qt.TextSelectableByMouse)
            warn.setStyleSheet("color: #b00;")
            layout.addWidget(warn)
            layout.addStretch()
            return

        # --- Koneksi ---
        conn = QGroupBox("Koneksi")
        cl = QVBoxLayout(conn)
        row = QHBoxLayout()
        row.addWidget(QLabel("Cloud Project ID"))
        self.txt_project = QLineEdit(QgsSettings().value(_SETTINGS_PROJECT, "", type=str))
        self.txt_project.setPlaceholderText("mis. my-gee-project")
        row.addWidget(self.txt_project, 1)
        cl.addLayout(row)
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self._connect)
        cl.addWidget(self.btn_connect)
        self.lbl_conn = QLabel("Belum terhubung.")
        self.lbl_conn.setWordWrap(True)
        cl.addWidget(self.lbl_conn)
        layout.addWidget(conn)

        # --- Dataset ---
        ds = QGroupBox("Dataset")
        dl = QVBoxLayout(ds)
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Cari katalog... (mis. sentinel, landsat, srtm, forest)")
        self.txt_search.textChanged.connect(self._fill_list)
        dl.addWidget(self.txt_search)
        self.list_ds = QListWidget()
        self.list_ds.setMinimumHeight(140)
        self.list_ds.currentItemChanged.connect(self._on_dataset_selected)
        dl.addWidget(self.list_ds)
        self.lbl_ds = QLabel("")
        self.lbl_ds.setWordWrap(True)
        dl.addWidget(self.lbl_ds)
        form = QFormLayout()
        self.txt_asset = QLineEdit()
        self.txt_asset.setPlaceholderText("atau ketik Asset ID, mis. projects/xxx/assets/yyy")
        form.addRow("Asset ID", self.txt_asset)
        self.combo_kind = QComboBox()
        for label, _v in KIND_ITEMS:
            self.combo_kind.addItem(label)
        form.addRow("Jenis", self.combo_kind)
        self.txt_layer_name = QLineEdit()
        self.txt_layer_name.setPlaceholderText("(opsional) nama layer di QGIS")
        form.addRow("Nama layer", self.txt_layer_name)
        dl.addLayout(form)
        layout.addWidget(ds)

        # --- Filter ---
        flt = QGroupBox("Filter (ImageCollection)")
        fl = QFormLayout(flt)
        today = QDate.currentDate()
        self.chk_date = QCheckBox("Filter tanggal")
        self.chk_date.setChecked(True)
        fl.addRow(self.chk_date)
        self.date_start = QDateEdit(today.addYears(-1))
        self.date_start.setCalendarPopup(True)
        self.date_end = QDateEdit(today)
        self.date_end.setCalendarPopup(True)
        fl.addRow("Mulai", self.date_start)
        fl.addRow("Sampai", self.date_end)
        self.combo_cloud = QComboBox()
        self.combo_cloud.setEditable(True)
        self.combo_cloud.addItems(["", "CLOUDY_PIXEL_PERCENTAGE", "CLOUD_COVER"])
        self.combo_cloud.setToolTip("Nama properti awan; kosongkan untuk tidak memfilter")
        fl.addRow("Properti awan", self.combo_cloud)
        self.spin_cloud = QSpinBox()
        self.spin_cloud.setRange(0, 100)
        self.spin_cloud.setValue(20)
        self.spin_cloud.setSuffix(" %")
        fl.addRow("Awan maks", self.spin_cloud)
        self.combo_comp = QComboBox()
        self.combo_comp.addItems(gee.COMPOSITES)
        fl.addRow("Komposit", self.combo_comp)
        self.combo_area = QgsMapLayerComboBox()
        self.combo_area.setAllowEmptyLayer(True)
        self.combo_area.setCurrentIndex(0)
        fl.addRow("Batasi ke extent layer", self.combo_area)
        self.chk_clip = QCheckBox("Clip hasil ke extent layer (kotak)")
        fl.addRow(self.chk_clip)
        layout.addWidget(flt)

        # --- Visualisasi ---
        vis = QGroupBox("Visualisasi")
        vl = QFormLayout(vis)
        self.combo_preset = QComboBox()
        for label, _v in VIS_PRESETS:
            self.combo_preset.addItem(label)
        self.combo_preset.currentIndexChanged.connect(self._on_preset)
        vl.addRow("Preset", self.combo_preset)
        self.txt_bands = QLineEdit()
        self.txt_bands.setPlaceholderText("mis. B4,B3,B2")
        vl.addRow("Bands", self.txt_bands)
        self.txt_min = QLineEdit()
        self.txt_max = QLineEdit()
        vl.addRow("Min", self.txt_min)
        vl.addRow("Max", self.txt_max)
        self.txt_palette = QLineEdit()
        self.txt_palette.setPlaceholderText("mis. 000000,FFFFFF (1 band)")
        vl.addRow("Palette", self.txt_palette)
        self.txt_color = QLineEdit("FF0000")
        vl.addRow("Warna (tabel)", self.txt_color)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 10)
        self.spin_width.setValue(2)
        vl.addRow("Tebal garis (tabel)", self.spin_width)
        layout.addWidget(vis)

        # --- Aksi ---
        self.btn_add = QPushButton("Tambahkan ke Peta (tiles)")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.clicked.connect(self._add_tiles)
        layout.addWidget(self.btn_add)
        self.btn_vec = QPushButton(f"Impor tabel sebagai layer vektor (maks {gee.MAX_VECTOR_FEATURES} fitur)")
        self.btn_vec.clicked.connect(self._import_vector)
        layout.addWidget(self.btn_vec)
        self.btn_refresh = QPushButton("Segarkan layer GEE di proyek (token tiles kedaluwarsa)")
        self.btn_refresh.clicked.connect(self._refresh_layers)
        layout.addWidget(self.btn_refresh)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        layout.addStretch()

    # ------------------------------------------------------------- koneksi
    def _connect(self):
        project = self.txt_project.text().strip()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            try:
                gee.initialize(project)
            except Exception as exc:  # noqa: BLE001
                if not gee.is_auth_error(exc):
                    raise
                QApplication.restoreOverrideCursor()
                ans = QMessageBox.question(
                    self, "Login Earth Engine",
                    "Belum login ke Google Earth Engine.\nBuka browser untuk login sekarang?",
                )
                QApplication.setOverrideCursor(Qt.WaitCursor)
                if ans != QMessageBox.Yes:
                    return
                gee.authenticate()
                gee.initialize(project)
        except Exception as exc:  # noqa: BLE001
            self._connected = False
            hint = ""
            if not project:
                hint = "\n\nIsi Cloud Project ID (project Google Cloud yang sudah mengaktifkan Earth Engine)."
            self.lbl_conn.setText("Gagal terhubung.")
            QMessageBox.critical(self, "Error", f"Gagal terhubung ke Earth Engine:\n{exc}{hint}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self._connected = True
        QgsSettings().setValue(_SETTINGS_PROJECT, project)
        self.lbl_conn.setText(f"Terhubung{' - project ' + project if project else ''}.")

    def _ensure_connected(self):
        if not self._connected:
            QMessageBox.information(self, "Info", "Klik Connect dulu.")
            return False
        return True

    # ------------------------------------------------------------- dataset
    def _fill_list(self, text):
        rows = gee.search_catalog(text)
        self.list_ds.blockSignals(True)
        self.list_ds.clear()
        for r in rows[:_MAX_LIST]:
            item = QListWidgetItem(f"{r['title']}  [{r['id']}]")
            item.setData(Qt.UserRole, r)
            self.list_ds.addItem(item)
        self.list_ds.blockSignals(False)
        extra = f" (menampilkan {_MAX_LIST} pertama)" if len(rows) > _MAX_LIST else ""
        self.lbl_ds.setText(f"{len(rows)} dataset{extra}.")

    def _on_dataset_selected(self, item, _prev=None):
        if item is None:
            return
        r = item.data(Qt.UserRole)
        self.txt_asset.setText(r["id"])
        kind = gee.kind_from_catalog_type(r["type"])
        for i, (_label, v) in enumerate(KIND_ITEMS):
            if v == kind:
                self.combo_kind.setCurrentIndex(i)
                break
        self.lbl_ds.setText(
            f"{r['provider']} \u00b7 {r['type']} \u00b7 {r['start_date']} \u2192 {r['end_date'] or 'sekarang'}\n"
            f"{r['asset_url']}"
        )
        if not self.txt_layer_name.text().strip():
            self.txt_layer_name.setPlaceholderText(r["title"])

    def _on_preset(self):
        preset = VIS_PRESETS[self.combo_preset.currentIndex()][1]
        if not preset:
            return
        self.txt_bands.setText(preset.get("bands", ""))
        self.txt_min.setText(preset.get("min", ""))
        self.txt_max.setText(preset.get("max", ""))
        self.txt_palette.setText(preset.get("palette", ""))

    # ---------------------------------------------------------- kumpulkan
    def _resolve_kind(self, asset_id):
        kind = KIND_ITEMS[self.combo_kind.currentIndex()][1]
        if kind:
            return kind
        kind = gee.detect_kind(asset_id)
        if not kind:
            raise ValueError(
                "Jenis asset tidak terdeteksi. Pilih jenisnya manual (Image / ImageCollection / Tabel)."
            )
        return kind

    def _bbox(self):
        layer = self.combo_area.currentLayer()
        if layer is None:
            return None
        xf = QgsCoordinateTransform(
            layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance().transformContext(),
        )
        r = xf.transformBoundingBox(layer.extent())
        return [r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum()]

    @staticmethod
    def _num(text):
        text = text.strip()
        if not text:
            return None
        return float(text.replace(",", "."))

    def _collect_params(self):
        asset_id = self.txt_asset.text().strip()
        if not asset_id:
            raise ValueError("Pilih dataset dari daftar atau isi Asset ID.")
        kind = self._resolve_kind(asset_id)

        vis = {}
        bands = [b.strip() for b in self.txt_bands.text().split(",") if b.strip()]
        if bands:
            vis["bands"] = bands
        vmin, vmax = self._num(self.txt_min.text()), self._num(self.txt_max.text())
        if vmin is not None:
            vis["min"] = vmin
        if vmax is not None:
            vis["max"] = vmax
        palette = [p.strip().lstrip("#") for p in self.txt_palette.text().split(",") if p.strip()]
        if palette:
            vis["palette"] = palette

        params = {
            "asset_id": asset_id,
            "kind": kind,
            "start": self.date_start.date().toString("yyyy-MM-dd") if self.chk_date.isChecked() else "",
            "end": self.date_end.date().toString("yyyy-MM-dd") if self.chk_date.isChecked() else "",
            "cloud_prop": self.combo_cloud.currentText().strip(),
            "cloud_max": self.spin_cloud.value(),
            "composite": self.combo_comp.currentText(),
            "bbox": self._bbox(),
            "clip": self.chk_clip.isChecked(),
            "vis": vis,
            "table_style": {"color": self.txt_color.text().strip() or "FF0000",
                            "width": self.spin_width.value()},
        }
        return params

    def _layer_name(self, params):
        name = self.txt_layer_name.text().strip() or self.txt_layer_name.placeholderText()
        if not name or name.startswith("(opsional"):
            name = params["asset_id"]
        return f"GEE - {name}"

    # ---------------------------------------------------------------- aksi
    def _add_tiles(self):
        if not self._ensure_connected():
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            params = self._collect_params()
            url = gee.get_tile_url(params)
            layer = QgsRasterLayer(ows_utils.xyz_uri(url, 0, 22), self._layer_name(params), "wms")
            if not layer.isValid():
                raise RuntimeError("QGIS tidak bisa membuka URL tiles dari Earth Engine.")
            layer.setCustomProperty(_LAYER_PROP, json.dumps(params))
            QgsProject.instance().addMapLayer(layer)
            self.lbl_status.setText(f"'{layer.name()}' ditambahkan ke peta.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal menambahkan layer GEE:\n{exc}")
        finally:
            QApplication.restoreOverrideCursor()

    def _import_vector(self):
        if not self._ensure_connected():
            return
        try:
            params = self._collect_params()
            if params["kind"] != "table":
                raise ValueError("Impor vektor hanya untuk asset jenis Tabel / FeatureCollection.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Info", str(exc))
            return

        path, _ = QFileDialog.getSaveFileName(self, "Simpan layer vektor", "", "GeoJSON (*.geojson)")
        if not path:
            return
        if not path.lower().endswith(".geojson"):
            path += ".geojson"

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            geojson, total, truncated = gee.fetch_geojson(params)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(geojson, f)
            layer = QgsVectorLayer(path, self._layer_name(params), "ogr")
            if not layer.isValid():
                raise RuntimeError("File GeoJSON hasil unduhan tidak bisa dibuka.")
            QgsProject.instance().addMapLayer(layer)
            msg = f"{len(geojson['features'])} fitur diimpor ke {os.path.basename(path)}."
            if truncated:
                msg += f"\nAsset punya {total} fitur; hanya {gee.MAX_VECTOR_FEATURES} pertama yang diambil. Persempit dengan 'Batasi ke extent layer'."
                QMessageBox.warning(self, "Sebagian diimpor", msg)
            self.lbl_status.setText(msg)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal mengimpor tabel:\n{exc}")
        finally:
            QApplication.restoreOverrideCursor()

    def _refresh_layers(self):
        if not self._ensure_connected():
            return
        done, failed = 0, []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for layer in QgsProject.instance().mapLayers().values():
                raw = layer.customProperty(_LAYER_PROP)
                if not raw:
                    continue
                try:
                    url = gee.get_tile_url(json.loads(raw))
                    layer.setDataSource(ows_utils.xyz_uri(url, 0, 22), layer.name(), "wms")
                    layer.triggerRepaint()
                    done += 1
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{layer.name()}: {exc}")
        finally:
            QApplication.restoreOverrideCursor()
        msg = f"{done} layer GEE disegarkan."
        if failed:
            msg += "\nGagal:\n" + "\n".join(failed)
            QMessageBox.warning(self, "Sebagian gagal", msg)
        self.lbl_status.setText(msg)

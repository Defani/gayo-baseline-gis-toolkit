# -*- coding: utf-8 -*-
"""Halaman sidebar "Add Layer": tambah layer web (XYZ / WMTS / WMS / WFS)
atau file dengan format apa pun yang dikenali QGIS (GDAL/OGR/mesh/point cloud).
Menggantikan menu "Add DEM Data".
"""
import os

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

try:  # QGIS >= 3.22
    from qgis.core import QgsProviderRegistry, QgsProviderSublayerDetails
    _HAS_SUBLAYER_API = hasattr(QgsProviderRegistry, "querySublayers")
except ImportError:  # pragma: no cover
    _HAS_SUBLAYER_API = False

from . import ows_utils

# Sumber tiles XYZ siap pakai (bisa diedit setelah dipilih).
XYZ_PRESETS = [
    ("(isi sendiri)", ""),
    ("OpenStreetMap", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
    ("OpenTopoMap", "https://tile.opentopomap.org/{z}/{x}/{y}.png"),
    ("Esri World Imagery",
     "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"),
    ("CARTO Positron", "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"),
]

SERVICE_TYPES = ["XYZ Tiles", "WMTS", "WMS", "WFS", "ArcGIS REST (Feature/Map Server)"]
ARCGIS_TYPE = "ArcGIS REST (Feature/Map Server)"


def _add_file_layers(path, project=None, collect=None):
    """Muat semua sublayer dari satu file/folder. Return (jumlah_ditambah, pesan_error).
    Kalau `collect` (list) diberikan, layer yang ditambahkan dimasukkan ke sana."""
    project = project or QgsProject.instance()
    base = os.path.splitext(os.path.basename(path.rstrip("/\\")))[0]
    added = 0

    if _HAS_SUBLAYER_API:
        subs = QgsProviderRegistry.instance().querySublayers(path)
        opts = QgsProviderSublayerDetails.LayerOptions(project.transformContext())
        for sub in subs:
            layer = sub.toLayer(opts)
            if layer is None or not layer.isValid():
                continue
            layer.setName(base if len(subs) == 1 else f"{base} - {sub.name()}")
            project.addMapLayer(layer)
            if collect is not None:
                collect.append(layer)
            added += 1
        if added:
            return added, ""

    # Fallback (QGIS lama / format yang tidak terdeteksi querySublayers)
    layer = QgsVectorLayer(path, base, "ogr")
    if not layer.isValid():
        layer = QgsRasterLayer(path, base)
    if layer.isValid():
        project.addMapLayer(layer)
        if collect is not None:
            collect.append(layer)
        return 1, ""
    return 0, "format tidak dikenali / file tidak bisa dibuka"


def make_vector_service_layer(kind, url, name, typename="", srs="EPSG:4326"):
    """Layer vektor dari layanan web. kind: 'WFS' atau ARCGIS_TYPE. Return QgsVectorLayer (cek isValid)."""
    if kind == "WFS":
        if not typename:
            raise ValueError("Isi Type name layer WFS.")
        return QgsVectorLayer(ows_utils.wfs_uri(url, typename, srs), name, "WFS")
    return QgsVectorLayer(ows_utils.arcgis_uri(url, srs), name, "arcgisfeatureserver")


class VectorServiceDialog(QDialog):
    """Dialog kecil: tambah layer vektor dari WFS / ArcGIS REST (dipakai menu Distance Analysis)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Layer vektor dari layanan web")
        self.layer = None
        form = QFormLayout(self)
        self.combo_kind = QComboBox()
        self.combo_kind.addItems(["WFS", ARCGIS_TYPE])
        self.combo_kind.currentIndexChanged.connect(self._toggle)
        form.addRow("Jenis", self.combo_kind)
        self.txt_url = QLineEdit()
        self.txt_url.setMinimumWidth(320)
        form.addRow("URL", self.txt_url)
        self.lbl_type = QLabel("Type name")
        self.txt_type = QLineEdit()
        self.txt_type.setPlaceholderText("mis. ns:nama_layer")
        form.addRow(self.lbl_type, self.txt_type)
        self.txt_srs = QLineEdit("EPSG:4326")
        form.addRow("CRS", self.txt_srs)
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Nama layer di QGIS")
        form.addRow("Nama", self.txt_name)
        hint = QLabel(
            "WFS: URL layanan GeoServer/MapServer (.../wfs).\n"
            "ArcGIS REST: URL layer, mis. .../MapServer/0 atau .../FeatureServer/0."
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        btn = QPushButton("Tambahkan")
        btn.clicked.connect(self._accept)
        form.addRow(btn)

    def _toggle(self):
        is_wfs = self.combo_kind.currentText() == "WFS"
        self.lbl_type.setVisible(is_wfs)
        self.txt_type.setVisible(is_wfs)

    def _accept(self):
        url = self.txt_url.text().strip()
        if not url:
            QMessageBox.information(self, "Info", "Isi URL dulu.")
            return
        kind = self.combo_kind.currentText()
        name = self.txt_name.text().strip() or kind
        try:
            layer = make_vector_service_layer(
                kind, url, name, self.txt_type.text().strip(), self.txt_srs.text().strip() or "EPSG:4326"
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", str(exc))
            return
        if not layer.isValid():
            QMessageBox.warning(self, "Layer tidak valid",
                                "QGIS tidak bisa membuka layanan ini. Periksa URL / type name / CRS.")
            return
        QgsProject.instance().addMapLayer(layer)
        self.layer = layer
        self.accept()


class AddLayerDialog(QWidget):
    TITLE = "Add Layer (Tiles / Web Service / File)"
    finished = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(380)
        self._wmts_layers = []
        self._wms_layers = []
        self._build_ui()
        self._on_type_changed()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_service_tab(), "Tiles / Web")
        tabs.addTab(self._build_file_tab(), "File")
        layout.addWidget(tabs)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

    def _build_service_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)

        form = QFormLayout()
        self.combo_type = QComboBox()
        self.combo_type.addItems(SERVICE_TYPES)
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Jenis", self.combo_type)

        self.lbl_preset = QLabel("Preset")
        self.combo_preset = QComboBox()
        for name, _url in XYZ_PRESETS:
            self.combo_preset.addItem(name)
        self.combo_preset.currentIndexChanged.connect(self._on_preset)
        form.addRow(self.lbl_preset, self.combo_preset)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Nama layer di QGIS")
        form.addRow("Nama", self.txt_name)

        self.txt_url = QLineEdit()
        form.addRow("URL", self.txt_url)
        v.addLayout(form)

        # --- XYZ zoom ---
        self.box_xyz = QGroupBox("Zoom")
        xl = QHBoxLayout(self.box_xyz)
        self.spin_zmin = QSpinBox()
        self.spin_zmin.setRange(0, 24)
        self.spin_zmax = QSpinBox()
        self.spin_zmax.setRange(0, 24)
        self.spin_zmax.setValue(19)
        xl.addWidget(QLabel("Min"))
        xl.addWidget(self.spin_zmin)
        xl.addWidget(QLabel("Max"))
        xl.addWidget(self.spin_zmax)
        xl.addStretch()
        v.addWidget(self.box_xyz)

        # --- WMTS / WMS ---
        self.box_ows = QGroupBox("Layer layanan")
        ol = QVBoxLayout(self.box_ows)
        self.btn_caps = QPushButton("Ambil daftar layer (GetCapabilities)")
        self.btn_caps.clicked.connect(self._fetch_capabilities)
        ol.addWidget(self.btn_caps)
        of = QFormLayout()
        self.combo_ows_layer = QComboBox()
        self.combo_ows_layer.setEditable(True)  # boleh diketik manual
        self.combo_ows_layer.currentIndexChanged.connect(self._on_ows_layer_changed)
        of.addRow("Layer", self.combo_ows_layer)
        self.lbl_tms = QLabel("Tile matrix set")
        self.combo_tms = QComboBox()
        self.combo_tms.setEditable(True)
        self.combo_tms.currentIndexChanged.connect(self._on_tms_changed)
        of.addRow(self.lbl_tms, self.combo_tms)
        self.combo_crs = QComboBox()
        self.combo_crs.setEditable(True)
        of.addRow("CRS", self.combo_crs)
        self.combo_format = QComboBox()
        self.combo_format.setEditable(True)
        of.addRow("Format", self.combo_format)
        self.lbl_style = QLabel("Style")
        self.combo_style = QComboBox()
        self.combo_style.setEditable(True)
        of.addRow(self.lbl_style, self.combo_style)
        ol.addLayout(of)
        v.addWidget(self.box_ows)

        # --- WFS ---
        self.box_wfs = QGroupBox("Layer vektor")
        wl = QFormLayout(self.box_wfs)
        self.txt_typename = QLineEdit()
        self.txt_typename.setPlaceholderText("mis. ns:nama_layer")
        self.lbl_typename = QLabel("Type name")
        wl.addRow(self.lbl_typename, self.txt_typename)
        self.txt_wfs_srs = QLineEdit("EPSG:4326")
        wl.addRow("CRS", self.txt_wfs_srs)
        v.addWidget(self.box_wfs)

        btn_add = QPushButton("Tambahkan ke Peta")
        btn_add.setMinimumHeight(30)
        btn_add.clicked.connect(self._add_service_layer)
        v.addWidget(btn_add)
        v.addStretch()
        return page

    def _build_file_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        info = QLabel(
            "Pilih file apa saja: shapefile, GeoPackage, GeoJSON, KML/KMZ, GPX, CSV, "
            "GeoTIFF/DEM, ECW, JP2, NetCDF, DXF, LAS/LAZ, dan format lain yang dikenali "
            "QGIS. File dengan banyak sublayer (mis. GeoPackage) ditambahkan semuanya."
        )
        info.setWordWrap(True)
        v.addWidget(info)

        btn_files = QPushButton("Pilih File...")
        btn_files.setMinimumHeight(30)
        btn_files.clicked.connect(self._add_files)
        v.addWidget(btn_files)

        btn_dir = QPushButton("Pilih Folder (mis. .gdb, folder raster)...")
        btn_dir.clicked.connect(self._add_folder)
        v.addWidget(btn_dir)
        v.addStretch()
        return page

    # ------------------------------------------------------- service logic
    def _type(self):
        return self.combo_type.currentText()

    def _on_type_changed(self):
        t = self._type()
        is_xyz, is_wmts, is_wms, is_wfs = t == "XYZ Tiles", t == "WMTS", t == "WMS", t == "WFS"
        is_arc = t == ARCGIS_TYPE
        self.lbl_preset.setVisible(is_xyz)
        self.combo_preset.setVisible(is_xyz)
        self.box_xyz.setVisible(is_xyz)
        self.box_ows.setVisible(is_wmts or is_wms)
        self.lbl_tms.setVisible(is_wmts)
        self.combo_tms.setVisible(is_wmts)
        self.lbl_style.setVisible(is_wmts)
        self.combo_style.setVisible(is_wmts)
        self.box_wfs.setVisible(is_wfs or is_arc)
        self.lbl_typename.setVisible(is_wfs)
        self.txt_typename.setVisible(is_wfs)
        self.txt_url.setPlaceholderText(
            "https://.../{z}/{x}/{y}.png" if is_xyz else "https://.../service (atau URL GetCapabilities)"
        )

    def _on_preset(self):
        idx = self.combo_preset.currentIndex()
        name, url = XYZ_PRESETS[idx]
        if url:
            self.txt_url.setText(url)
            if not self.txt_name.text().strip():
                self.txt_name.setText(name)

    def _fetch_capabilities(self):
        import requests  # sudah dipakai kobo_connector

        url = self.txt_url.text().strip()
        if not url:
            QMessageBox.information(self, "Info", "Isi URL layanan dulu.")
            return
        service = "WMTS" if self._type() == "WMTS" else "WMS"
        cap_url = ows_utils.capabilities_url(url, service)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            resp = requests.get(cap_url, timeout=30)
            resp.raise_for_status()
            if service == "WMTS":
                self._wmts_layers = ows_utils.parse_wmts(resp.content)
                entries = [(l["title"], l["id"]) for l in self._wmts_layers]
            else:
                self._wms_layers, self._wms_formats = ows_utils.parse_wms(resp.content)
                entries = [(l["title"], l["id"]) for l in self._wms_layers]
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal membaca capabilities:\n{exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.combo_ows_layer.blockSignals(True)
        self.combo_ows_layer.clear()
        for title, ident in entries:
            self.combo_ows_layer.addItem(f"{title}  [{ident}]" if title != ident else ident, ident)
        self.combo_ows_layer.blockSignals(False)
        self.lbl_status.setText(f"{len(entries)} layer ditemukan.")
        self._on_ows_layer_changed()

    def _current_ows_id(self):
        idx = self.combo_ows_layer.currentIndex()
        data = self.combo_ows_layer.itemData(idx) if idx >= 0 else None
        if data and self.combo_ows_layer.currentText() == self.combo_ows_layer.itemText(idx):
            return data
        return self.combo_ows_layer.currentText().strip()  # diketik manual

    def _on_ows_layer_changed(self):
        ident = self._current_ows_id()
        if self._type() == "WMTS":
            info = next((l for l in self._wmts_layers if l["id"] == ident), None)
            if not info:
                return
            self.combo_tms.blockSignals(True)
            self.combo_tms.clear()
            for tms, crs in info["tilematrixsets"]:
                self.combo_tms.addItem(tms, crs)
            self.combo_tms.blockSignals(False)
            self._fill(self.combo_format, info["formats"])
            self._fill(self.combo_style, info["styles"])
            self._on_tms_changed()
        else:
            info = next((l for l in self._wms_layers if l["id"] == ident), None)
            if not info:
                return
            self._fill(self.combo_crs, info["crs"])
            self._fill(self.combo_format, getattr(self, "_wms_formats", ["image/png"]))

    def _on_tms_changed(self):
        crs = self.combo_tms.currentData()
        if crs:
            self._fill(self.combo_crs, [crs])

    @staticmethod
    def _fill(combo, values):
        combo.clear()
        combo.addItems([v for v in values if v])

    def _add_service_layer(self):
        t = self._type()
        url = self.txt_url.text().strip()
        name = self.txt_name.text().strip() or t
        if not url:
            QMessageBox.information(self, "Info", "Isi URL dulu.")
            return

        try:
            if t == "XYZ Tiles":
                uri = ows_utils.xyz_uri(url, self.spin_zmin.value(), self.spin_zmax.value())
                layer = QgsRasterLayer(uri, name, "wms")
            elif t == "WMTS":
                ident = self._current_ows_id()
                tms = self.combo_tms.currentText().strip()
                if not ident or not tms:
                    QMessageBox.information(
                        self, "Info", "Isi Layer dan Tile matrix set (atau klik 'Ambil daftar layer')."
                    )
                    return
                uri = ows_utils.wmts_uri(
                    url, ident, tms,
                    self.combo_crs.currentText().strip() or "EPSG:3857",
                    self.combo_format.currentText().strip() or "image/png",
                    self.combo_style.currentText().strip() or "default",
                )
                layer = QgsRasterLayer(uri, name, "wms")
            elif t == "WMS":
                ident = self._current_ows_id()
                if not ident:
                    QMessageBox.information(
                        self, "Info", "Isi nama Layer (atau klik 'Ambil daftar layer')."
                    )
                    return
                uri = ows_utils.wms_uri(
                    url, ident,
                    self.combo_crs.currentText().strip() or "EPSG:4326",
                    self.combo_format.currentText().strip() or "image/png",
                )
                layer = QgsRasterLayer(uri, name, "wms")
            else:  # WFS / ArcGIS REST
                if t == "WFS" and not self.txt_typename.text().strip():
                    QMessageBox.information(self, "Info", "Isi Type name layer WFS.")
                    return
                layer = make_vector_service_layer(
                    t, url, name, self.txt_typename.text().strip(),
                    self.txt_wfs_srs.text().strip() or "EPSG:4326",
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal membuat layer:\n{exc}")
            return

        if not layer.isValid():
            QMessageBox.warning(
                self, "Layer tidak valid",
                "QGIS tidak bisa membuka layer ini. Periksa URL, nama layer, tile matrix set, "
                "dan CRS. Untuk WMTS/WMS pakai tombol 'Ambil daftar layer' supaya isiannya otomatis.",
            )
            return
        QgsProject.instance().addMapLayer(layer)
        self.lbl_status.setText(f"'{name}' ditambahkan ke peta.")

    # ---------------------------------------------------------- file logic
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Pilih file", "", "Semua file (*)")
        self._load_paths(paths)

    def _add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Pilih folder")
        if path:
            self._load_paths([path])

    def _load_paths(self, paths):
        if not paths:
            return
        total, failed = 0, []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for path in paths:
                try:
                    n, err = _add_file_layers(path)
                except Exception as exc:  # noqa: BLE001
                    n, err = 0, str(exc)
                total += n
                if not n:
                    failed.append(f"{os.path.basename(path)}: {err}")
        finally:
            QApplication.restoreOverrideCursor()

        msg = f"{total} layer ditambahkan."
        if failed:
            msg += "\nGagal:\n" + "\n".join(failed)
            QMessageBox.warning(self, "Sebagian gagal", msg)
        self.lbl_status.setText(msg)

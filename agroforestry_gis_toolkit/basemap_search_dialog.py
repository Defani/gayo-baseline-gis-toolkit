# -*- coding: utf-8 -*-
"""Embedded "Basemap Search (QMS)" page for the Agroforestry sidebar panel.

Reuses the separately installed "QuickMapServices" plugin's own data (bundled
basemaps: OSM, Google, Bing, Esri, USGS, Yandex, etc., plus anything the user
added themselves) and its own ``add_layer_to_map`` helper - this page is just
a quick search + add-to-map front end so a basemap can be added without
opening QGIS's Web > QuickMapServices menu.
"""
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from quick_map_services.data_sources_list import DataSourcesList
    from quick_map_services.qgis_map_helpers import add_layer_to_map
    _QMS_AVAILABLE = True
except ImportError:
    _QMS_AVAILABLE = False


class BasemapSearchDialog(QWidget):
    """Sidebar page: search QMS basemaps and add one straight to the map."""

    TITLE = "Basemap Search (QMS)"
    finished = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(380)
        self._data_sources = {}  # id -> DataSourceInfo
        self._build_ui()
        if _QMS_AVAILABLE:
            self._reload_sources()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        if not _QMS_AVAILABLE:
            warn = QLabel(
                "Plugin 'QuickMapServices' belum terpasang/aktif. Install dulu "
                "plugin itu, lalu buka panel ini lagi."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #b00;")
            layout.addWidget(warn)
            layout.addStretch()
            return

        search_row = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Cari basemap... (mis. OSM, Bing, Esri)")
        self.txt_search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.txt_search, 1)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._reload_sources)
        search_row.addWidget(btn_refresh)
        layout.addLayout(search_row)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._add_selected)
        layout.addWidget(self.list_widget, 1)

        btn_add = QPushButton("Tambahkan ke Peta")
        btn_add.clicked.connect(self._add_selected)
        layout.addWidget(btn_add)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

    def _reload_sources(self):
        try:
            self._data_sources = dict(DataSourcesList().data_sources)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal memuat daftar basemap:\n{exc}")
            return

        items = sorted(
            self._data_sources.values(),
            key=lambda ds: (str(ds.group or ""), str(ds.alias or "")),
        )
        self.list_widget.clear()
        for ds in items:
            label = f"{ds.group or '-'} / {ds.alias or ds.id}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, ds.id)
            self.list_widget.addItem(item)

        self.lbl_status.setText(f"{len(items)} basemap tersedia.")

    def _apply_filter(self, text):
        text = text.strip().lower()
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            item.setHidden(bool(text) and text not in item.text().lower())

    def _add_selected(self):
        item = self.list_widget.currentItem()
        if item is None or item.isHidden():
            QMessageBox.information(self, "Info", "Pilih satu basemap dari daftar dulu.")
            return
        ds_id = item.data(Qt.UserRole)
        ds = self._data_sources.get(ds_id)
        if ds is None:
            QMessageBox.warning(self, "Error", "Basemap ini tidak ditemukan lagi, klik Refresh.")
            return
        try:
            ok = add_layer_to_map(ds)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal menambahkan basemap:\n{exc}")
            return
        if ok:
            self.lbl_status.setText(f"'{ds.alias}' ditambahkan ke peta.")
        else:
            self.lbl_status.setText(f"'{ds.alias}' gagal ditambahkan.")

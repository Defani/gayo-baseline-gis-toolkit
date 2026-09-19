# -*- coding: utf-8 -*-
"""Embedded "Foto Explorer (Kobo)" page for the Agroforestry sidebar panel.

Kobo stores each photo as just a filename on the submission plus a separate
authenticated download URL in "_attachments" - there is no built-in way to
see "where was this photo taken" on a map. This page:

  1. Fetches submissions for a chosen form.
  2. Turns every occurrence of a chosen image field into a point, positioned
     using the geopoint field that shares the same repeat instance (e.g. the
     photo of plot #2 gets plot #2's GPS, not plot #1's).
  3. Lets you select a point on the map and open the actual photo, which is
     downloaded on demand (Kobo attachments need authentication) and opened
     with the system's default image viewer.
"""
import os
import tempfile

from qgis.core import QgsProject
from qgis.PyQt.QtCore import QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import kobo_connector as kobo


class FotoExplorerDialog(QWidget):
    TITLE = "Foto Explorer (Kobo)"
    finished = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(420)
        self._forms = []
        self._layer = None
        self._cache_dir = os.path.join(tempfile.gettempdir(), "agroforestry_foto_explorer")
        os.makedirs(self._cache_dir, exist_ok=True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        conn_box = QGroupBox("KoboToolbox connection")
        conn_layout = QVBoxLayout(conn_box)

        conn_layout.addWidget(QLabel("API URL"))
        self.txt_api_url = QLineEdit("kf.kobotoolbox.org")
        conn_layout.addWidget(self.txt_api_url)

        conn_layout.addWidget(QLabel("Username"))
        self.txt_username = QLineEdit()
        conn_layout.addWidget(self.txt_username)

        conn_layout.addWidget(QLabel("Password"))
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        conn_layout.addWidget(self.txt_password)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self._connect)
        conn_layout.addWidget(self.btn_connect)

        layout.addWidget(conn_box)

        form_box = QGroupBox("Form, Foto & Titik GPS")
        form_layout = QVBoxLayout(form_box)

        form_layout.addWidget(QLabel("Form"))
        self.combo_forms = QComboBox()
        self.combo_forms.setEnabled(False)
        self.combo_forms.currentIndexChanged.connect(self._on_form_change)
        form_layout.addWidget(self.combo_forms)

        form_layout.addWidget(QLabel("Field foto (image)"))
        self.combo_image_fields = QComboBox()
        self.combo_image_fields.setEnabled(False)
        form_layout.addWidget(self.combo_image_fields)

        form_layout.addWidget(QLabel("Field GPS (dipakai kalau satu repeat sama foto)"))
        self.combo_geo_fields = QComboBox()
        self.combo_geo_fields.setEnabled(False)
        form_layout.addWidget(self.combo_geo_fields)

        layout.addWidget(form_box)

        self.btn_load = QPushButton("Fetch & Show Photos on Map")
        self.btn_load.setEnabled(False)
        self.btn_load.clicked.connect(self._load_photos)
        layout.addWidget(self.btn_load)

        open_box = QGroupBox("Buka Foto")
        open_layout = QVBoxLayout(open_box)
        info = QLabel(
            "Klik/select satu titik di layer foto pada peta, lalu klik tombol "
            "di bawah - foto akan diunduh sementara dan dibuka di image viewer."
        )
        info.setWordWrap(True)
        open_layout.addWidget(info)
        self.btn_open_photo = QPushButton("Buka Foto dari Titik Terpilih")
        self.btn_open_photo.clicked.connect(self._open_selected_photo)
        open_layout.addWidget(self.btn_open_photo)
        layout.addWidget(open_box)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        layout.addStretch()

    def _creds(self):
        return (
            self.txt_api_url.text().strip(),
            self.txt_username.text().strip(),
            self.txt_password.text(),
        )

    def _connect(self):
        api_url, username, password = self._creds()
        if not api_url or not username:
            QMessageBox.warning(self, "Warning", "Isi API URL dan Username dulu.")
            return
        try:
            self.btn_connect.setEnabled(False)
            self.btn_connect.setText("Connecting...")
            self.btn_connect.repaint()
            self._forms = kobo.list_forms(api_url, username, password)
            self.combo_forms.clear()
            if not self._forms:
                QMessageBox.information(self, "Info", "Tidak ada form dengan data geo di akun ini.")
                return
            for f in self._forms:
                self.combo_forms.addItem(f["name"], f["uid"])
            self.combo_forms.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal connect ke KoboToolbox:\n{exc}")
        finally:
            self.btn_connect.setEnabled(True)
            self.btn_connect.setText("Connect")

    def _on_form_change(self):
        asset_uid = self.combo_forms.currentData()
        if not asset_uid:
            return
        api_url, username, password = self._creds()
        try:
            self.combo_image_fields.clear()
            self.combo_geo_fields.clear()

            image_fields = kobo.get_image_fields(api_url, username, password, asset_uid)
            geo_fields = kobo.get_geo_fields(api_url, username, password, asset_uid)

            if not image_fields:
                self.combo_image_fields.setEnabled(False)
                self.btn_load.setEnabled(False)
                QMessageBox.information(self, "Info", "Form ini tidak punya field foto (image).")
                return
            if not geo_fields:
                self.combo_geo_fields.setEnabled(False)
                self.btn_load.setEnabled(False)
                QMessageBox.information(self, "Info", "Form ini tidak punya field GPS.")
                return

            self.combo_image_fields.addItems(image_fields)
            self.combo_image_fields.setEnabled(True)
            self.combo_geo_fields.addItems(geo_fields)
            self.combo_geo_fields.setEnabled(True)
            self.btn_load.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal ambil field form:\n{exc}")

    def _load_photos(self):
        api_url, username, password = self._creds()
        asset_uid = self.combo_forms.currentData()
        asset_name = self.combo_forms.currentText()
        image_field = self.combo_image_fields.currentText()
        geo_field = self.combo_geo_fields.currentText()
        if not (asset_uid and image_field and geo_field):
            return
        try:
            self.btn_load.setEnabled(False)
            self.btn_load.setText("Fetching data...")
            self.btn_load.repaint()

            submissions = kobo.fetch_submissions(api_url, username, password, asset_uid)
            if not submissions:
                QMessageBox.information(self, "Info", "Form ini belum ada data submission.")
                return

            fc = kobo.build_photo_feature_collection(submissions, image_field, geo_field)
            if not fc["features"]:
                QMessageBox.information(
                    self, "Info",
                    "Tidak ada foto yang bisa dipetakan (cek field foto & GPS yang dipilih).",
                )
                return

            layer_name = f"Foto_{asset_name}_{image_field}".replace(" ", "_")
            self._layer = kobo.load_features_to_layer(fc, layer_name)

            self.lbl_status.setText(
                f"{len(fc['features'])} foto dimuat sebagai layer '{layer_name}'. "
                "Select satu titik lalu klik 'Buka Foto dari Titik Terpilih'."
            )
            self.finished.emit()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal mengambil data Kobo:\n{exc}")
        finally:
            self.btn_load.setEnabled(True)
            self.btn_load.setText("Fetch & Show Photos on Map")

    def _open_selected_photo(self):
        layer = self._layer or self.iface.activeLayer()
        if layer is None or "download_url" not in layer.fields().names():
            QMessageBox.warning(
                self, "Layer salah",
                "Pilih/aktifkan layer hasil 'Fetch & Show Photos on Map' dulu.",
            )
            return

        selected = list(layer.getSelectedFeatures())
        if not selected:
            QMessageBox.information(self, "Info", "Select dulu satu titik foto di peta.")
            return
        feat = selected[0]

        url = feat["download_url"]
        filename = feat["filename"] or "foto.jpg"
        if not url:
            QMessageBox.warning(self, "Tidak ada URL", "Foto ini tidak punya URL unduhan yang cocok.")
            return

        api_url, username, password = self._creds()
        dest_path = os.path.join(self._cache_dir, f"{feat['submission_id']}_{filename}")
        try:
            if not os.path.exists(dest_path):
                self.lbl_status.setText("Mengunduh foto...")
                self.lbl_status.repaint()
                kobo.download_attachment(username, password, url, dest_path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(dest_path))
            self.lbl_status.setText(f"Foto dibuka: {filename}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Gagal mengunduh/membuka foto:\n{exc}")

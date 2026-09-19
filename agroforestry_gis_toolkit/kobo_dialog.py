# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QMessageBox,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal

from . import kobo_connector as kobo


class KoboDialog(QWidget):
    TITLE = "Kobo Connect"
    finished = pyqtSignal()
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(420)
        self._forms = []
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

        form_box = QGroupBox("Form & Geo Field")
        form_layout = QVBoxLayout(form_box)
        form_layout.addWidget(QLabel("Select form"))
        self.combo_forms = QComboBox()
        self.combo_forms.setEnabled(False)
        self.combo_forms.currentIndexChanged.connect(self._on_form_change)
        form_layout.addWidget(self.combo_forms)

        form_layout.addWidget(QLabel("Geo field"))
        self.combo_geo_fields = QComboBox()
        self.combo_geo_fields.setEnabled(False)
        form_layout.addWidget(self.combo_geo_fields)
        layout.addWidget(form_box)

        self.btn_load = QPushButton("Fetch & Show on Map")
        self.btn_load.setEnabled(False)
        self.btn_load.clicked.connect(self._load_data)
        layout.addWidget(self.btn_load)

        hint = QLabel(
            "Tip: once the data is loaded as a layer, use the \"Export Data\" "
            "menu to save it to Excel/GeoJSON/CSV."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _creds(self):
        return (
            self.txt_api_url.text().strip(),
            self.txt_username.text().strip(),
            self.txt_password.text(),
        )

    def _connect(self):
        api_url, username, password = self._creds()
        if not api_url or not username:
            QMessageBox.warning(self, "Warning", "Fill in the API URL and Username first.")
            return
        try:
            self.btn_connect.setEnabled(False)
            self.btn_connect.setText("Connecting...")
            self.btn_connect.repaint()
            self._forms = kobo.list_forms(api_url, username, password)
            self.combo_forms.clear()
            if not self._forms:
                QMessageBox.information(
                    self, "Info", "No forms with geo data found on this account."
                )
                return
            for f in self._forms:
                self.combo_forms.addItem(f["name"], f["uid"])
            self.combo_forms.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Failed to connect to KoboToolbox:\n{exc}")
        finally:
            self.btn_connect.setEnabled(True)
            self.btn_connect.setText("Connect")

    def _on_form_change(self):
        asset_uid = self.combo_forms.currentData()
        if not asset_uid:
            return
        api_url, username, password = self._creds()
        try:
            self.combo_geo_fields.clear()
            fields = kobo.get_geo_fields(api_url, username, password, asset_uid)
            if fields:
                self.combo_geo_fields.addItems(fields)
                self.combo_geo_fields.setEnabled(True)
                self.btn_load.setEnabled(True)
            else:
                self.combo_geo_fields.setEnabled(False)
                self.btn_load.setEnabled(False)
                QMessageBox.information(self, "Info", "This form has no geo field.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Failed to fetch geo fields:\n{exc}")

    def _load_data(self):
        api_url, username, password = self._creds()
        asset_uid = self.combo_forms.currentData()
        asset_name = self.combo_forms.currentText()
        geo_field = self.combo_geo_fields.currentText()
        if not (asset_uid and geo_field):
            return
        try:
            self.btn_load.setEnabled(False)
            self.btn_load.setText("Fetching data...")
            self.btn_load.repaint()

            submissions = kobo.fetch_submissions(api_url, username, password, asset_uid)
            if not submissions:
                QMessageBox.information(self, "Info", "This form has no submission data.")
                return

            fc = kobo.build_feature_collection(submissions, geo_field)
            layer_name = f"Kobo_{asset_name}".replace(" ", "_")
            kobo.load_features_to_layer(fc, layer_name)

            QMessageBox.information(
                self, "Done", f"{len(fc['features'])} records loaded successfully as layer '{layer_name}'."
            )
            self.finished.emit()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Failed to fetch Kobo data:\n{exc}")
        finally:
            self.btn_load.setEnabled(True)
            self.btn_load.setText("Fetch & Show on Map")

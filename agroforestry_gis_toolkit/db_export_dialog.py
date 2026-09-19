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
    QPushButton,
    QMessageBox,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.gui import QgsMapLayerComboBox
from qgis.core import QgsMapLayerProxyModel

from . import db_exporter


class DbExportDialog(QWidget):
    TITLE = "Export to Database (PostGIS / Supabase)"
    finished = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(420)
        self._build_ui()
        self._refresh_saved_connections()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layer_box = QGroupBox("Select layer")
        layer_layout = QVBoxLayout(layer_box)
        self.combo_layer = QgsMapLayerComboBox()
        self.combo_layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        layer_layout.addWidget(self.combo_layer)
        layout.addWidget(layer_box)

        conn_box = QGroupBox("Database connection")
        conn_layout = QVBoxLayout(conn_box)

        conn_layout.addWidget(QLabel("Saved QGIS connection (optional)"))
        row_saved = QHBoxLayout()
        self.combo_saved = QComboBox()
        self.combo_saved.addItem("(Fill in manually below)")
        self.combo_saved.currentIndexChanged.connect(self._apply_saved_connection)
        btn_refresh = QPushButton("\u21bb")
        btn_refresh.setFixedWidth(28)
        btn_refresh.setToolTip("Refresh list of saved connections")
        btn_refresh.clicked.connect(self._refresh_saved_connections)
        row_saved.addWidget(self.combo_saved, 1)
        row_saved.addWidget(btn_refresh)
        conn_layout.addLayout(row_saved)

        conn_layout.addWidget(QLabel("Host"))
        self.txt_host = QLineEdit()
        conn_layout.addWidget(self.txt_host)

        row_port_db = QHBoxLayout()
        port_col = QVBoxLayout()
        port_col.addWidget(QLabel("Port"))
        self.txt_port = QLineEdit("5432")
        port_col.addWidget(self.txt_port)
        db_col = QVBoxLayout()
        db_col.addWidget(QLabel("Database"))
        self.txt_database = QLineEdit("postgres")
        db_col.addWidget(self.txt_database)
        row_port_db.addLayout(port_col)
        row_port_db.addLayout(db_col)
        conn_layout.addLayout(row_port_db)

        conn_layout.addWidget(QLabel("Username"))
        self.txt_username = QLineEdit()
        conn_layout.addWidget(self.txt_username)

        conn_layout.addWidget(QLabel("Password"))
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        conn_layout.addWidget(self.txt_password)

        conn_layout.addWidget(QLabel("SSL mode"))
        self.combo_ssl = QComboBox()
        self.combo_ssl.addItems(["prefer", "require", "allow", "disable"])
        conn_layout.addWidget(self.combo_ssl)

        layout.addWidget(conn_box)

        dest_box = QGroupBox("Destination table")
        dest_layout = QVBoxLayout(dest_box)
        dest_layout.addWidget(QLabel("Schema"))
        self.txt_schema = QLineEdit("public")
        dest_layout.addWidget(self.txt_schema)
        dest_layout.addWidget(QLabel("Table name"))
        self.txt_table = QLineEdit()
        dest_layout.addWidget(self.txt_table)
        self.chk_overwrite = QCheckBox("Overwrite table if it already exists")
        dest_layout.addWidget(self.chk_overwrite)
        layout.addWidget(dest_box)

        hint = QLabel(
            "Long/repeated field names (e.g. from Kobo forms) are shortened "
            "automatically so they don't collide once Postgres truncates them."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(hint)

        self.btn_run = QPushButton("Send to Database")
        self.btn_run.clicked.connect(self._run)
        layout.addWidget(self.btn_run)

    def _refresh_saved_connections(self):
        current = self.combo_saved.currentText()
        self.combo_saved.blockSignals(True)
        self.combo_saved.clear()
        self.combo_saved.addItem("(Fill in manually below)")
        try:
            for name in db_exporter.list_saved_connections():
                self.combo_saved.addItem(name)
        except Exception:  # noqa: BLE001
            pass
        idx = self.combo_saved.findText(current)
        self.combo_saved.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_saved.blockSignals(False)

    def _apply_saved_connection(self):
        name = self.combo_saved.currentText()
        if not name or name.startswith("("):
            return
        try:
            defaults = db_exporter.get_connection_defaults(name)
        except Exception:  # noqa: BLE001
            return
        if defaults.get("host"):
            self.txt_host.setText(str(defaults["host"]))
        if defaults.get("port"):
            self.txt_port.setText(str(defaults["port"]))
        if defaults.get("database"):
            self.txt_database.setText(str(defaults["database"]))

    def _run(self):
        layer = self.combo_layer.currentLayer()
        if layer is None:
            QMessageBox.warning(self, "Warning", "Select the layer to send.")
            return

        host = self.txt_host.text().strip()
        port = self.txt_port.text().strip() or "5432"
        database = self.txt_database.text().strip()
        username = self.txt_username.text().strip()
        password = self.txt_password.text()
        schema = self.txt_schema.text().strip() or "public"
        table = self.txt_table.text().strip()
        sslmode = self.combo_ssl.currentText()
        overwrite = self.chk_overwrite.isChecked()

        if not (host and database and username and table):
            QMessageBox.warning(
                self, "Warning",
                "Fill in at least Host, Database, Username, and Table name."
            )
            return

        try:
            self.btn_run.setEnabled(False)
            self.btn_run.setText("Sending...")
            self.btn_run.repaint()
            mapping, count = db_exporter.export_layer_to_postgis(
                layer, host, port, database, username, password,
                schema, table, sslmode=sslmode, overwrite=overwrite,
            )
            QMessageBox.information(
                self, "Done",
                f"{count} feature(s) sent successfully to "
                f"{schema}.{table}."
            )
            self.finished.emit()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Failed to send data to database:\n{exc}")
        finally:
            self.btn_run.setEnabled(True)
            self.btn_run.setText("Send to Database")

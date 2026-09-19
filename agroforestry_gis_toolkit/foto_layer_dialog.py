# -*- coding: utf-8 -*-
"""Halaman sidebar "Foto di Layer (Kobo)".

Untuk layer titik hasil survei Kobo yang punya kolom foto + URL-nya
(mis. geo2_foto_1 / geo2_foto_1_URL), halaman ini:

  1. mengunduh semua foto di latar belakang (terautentikasi, paralel),
     diperkecil ke ukuran layar dan diputar sesuai orientasi EXIF;
  2. menambah kolom virtual `path_<kolom foto>` berisi lokasi file foto lokal
     (tidak mengubah data sumber - aman untuk GeoJSON/CSV/layer memori);
  3. mengatur layer supaya foto tampil di titiknya:
       - Map Tip: arahkan kursor ke titik -> foto muncul
       - Form atribut / Identify: pratinjau foto pada kolom path_*

Foto disimpan di folder project (default: <folder project>/foto_kobo), jadi
unduhan berikutnya hanya mengambil foto yang belum ada.
"""
import os

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsEditorWidgetSetup,
    QgsExpression,
    QgsFeatureRequest,
    QgsField,
    QgsFields,
    QgsMapLayerProxyModel,
    QgsMessageLog,
    QgsProject,
    QgsSettings,
    QgsTask,
)
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtCore import QStandardPaths, QVariant, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import foto_layer_utils as utils

LOG_TAG = "AgroforestryGisToolkit"
SETTINGS_USER_KEY = "AgroforestryGisToolkit/foto_layer/username"


def _log(msg, level=Qgis.Info):
    QgsMessageLog.logMessage(msg, LOG_TAG, level)


# --------------------------------------------------------------------------
# Tugas latar belakang
# --------------------------------------------------------------------------

class _PhotoDownloadTask(QgsTask):
    """Unduh foto di thread lain supaya QGIS tetap responsif."""

    def __init__(self, description, jobs, username, password, max_px,
                 keep_original, redownload, on_done):
        super().__init__(description, QgsTask.CanCancel)
        self._jobs = jobs
        self._username = username
        self._password = password
        self._max_px = max_px
        self._keep_original = keep_original
        self._redownload = redownload
        self._on_done = on_done
        self.summary = None
        self.error = None

    def run(self):
        try:
            self.summary = utils.run_download_jobs(
                self._jobs,
                self._username,
                self._password,
                max_px=self._max_px,
                keep_original=self._keep_original,
                redownload=self._redownload,
                is_canceled=self.isCanceled,
                on_progress=lambda frac: self.setProgress(frac * 100.0),
            )
            return not self.isCanceled()
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            return False

    def finished(self, result):
        # Dipanggil di thread utama oleh QGIS.
        self._on_done(self, result)


# --------------------------------------------------------------------------
# Pengaturan tampilan layer
# --------------------------------------------------------------------------

def _replace_expression_field(layer, name, expression):
    idx = layer.fields().indexFromName(name)
    if idx >= 0:
        if layer.fields().fieldOrigin(idx) != QgsFields.OriginExpression:
            raise RuntimeError(
                f"Layer sudah punya kolom biasa bernama '{name}'. "
                "Ganti nama kolom itu dulu."
            )
        layer.removeExpressionField(idx)
    layer.addExpressionField(expression, QgsField(name, QVariant.String))
    return layer.fields().indexFromName(name)


def apply_photo_display(layer, slots, id_field, title_field, folder, iface=None):
    """Pasang kolom path_*, widget pratinjau foto, dan Map Tip pada layer."""
    home = QgsProject.instance().homePath() or None
    prefix = utils.folder_expression_prefix(folder, home)

    for slot in slots:
        expr = utils.build_path_expression(slot, id_field, prefix, use_file_exists=True)
        if QgsExpression(expr).hasParserError():
            # QGIS lama tanpa file_exists(): pakai versi tanpa cek berkas.
            expr = utils.build_path_expression(slot, id_field, prefix, use_file_exists=False)
        idx = _replace_expression_field(layer, slot["path_field"], expr)
        if idx >= 0:
            layer.setEditorWidgetSetup(
                idx,
                QgsEditorWidgetSetup(
                    "ExternalResource",
                    {
                        "DocumentViewer": 1,  # 1 = Image
                        "DocumentViewerHeight": 260,
                        "DocumentViewerWidth": 0,
                        "FileWidget": True,
                        "FileWidgetButton": False,
                        "RelativeStorage": 0,
                    },
                ),
            )

    layer.setMapTipTemplate(utils.build_map_tip(slots, title_field))
    layer.triggerRepaint()

    if iface is not None:
        try:
            action = iface.actionMapTips()
            if not action.isChecked():
                action.setChecked(True)
        except Exception:  # noqa: BLE001
            pass
        try:
            iface.setActiveLayer(layer)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# Halaman sidebar
# --------------------------------------------------------------------------

class FotoLayerDialog(QWidget):
    TITLE = "Foto di Layer (Kobo)"
    finished = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setMinimumWidth(420)
        self._task = None
        self._run = None  # konteks proses yang sedang berjalan
        self._slots = []
        self._id_field = None
        self._folder_user_set = False
        self._build_ui()
        self._on_layer_changed(self.combo_layer.currentLayer())

    # --- UI ---

    def _build_ui(self):
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Menampilkan foto survei Kobo langsung di titiknya pada layer QGIS. "
            "Pilih layer titik yang punya kolom foto (mis. geo2_foto_1 dan "
            "geo2_foto_1_URL), lalu klik unduh."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layer_row = QHBoxLayout()
        layer_row.addWidget(QLabel("Layer:"))
        self.combo_layer = QgsMapLayerComboBox()
        self.combo_layer.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.combo_layer.layerChanged.connect(self._on_layer_changed)
        layer_row.addWidget(self.combo_layer, 1)
        layout.addLayout(layer_row)

        self.lbl_detect = QLabel("")
        self.lbl_detect.setWordWrap(True)
        layout.addWidget(self.lbl_detect)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Judul di popup:"))
        self.combo_title = QComboBox()
        title_row.addWidget(self.combo_title, 1)
        layout.addLayout(title_row)

        login_box = QGroupBox("Login KoboToolbox")
        login_layout = QVBoxLayout(login_box)
        note = QLabel("Foto di Kobo perlu login. Kosongkan kalau project Kobo-nya publik.")
        note.setWordWrap(True)
        login_layout.addWidget(note)
        login_layout.addWidget(QLabel("Username"))
        self.txt_username = QLineEdit(QgsSettings().value(SETTINGS_USER_KEY, "", type=str))
        login_layout.addWidget(self.txt_username)
        login_layout.addWidget(QLabel("Password"))
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        login_layout.addWidget(self.txt_password)
        layout.addWidget(login_box)

        opt_box = QGroupBox("Penyimpanan foto")
        opt_layout = QVBoxLayout(opt_box)
        opt_layout.addWidget(QLabel("Folder foto"))
        folder_row = QHBoxLayout()
        self.txt_folder = QLineEdit()
        self.txt_folder.textEdited.connect(self._on_folder_edited)
        folder_row.addWidget(self.txt_folder, 1)
        btn_browse = QPushButton("...")
        btn_browse.setMaximumWidth(32)
        btn_browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(btn_browse)
        opt_layout.addLayout(folder_row)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Ukuran maks. foto (px, sisi terpanjang)"))
        self.spin_max_px = QSpinBox()
        self.spin_max_px.setRange(400, 4000)
        self.spin_max_px.setSingleStep(100)
        self.spin_max_px.setValue(1280)
        size_row.addWidget(self.spin_max_px)
        opt_layout.addLayout(size_row)

        self.chk_keep_original = QCheckBox("Simpan juga foto asli (ukuran penuh, subfolder 'asli')")
        opt_layout.addWidget(self.chk_keep_original)
        self.chk_redownload = QCheckBox("Unduh ulang foto yang sudah ada")
        opt_layout.addWidget(self.chk_redownload)
        layout.addWidget(opt_box)

        self.btn_start = QPushButton("Unduh Foto && Tampilkan di Layer")
        self.btn_start.setMinimumHeight(32)
        self.btn_start.clicked.connect(self._start)
        layout.addWidget(self.btn_start)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        layout.addStretch()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        # Kalau layer aktif adalah layer titik, langsung dipilih.
        active = self.iface.activeLayer()
        if active is not None and active is not self.combo_layer.currentLayer():
            try:
                self.combo_layer.setLayer(active)
            except Exception:  # noqa: BLE001
                pass

    # --- Layer & deteksi ---

    def _on_layer_changed(self, layer):
        self._slots = []
        self._id_field = None
        self.combo_title.clear()
        if layer is None:
            self.lbl_detect.setText("Belum ada layer titik di project.")
            self.btn_start.setEnabled(False)
            return

        names = layer.fields().names()
        self._slots = utils.detect_photo_slots(names)
        self._id_field = utils.pick_id_field(names)

        self.combo_title.addItem("(tanpa judul)", None)
        for n in names:
            if not n.startswith(utils.PATH_FIELD_PREFIX):
                self.combo_title.addItem(n, n)
        guess = utils.pick_title_field(names)
        if guess:
            self.combo_title.setCurrentIndex(max(0, self.combo_title.findData(guess)))

        if not self._slots:
            self.lbl_detect.setText(
                "Kolom foto tidak ditemukan. Layer harus punya pasangan kolom "
                "<nama> dan <nama>_URL (ekspor Kobo dengan media URL), atau "
                "kolom _attachments[n]/download_url (hasil Kobo Connect)."
            )
            self.btn_start.setEnabled(False)
        elif not self._id_field:
            self.lbl_detect.setText("Layer tidak punya kolom _id atau _uuid untuk menamai file foto.")
            self.btn_start.setEnabled(False)
        else:
            rows = self._collect_rows(layer)
            jobs = utils.build_jobs(rows, self._slots, self._id_field, "")
            self.lbl_detect.setText(
                f"Terdeteksi {len(self._slots)} kolom foto "
                f"({', '.join(s['slot'] for s in self._slots)}): "
                f"{len(jobs)} foto pada {len(rows)} titik."
            )
            self.btn_start.setEnabled(True)

        if not self._folder_user_set:
            self.txt_folder.setText(self._default_folder())

    def _collect_rows(self, layer):
        """Ambil nilai kolom yang dibutuhkan (di thread utama)."""
        needed = {self._id_field}
        for s in self._slots:
            needed.add(s["url_field"])
            if s["mime_field"]:
                needed.add(s["mime_field"])
        needed = [n for n in needed if n]
        req = QgsFeatureRequest()
        req.setFlags(QgsFeatureRequest.NoGeometry)
        req.setSubsetOfAttributes(needed, layer.fields())
        return [{n: feat[n] for n in needed} for feat in layer.getFeatures(req)]

    # --- Folder ---

    def _default_folder(self):
        home = QgsProject.instance().homePath()
        if home:
            return os.path.join(home, utils.DEFAULT_SUBFOLDER)
        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        return os.path.join(docs or os.path.expanduser("~"), utils.DEFAULT_SUBFOLDER)

    def _on_folder_edited(self, _text):
        self._folder_user_set = True

    def _browse_folder(self):
        start = self.txt_folder.text() or self._default_folder()
        chosen = QFileDialog.getExistingDirectory(self, "Pilih folder foto", start)
        if chosen:
            self.txt_folder.setText(chosen)
            self._folder_user_set = True

    # --- Proses ---

    def _start(self):
        layer = self.combo_layer.currentLayer()
        if layer is None or not self._slots or not self._id_field:
            return
        if self._task is not None:
            QMessageBox.information(self, "Info", "Pengunduhan masih berjalan.")
            return

        folder = self.txt_folder.text().strip()
        if not folder:
            QMessageBox.warning(self, "Folder kosong", "Isi folder penyimpanan foto dulu.")
            return
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Folder tidak bisa dibuat:\n{exc}")
            return

        rows = self._collect_rows(layer)
        jobs = utils.build_jobs(rows, self._slots, self._id_field, folder)
        if not jobs:
            QMessageBox.information(self, "Info", "Tidak ada URL foto pada layer ini.")
            return

        username = self.txt_username.text().strip()
        QgsSettings().setValue(SETTINGS_USER_KEY, username)

        self._run = {
            "layer_id": layer.id(),
            "slots": list(self._slots),
            "id_field": self._id_field,
            "title_field": self.combo_title.currentData(),
            "folder": folder,
            "total": len(jobs),
        }
        task = _PhotoDownloadTask(
            "Unduh foto Kobo",
            jobs,
            username,
            self.txt_password.text(),
            self.spin_max_px.value(),
            self.chk_keep_original.isChecked(),
            self.chk_redownload.isChecked(),
            self._on_task_done,
        )
        task.progressChanged.connect(lambda v: self.progress.setValue(int(v)))
        self._task = task

        self.btn_start.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self.lbl_status.setText(f"Mengunduh {len(jobs)} foto di latar belakang...")
        QgsApplication.taskManager().addTask(task)

    def _on_task_done(self, task, ok):
        run = self._run or {}
        self._task = None
        self._run = None
        self.btn_start.setEnabled(bool(self._slots and self._id_field))
        self.progress.hide()

        if task.error:
            self.lbl_status.setText(f"Gagal: {task.error}")
            QMessageBox.critical(self, "Error", f"Gagal mengunduh foto:\n{task.error}")
            return
        summary = task.summary or {"ok": 0, "skipped": 0, "failed": [], "auth_failed": False}

        for label, msg in summary["failed"]:
            _log(f"Foto {label} gagal: {msg}", Qgis.Warning)

        if summary["auth_failed"]:
            self.lbl_status.setText("Akses ditolak.")
            QMessageBox.warning(
                self, "Akses ditolak",
                "Username/password salah, atau akun ini tidak punya akses ke data Kobo tersebut.",
            )
            return
        if not summary["ok"] and not summary["skipped"]:
            if not ok:
                self.lbl_status.setText("Dibatalkan.")
            else:
                first = summary["failed"][0] if summary["failed"] else ("-", "tidak diketahui")
                self.lbl_status.setText(
                    f"Semua {len(summary['failed'])} foto gagal diunduh "
                    f"(mis. {first[0]}: {first[1]}). Detail ada di panel Log Messages "
                    f"tab '{LOG_TAG}'."
                )
            return

        layer = QgsProject.instance().mapLayer(run.get("layer_id", ""))
        if layer is None:
            self.lbl_status.setText("Layer sudah dihapus dari project; foto tetap tersimpan di folder.")
            return

        try:
            apply_photo_display(
                layer, run["slots"], run["id_field"], run["title_field"],
                run["folder"], self.iface,
            )
        except Exception as exc:  # noqa: BLE001
            self.lbl_status.setText(f"Foto terunduh, tapi gagal mengatur layer: {exc}")
            QMessageBox.critical(self, "Error", f"Gagal mengatur tampilan layer:\n{exc}")
            return

        msg = f"{summary['ok']} foto baru diunduh"
        if summary["skipped"]:
            msg += f", {summary['skipped']} sudah ada"
        if summary["failed"]:
            first = summary["failed"][0]
            msg += f", {len(summary['failed'])} gagal (mis. {first[0]}: {first[1]})"
        if not ok:
            msg += " (dibatalkan sebelum selesai)"
        msg += (
            ". Arahkan kursor ke titik untuk melihat foto (layer harus terpilih di "
            "panel Layers), atau klik titik dengan Identify. Simpan project (.qgz) "
            "supaya pengaturan foto ikut tersimpan."
        )
        self.lbl_status.setText(msg)

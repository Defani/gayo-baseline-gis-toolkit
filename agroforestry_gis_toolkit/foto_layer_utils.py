# -*- coding: utf-8 -*-
"""Logika murni untuk fitur "Foto di Layer (Kobo)".

Modul ini sengaja TIDAK mengimpor qgis.core, supaya mudah dites di luar QGIS.
Isinya:

  * deteksi kolom foto pada layer hasil survei Kobo
  * pembuat ekspresi QGIS (path foto lokal) dan template map tip
  * pekerja unduh foto (paralel, terautentikasi) + perkecil ukuran foto

Dua format layer yang dikenali:

  A. Ekspor CSV/GeoJSON Kobo dengan "media URL":
         geo2_foto_1      = 1789425909018.jpg          (nama file)
         geo2_foto_1_URL  = https://kf.../attachments/attXXXX/
  B. Layer hasil "Kobo Connect" (API):
         _attachments[1]/download_url, _attachments[1]/filename, ...
"""
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

PATH_FIELD_PREFIX = "path_"
DEFAULT_SUBFOLDER = "foto_kobo"
ORIGINAL_SUBFOLDER = "asli"


# --------------------------------------------------------------------------
# Deteksi kolom
# --------------------------------------------------------------------------

def is_blank(value):
    """True untuk None / NULL QGIS / string kosong."""
    if value is None:
        return True
    is_null = getattr(value, "isNull", None)
    if callable(is_null):
        try:
            if is_null():
                return True
        except Exception:  # noqa: BLE001
            pass
    return str(value).strip() in ("", "NULL")


def safe_name(text):
    """Nama aman untuk file/kolom: huruf, angka, garis bawah, minus."""
    return re.sub(r"[^0-9A-Za-z_-]+", "_", str(text)).strip("_") or "x"


_ATT_RE = re.compile(r"^_attachments\[(\d+)\]/download_url$")


def detect_photo_slots(field_names):
    """Cari "slot" foto pada daftar nama kolom.

    Mengembalikan list dict:
      {"slot": "geo2_foto_1", "url_field": "geo2_foto_1_URL",
       "mime_field": None|str, "path_field": "path_geo2_foto_1"}
    Format A (kolom *_URL) diprioritaskan; format B dipakai hanya jika A tidak ada.
    """
    names = list(field_names)
    nameset = set(names)

    slots = []
    for name in names:
        if name.endswith("_URL") and len(name) > 4 and name[:-4] in nameset:
            base = name[:-4]
            slots.append({
                "slot": safe_name(base),
                "url_field": name,
                "mime_field": None,
                "path_field": PATH_FIELD_PREFIX + safe_name(base),
            })
    if slots:
        return slots

    for name in names:
        m = _ATT_RE.match(name)
        if not m:
            continue
        idx = m.group(1)
        mime = f"_attachments[{idx}]/mimetype"
        slots.append({
            "slot": f"att_{idx}",
            "url_field": name,
            "mime_field": mime if mime in nameset else None,
            "path_field": f"{PATH_FIELD_PREFIX}att_{idx}",
        })
    slots.sort(key=lambda s: int(s["slot"].split("_")[1]))
    return slots


def pick_id_field(field_names):
    """Kolom yang dipakai sebagai kunci nama file foto."""
    for candidate in ("_id", "_uuid"):
        if candidate in field_names:
            return candidate
    return None


def pick_title_field(field_names):
    """Tebakan kolom untuk judul popup (nama responden / ID)."""
    for candidate in ("a1_nama", "nama", "nama_lengkap", "kode_petani", "_id"):
        if candidate in field_names:
            return candidate
    return None


# --------------------------------------------------------------------------
# Ekspresi QGIS
# --------------------------------------------------------------------------

def q_ident(name):
    """Kutip nama kolom untuk ekspresi QGIS."""
    return '"' + str(name).replace('"', '""') + '"'


def q_str(text):
    """Kutip string literal untuk ekspresi QGIS."""
    return "'" + str(text).replace("'", "''") + "'"


def folder_expression_prefix(folder, project_home=None):
    """Ekspresi QGIS untuk folder foto, diakhiri '/'.

    Kalau folder ada di dalam folder project, dipakai @project_folder supaya
    project tetap jalan setelah dipindah/di-zip. Kalau tidak, path absolut.
    """
    folder_n = os.path.normpath(folder)
    if project_home:
        home_n = os.path.normpath(project_home)
        a, b = os.path.normcase(folder_n), os.path.normcase(home_n)
        if a == b or a.startswith(b + os.sep):
            rel = os.path.relpath(folder_n, home_n)
            rel = "" if rel == "." else rel.replace("\\", "/") + "/"
            return f"@project_folder || {q_str('/' + rel)}"
    return q_str(folder_n.replace("\\", "/").rstrip("/") + "/")


def file_stem(id_value, slot):
    return f"{safe_name(id_value)}_{slot}"


def build_path_expression(slot, id_field, prefix_expr, use_file_exists=True):
    """Ekspresi kolom virtual: path foto lokal, atau NULL kalau tidak ada."""
    path = f"{prefix_expr} || {q_ident(id_field)} || {q_str('_' + slot['slot'] + '.jpg')}"
    url = q_ident(slot["url_field"])
    cond = f"{url} IS NOT NULL AND {url} <> ''"
    if use_file_exists:
        cond += f" AND file_exists({path})"
    return f"CASE WHEN {cond} THEN {path} END"


def build_map_tip(slots, title_field=None, photo_width=220):
    """Template HTML map tip QGIS ([% ekspresi %])."""
    parts = ['<div style="font-family:sans-serif">']
    if title_field:
        parts.append(f"<b>[% coalesce({q_ident(title_field)}, '') %]</b><br/>")
    for s in slots:
        p = q_ident(s["path_field"])
        img = (
            "'<img style=\"margin:2px\" src=\"' || "
            "if(left(" + p + ", 1) = '/', 'file://', 'file:///') || "
            "replace(" + p + ", ' ', '%20') || "
            f"'\" width=\"{photo_width}\"/>'"
        )
        parts.append(f"[% if({p} IS NOT NULL, {img}, '') %]")
    coalesced = ", ".join(q_ident(s["path_field"]) for s in slots)
    parts.append(
        f"[% if(coalesce({coalesced}) IS NULL, '<i>(belum ada foto terunduh)</i>', '') %]"
    )
    parts.append("</div>")
    return "\n".join(parts)


# --------------------------------------------------------------------------
# Daftar pekerjaan unduh
# --------------------------------------------------------------------------

def build_jobs(rows, slots, id_field, folder):
    """rows: list dict {nama_kolom: nilai} (diambil di main thread).

    Mengembalikan list job {url, dest, orig_dest, label}. Baris tanpa ID atau
    tanpa URL http(s) dilewati; slot yang mimetype-nya bukan image juga.
    """
    jobs = []
    for row in rows:
        id_value = row.get(id_field)
        if is_blank(id_value):
            continue
        if isinstance(id_value, float) and id_value.is_integer():
            id_value = int(id_value)  # 867933462.0 -> 867933462 (cocok dgn ekspresi QGIS)
        for s in slots:
            url = row.get(s["url_field"])
            if is_blank(url) or not str(url).strip().lower().startswith("http"):
                continue
            if s["mime_field"]:
                mime = row.get(s["mime_field"])
                if not is_blank(mime) and not str(mime).lower().startswith("image"):
                    continue
            stem = file_stem(id_value, s["slot"])
            jobs.append({
                "url": str(url).strip(),
                "dest": os.path.join(folder, stem + ".jpg"),
                "orig_dest": os.path.join(folder, ORIGINAL_SUBFOLDER, stem + ".jpg"),
                "label": stem,
            })
    return jobs


# --------------------------------------------------------------------------
# Unduh + perkecil
# --------------------------------------------------------------------------

class DownloadError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _fetch_bytes(session, url, timeout=60):
    resp = session.get(url, timeout=timeout)
    if resp.status_code in (401, 403):
        raise DownloadError(f"HTTP {resp.status_code} (akses ditolak)", resp.status_code)
    resp.raise_for_status()
    ctype = resp.headers.get("Content-Type", "").lower()
    if "json" in ctype:
        # Sebagian server mengembalikan metadata lampiran, bukan berkas.
        try:
            real = resp.json().get("download_url")
        except Exception:  # noqa: BLE001
            real = None
        if not real or real == url:
            raise DownloadError("server mengembalikan JSON, bukan gambar")
        resp = session.get(real, timeout=timeout)
        resp.raise_for_status()
    return resp.content


def _save_resized(data, dest, max_px, keep_original_path=None):
    """Simpan data gambar sebagai JPEG berukuran maks max_px (sisi terpanjang).

    Orientasi EXIF diterapkan (foto HP sering disimpan miring + tag EXIF; tag
    itu hilang saat disimpan ulang, jadi rotasinya harus 'dibakar' dulu).
    """
    from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from qgis.PyQt.QtGui import QImageReader

    ba = QByteArray(data)
    buf = QBuffer(ba)
    buf.open(QIODevice.ReadOnly)
    reader = QImageReader(buf)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        raise DownloadError("berkas bukan gambar yang valid")
    if max_px and max(img.width(), img.height()) > max_px:
        img = img.scaled(max_px, max_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    if not img.save(tmp, "JPG", 85):
        raise DownloadError("gagal menyimpan JPEG")
    os.replace(tmp, dest)

    if keep_original_path:
        os.makedirs(os.path.dirname(keep_original_path), exist_ok=True)
        with open(keep_original_path, "wb") as f:
            f.write(data)


def run_download_jobs(jobs, username, password, max_px=1280, keep_original=False,
                      redownload=False, is_canceled=None, on_progress=None,
                      workers=4, session_factory=None):
    """Unduh semua job secara paralel. Mengembalikan ringkasan dict:
    {"ok": n, "skipped": n, "failed": [(label, pesan)], "auth_failed": bool}
    """
    import requests

    def make_session():
        if session_factory:
            return session_factory()
        s = requests.Session()
        if username:
            s.auth = (username, password)
        return s

    total = len(jobs)
    lock = threading.Lock()
    state = {"done": 0, "ok": 0, "skipped": 0, "failed": [], "auth": 0}

    def work(job):
        if is_canceled and is_canceled():
            return
        try:
            if not redownload and os.path.exists(job["dest"]):
                with lock:
                    state["skipped"] += 1
            else:
                data = _fetch_bytes(make_session(), job["url"])
                _save_resized(data, job["dest"], max_px,
                              job["orig_dest"] if keep_original else None)
                with lock:
                    state["ok"] += 1
        except DownloadError as exc:
            with lock:
                state["failed"].append((job["label"], str(exc)))
                if exc.status in (401, 403):
                    state["auth"] += 1
        except Exception as exc:  # noqa: BLE001
            with lock:
                state["failed"].append((job["label"], str(exc)))
        finally:
            with lock:
                state["done"] += 1
                frac = state["done"] / total if total else 1.0
            if on_progress:
                on_progress(frac)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, jobs))

    return {
        "ok": state["ok"],
        "skipped": state["skipped"],
        "failed": state["failed"],
        "auth_failed": bool(state["auth"]) and state["auth"] == len(state["failed"])
        and state["ok"] == 0 and state["skipped"] == 0,
    }

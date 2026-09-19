# -*- coding: utf-8 -*-
"""Konektor Google Earth Engine (tanpa Qt).

Pendekatan sama seperti geemap (ee_tile_layers): objek EE -> getMapId() ->
URL tiles XYZ, yang lalu ditambahkan ke QGIS sebagai layer raster. Tidak
memakai paket geemap sendiri (berat & butuh ipyleaflet dsb.), cukup
`earthengine-api`.
"""
import csv
import os
from datetime import date, timedelta

_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "gee_catalog.csv")

COMPOSITES = ["median", "mean", "min", "max", "mosaic", "first"]
MAX_VECTOR_FEATURES = 5000

_ee = None  # modul ee (lazy import)


def ee_available():
    try:
        import ee  # noqa: F401
        return True
    except ImportError:
        return False


def _get_ee():
    global _ee
    if _ee is None:
        import ee
        _ee = ee
    return _ee


INSTALL_HINT = (
    "Paket 'earthengine-api' belum terpasang di Python QGIS.\n"
    "Windows: buka OSGeo4W Shell lalu jalankan\n"
    "    python -m pip install earthengine-api\n"
    "Lalu restart QGIS."
)


# ---------------------------------------------------------------------------
# Koneksi
# ---------------------------------------------------------------------------
def initialize(project=None):
    """Inisialisasi EE dengan kredensial tersimpan. Raise kalau belum login."""
    ee = _get_ee()
    project = (project or "").strip() or None
    ee.Initialize(project=project)
    return project


def authenticate():
    """Login Google (buka browser, terima kode lewat localhost)."""
    ee = _get_ee()
    ee.Authenticate(auth_mode="localhost")


def is_auth_error(exc):
    msg = str(exc).lower()
    return any(k in msg for k in (
        "credentials", "authenticate", "authorize", "not authorized",
        "oauth", "invalid_grant", "reauth",
    ))


# ---------------------------------------------------------------------------
# Katalog dataset (dari geemap)
# ---------------------------------------------------------------------------
_catalog = None


def load_catalog():
    global _catalog
    if _catalog is None:
        with open(_CATALOG_PATH, encoding="utf-8", newline="") as f:
            _catalog = list(csv.DictReader(f))
        for r in _catalog:
            r["_hay"] = " ".join(
                (r["id"], r["title"], r["provider"], r["tags"])
            ).lower()
    return _catalog


def search_catalog(text):
    text = (text or "").strip().lower()
    cat = load_catalog()
    if not text:
        return cat
    words = text.split()
    return [r for r in cat if all(w in r["_hay"] for w in words)]


def kind_from_catalog_type(t):
    return {"image": "image", "image_collection": "image_collection", "table": "table"}.get(t)


def detect_kind(asset_id):
    """Tanya EE tipe asset: 'image' | 'image_collection' | 'table' | None."""
    ee = _get_ee()
    try:
        t = ee.data.getAsset(asset_id).get("type", "")
    except Exception:  # noqa: BLE001
        return None
    return {"IMAGE": "image", "IMAGE_COLLECTION": "image_collection",
            "TABLE": "table"}.get(t)


# ---------------------------------------------------------------------------
# Bangun objek EE dari parameter
# ---------------------------------------------------------------------------
def _region(params):
    ee = _get_ee()
    bbox = params.get("bbox")
    return ee.Geometry.Rectangle(bbox) if bbox else None


def _end_exclusive(end_iso):
    return (date.fromisoformat(end_iso) + timedelta(days=1)).isoformat()


def _clean_vis(vis):
    """Buang nilai kosong supaya getMapId tidak error."""
    out = {}
    for k, v in (vis or {}).items():
        if v in (None, "", [], ()):
            continue
        out[k] = v
    return out


def build_image(params):
    """params -> (ee.Image siap tampil, vis_params).

    params: asset_id, kind, start, end (ISO / ""), cloud_prop, cloud_max,
            composite, bbox [xmin,ymin,xmax,ymax] WGS84 / None, clip (bool),
            vis {bands, min, max, palette}, table_style {color, width}
    """
    ee = _get_ee()
    kind = params["kind"]
    aid = params["asset_id"]
    region = _region(params)
    vis = _clean_vis(params.get("vis"))

    if kind == "table":
        fc = ee.FeatureCollection(aid)
        if region is not None:
            fc = fc.filterBounds(region)
        st = params.get("table_style") or {}
        color = (st.get("color") or "FF0000").lstrip("#")
        image = fc.style(color=color, fillColor=color + "33", width=int(st.get("width") or 2))
        return image, {}

    if kind == "image":
        image = ee.Image(aid)
    elif kind == "image_collection":
        col = ee.ImageCollection(aid)
        if region is not None:
            col = col.filterBounds(region)
        start, end = params.get("start") or "", params.get("end") or ""
        if start and end:
            col = col.filterDate(start, _end_exclusive(end))
        elif start:
            col = col.filterDate(start, "2100-01-01")
        elif end:
            col = col.filterDate("1970-01-01", _end_exclusive(end))
        prop, cmax = params.get("cloud_prop") or "", params.get("cloud_max")
        if prop and cmax is not None:
            col = col.filter(ee.Filter.lte(prop, cmax))
        if col.size().getInfo() == 0:
            raise ValueError(
                "Tidak ada citra setelah difilter (tanggal / area / batas awan). "
                "Longgarkan filternya."
            )
        method = params.get("composite") or "median"
        if method not in COMPOSITES:
            method = "median"
        image = getattr(col, method)()
    else:
        raise ValueError(f"Jenis asset tidak dikenal: {kind}")

    if params.get("clip") and region is not None:
        image = image.clip(region)
    return image, vis


def get_tile_url(params):
    """URL tiles XYZ ({z}/{x}/{y}) untuk parameter layer."""
    image, vis = build_image(params)
    return image.getMapId(vis)["tile_fetcher"].url_format


def fetch_geojson(params):
    """Ambil FeatureCollection sebagai GeoJSON dict. Return (geojson, total, dipotong)."""
    ee = _get_ee()
    fc = ee.FeatureCollection(params["asset_id"])
    region = _region(params)
    if region is not None:
        fc = fc.filterBounds(region)
    total = fc.size().getInfo()
    data = fc.limit(MAX_VECTOR_FEATURES).getInfo()
    geojson = {"type": "FeatureCollection", "features": data.get("features", [])}
    return geojson, total, total > MAX_VECTOR_FEATURES

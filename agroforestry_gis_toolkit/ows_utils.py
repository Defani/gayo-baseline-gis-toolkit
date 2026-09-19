# -*- coding: utf-8 -*-
"""Helper murni-Python (tanpa QGIS) untuk menu "Add Layer".

Isinya: baca GetCapabilities WMTS/WMS, dan susun URI datasource QGIS untuk
XYZ / WMTS / WMS / WFS. Dipisah supaya gampang dites di luar QGIS.
"""
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


# --------------------------------------------------------------------------
# XML helpers (abaikan namespace)
# --------------------------------------------------------------------------
def _tag(el):
    return el.tag.rsplit("}", 1)[-1]


def _children(el, name):
    return [c for c in el if _tag(c) == name]


def _child(el, name):
    for c in el:
        if _tag(c) == name:
            return c
    return None


def _child_text(el, name):
    c = _child(el, name)
    return (c.text or "").strip() if c is not None else ""


def normalize_crs(text):
    """'urn:ogc:def:crs:EPSG::3857' -> 'EPSG:3857', CRS84 -> EPSG:4326."""
    if not text:
        return ""
    s = text.strip()
    if "CRS84" in s.upper():
        return "EPSG:4326"
    m = re.search(r"EPSG:(?:[\d.]*:)?:?(\d+)$", s, re.IGNORECASE)
    if m:
        return "EPSG:" + m.group(1)
    return s


# --------------------------------------------------------------------------
# URL helpers
# --------------------------------------------------------------------------
_OWS_KEYS = {"service", "request", "version"}


def clean_ows_url(url):
    """Buang parameter SERVICE/REQUEST/VERSION dari URL layanan OGC."""
    parts = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
         if k.lower() not in _OWS_KEYS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), ""))


def capabilities_url(url, service):
    """URL GetCapabilities. Kalau user sudah memberi URL lengkap / file .xml, dipakai apa adanya."""
    u = url.strip()
    low = u.lower()
    if "getcapabilities" in low or urlsplit(u).path.lower().endswith(".xml"):
        return u
    base = clean_ows_url(u)
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}SERVICE={service}&REQUEST=GetCapabilities"


def _enc(value):
    return quote(value, safe=":/")


# --------------------------------------------------------------------------
# Parsers
# --------------------------------------------------------------------------
def parse_wmts(xml_bytes):
    """-> list of dict(id, title, formats, styles, tilematrixsets=[(id, crs)])."""
    root = ET.fromstring(xml_bytes)
    contents = _child(root, "Contents")
    if contents is None:
        raise ValueError("Capabilities WMTS tidak valid (tidak ada <Contents>).")

    tms_crs = {}
    for t in _children(contents, "TileMatrixSet"):
        tms_crs[_child_text(t, "Identifier")] = normalize_crs(_child_text(t, "SupportedCRS"))

    layers = []
    for lay in _children(contents, "Layer"):
        ident = _child_text(lay, "Identifier")
        if not ident:
            continue
        styles = [_child_text(s, "Identifier") for s in _children(lay, "Style")]
        default_first = sorted(
            zip(styles, [s.get("isDefault") == "true" for s in _children(lay, "Style")]),
            key=lambda x: not x[1],
        )
        styles = [s for s, _ in default_first if s] or ["default"]
        links = [_child_text(k, "TileMatrixSet") for k in _children(lay, "TileMatrixSetLink")]
        layers.append({
            "id": ident,
            "title": _child_text(lay, "Title") or ident,
            "formats": [(f.text or "").strip() for f in _children(lay, "Format")] or ["image/png"],
            "styles": styles,
            "tilematrixsets": [(k, tms_crs.get(k, "")) for k in links],
        })
    return layers


def parse_wms(xml_bytes):
    """-> (layers, formats). layers = list of dict(id, title, crs)."""
    root = ET.fromstring(xml_bytes)
    cap = _child(root, "Capability")
    if cap is None:
        raise ValueError("Capabilities WMS tidak valid (tidak ada <Capability>).")

    layers = []

    def walk(el, inherited):
        crs = list(inherited)
        for tag in ("CRS", "SRS"):
            for c in _children(el, tag):
                for token in (c.text or "").split():
                    if token not in crs:
                        crs.append(token)
        name = _child_text(el, "Name")
        if name:
            layers.append({"id": name, "title": _child_text(el, "Title") or name, "crs": crs})
        for sub in _children(el, "Layer"):
            walk(sub, crs)

    for top in _children(cap, "Layer"):
        walk(top, [])

    formats = []
    req = _child(cap, "Request")
    getmap = _child(req, "GetMap") if req is not None else None
    if getmap is not None:
        formats = [(f.text or "").strip() for f in _children(getmap, "Format")]
    return layers, formats or ["image/png"]


# --------------------------------------------------------------------------
# URI builders (format datasource QGIS)
# --------------------------------------------------------------------------
def xyz_uri(url, zmin=0, zmax=19):
    return f"type=xyz&url={_enc(url.strip())}&zmax={int(zmax)}&zmin={int(zmin)}"


def wmts_uri(url, layer, tile_matrix_set, crs, fmt="image/png", style="default"):
    return (
        f"contextualWMSLegend=0&crs={crs}&dpiMode=7&featureCount=10&format={fmt}"
        f"&layers={_enc(layer)}&styles={_enc(style)}&tileMatrixSet={_enc(tile_matrix_set)}"
        f"&url={_enc(capabilities_url(url, 'WMTS'))}"
    )


def wms_uri(url, layer, crs="EPSG:4326", fmt="image/png", style=""):
    return (
        f"contextualWMSLegend=0&crs={crs}&dpiMode=7&featureCount=10&format={fmt}"
        f"&layers={_enc(layer)}&styles={_enc(style)}&url={_enc(clean_ows_url(url))}"
    )


def wfs_uri(url, typename, srs="EPSG:4326"):
    base = clean_ows_url(url)
    return (
        f"pagingEnabled='default' preferCoordinatesForWfsT11='false' "
        f"restrictToRequestBBOX='1' srsname='{srs}' typename='{typename}' "
        f"url='{base}' version='auto'"
    )


def arcgis_uri(url, srs="EPSG:4326"):
    """URI provider 'arcgisfeatureserver' untuk layer .../FeatureServer/N atau .../MapServer/N."""
    return f"crs='{srs}' url='{url.strip().split('?')[0].rstrip('/')}'"

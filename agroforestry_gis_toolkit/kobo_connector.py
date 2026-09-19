# -*- coding: utf-8 -*-
"""
KoboToolbox connector - lightweight version for personal use.

Workflow:
1. list_forms()               -> list of forms that have a geo field
2. get_geo_fields()            -> fields of type geopoint/geotrace/geoshape on the selected form
3. fetch_submissions()         -> fetch all submission data (with pagination)
4. build_feature_collection()  -> turn submissions into GeoJSON based on geo_field
5. load_features_to_layer()    -> create a QGIS vector layer from that GeoJSON
"""
import json

import requests
from requests.auth import HTTPBasicAuth

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsProject,
    QgsMessageLog,
    Qgis,
)
from qgis.PyQt.QtCore import QVariant

LOG_TAG = "AgroforestryGisToolkit"
GEO_TYPES = {"geopoint", "geotrace", "geoshape"}


def _log(msg, level=Qgis.Info):
    QgsMessageLog.logMessage(msg, LOG_TAG, level)


def _session(username, password):
    s = requests.Session()
    if username:
        s.auth = HTTPBasicAuth(username, password)
    return s


def list_forms(api_url, username, password):
    """Return the list of forms (assets) that have geo data.
    Each item: {"uid": ..., "name": ..., "date_created": ...}
    """
    url = f"https://{api_url}/api/v2/assets.json"
    resp = _session(username, password).get(url, timeout=30)
    resp.raise_for_status()
    assets = resp.json().get("results", [])
    forms = []
    for a in assets:
        if a.get("summary", {}).get("geo"):
            forms.append(
                {
                    "uid": a.get("uid"),
                    "name": a.get("name"),
                    "date_created": a.get("date_created"),
                }
            )
    return forms


def get_geo_fields(api_url, username, password, asset_uid):
    """Return the list of field names of type geopoint/geotrace/geoshape on the form."""
    url = f"https://{api_url}/api/v2/assets/{asset_uid}.json"
    resp = _session(username, password).get(url, params={"metadata": "on"}, timeout=30)
    resp.raise_for_status()
    content = resp.json().get("content", {})
    survey = content.get("survey", [])
    fields = [
        f.get("$autoname") or f.get("name")
        for f in survey
        if f.get("type") in GEO_TYPES
    ]
    return [f for f in fields if f]


def get_image_fields(api_url, username, password, asset_uid):
    """Return the list of field names of type 'image' on the form (top-level or inside repeats)."""
    url = f"https://{api_url}/api/v2/assets/{asset_uid}.json"
    resp = _session(username, password).get(url, params={"metadata": "on"}, timeout=30)
    resp.raise_for_status()
    content = resp.json().get("content", {})
    survey = content.get("survey", [])
    fields = [
        f.get("$autoname") or f.get("name")
        for f in survey
        if f.get("type") == "image"
    ]
    return [f for f in fields if f]


def fetch_submissions(api_url, username, password, asset_uid, page_size=1000):
    """Fetch all submission data for one form (auto pagination)."""
    url = f"https://{api_url}/api/v2/assets/{asset_uid}/data.json"
    session = _session(username, password)
    all_results = []
    start = 0
    while True:
        params = {"limit": page_size, "start": start}
        resp = session.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break
        all_results.extend(results)
        start += page_size
        if len(results) < page_size:
            break
    return all_results


def _flatten(data, parent_key="", sep="/"):
    flat = {}
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            flat.update(_flatten(value, new_key, sep))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    flat.update(_flatten(item, f"{new_key}[{i + 1}]", sep))
                else:
                    flat[f"{new_key}[{i + 1}]"] = item
        else:
            flat[new_key] = value
    return flat


def _parse_geopoint(value):
    """Standard ODK/Kobo geopoint format: 'lat lon alt accuracy'."""
    parts = value.strip().split(" ")
    if len(parts) < 2:
        return None
    lat, lon = float(parts[0]), float(parts[1])
    return (lon, lat)


def _parse_geotrace_or_shape(value):
    """ODK/Kobo geotrace/geoshape format: points separated by ';', each point 'lat lon alt accuracy'."""
    points = []
    for chunk in value.strip().split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        coord = _parse_geopoint(chunk)
        if coord:
            points.append(coord)
    return points


def build_feature_collection(submissions, geo_field):
    """Turn a list of submissions (JSON from Kobo) into a GeoJSON FeatureCollection,
    based on the value of geo_field (geopoint/geotrace/geoshape)."""
    features = []
    for datum in submissions:
        flat = _flatten(datum)
        raw_geo = None
        for key, value in flat.items():
            if key == geo_field or key.split("/")[-1] == geo_field:
                raw_geo = value
                break
        if not raw_geo:
            continue

        props = {k: v for k, v in flat.items() if k != geo_field and not str(k).endswith(f"/{geo_field}")}

        if ";" in raw_geo:
            coords = _parse_geotrace_or_shape(raw_geo)
            if len(coords) >= 3:
                geometry = {"type": "Polygon", "coordinates": [coords]}
            elif len(coords) == 2:
                geometry = {"type": "LineString", "coordinates": coords}
            else:
                continue
        else:
            coord = _parse_geopoint(raw_geo)
            if not coord:
                continue
            geometry = {"type": "Point", "coordinates": list(coord)}

        features.append({"type": "Feature", "geometry": geometry, "properties": props})

    return {"type": "FeatureCollection", "features": features}


# A handful of common identifying fields worth carrying onto every photo
# point, when the form happens to have them, so a photo can be traced back
# to a person without opening Kobo.
_ID_FIELDS = ("nama_lengkap", "kode_petani", "nama_kelompok_tani")


def _find_attachment_url(attachments, filename):
    """Match a submission's stored image filename to its Kobo attachment
    record and return the best download URL, or None."""
    if not filename:
        return None
    for att in attachments:
        att_name = att.get("filename", "")
        base = att_name.rsplit("/", 1)[-1]
        if base == filename or att_name.endswith(filename):
            return (
                att.get("download_large_url")
                or att.get("download_url")
                or att.get("download_medium_url")
                or att.get("download_small_url")
            )
    return None


def build_photo_feature_collection(submissions, image_field, geo_field):
    """Turn every occurrence of image_field across all submissions into a
    point feature, positioned using the geo_field value that shares the same
    repeat-instance prefix (so a photo inside repeat instance N of a group
    uses that same instance's geopoint, not instance 1's).

    Falls back to a submission-level geo_field value when image_field and
    geo_field are not both inside the same repeat.
    """
    features = []
    for datum in submissions:
        flat = _flatten(datum)
        attachments = datum.get("_attachments", [])

        for key, value in flat.items():
            segs = key.split("/")
            if segs[-1] != image_field or not value:
                continue
            prefix = "/".join(segs[:-1])

            geo_value = flat.get(f"{prefix}/{geo_field}") if prefix else None
            if not geo_value:
                geo_value = flat.get(geo_field)
            if not geo_value:
                continue
            coord = _parse_geopoint(geo_value)
            if not coord:
                continue

            props = {
                "filename": value,
                "download_url": _find_attachment_url(attachments, value) or "",
                "submission_id": datum.get("_id"),
                "field": prefix + "/" + image_field if prefix else image_field,
            }
            for id_field in _ID_FIELDS:
                if id_field in flat:
                    props[id_field] = flat[id_field]

            features.append(
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": list(coord)}, "properties": props}
            )

    return {"type": "FeatureCollection", "features": features}


def download_attachment(username, password, url, dest_path):
    """Download one Kobo attachment (photo) to dest_path, authenticated the
    same way as the rest of the API. Returns dest_path."""
    session = _session(username, password)
    resp = session.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(8192):
            if chunk:
                f.write(chunk)
    return dest_path


def load_features_to_layer(feature_collection, layer_name):
    """Create a memory QgsVectorLayer from a GeoJSON FeatureCollection and add it to the project."""
    features = feature_collection.get("features", [])
    if not features:
        raise ValueError("No geo data could be loaded (check the selected geo field).")

    geom_type = features[0]["geometry"]["type"]
    layer = QgsVectorLayer(f"{geom_type}?crs=EPSG:4326", layer_name, "memory")
    provider = layer.dataProvider()

    # collect all property names across all features (Kobo forms can have dynamic fields)
    all_keys = []
    for feat in features:
        for k in feat["properties"].keys():
            if k not in all_keys:
                all_keys.append(k)

    provider.addAttributes([QgsField(k, QVariant.String) for k in all_keys])
    layer.updateFields()

    qgs_features = []
    for feat in features:
        f = QgsFeature(layer.fields())
        f.setGeometry(_geojson_geom_to_qgsgeometry(feat["geometry"]))
        f.setAttributes([str(feat["properties"].get(k, "")) for k in all_keys])
        qgs_features.append(f)

    provider.addFeatures(qgs_features)
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


def _geojson_geom_to_qgsgeometry(geometry):
    gtype = geometry["type"]
    coords = geometry["coordinates"]
    if gtype == "Point":
        return QgsGeometry.fromWkt(f"POINT({coords[0]} {coords[1]})")
    elif gtype == "LineString":
        pts = ", ".join(f"{x} {y}" for x, y in coords)
        return QgsGeometry.fromWkt(f"LINESTRING({pts})")
    elif gtype == "Polygon":
        ring = coords[0]
        pts = ", ".join(f"{x} {y}" for x, y in ring)
        return QgsGeometry.fromWkt(f"POLYGON(({pts}))")
    return QgsGeometry()

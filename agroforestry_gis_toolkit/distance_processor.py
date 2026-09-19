# -*- coding: utf-8 -*-
"""Jarak titik (mis. hasil Kobo) ke kawasan hutan terdekat.

Cara hitung:
  1. Titik & poligon kawasan hutan dialihkan sementara ke UTM (zona dipilih
     otomatis dari lokasi titik) supaya pencarian titik terdekat pada batas
     poligon akurat dalam meter.
  2. Jarak akhir dihitung elipsoidal (WGS84) antara titik dan titik terdekat
     di batas kawasan, jadi tidak terpengaruh distorsi proyeksi.
  3. Titik yang berada di dalam poligon: jarak = 0, posisi = "Di dalam".
Status/nama kawasan diambil dari poligon yang jaraknya terdekat.
"""
import math

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorDataProvider,
    QgsVectorLayer,
    QgsWkbTypes,
)

WGS84 = "EPSG:4326"
POS_INSIDE = "Di dalam"
POS_OUTSIDE = "Di luar"

UNITS = {"km": 1000.0, "m": 1.0}


def utm_crs_for_point(lon, lat):
    zone = max(1, min(60, int((lon + 180.0) // 6) + 1))
    epsg = (32600 if lat >= 0 else 32700) + zone
    return QgsCoordinateReferenceSystem(f"EPSG:{epsg}")


def _bbox_distance(bbox, pt):
    dx = max(bbox.xMinimum() - pt.x(), 0.0, pt.x() - bbox.xMaximum())
    dy = max(bbox.yMinimum() - pt.y(), 0.0, pt.y() - bbox.yMaximum())
    return math.hypot(dx, dy)


def _text(value):
    if value is None:
        return ""
    s = str(value)
    return "" if s == "NULL" else s


class _ForestIndex:
    """Poligon kawasan hutan (sudah di UTM) + pencarian terdekat yang eksak."""

    def __init__(self, layer, utm_crs, status_field, name_field, context, rect=None):
        xf = QgsCoordinateTransform(layer.crs(), utm_crs, context)
        self.items = []
        request = QgsFeatureRequest()
        if rect is not None:
            request.setFilterRect(rect)  # rect dalam CRS layer kawasan
        for feat in layer.getFeatures(request):
            geom = feat.geometry()
            if geom is None or geom.isNull() or geom.isEmpty():
                continue
            geom = QgsGeometry(geom)
            try:
                geom.transform(xf)
            except Exception:  # noqa: BLE001
                continue
            status = _text(feat[status_field]) if status_field else ""
            name = _text(feat[name_field]) if name_field else ""
            self.items.append((geom.boundingBox(), geom, status, name))

    def nearest(self, pt):
        """Return (jarak_utm, index) poligon terdekat dari QgsPointXY `pt`."""
        pgeom = QgsGeometry.fromPointXY(pt)
        order = sorted((_bbox_distance(item[0], pt), i) for i, item in enumerate(self.items))
        best = None
        for bbox_d, i in order:
            if best is not None and bbox_d >= best[0]:
                break  # sisanya pasti lebih jauh
            d = self.items[i][1].distance(pgeom)
            if best is None or d < best[0]:
                best = (d, i)
            if d == 0:
                break
        return best


def is_web_layer(layer):
    return layer.providerType().lower() in ("wfs", "arcgisfeatureserver", "arcgismapserver")


def compute_distances(point_layer, forest_layer, status_field, name_field=None,
                      progress=None, context=None, search_km=None):
    """Hitung jarak tiap titik ke kawasan hutan terdekat.

    Return (results, info):
      results : list of dict(fid, dist_m, status, name, inside, pt, near)
                pt/near = QgsPointXY dalam CRS layer titik
      info    : dict(total, skipped, forest_count, beyond)

    search_km : kalau diisi, hanya kawasan hutan dalam radius sekitar extent titik
                yang diambil (berguna untuk layer WFS/ArcGIS yang besar). Titik yang
                jaraknya melebihi radius ini dihitung di `beyond` (hasilnya bisa
                kurang akurat).
    """
    context = context or QgsProject.instance().transformContext()
    wgs = QgsCoordinateReferenceSystem(WGS84)

    # Zona UTM dari pusat sebaran titik
    to_wgs_extent = QgsCoordinateTransform(point_layer.crs(), wgs, context)
    center = to_wgs_extent.transformBoundingBox(point_layer.extent()).center()
    utm = utm_crs_for_point(center.x(), center.y())

    src_to_utm = QgsCoordinateTransform(point_layer.crs(), utm, context)
    utm_to_src = QgsCoordinateTransform(utm, point_layer.crs(), context)
    src_to_wgs = QgsCoordinateTransform(point_layer.crs(), wgs, context)
    utm_to_wgs = QgsCoordinateTransform(utm, wgs, context)

    rect = None
    if search_km:
        ll = to_wgs_extent.transformBoundingBox(point_layer.extent())
        dlat = search_km / 111.0
        dlon = search_km / (111.0 * max(math.cos(math.radians(center.y())), 0.1))
        ll.setXMinimum(ll.xMinimum() - dlon)
        ll.setXMaximum(ll.xMaximum() + dlon)
        ll.setYMinimum(ll.yMinimum() - dlat)
        ll.setYMaximum(ll.yMaximum() + dlat)
        rect = QgsCoordinateTransform(wgs, forest_layer.crs(), context).transformBoundingBox(ll)

    forest = _ForestIndex(forest_layer, utm, status_field, name_field, context, rect)
    if not forest.items:
        raise ValueError(
            "Tidak ada poligon kawasan hutan yang terbaca"
            + (f" dalam radius {search_km:g} km dari titik (perbesar radius)." if search_km else ".")
        )

    da = QgsDistanceArea()
    da.setSourceCrs(wgs, context)
    da.setEllipsoid("WGS84")

    total = point_layer.featureCount()
    results, skipped, beyond = [], 0, 0
    limit_m = search_km * 1000.0 if search_km else None
    for n, feat in enumerate(point_layer.getFeatures()):
        if progress and n % 20 == 0:
            progress(n, total)
        geom = feat.geometry()
        if geom is None or geom.isNull() or geom.isEmpty():
            skipped += 1
            continue
        pt = geom.asMultiPoint()[0] if geom.isMultipart() else geom.asPoint()

        try:
            pt_utm = src_to_utm.transform(pt)
            best = forest.nearest(pt_utm)
            if best is None:
                skipped += 1
                continue
            d_utm, idx = best
            _bbox, poly, status, name = forest.items[idx]

            if d_utm == 0:
                dist_m, near_src, inside = 0.0, pt, True
            else:
                near_utm = poly.nearestPoint(QgsGeometry.fromPointXY(pt_utm)).asPoint()
                dist_m = da.measureLine(src_to_wgs.transform(pt), utm_to_wgs.transform(near_utm))
                near_src = utm_to_src.transform(near_utm)
                inside = False
        except Exception:  # noqa: BLE001  (titik di luar domain transformasi, dsb.)
            skipped += 1
            continue

        if limit_m is not None and dist_m > limit_m:
            beyond += 1
        results.append({
            "fid": feat.id(), "dist_m": dist_m, "status": status, "name": name,
            "inside": inside, "pt": pt, "near": near_src,
        })

    if progress:
        progress(total, total)
    return results, {"total": total, "skipped": skipped,
                     "forest_count": len(forest.items), "beyond": beyond}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def _convert(dist_m, unit):
    value = dist_m / UNITS[unit]
    return round(value, 3) if unit == "km" else round(value, 1)


def field_names(unit):
    return {
        "dist": f"jrk_kws_{unit}",
        "status": "status_kws",
        "name": "nama_kws",
        "pos": "posisi_kws",
    }


def create_line_layer(point_layer, results, unit, with_name, add_to_project=True):
    """Layer garis titik -> titik terdekat di batas kawasan hutan."""
    fn = field_names(unit)
    layer = QgsVectorLayer(
        f"LineString?crs={point_layer.crs().authid()}",
        f"Garis jarak ke kawasan hutan ({unit}) - {point_layer.name()}",
        "memory",
    )
    fields = [
        QgsField("pt_fid", QVariant.LongLong),
        QgsField(fn["dist"], QVariant.Double),
        QgsField(fn["status"], QVariant.String),
    ]
    if with_name:
        fields.append(QgsField(fn["name"], QVariant.String))
    layer.dataProvider().addAttributes(fields)
    layer.updateFields()

    feats = []
    for r in results:
        if r["inside"]:
            continue  # titik di dalam kawasan: tidak ada garis
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPolylineXY([r["pt"], r["near"]]))
        attrs = [r["fid"], _convert(r["dist_m"], unit), r["status"]]
        if with_name:
            attrs.append(r["name"])
        f.setAttributes(attrs)
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()

    # Styling & label jarak (opsional; kalau API-nya beda, layer tetap jadi)
    try:
        symbol = layer.renderer().symbol()
        symbol.setColor(QColor("#d62728"))
        symbol.setWidth(0.5)
        from qgis.core import QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling
        s = QgsPalLayerSettings()
        s.fieldName = f"format_number(\"{fn['dist']}\", 2) || ' {unit}'"
        s.isExpression = True
        s.placement = QgsPalLayerSettings.Line
        fmt = QgsTextFormat()
        fmt.setSize(9)
        s.setFormat(fmt)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(s))
        layer.setLabelsEnabled(True)
    except Exception:  # noqa: BLE001
        pass

    if add_to_project:
        QgsProject.instance().addMapLayer(layer)
    return layer


def _field_specs(unit, with_name):
    fn = field_names(unit)
    specs = [
        (fn["dist"], QVariant.Double, f"Jarak ke kawasan hutan terdekat ({unit})"),
        (fn["status"], QVariant.String, "Status kawasan hutan terdekat"),
    ]
    if with_name:
        specs.append((fn["name"], QVariant.String, "Nama kawasan hutan terdekat"))
    specs.append((fn["pos"], QVariant.String, "Posisi terhadap kawasan hutan"))
    return specs


def _values_for(result, unit, with_name):
    vals = {
        field_names(unit)["dist"]: _convert(result["dist_m"], unit),
        field_names(unit)["status"]: result["status"],
        field_names(unit)["pos"]: POS_INSIDE if result["inside"] else POS_OUTSIDE,
    }
    if with_name:
        vals[field_names(unit)["name"]] = result["name"]
    return vals


def _can_edit_schema(layer):
    if layer.isEditable():
        return True
    caps = layer.dataProvider().capabilities()
    return bool(caps & QgsVectorDataProvider.AddAttributes) and \
        bool(caps & QgsVectorDataProvider.ChangeAttributeValues)


def add_fields_to_points(point_layer, results, unit, with_name):
    """Tambahkan field jarak + status langsung ke layer titik.

    Kalau layer titik tidak bisa diubah (mis. sumber read-only), dibuat salinan
    memory baru bernama '<nama>_jarak'. Return (layer_hasil, dibuat_salinan).
    """
    specs = _field_specs(unit, with_name)
    values = {r["fid"]: _values_for(r, unit, with_name) for r in results}

    if not _can_edit_schema(point_layer):
        return _copy_with_fields(point_layer, specs, values), True

    was_editing = point_layer.isEditable()
    existing = {f.name() for f in point_layer.fields()}
    new_fields = [QgsField(n, t) for n, t, _a in specs if n not in existing]

    if was_editing:
        for fld in new_fields:
            point_layer.addAttribute(fld)
    elif new_fields:
        if not point_layer.dataProvider().addAttributes(new_fields):
            raise RuntimeError("Gagal menambah field ke layer titik.")
    point_layer.updateFields()

    idx_of = {n: point_layer.fields().lookupField(n) for n, _t, _a in specs}
    if was_editing:
        for fid, vals in values.items():
            for name, val in vals.items():
                point_layer.changeAttributeValue(fid, idx_of[name], val)
    else:
        changes = {fid: {idx_of[n]: v for n, v in vals.items()} for fid, vals in values.items()}
        if changes and not point_layer.dataProvider().changeAttributeValues(changes):
            raise RuntimeError("Gagal mengisi nilai field di layer titik.")

    for name, _t, alias in specs:
        point_layer.setFieldAlias(idx_of[name], alias)
    point_layer.triggerRepaint()
    return point_layer, False


def _copy_with_fields(point_layer, specs, values):
    wkb = QgsWkbTypes.displayString(point_layer.wkbType())
    out = QgsVectorLayer(
        f"{wkb}?crs={point_layer.crs().authid()}", f"{point_layer.name()}_jarak", "memory"
    )
    dp = out.dataProvider()
    existing = {f.name() for f in point_layer.fields()}
    dp.addAttributes([QgsField(f) for f in point_layer.fields()])
    dp.addAttributes([QgsField(n, t) for n, t, _a in specs if n not in existing])
    out.updateFields()

    feats = []
    for feat in point_layer.getFeatures():
        nf = QgsFeature(out.fields())
        nf.setGeometry(feat.geometry())
        for f in point_layer.fields():
            nf.setAttribute(f.name(), feat[f.name()])
        for name, val in values.get(feat.id(), {}).items():
            nf.setAttribute(name, val)
        feats.append(nf)
    dp.addFeatures(feats)
    out.updateExtents()
    for name, _t, alias in specs:
        out.setFieldAlias(out.fields().lookupField(name), alias)
    QgsProject.instance().addMapLayer(out)
    return out


def summarize(results, unit):
    if not results:
        return "Tidak ada titik yang berhasil dihitung."
    vals = [r["dist_m"] / UNITS[unit] for r in results]
    inside = sum(1 for r in results if r["inside"])
    return (
        f"{len(results)} titik dihitung ({inside} di dalam kawasan).\n"
        f"Jarak min {min(vals):.3f} {unit}, maks {max(vals):.3f} {unit}, "
        f"rata-rata {sum(vals) / len(vals):.3f} {unit}."
    )

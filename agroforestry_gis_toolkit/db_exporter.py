# -*- coding: utf-8 -*-
"""Export a QGIS vector layer directly into a PostgreSQL / PostGIS
database (e.g. Supabase) from inside the plugin sidebar, without having
to go through Layer > Add Layer > Add PostgreSQL Layer / DB Manager.

Kobo-style layers can have very long, repeat-group field names such as
'data_plot[1]/data_plot/tanaman_naungan[1]/tanaman_naungan/jenis'.
Postgres silently truncates identifiers to 63 characters, so two such
fields can truncate to the exact same column name and the export fails
with "column ... already exists". `sanitize_layer()` rewrites the field
names first so this can never happen.
"""
import re

from qgis.core import (
    QgsDataSourceUri,
    QgsVectorLayerExporter,
    QgsSettings,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsWkbTypes,
)

# Keep a safety margin under Postgres' 63-character identifier limit.
MAX_IDENTIFIER_LEN = 59

SSL_MODES = {
    "disable": QgsDataSourceUri.SslDisable,
    "allow": QgsDataSourceUri.SslAllow,
    "prefer": QgsDataSourceUri.SslPrefer,
    "require": QgsDataSourceUri.SslRequire,
}


def list_saved_connections():
    """Names of PostgreSQL connections already created in QGIS via
    Layer > Add Layer > Add PostgreSQL Layer > New (e.g. a Supabase
    project set up that way). Lets the user pick one instead of typing
    the host again."""
    s = QgsSettings()
    s.beginGroup("PostgreSQL/connections")
    names = s.childGroups()
    s.endGroup()
    return names


def get_connection_defaults(name):
    """Host/port/database saved for a connection name. Credentials are
    intentionally not read back here -- the user re-enters them in the
    export panel so nothing relies on how/whether QGIS stored them."""
    s = QgsSettings()
    base = f"PostgreSQL/connections/{name}"
    return {
        "host": s.value(f"{base}/host", ""),
        "port": s.value(f"{base}/port", "5432"),
        "database": s.value(f"{base}/database", ""),
    }


def _sanitize_field_name(name, used):
    """Turn `name` into a safe, unique Postgres column name (<=59 chars)."""
    n = name.lower()
    n = n.replace("/", "_").replace("[", "").replace("]", "")
    n = re.sub(r"[^a-z0-9_]", "_", n)
    n = re.sub(r"_+", "_", n).strip("_") or "field"

    base = n[:MAX_IDENTIFIER_LEN]
    candidate = base
    i = 1
    while candidate in used:
        suffix = f"_{i}"
        candidate = base[: MAX_IDENTIFIER_LEN - len(suffix)] + suffix
        i += 1
    used.add(candidate)
    return candidate


def sanitize_layer(layer):
    """Return (memory_layer, mapping) where memory_layer is a copy of
    `layer` with safe/unique field names, and mapping is a list of
    (old_name, new_name, field_type) for reference."""
    used = set()
    mapping = [
        (f.name(), _sanitize_field_name(f.name(), used), f.type())
        for f in layer.fields()
    ]

    geom_str = QgsWkbTypes.displayString(layer.wkbType())
    uri = f"{geom_str}?crs={layer.crs().authid()}"
    mem_layer = QgsVectorLayer(uri, layer.name(), "memory")
    provider = mem_layer.dataProvider()
    provider.addAttributes([QgsField(new, ftype) for (_old, new, ftype) in mapping])
    mem_layer.updateFields()

    feats = []
    for feat in layer.getFeatures():
        new_feat = QgsFeature(mem_layer.fields())
        new_feat.setGeometry(feat.geometry())
        for old, new, _ftype in mapping:
            new_feat.setAttribute(new, feat.attribute(old))
        feats.append(new_feat)
    provider.addFeatures(feats)
    mem_layer.updateExtents()

    return mem_layer, mapping


def export_layer_to_postgis(
    layer,
    host,
    port,
    database,
    username,
    password,
    schema,
    table,
    sslmode="prefer",
    overwrite=False,
):
    """Send `layer` into a PostgreSQL/PostGIS table, sanitizing field
    names first. Returns (mapping, feature_count) on success; raises
    RuntimeError with a readable message on failure.
    """
    clean_layer, mapping = sanitize_layer(layer)

    uri = QgsDataSourceUri()
    uri.setConnection(
        host,
        str(port),
        database,
        username,
        password,
        SSL_MODES.get(sslmode, QgsDataSourceUri.SslPrefer),
    )
    geometry_column = "geom" if clean_layer.isSpatial() else None
    uri.setDataSource(schema, table, geometry_column)

    result = QgsVectorLayerExporter.exportLayer(
        clean_layer,
        uri.uri(False),
        "postgres",
        clean_layer.crs(),
        False,
        overwrite=overwrite,
    )

    # Some QGIS/PyQGIS versions return just an int, others a tuple of
    # (error_code, error_message) -- handle both, same as exporter.py.
    if isinstance(result, (tuple, list)):
        error_code = result[0]
        error_message = result[1] if len(result) > 1 else ""
    else:
        error_code = result
        error_message = ""

    if error_code != QgsVectorLayerExporter.NoError:
        raise RuntimeError(error_message or f"Export failed (code {error_code})")

    return mapping, clean_layer.featureCount()

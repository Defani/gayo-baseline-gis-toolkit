# -*- coding: utf-8 -*-
from qgis.core import (
    QgsVectorFileWriter,
    QgsCoordinateTransformContext,
    QgsProject,
)

# Format name shown to the user -> (OGR driver, file extension)
EXPORT_FORMATS = {
    "CSV": ("CSV", "csv"),
    "GeoJSON": ("GeoJSON", "geojson"),
    "Excel (XLSX)": ("XLSX", "xlsx"),
}


def export_layer(layer, format_label, output_path):
    """Export a vector layer to CSV / GeoJSON / XLSX.

    layer        : QgsVectorLayer
    format_label : one of the EXPORT_FORMATS keys, e.g. "CSV"
    output_path  : destination file path (extension will be adjusted if needed)
    """
    if format_label not in EXPORT_FORMATS:
        raise ValueError(f"Unknown format: {format_label}")

    driver_name, ext = EXPORT_FORMATS[format_label]

    if not output_path.lower().endswith(f".{ext}"):
        output_path = f"{output_path}.{ext}"

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver_name
    options.fileEncoding = "UTF-8"

    # CSV/XLSX don't always need geometry as a column, but we store it as WKT
    # so location information isn't lost when opened in Excel.
    if driver_name in ("CSV", "XLSX"):
        options.attributes = []  # all attributes included by default
        options.layerOptions = ["GEOMETRY=AS_WKT"] if driver_name == "CSV" else []

    transform_context = QgsProject.instance().transformContext()

    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, output_path, transform_context, options
    )

    # writeAsVectorFormatV3 returns a tuple (error_code, error_message, ...)
    error_code = result[0] if isinstance(result, (tuple, list)) else result
    if error_code != QgsVectorFileWriter.NoError:
        error_message = result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else str(result)
        raise RuntimeError(f"Export failed ({driver_name}): {error_message}")

    return output_path

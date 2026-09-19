# -*- coding: utf-8 -*-
"""
Export a vector layer (point/line/polygon) to a GPX file for Garmin devices.

The conversion workflow is adapted from the open-source plugin "GPX Maker for
GARMIN(R) devices" by Sanda Takeru (GPLv3) -
https://github.com/SandaTakeru/GPX-Maker-for-Garmin-devices
Simplified here into a single plain function (without QgsProcessingAlgorithm)
so it can be called directly from this toolkit's sidebar dialog.
"""
import processing

from qgis.core import (
    Qgis,
    QgsProcessing,
    QgsProcessingUtils,
    QgsVectorFileWriter,
    QgsProject,
)


def export_to_gpx(layer, display_name, name_field, output_path, feedback=None):
    """Convert 1 active vector layer into a GPX file.

    - layer: source QgsVectorLayer
    - display_name: name used when features are dissolved into one (when name_field is empty)
    - name_field: source field name for the per-feature 'name' column (optional, leave empty to dissolve)
    - output_path: destination .gpx file path
    """
    if layer is None:
        raise ValueError("No layer has been selected.")
    if layer.featureCount() == 0:
        raise ValueError(f'Layer "{layer.name()}" has no features.')

    layer_type = layer.geometryType()

    if name_field:
        name_value = f'"{name_field}"'
        dissolve = False
    else:
        safe_display_name = (display_name or "Display Name").replace("'", "\\'")
        name_value = f"'{safe_display_name}'"
        dissolve = True

    context = None  # use default processing context (None -> new context per run)
    next_input = layer

    # 1. Fix geometries
    fixed = processing.run(
        "native:fixgeometries",
        {"INPUT": next_input, "METHOD": 1, "OUTPUT": "TEMPORARY_OUTPUT"},
        feedback=feedback,
    )
    next_input = fixed["OUTPUT"]

    # 2. Polygon -> line (GPX has no polygon type)
    if layer_type == Qgis.GeometryType.Polygon:
        lines = processing.run(
            "native:polygonstolines",
            {"INPUT": next_input, "OUTPUT": "TEMPORARY_OUTPUT"},
            feedback=feedback,
        )
        next_input = lines["OUTPUT"]

    # 3. Dissolve into one feature named display_name (when name_field is not set)
    if dissolve and layer_type != Qgis.GeometryType.Point:
        dissolved = processing.run(
            "native:dissolve",
            {"FIELD": [""], "INPUT": next_input, "SEPARATE_DISJOINT": False, "OUTPUT": "TEMPORARY_OUTPUT"},
            feedback=feedback,
        )
        next_input = dissolved["OUTPUT"]

    # 4. Multipart points -> singlepart
    if layer_type == Qgis.GeometryType.Point:
        singles = processing.run(
            "native:multiparttosingleparts",
            {"INPUT": next_input, "OUTPUT": "TEMPORARY_OUTPUT"},
            feedback=feedback,
        )
        next_input = singles["OUTPUT"]

    # 5. Set the 'name' column according to name_value
    refactored = processing.run(
        "native:refactorfields",
        {
            "FIELDS_MAPPING": [{"expression": name_value, "name": "name", "type": 10, "type_name": "text"}],
            "INPUT": next_input,
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
        feedback=feedback,
    )

    output_layer = QgsProcessingUtils.mapLayerFromString(refactored["OUTPUT"], QgsProject.instance())

    if not output_path.lower().endswith(".gpx"):
        output_path += ".gpx"

    vector_options = QgsVectorFileWriter.SaveVectorOptions()
    vector_options.driverName = "GPX"
    vector_options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
    vector_options.fileEncoding = "UTF-8"
    vector_options.datasourceOptions = ["GPX_USE_EXTENSIONS=YES"]
    vector_options.layerOptions = ["FORCE_GPX_TRACKS=YES"]

    QgsVectorFileWriter.writeAsVectorFormatV3(
        layer=output_layer,
        fileName=output_path,
        transformContext=QgsProject.instance().transformContext(),
        options=vector_options,
    )

    return output_path

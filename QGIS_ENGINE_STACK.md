# QGIS and engine stack reference

Complete, categorized list of every engine, API, framework, driver and external service the **Gayo Coffee Baseline GIS Toolkit** plugin actually calls into, taken directly from the source code (not a generic list). Each entry links to its official reference.

## 1. Host application

| Component | Role | Reference |
| --- | --- | --- |
| QGIS Desktop 3.16+ | Host GIS application the plugin runs inside | https://qgis.org |
| PyQGIS | Python bindings QGIS exposes to plugins (`qgis.core`, `qgis.gui`, `qgis.PyQt`, `processing`) | https://qgis.org/pyqgis/master/ |
| QGIS Plugin architecture | `metadata.txt` + `classFactory()` + `QgsProcessingProvider` registration | https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/plugins/index.html |

## 2. `qgis.core` classes used

| Class | Used for | Reference |
| --- | --- | --- |
| `QgsApplication` | Access the Processing registry at plugin load/unload | https://qgis.org/pyqgis/master/core/QgsApplication.html |
| `QgsCoordinateReferenceSystem` | Define/parse CRSs (EPSG codes, UTM zones, EPSG:3395, EPSG:4326) | https://qgis.org/pyqgis/master/core/QgsCoordinateReferenceSystem.html |
| `QgsCoordinateTransform` | Reproject geometries between source/UTM/WGS84/output CRS | https://qgis.org/pyqgis/master/core/QgsCoordinateTransform.html |
| `QgsCoordinateTransformContext` | Transform context passed to writers/transforms | https://qgis.org/pyqgis/master/core/QgsCoordinateTransformContext.html |
| `QgsDataSourceUri` | Build WMTS/WMS/WFS/PostGIS connection URIs | https://qgis.org/pyqgis/master/core/QgsDataSourceUri.html |
| `QgsDistanceArea` | Ellipsoidal distance/area calculations | https://qgis.org/pyqgis/master/core/QgsDistanceArea.html |
| `QgsEditorWidgetSetup` | Configure the "Photo" attribute-form widget for photo fields | https://qgis.org/pyqgis/master/core/QgsEditorWidgetSetup.html |
| `QgsExpression` | Evaluate field/map-tip and Quick Query expressions | https://qgis.org/pyqgis/master/core/QgsExpression.html |
| `QgsFeature` / `QgsFeatureRequest` / `QgsFeatureSink` | Build, request and write features | https://qgis.org/pyqgis/master/core/QgsFeature.html |
| `QgsField` / `QgsFields` | Define attribute schemas for generated layers | https://qgis.org/pyqgis/master/core/QgsField.html |
| `QgsGeometry` | Build/convert point, line and polygon geometries (incl. GeoJSON parsing) | https://qgis.org/pyqgis/master/core/QgsGeometry.html |
| `QgsMapLayerType` | Distinguish vector/raster/web layers | https://qgis.org/pyqgis/master/core/Qgis.html |
| `QgsMessageLog` | Write to the QGIS log panel | https://qgis.org/pyqgis/master/core/QgsMessageLog.html |
| `QgsPalLayerSettings` / `QgsVectorLayerSimpleLabeling` / `QgsTextFormat` | Label the Grid Index output layer | https://qgis.org/pyqgis/master/core/QgsPalLayerSettings.html |
| `QgsPointXY` | Point geometry construction | https://qgis.org/pyqgis/master/core/QgsPointXY.html |
| `QgsProject` | Access the current project, its layers, transform context | https://qgis.org/pyqgis/master/core/QgsProject.html |
| `QgsProviderRegistry` / `QgsProviderSublayerDetails` | Inspect data providers and sublayers when adding files | https://qgis.org/pyqgis/master/core/QgsProviderRegistry.html |
| `QgsRasterDataProvider` / `QgsRasterLayer` | Load XYZ/WMTS/WMS raster and GEE tile layers | https://qgis.org/pyqgis/master/core/QgsRasterLayer.html |
| `QgsRectangle` | Bounding boxes / extents (Grid Index, distance search) | https://qgis.org/pyqgis/master/core/QgsRectangle.html |
| `QgsSettings` | Persist plugin settings (e.g. saved Claude Desktop path, formerly used) | https://qgis.org/pyqgis/master/core/QgsSettings.html |
| `QgsSpatialIndex` | Fast nearest-forest lookup in Distance Analysis | https://qgis.org/pyqgis/master/core/QgsSpatialIndex.html |
| `QgsTask` | Background/async task base class | https://qgis.org/pyqgis/master/core/QgsTask.html |
| `QgsUnitTypes` | Distance unit conversion (m/km) | https://qgis.org/pyqgis/master/core/QgsUnitTypes.html |
| `QgsVectorDataProvider` | Field/schema editing capability checks | https://qgis.org/pyqgis/master/core/QgsVectorDataProvider.html |
| `QgsVectorFileWriter` | Write CSV / GeoJSON / XLSX / GPX output files | https://qgis.org/pyqgis/master/core/QgsVectorFileWriter.html |
| `QgsVectorLayer` | Core in-memory/disk vector layer object used everywhere | https://qgis.org/pyqgis/master/core/QgsVectorLayer.html |
| `QgsVectorLayerExporter` | Export layers to PostGIS/Supabase | https://qgis.org/pyqgis/master/core/QgsVectorLayerExporter.html |
| `QgsWkbTypes` | Geometry type checks (point/line/polygon) | https://qgis.org/pyqgis/master/core/QgsWkbTypes.html |

## 3. `qgis.gui` classes used

| Class | Used for | Reference |
| --- | --- | --- |
| `QgsMapLayerComboBox` | Layer picker widgets in tool dialogs | https://qgis.org/pyqgis/master/gui/QgsMapLayerComboBox.html |
| `QgsMapLayerProxyModel` | Filter layer pickers to vector/point/line layers | https://qgis.org/pyqgis/master/gui/QgsMapLayerProxyModel.html |
| `QgsFieldComboBox` | Field picker widgets (name field, status field, id field) | https://qgis.org/pyqgis/master/gui/QgsFieldComboBox.html |

## 4. QGIS Processing framework

| Component | Used for | Reference |
| --- | --- | --- |
| `QgsProcessingAlgorithm` | Base class for the Grid Index algorithm | https://qgis.org/pyqgis/master/core/QgsProcessingAlgorithm.html |
| `QgsProcessingProvider` | Registers the toolkit's algorithm(s) in the Processing Toolbox | https://qgis.org/pyqgis/master/core/QgsProcessingProvider.html |
| `QgsProcessingContext` / `QgsProcessingFeedback` / `QgsProcessingException` | Execution context, progress reporting, error handling | https://qgis.org/pyqgis/master/core/QgsProcessingContext.html |
| `QgsProcessingParameterBoolean` / `Distance` / `Enum` / `FeatureSink` / `MapLayer` / `Number` | Grid Index algorithm's input parameter widgets | https://qgis.org/pyqgis/master/core/QgsProcessingParameterDefinition.html |
| `QgsProcessingUtils` | Resolve temporary layer outputs between chained algorithms | https://qgis.org/pyqgis/master/core/QgsProcessingUtils.html |
| `processing.run()` module | Runs native algorithms programmatically (GPX export pipeline) | https://qgis.org/pyqgis/master/core/Processing.html |

**Native Processing algorithms invoked (via `processing.run`)** - all part of QGIS's built-in "Native" provider:

- `native:fixgeometries`
- `native:polygonstolines`
- `native:dissolve`
- `native:multiparttosingleparts`
- `native:refactorfields`

Reference: https://docs.qgis.org/latest/en/docs/user_manual/processing_algs/qgis/index.html

## 5. Underlying GDAL/OGR drivers

QGIS's `QgsVectorFileWriter` delegates to GDAL/OGR for every file format the toolkit writes:

| Format | OGR driver | Used by |
| --- | --- | --- |
| CSV | `CSV` | Export Data |
| GeoJSON | `GeoJSON` | Export Data |
| Excel | `XLSX` | Export Data |
| GPX | `GPX` (with `GPX_USE_EXTENSIONS`, `FORCE_GPX_TRACKS`) | Export to GPX |

Reference: https://gdal.org/drivers/vector/index.html

## 6. Qt / PyQt5

| Layer | Reference |
| --- | --- |
| PyQt5 bindings, imported through `qgis.PyQt` (`QtCore`, `QtGui`, `QtWidgets`) | https://www.riverbankcomputing.com/software/pyqt/ |
| Qt Widgets used across dialogs: `QDialog`, `QDockWidget`, `QStackedWidget`, `QTabWidget`, `QGroupBox`, `QFormLayout`, `QVBoxLayout`/`QHBoxLayout`, `QComboBox`, `QLineEdit`, `QSpinBox`/`QDoubleSpinBox`, `QDateEdit`, `QCheckBox`, `QRadioButton`/`QButtonGroup`, `QListWidget`, `QProgressBar`, `QPushButton`, `QLabel`, `QMessageBox`, `QFileDialog`, `QScrollArea` | https://doc.qt.io/qt-5/classes.html |
| `QVariant` | Attribute field typing | https://doc.qt.io/qt-5/qvariant.html |

## 7. Reused/optional community QGIS plugins

| Plugin | Role in this toolkit | Reference |
| --- | --- | --- |
| QuickMapServices (NextGIS) | Basemap Search reuses its bundled basemap catalog (`quick_map_services.data_sources_list`) and its `add_layer_to_map` helper | https://plugins.qgis.org/plugins/quick_map_services/ |

## 8. Google Earth Engine

| Component | Used for | Reference |
| --- | --- | --- |
| Google Earth Engine platform | Cloud geospatial analysis platform behind GEE Connect | https://earthengine.google.com/ |
| `earthengine-api` (`ee` Python package) | `ee.Initialize`, `ee.Authenticate` (local OAuth), `ee.Image`, `ee.ImageCollection`, `ee.FeatureCollection`, `ee.Geometry.Rectangle`, `ee.Filter.lte`, `ee.data.getAsset` | https://developers.google.com/earth-engine/guides/python_install |
| `Image.getMapId()` tile fetcher | Produces the XYZ tile URL added to QGIS as a raster layer | https://developers.google.com/earth-engine/apidocs/ee-image-getmapid |
| Earth Engine Data Catalog (trimmed copy via geemap) | Dataset search list shown in GEE Connect (`gee_catalog.csv`) | https://developers.google.com/earth-engine/datasets |
| Earth Engine Code Editor (reference only, not embedded) | Where asset IDs/visualization params can be previewed before use | https://code.earthengine.google.com/ |

**Citation** for the platform underlying GEE Connect:

> Gorelick, N., Hancher, M., Dixon, M., Ilyushchenko, S., Thau, D., & Moore, R. (2017). Google Earth Engine: Planetary-scale geospatial analysis for everyone. *Remote Sensing of Environment*, 202, 18-27. https://doi.org/10.1016/j.rse.2017.06.031

**Citation** for geemap, the source project `gee_catalog.csv` was trimmed from:

> Wu, Q. (2020). geemap: A Python package for interactive mapping with Google Earth Engine. *Journal of Open Source Software*, 5(51), 2305. https://doi.org/10.21105/joss.02305

## 9. Web / cloud services

| Service | Used for | Reference |
| --- | --- | --- |
| KoboToolbox REST API | Kobo Connect, Foto di Layer, Foto Explorer (`requests` + HTTP Basic Auth, paginated submissions) | https://support.kobotoolbox.org/api.html - source code: https://github.com/kobotoolbox |
| OGC XYZ / WMTS / WMS / WFS | Web tile/service layers added via Add Layer (GetCapabilities parsed with `xml.etree.ElementTree`) | https://www.ogc.org/standards/wmts, https://www.ogc.org/standards/wms, https://www.ogc.org/standards/wfs |
| PostgreSQL / PostGIS | Spatial database target for Export to Database | https://postgis.net/ |
| Supabase | Managed Postgres/PostGIS target, connected the same way as PostGIS | https://supabase.com/ |
| Garmin GPX format | Output format for Export to GPX (GPX 1.1 XML schema, written via GDAL's GPX driver) | https://www.topografix.com/gpx.asp |

## 10. Python standard library / third-party packages

| Package | Used for |
| --- | --- |
| `requests`, `requests.auth` | HTTP calls to the KoboToolbox API |
| `concurrent.futures`, `threading` | Non-blocking photo downloads and network checks |
| `csv` | Reading `gee_catalog.csv` |
| `json` | Parsing/building GeoJSON payloads |
| `re` | Field-name sanitizing, CRS string parsing |
| `math` | Distance/geometry calculations |
| `datetime` | GEE date range filtering |
| `xml.etree.ElementTree` | Parsing WMTS/WMS `GetCapabilities` XML |
| `urllib.parse` | Building/parsing service URLs |
| `tempfile`, `os` | Temporary files and filesystem paths |

## 11. Licensed/attributed third-party code

| Component | Origin | License |
| --- | --- | --- |
| Grid Index algorithm | Adapted from a plugin by Kapildev Adhikari | GNU GPLv3 |
| GPX export pipeline | Conversion approach adapted from "GPX Maker for GARMIN(R) devices" by Sanda Takeru - https://github.com/SandaTakeru/GPX-Maker-for-Garmin-devices | GNU GPLv3 |
| `gee_catalog.csv` | Trimmed from geemap's Earth Engine dataset catalog by Qiusheng Wu, itself derived from the Earth Engine Datasets List by Samapriya Roy - https://github.com/gee-community/geemap | MIT |

## 12. References

Full bibliography of every platform, API, standard and dataset referenced above, in one place.

**Software / platforms**

- QGIS Desktop - https://qgis.org
- PyQGIS API documentation - https://qgis.org/pyqgis/master/
- QGIS Processing algorithm reference - https://docs.qgis.org/latest/en/docs/user_manual/processing_algs/qgis/index.html
- GDAL/OGR - https://gdal.org
- Qt / PyQt5 - https://www.riverbankcomputing.com/software/pyqt/
- QuickMapServices plugin (NextGIS) - https://plugins.qgis.org/plugins/quick_map_services/
- KoboToolbox - https://www.kobotoolbox.org/ - source code: https://github.com/kobotoolbox
- KoboToolbox API documentation - https://support.kobotoolbox.org/api.html
- Google Earth Engine - https://earthengine.google.com/
- Earth Engine Python API - https://developers.google.com/earth-engine/guides/python_install
- Earth Engine Data Catalog - https://developers.google.com/earth-engine/datasets
- Earth Engine Code Editor - https://code.earthengine.google.com/
- geemap - https://github.com/gee-community/geemap
- PostGIS - https://postgis.net/
- Supabase - https://supabase.com/
- OGC WMTS standard - https://www.ogc.org/standards/wmts
- OGC WMS standard - https://www.ogc.org/standards/wms
- OGC WFS standard - https://www.ogc.org/standards/wfs
- GPX 1.1 schema (Garmin/Topografix) - https://www.topografix.com/gpx.asp

**Third-party code reused/adapted**

- Grid Index plugin by Kapildev Adhikari (GPLv3)
- "GPX Maker for GARMIN(R) devices" by Sanda Takeru (GPLv3) - https://github.com/SandaTakeru/GPX-Maker-for-Garmin-devices

**Academic citations**

Gorelick, N., Hancher, M., Dixon, M., Ilyushchenko, S., Thau, D., & Moore, R. (2017). Google Earth Engine: Planetary-scale geospatial analysis for everyone. *Remote Sensing of Environment*, 202, 18-27. https://doi.org/10.1016/j.rse.2017.06.031

Wu, Q. (2020). geemap: A Python package for interactive mapping with Google Earth Engine. *Journal of Open Source Software*, 5(51), 2305. https://doi.org/10.21105/joss.02305

# Feature diagrams

> Repository status: `https://github.com/Defani/gayo-baseline-gis-toolkit` is currently empty. The plugin source has not been pushed there yet - the diagrams below describe the local codebase and are ready to drop into the README once the repository is populated.

## 0. System architecture

How the toolkit is wired together end to end: plugin bootstrap, the single sidebar panel, the per-tool modules, and the external systems each one talks to.

### 0.1 Component overview

```mermaid
flowchart TB
    subgraph HOST["QGIS Desktop (host application)"]
        TB["Toolbar icon / Plugins menu action"]
        PB["agroforestry_gis_toolkit_plugin.py<br/>(classFactory entry point, initGui, unload)"]
        DOCK["QDockWidget<br/>(right dock area)"]
        PANEL["sidebar_panel.py: SidebarPanel<br/>QStackedWidget - menu page + cached tool pages"]
        PROC["Processing Toolbox<br/>GridIndexProvider (QgsProcessingProvider)"]
        CANVAS["QGIS Project / Map Canvas<br/>(layers, attribute tables, map tips)"]
    end

    subgraph TOOLS["Tool dialogs (UI layer, one QWidget per tool)"]
        T1[AddLayerDialog]
        T2[BasemapSearchDialog]
        T3[QuickQueryDialog]
        T4[GeeDialog]
        T5[DistanceDialog]
        T6[ExportDialog]
        T7[DbExportDialog]
        T8[KoboDialog]
        T9[FotoExplorerDialog]
        T10[FotoLayerDialog]
        T11[GpxDialog]
        T12[GridIndexDialog]
    end

    subgraph LOGIC["Business logic / connector modules (no Qt, mostly testable in isolation)"]
        L1[ows_utils.py]
        L2["QMS: quick_map_services<br/>(external plugin)"]
        L3[qgis native expressions]
        L4[gee_connector.py]
        L5[distance_processor.py]
        L6[exporter.py]
        L7[db_exporter.py]
        L8[kobo_connector.py]
        L9[foto_layer_utils.py]
        L10[gpx_processor.py + processing.run]
        L11[grid_index_algorithm.py]
    end

    subgraph EXTERNAL["External systems and formats"]
        E1["OGC XYZ / WMTS / WMS / WFS servers"]
        E2["QuickMapServices basemap catalog"]
        E3["Google Earth Engine platform"]
        E4["Forest/kawasan reference layer (local)"]
        E5["CSV / GeoJSON / XLSX files"]
        E6["PostGIS / Supabase database"]
        E7["KoboToolbox REST API"]
        E8["GPX file (Garmin)"]
        E9["GDAL/OGR + native Processing algorithms"]
    end

    TB --> PB --> DOCK --> PANEL
    PB --> PROC
    PANEL -->|"_open_tool(key, dialog_cls)<br/>creates once, caches in _pages"| T1 & T2 & T3 & T4 & T5 & T6 & T7 & T8 & T9 & T10 & T11 & T12

    T1 --> L1 --> E1
    T1 -.-> L4
    T2 --> L2 --> E2
    T3 --> L3
    T4 --> L4 --> E3
    T5 --> L5 --> E4
    T6 --> L6 --> E5
    T7 --> L7 --> E6
    T8 --> L8 --> E7
    T9 --> L8
    T10 --> L9 --> E7
    T11 --> L10 --> E9 --> E8
    T12 --> L11
    PROC --> L11

    T1 & T3 & T5 & T6 & T7 & T8 & T9 & T10 & T11 & T12 -->|"finished signal<br/>adds/updates layer"| CANVAS
    L11 -->|"output grid layer"| CANVAS
```

### 0.2 How opening a tool works (sidebar lifecycle)

```mermaid
sequenceDiagram
    participant U as User
    participant Plug as AgroforestryGisToolkitPlugin
    participant Dock as QDockWidget
    participant Panel as SidebarPanel
    participant Dlg as Tool dialog (e.g. KoboDialog)
    participant Ext as External system / QGIS core

    U->>Plug: Click toolbar icon
    Plug->>Dock: toggle_panel() -> show()/hide()
    Dock->>Panel: display SidebarPanel (menu page)
    U->>Panel: Click a tool button
    alt tool page not opened yet
        Panel->>Dlg: create dialog_cls(iface)
        Panel->>Panel: cache in self._pages[key]
    else tool page already cached
        Panel->>Panel: reuse self._pages[key]
    end
    Panel->>Panel: stack.setCurrentWidget(page), show "Back to menu"
    U->>Dlg: fill inputs, run action
    Dlg->>Ext: call connector/processor (Kobo API, GEE, PostGIS, GDAL, etc.)
    Ext-->>Dlg: result (data, layer, file, error)
    Dlg-->>U: show result / status message
    Dlg->>Panel: emit finished signal
    Panel->>Panel: _show_menu() -> back to tool list
```

### 0.3 What each layer is responsible for

| Layer | Files | Responsibility |
| --- | --- | --- |
| Bootstrap | `__init__.py`, `agroforestry_gis_toolkit_plugin.py` | QGIS entry point (`classFactory`), toolbar/menu action, dock widget lifecycle, Processing provider registration |
| Panel/navigation | `sidebar_panel.py` | Single dockable panel; menu list of tools; lazily creates and caches each tool's widget in a `QStackedWidget`; handles "Back to menu" |
| UI layer | `*_dialog.py` | One `QWidget`/`QDialog` per tool; collects user input, shows status/progress, emits `finished` when done |
| Business logic | `*_processor.py`, `*_connector.py`, `*_utils.py`, `exporter.py`, `db_exporter.py` | Pure(ish) Python functions that do the actual work: HTTP calls, geometry math, file writing - kept separate from Qt so they are easier to test |
| QGIS core integration | `qgis.core` / `qgis.gui` objects (`QgsVectorLayer`, `QgsProject`, `QgsSpatialIndex`, `QgsVectorFileWriter`, ...) | Represent and persist layers, run coordinate transforms, write output files, register the Processing algorithm |
| External systems | KoboToolbox API, Google Earth Engine, OGC WMTS/WMS/WFS servers, QuickMapServices catalog, PostGIS/Supabase, GDAL/OGR, filesystem | Everything outside the plugin/QGIS process that data is pulled from or pushed to |

Each diagram below reflects the actual code flow of that individual tool (dialog -> processing module -> QGIS API), and fits into the architecture above as one branch under `LOGIC`/`EXTERNAL`.

## 1. Kobo Connect

```mermaid
flowchart TD
    A[Open Kobo Connect] --> B[Enter API URL, username, password]
    B --> C["list_forms(): authenticate and list KoboToolbox forms"]
    C --> D[Select a form / asset UID]
    D --> E["get_geo_fields(): detect geometry field"]
    E --> F[Select geo field]
    F --> G["fetch_submissions(): paginated fetch, page_size=1000"]
    G --> H["build_feature_collection(): flatten + parse geopoint/geotrace"]
    H --> I["load_features_to_layer(): create QGIS memory layer"]
    I --> J[Layer added to project]
```

## 2. Foto di Layer (Kobo)

```mermaid
flowchart TD
    A[Open Foto di Layer] --> B[Pick survey layer with photo field]
    B --> C["detect_photo_slots(): find photo attachment fields"]
    C --> D["pick_id_field() / pick_title_field()"]
    D --> E[Choose destination folder]
    E --> F["build_jobs(): one download job per photo slot per feature"]
    F --> G["run_download_jobs(): authenticated session, fetch_bytes()"]
    G --> H["_save_resized(): resize + EXIF rotation"]
    H --> I[Save file, build virtual path field]
    I --> J["build_map_tip(): HTML preview"]
    J --> K[Map tip + attribute form show photo at point]
```

## 3. Foto Explorer (Kobo)

```mermaid
flowchart TD
    A[Open Foto Explorer] --> B[Connect to Kobo form]
    B --> C["get_image_fields(): detect repeat-group image fields"]
    C --> D["fetch_submissions(): submissions incl. repeat groups"]
    D --> E["build_photo_feature_collection(): one entry per photo"]
    E --> F[Browse photo list/grid in dialog]
    F --> G{Photo selected?}
    G -->|Yes| H["download_attachment(): fetch on demand"]
    H --> I[Show full-size preview]
    G -->|No| F
```

## 4. Quick Query

```mermaid
flowchart TD
    A[Open Quick Query] --> B[Select target layer]
    B --> C[Search box: text/attribute search]
    B --> D[Filter box: field + operator + value]
    B --> E[QC box: presets, e.g. empty geometry / missing coordinates]
    C --> F[Build QGIS expression]
    D --> F
    E --> F
    F --> G["layer.setSubsetString() / selectByExpression()"]
    G --> H[Filtered features shown on map and attribute table]
```

## 5. Distance Analysis

```mermaid
flowchart TD
    A[Open Distance Analysis] --> B[Select point layer]
    A --> C[Select forest/kawasan layer + status field]
    B --> D["utm_crs_for_point(): pick local UTM zone"]
    C --> E["_ForestIndex: build spatial index of forest polygons"]
    D --> F["compute_distances(): nearest forest, distance, status per point"]
    E --> F
    F --> G["_convert(): distance in m/km"]
    G --> H{Output type}
    H -->|Line layer| I["create_line_layer(): point-to-nearest-forest lines"]
    H -->|Add fields| J["add_fields_to_points(): distance + status columns"]
    I --> K["summarize(): result stats"]
    J --> K
```

## 6. Export Data (Excel / GeoJSON / CSV)

```mermaid
flowchart TD
    A[Open Export Data] --> B[Select layer]
    B --> C[Choose format: Excel, GeoJSON or CSV]
    C --> D[Choose output path]
    D --> E["export_layer(): QGIS OGR/XLSX writer"]
    E --> F[File written to disk]
```

## 7. Export to Database (PostGIS / Supabase)

```mermaid
flowchart TD
    A[Open Export to Database] --> B["list_saved_connections(): QGIS saved PostGIS connections"]
    B --> C[Pick connection + destination table name]
    C --> D[Select source layer]
    D --> E["sanitize_layer() / _sanitize_field_name(): safe SQL identifiers"]
    E --> F["export_layer_to_postgis(): QgsVectorLayerExporter"]
    F --> G[Table created/appended in PostGIS or Supabase]
```

## 8. Add Layer (Tiles / WMTS / WMS / WFS / File / GEE)

```mermaid
flowchart TD
    A[Open Add Layer] --> B{Source tab}
    B -->|XYZ / WMTS / WMS / WFS| C[Fill service URL + params]
    C --> D["ows_utils: build QGIS data source URI"]
    B -->|Local file| E[Browse file of any OGR/GDAL-supported format]
    B -->|Google Earth Engine| F[Pick GEE dataset + parameters]
    D --> G[iface.addRasterLayer / addVectorLayer]
    E --> G
    F --> G
    G --> H[Layer added to map canvas]
```

## 9. Basemap Search (QMS)

```mermaid
flowchart TD
    A[Open Basemap Search] --> B[Type search text]
    B --> C[Query Quick Map Services catalog]
    C --> D[Show matching basemap results]
    D --> E[Select a basemap]
    E --> F[Add as XYZ raster tile layer]
```

## 10. GEE Connect (Google Earth Engine)

```mermaid
flowchart TD
    A[Open GEE Connect] --> B{"ee_available()?"}
    B -->|No| Z[Show install/setup warning]
    B -->|Yes| C["initialize() / authenticate()"]
    C --> D["load_catalog(): trimmed geemap dataset catalog"]
    D --> E["search_catalog(): find dataset"]
    E --> F[Select dataset + date range + area of interest]
    F --> G["build_image(): apply date/region/visualization params"]
    G --> H["get_tile_url(): Earth Engine map tile URL"]
    H --> I[Add as XYZ layer in QGIS]
    F -.vector dataset.-> J["fetch_geojson(): retrieve features"]
    J --> I
```

## 11. Export to GPX (Garmin)

```mermaid
flowchart TD
    A[Open Export to GPX] --> B[Select point or line layer]
    B --> C[Choose name field]
    C --> D[Choose output .gpx path]
    D --> E["export_to_gpx(): build GPX XML (waypoints/tracks)"]
    E --> F[.gpx file ready to load onto a Garmin device]
```

## 12. Grid Index

```mermaid
flowchart TD
    A[Open Grid Index] --> B[Set extent, scale, page size, rotation]
    B --> C["GridIndexAlgorithm.processAlgorithm()"]
    C --> D{Layer CRS type}
    D -->|Projected| E[Compute grid cells directly in layer CRS]
    D -->|Geographic e.g. WGS84| F[Transform to World Mercator EPSG:3395 for distance-accurate cells]
    E --> G[Generate indexed grid/page polygons]
    F --> G
    G --> H[Output grid layer for map series / atlas]
    G --> I[Also available from Processing Toolbox]
```

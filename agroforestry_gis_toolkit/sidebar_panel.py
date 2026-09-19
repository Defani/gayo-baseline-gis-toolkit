# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtCore import Qt

from .branding import AFFILIATION, AUTHOR_NAME, AUTHOR_ROLE, LOCATION, PLUGIN_NAME
from .add_layer_dialog import AddLayerDialog
from .distance_dialog import DistanceDialog
from .gee_dialog import GeeDialog
from .export_dialog import ExportDialog
from .db_export_dialog import DbExportDialog
from .kobo_dialog import KoboDialog
from .foto_explorer_dialog import FotoExplorerDialog
from .foto_layer_dialog import FotoLayerDialog
from .basemap_search_dialog import BasemapSearchDialog
from .gpx_dialog import GpxDialog
from .grid_index_dialog import GridIndexDialog
from .quick_query_dialog import QuickQueryDialog

# Width (px) of the small logo shown in the panel header. Kept compact so
# the header stays a thin strip instead of a big centered banner.
LOGO_WIDTH = 22



class SidebarPanel(QWidget):
    """Content of the sidebar panel.

    Everything happens inside this single embedded panel: there are no
    popup dialogs. A small menu lists each tool; picking one swaps the
    panel's content area to that tool's settings in place. A "Back to
    menu" button returns to the list.
    """

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.iface = plugin.iface
        self._pages = {}
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        # --- Compact header: small logo + title ---
        header = QHBoxLayout()
        header.setSpacing(6)
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            logo = QLabel()
            pixmap = QPixmap(icon_path).scaledToWidth(LOGO_WIDTH, Qt.SmoothTransformation)
            logo.setPixmap(pixmap)
            logo.setFixedWidth(LOGO_WIDTH)
            header.addWidget(logo)

        title = QLabel(PLUGIN_NAME)
        title.setStyleSheet("font-weight: bold;")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        outer.addLayout(header)

        # --- Back button, shown only while a tool page is active ---
        self.btn_back = QPushButton("\u2190 Back to menu")
        self.btn_back.clicked.connect(self._show_menu)
        self.btn_back.hide()
        outer.addWidget(self.btn_back)

        # --- Stacked content area: page 0 is the tool menu, the rest are
        # the individual tools, opened in place instead of as popups ---
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        self.menu_page = self._build_menu_page()
        self.stack.addWidget(self.menu_page)

        # --- Footer: author / consultant credit, always visible ---
        footer = QLabel(f"{AUTHOR_NAME} \u00b7 {AUTHOR_ROLE}\n{AFFILIATION}\n{LOCATION}")
        footer.setAlignment(Qt.AlignLeft)
        footer.setStyleSheet("color: gray; font-size: 10px; margin-top: 4px;")
        footer.setWordWrap(True)
        outer.addWidget(footer)

    def _build_menu_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)

        tools = [
            ("Add Layer (Tiles / WMTS / File)...", lambda: self._open_tool("add_layer", AddLayerDialog)),
            ("Basemap Search (QMS)...", lambda: self._open_tool("basemap", BasemapSearchDialog)),
            ("Quick Query...", lambda: self._open_tool("quick_query", QuickQueryDialog)),
            ("GEE Connect (Earth Engine)...", lambda: self._open_tool("gee", GeeDialog)),
            ("Distance Analysis (Titik ke Kawasan Hutan)...", lambda: self._open_tool("distance", DistanceDialog)),
            ("Export Data (Excel/GeoJSON/CSV)...", lambda: self._open_tool("export", ExportDialog)),
            ("Export to Database (PostGIS/Supabase)...", lambda: self._open_tool("db_export", DbExportDialog)),
            ("Kobo Connect...", lambda: self._open_tool("kobo", KoboDialog)),
            ("Foto Explorer (Kobo)...", lambda: self._open_tool("foto_explorer", FotoExplorerDialog)),
            ("Foto di Layer (Kobo)...", lambda: self._open_tool("foto_layer", FotoLayerDialog)),
            ("Export to GPX (Garmin)...", lambda: self._open_tool("gpx", GpxDialog)),
            ("Grid Index...", lambda: self._open_tool("grid_index", GridIndexDialog)),
        ]
        for label, callback in tools:
            btn = QPushButton(label)
            btn.setMinimumHeight(32)
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        layout.addStretch()
        return page

    def _open_tool(self, key, dialog_cls):
        if key not in self._pages:
            page = dialog_cls(self.iface)
            # Tools used to close a popup dialog via self.accept(); they now
            # emit `finished` instead, which just returns us to the menu.
            page.finished.connect(self._show_menu)
            self._pages[key] = page
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(self._pages[key])
        self.btn_back.show()

    def _show_menu(self):
        self.stack.setCurrentWidget(self.menu_page)
        self.btn_back.hide()

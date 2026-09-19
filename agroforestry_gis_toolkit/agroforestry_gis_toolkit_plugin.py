# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtWidgets import QAction, QDockWidget
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsApplication

from .branding import PLUGIN_NAME
from .grid_index_provider import GridIndexProvider
from .sidebar_panel import SidebarPanel


class AgroforestryGisToolkitPlugin:
    """Personal GIS toolkit for agroforestry landscape fieldwork and mapping."""

    MENU_NAME = "&" + PLUGIN_NAME

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.toolbar = None
        self.dock_widget = None
        self.processing_provider = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        # Single toolbar icon - click to open/close the sidebar panel.
        # Every tool lives inside this one panel; nothing opens as a
        # separate popup window.
        self.toolbar = self.iface.addToolBar(PLUGIN_NAME)
        self.toolbar.setObjectName("AgroforestryGisToolkitToolbar")

        self.action_toggle_panel = QAction(icon, PLUGIN_NAME, self.iface.mainWindow())
        self.action_toggle_panel.setCheckable(True)
        self.action_toggle_panel.triggered.connect(self.toggle_panel)
        self.toolbar.addAction(self.action_toggle_panel)
        self.actions.append(self.action_toggle_panel)

        # Also keep an entry in the Plugins menu that opens the same panel
        self.iface.addPluginToMenu(self.MENU_NAME, self.action_toggle_panel)

        self._create_dock_widget()
        self.initProcessing()

    def initProcessing(self):
        """Register the Processing providers (Grid Index) so they are
        also available from the Processing Toolbox, in addition to the
        sidebar panel."""
        self.processing_provider = GridIndexProvider()
        QgsApplication.processingRegistry().addProvider(self.processing_provider)

    def _create_dock_widget(self):
        self.dock_widget = QDockWidget(PLUGIN_NAME, self.iface.mainWindow())
        self.dock_widget.setObjectName("AgroforestryGisToolkitDock")
        self.dock_widget.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.dock_widget.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable
        )
        self.dock_widget.setWidget(SidebarPanel(self))
        # Docked permanently in the sidebar, NOT floating
        self.dock_widget.setFloating(False)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
        self.dock_widget.hide()
        self.dock_widget.visibilityChanged.connect(self._on_visibility_changed)

    def toggle_panel(self):
        if self.dock_widget.isVisible():
            self.dock_widget.hide()
        else:
            self.dock_widget.setFloating(False)
            self.dock_widget.show()
            self.dock_widget.raise_()

    def _on_visibility_changed(self, visible):
        # Keep the toolbar button state in sync with the panel (e.g. when
        # closed via the dock's own X button)
        self.action_toggle_panel.setChecked(visible)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.MENU_NAME, action)
        self.actions = []
        if self.toolbar:
            del self.toolbar
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget = None
        if self.processing_provider:
            QgsApplication.processingRegistry().removeProvider(self.processing_provider)
            self.processing_provider = None

# -*- coding: utf-8 -*-

"""
Processing provider that exposes the Grid Index algorithm in the QGIS
Processing Toolbox, in addition to the dedicated sidebar dialog.
"""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .grid_index_algorithm import GridIndexAlgorithm


class GridIndexProvider(QgsProcessingProvider):

    def unload(self):
        """Unloads the provider. Any tear-down steps required by the
        provider should be implemented here."""
        pass

    def loadAlgorithms(self, *args, **kwargs):
        """Loads all algorithms belonging to this provider."""
        self.addAlgorithm(GridIndexAlgorithm())

    def id(self, *args, **kwargs):
        """The ID of this provider, used for identifying it internally.

        This string should be unique and must not be changed once released.
        """
        return 'agroforestry_grid_index'

    def name(self, *args, **kwargs):
        return self.tr('Grid Index')

    def longName(self, *args, **kwargs):
        return self.tr('Grid Index')

    def icon(self):
        """Returns a QIcon used for this provider inside the Processing
        toolbox."""
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        return QIcon(icon_path)

# -*- coding: utf-8 -*-
"""
Gayo Coffee Baseline GIS Toolkit
GIS toolkit for the Gayo coffee farmer baseline survey (Aceh Tengah & Bener Meriah).
Author: Defani Arman, GIS Consultant - TFCA Sumatera Program,
Rumah Indonesia Berkelanjutan, Redelong Institute.
"""


def classFactory(iface):
    from .agroforestry_gis_toolkit_plugin import AgroforestryGisToolkitPlugin
    return AgroforestryGisToolkitPlugin(iface)

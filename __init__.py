def classFactory(iface):
    from .plugin import DNLRasterLoader
    return DNLRasterLoader(iface)

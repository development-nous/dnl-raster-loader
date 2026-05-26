import os
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsVectorLayer,
    QgsRasterLayer,
    QgsProject,
    QgsDataSourceUri,
    Qgis,
)

MAX_TILES = 25

## Names of tables that constitute valid raster dataset layers.
## Extend this list if you add more dataset tables in future.
RASTER_DATASET_TABLE = "raster_dataset"
RASTER_DATASET_SCHEMA = "__attribute"


class DNLRasterLoader:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.toolbar = None

    ## ------------------------------------------------------------------
    ## QGIS plugin lifecycle
    ## ------------------------------------------------------------------

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "res/icons/icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(icon, "Load Selected Raster Tiles", self.iface.mainWindow())
        self.action.setToolTip(
            "Load raster images from MinIO for the selected tile footprints.\n"
            f"Maximum {MAX_TILES} tiles per operation."
        )
        self.action.triggered.connect(self.run)

        ## Add to the Raster menu and to a dedicated toolbar
        self.iface.addRasterToolBarIcon(self.action)
        self.iface.addPluginToRasterMenu("DNL Raster Loader", self.action)

    def unload(self):
        self.iface.removeRasterToolBarIcon(self.action)
        self.iface.removePluginRasterMenu("DNL Raster Loader", self.action)

    ## ------------------------------------------------------------------
    ## Helpers
    ## ------------------------------------------------------------------

    def _push(self, message, level=Qgis.Info, duration=5):
        self.iface.messageBar().pushMessage(
            "Raster Loader",
            message,
            level=level,
            duration=duration,
        )

    def _get_registered_tables(self, layer):
        """
        Query __attributes.raster_dataset non-spatial table on the same PostGIS
        connection as the active layer and return a set of registered table
        names. Returns an empty set on any failure.
        """
        try:
            uri = QgsDataSourceUri(layer.dataProvider().dataSourceUri())

            ## Reuse the same connection parameters but point at the registry table
            query_uri = QgsDataSourceUri()
            query_uri.setConnection(
                uri.host(),
                uri.port() or "32032",
                uri.database(),
                uri.username(),
                uri.password()
            )

            ## Pass the auth config token through if present
            if uri.authConfigId():
                query_uri.setAuthConfigId(uri.authConfigId())

            query_uri.setDataSource(
                RASTER_DATASET_SCHEMA,
                RASTER_DATASET_TABLE,
                None,
                '',
                'table_name',
            )

            tmp = QgsVectorLayer(
                query_uri.uri(False),
                f"{RASTER_DATASET_SCHEMA}.{RASTER_DATASET_TABLE}",
                "postgres",
            )
            if not tmp.isValid():
                error = tmp.dataProvider().error().message() if tmp.dataProvider() else "no provider"
                self._push(f"Registry invalid: {error}", Qgis.Warning)
                self._push(f"URI was: {query_uri.uri(False)}", Qgis.Warning)
                return set()

            return {f["table_name"] for f in tmp.getFeatures()}

        except Exception as e:
            self._push(f"Registry query failed: {e}", Qgis.Warning)
            return set()

    def _layer_is_registered(self, layer):
        """
        Return True if the layer's source table is listed in the tables in
        RASTER_DATASET_TABLES.
        Works for PostGIS vector layers; falls back gracefully for other
        providers.
        """
        try:
            registered_tables = self._get_registered_tables(layer)
            uri = QgsDataSourceUri(layer.dataProvider().dataSourceUri())
            if uri.table() not in registered_tables:
                self._push(
                    f"Layer '{layer.name()}' is not registered in {RASTER_DATASET_TABLE}.",
                    Qgis.Warning,
                )
                return False
            return True
        except Exception:
            return False

    def _layer_has_uri_field(self, layer):
        """Return True if the layer has a field named 'uri'."""
        return layer.fields().indexFromName("uri") != -1

    ## ------------------------------------------------------------------
    ## Main action
    ## ------------------------------------------------------------------

    def run(self):
        layer = self.iface.activeLayer()

        ## --- Guard: must have an active layer ---
        if layer is None:
            self._push("No active layer. Select a tile footprint layer first.", Qgis.Warning)
            return

        ## --- Guard: layer must be registered in raster_dataset ---
        if not self._layer_is_registered(layer):
            self._push(
                f"Layer '{layer.name()}' is not a registered raster_dataset layer.",
                Qgis.Warning,
            )
            return

        ## --- Guard: layer must have a uri field ---
        if not self._layer_has_uri_field(layer):
            self._push(
                f"Layer '{layer.name()}' has no 'uri' field.",
                Qgis.Warning,
            )
            return

        ## --- Guard: something must be selected ---
        selected = layer.selectedFeatures()
        if not selected:
            self._push("No tiles selected. Use the Select tool to choose tiles first.", Qgis.Warning)
            return

        ## --- Guard: cap selection size ---
        if len(selected) > MAX_TILES:
            self._push(
                f"{len(selected)} tiles selected — maximum is {MAX_TILES}. "
                "Refine your selection and try again.",
                Qgis.Warning,
                duration=8,
            )
            return

        ## --- Load rasters ---
        loaded = 0
        skipped = 0
        failed = []

        for feature in selected:
            path = feature["uri"]

            if not path or str(path).strip() == "" or str(path) == "NULL":
                failed.append(f"(fid {feature.id()}: empty uri)")
                continue

            path = str(path).strip()
            layer_name = path.split("/")[-1] or path

            ## Skip if already loaded
            if QgsProject.instance().mapLayersByName(layer_name):
                skipped += 1
                continue

            rl = QgsRasterLayer(path, layer_name)
            if rl.isValid():
                QgsProject.instance().addMapLayer(rl)
                loaded += 1
            else:
                err = rl.error().message() if rl.error() else "unknown error"
                failed.append(f"{layer_name}: {err}")

        ## --- Report ---
        parts = []
        if loaded:
            parts.append(f"{loaded} loaded")
        if skipped:
            parts.append(f"{skipped} already open")
        if failed:
            parts.append(f"{len(failed)} failed")

        summary = ", ".join(parts) if parts else "nothing to do"

        if failed:
            detail = "\n".join(failed)
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Raster Loader",
                f"Completed with errors ({summary}):\n\n{detail}",
            )
        else:
            level = Qgis.Success if loaded else Qgis.Info
            self._push(summary.capitalize() + ".", level)

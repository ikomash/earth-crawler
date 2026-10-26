from mpl_toolkits.basemap import Basemap
import matplotlib.pyplot as plt

from paths import Paths


class MplMinimap():
    """Create a small minimap preview."""

    def __init__(self):
        """Initialize a Matplotlib basemap used for the minimap image."""
        # create new figure, axes instances.
        fig = plt.figure(figsize=(1, 1), frameon=False)
        self.ax = fig.add_axes((0.1, 0.1, 0.8, 0.8))
        for facet in ['top', 'bottom', 'left', 'right']:
            self.ax.spines[facet].set_linewidth(0.3)
        # setup mercator map projection.
        self.m = Basemap()
        self.m.drawcoastlines(linewidth=0.3)
        self.m.fillcontinents()
        self.sc = None

    def set_point(self, lat: float, lon: float, index: int):
        """Adds point to created basemap

        Args:
            lat (float): Point latitude
            lon (float): Point longitude
            index (int): List widget row number
        """
        if self.sc is not None:
            self.sc.remove()
        self.sc = self.m.scatter(
            lon, lat, marker='o', c='r', edgecolors="b",
            linewidths=0.5, s=6, zorder=5
            )
        Paths.tmp_folder.mkdir(parents=True, exist_ok=True)
        image_path = Paths.tmp_folder / f"minimap_{index}.png"
        plt.savefig(str(image_path), dpi=200)

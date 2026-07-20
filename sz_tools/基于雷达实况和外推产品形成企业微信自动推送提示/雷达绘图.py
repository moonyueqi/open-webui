# -*- coding: utf-8 -*-
"""
Created on Thu Jun  4 13:53:44 2026

@author: LJH
"""

from netCDF4 import Dataset
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import geopandas as gpd
from matplotlib.colors import BoundaryNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import cartopy.crs as ccrs
import datetime
from shapely.ops import unary_union
from matplotlib.font_manager import FontProperties

# ===== 读取 nc =====
ds = Dataset(r"D:/Mosaic20260604053600_TreRef.nc", "r")
lat  = ds.variables["lat"][:]
lon  = ds.variables["lon"][:]
data = ds.variables["data"][:]
tss  = ds.variables["tss"][:]
ds.close()

# ===== 读取 shp =====
province = gpd.read_file(r"D:/最新2021年全国行政区划/省.shp", encoding="GBK")
city     = gpd.read_file(r"D:/最新2021年全国行政区划/市.shp", encoding="GBK")
county   = gpd.read_file(r"D:/最新2021年全国行政区划/县.shp", encoding="GBK")
township = gpd.read_file(r"D:/苏州乡镇/苏州乡镇.shp",         encoding="GBK")

# ===== 筛选苏州 =====
def find_by_name(gdf, keyword):
    for col in gdf.columns:
        if gdf[col].dtype == object and gdf[col].str.contains(keyword, na=False).any():
            return gdf[gdf[col].str.contains(keyword, na=False)].copy()
    raise ValueError(f"未找到包含'{keyword}'的字段")

suzhou        = find_by_name(city,   "苏州")
suzhou_county = find_by_name(county, "苏州")

suzhou_wgs84        = suzhou.to_crs(epsg=4326)
suzhou_county_wgs84 = suzhou_county.to_crs(epsg=4326)
township_wgs84      = township.to_crs(epsg=4326)

# ===== 缓冲区（改为75km）=====
suzhou_union = unary_union(suzhou.to_crs(epsg=32651).geometry)

buffer_50km_gdf = gpd.GeoDataFrame(
    geometry=[suzhou_union.buffer(50000)], crs="EPSG:32651"
).to_crs(epsg=4326)

b = gpd.GeoDataFrame(
    geometry=[suzhou_union.buffer(75000)], crs="EPSG:32651"
).to_crs(epsg=4326).total_bounds
extent = [b[0] - 0.1, b[2] + 0.1, b[1] - 0.1, b[3] + 0.1]

# ===== 色标 =====
levels = [-10, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]
colors = [
    "#FFFFFF", "#9DFAFF", "#00BFFF", "#0000FF",
    "#00FF00", "#00CC00", "#009900", "#FFFF00",
    "#FFD700", "#FF8C00", "#FF4500", "#FF0000",
    "#CC0000", "#990000", "#FF00FF",
]
cmap = mcolors.ListedColormap(colors)
norm = BoundaryNorm(levels, ncolors=cmap.N)
lon2d, lat2d = np.meshgrid(lon, lat)

# ===== 画图 =====
fig, ax = plt.subplots(figsize=(10, 9),
                       subplot_kw={"projection": ccrs.PlateCarree()})
ax.set_extent(extent, crs=ccrs.PlateCarree())

# 雷达数据
plot_data = np.ma.masked_where(data[0, 0, :, :] <= -32768, data[0, 0, :, :])
ax.pcolormesh(lon2d, lat2d, plot_data, cmap=cmap, norm=norm,
              transform=ccrs.PlateCarree(), shading="auto")

# 省界
province.boundary.plot(ax=ax, edgecolor="black", linewidth=1.2,
                       transform=ccrs.PlateCarree(), zorder=3)

# 市界（全国）
city.boundary.plot(ax=ax, edgecolor="#666666", linewidth=0.6,
                   linestyle="--", transform=ccrs.PlateCarree(), zorder=3)

# 苏州县界 —— 黑色实线
suzhou_county_wgs84.boundary.plot(ax=ax, edgecolor="black", linewidth=0.8,
                                  linestyle="-",
                                  transform=ccrs.PlateCarree(), zorder=4)

# 苏州乡镇界 —— 黑色点线
township_wgs84.boundary.plot(ax=ax, edgecolor="black", linewidth=0.5,
                             linestyle=":",
                             transform=ccrs.PlateCarree(), zorder=4)

# 苏州市界 —— 黑色加粗实线
suzhou_wgs84.boundary.plot(ax=ax, edgecolor="black", linewidth=2.0,
                           transform=ccrs.PlateCarree(), zorder=5)

# 50km 缓冲区
buffer_50km_gdf.plot(ax=ax, facecolor="red", alpha=0.04,
                     transform=ccrs.PlateCarree(), zorder=4)
buffer_50km_gdf.boundary.plot(ax=ax, edgecolor="red", linewidth=1.8,
                               linestyle="--",
                               transform=ccrs.PlateCarree(), zorder=6)

# 网格线
gl = ax.gridlines(draw_labels=True, linewidth=0.4,
                  color="gray", alpha=0.5, linestyle="--")
gl.top_labels = False;  gl.right_labels = False
gl.xlabel_style = {"size": 9};  gl.ylabel_style = {"size": 9}

# 色标
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])
cbar = fig.colorbar(sm, ax=ax, orientation="vertical",
                    pad=0.02, shrink=0.85, extend="both")
cbar.set_label("反射率 (dBZ)", fontsize=11, fontproperties="SimHei")
cbar.set_ticks(levels);  cbar.ax.tick_params(labelsize=8)

# 图例
legend_elements = [
    Line2D([0], [0], color="black", linewidth=2,                  label="苏州市界"),
    Line2D([0], [0], color="black", linewidth=0.8, linestyle="-", label="苏州县界"),
    Line2D([0], [0], color="black", linewidth=0.5, linestyle=":", label="苏州乡镇界"),
    Line2D([0], [0], color="red",   linewidth=1.8, linestyle="--",label="苏州市外50km缓冲区"),
    Patch(facecolor="red", alpha=0.1,                label="缓冲区范围"),
]
ax.legend(handles=legend_elements, loc="lower left",
          prop={"family": "SimHei", "size": 9},
          framealpha=0.7, facecolor="white")

# 标题
dt_bj = datetime.datetime.utcfromtimestamp(int(tss[0])) + datetime.timedelta(hours=8)
font_title = FontProperties(family="SimHei", size=15)
ax.set_title(f"雷达组合反射率  {dt_bj.strftime('%Y-%m-%d %H:%M')} CST",
             fontproperties=font_title, pad=8)

plt.savefig(r"D:/radar_suzhou_township.png", dpi=150, bbox_inches="tight")
plt.show()
print("已保存到 D:/radar_suzhou_township.png")


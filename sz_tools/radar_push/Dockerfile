# 雷达推送服务镜像。
# geojson 已离线预生成并随源码 COPY 进镜像，因此运行时无需 geopandas/GDAL。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 中文字体（plotter 渲染需要）+ 时区。
# 说明：netCDF4 的 PyPI wheel 已内置 HDF5/netcdf 库，无需再装系统的
# libhdf5/libnetcdf（其包名在不同 Debian 版本间会变，反而易构建失败）。
# apt 换清华镜像源：兼容 trixie 的 deb822 格式（debian.sources）与旧的
# sources.list 格式，避免连不上官方 deb.debian.org 导致构建失败。
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
        fonts-wqy-zenhei \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# 应用代码 + 预生成的 geojson（data/）
COPY app /app/app
COPY data /app/data
# 运维脚本（历史回放 replay.py、空跑 dryrun.py 等），运行时按需手动执行
COPY scripts /app/scripts

# 去重状态目录（compose 会把宿主机卷挂到这里）
RUN mkdir -p /app/state

EXPOSE 8770

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8770/health').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8770"]

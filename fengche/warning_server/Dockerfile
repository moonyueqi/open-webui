FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 1) 换 Debian APT 源为国内清华镜像，再装 netCDF/HDF5/GEOS 头文件
#    python:3.11-slim 基于 Debian 12 (bookworm)，源文件在 /etc/apt/sources.list.d/debian.sources；
#    同时兼容老的 /etc/apt/sources.list。
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list; \
    fi; \
    apt-get update \
 && apt-get install -y --no-install-recommends \
        libnetcdf-dev \
        libhdf5-dev \
        libgeos-dev \
 && rm -rf /var/lib/apt/lists/*

# 2) pip 走清华源安装 Python 依赖
#    构建上下文为 fengche/，所以这里写 warning_server/...
COPY warning_server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        --trusted-host pypi.tuna.tsinghua.edu.cn \
        -r requirements.txt

# 3) 依赖：fengche_tool_server.app.datasource / forecast_finder
#    容器内 import 路径仍是 fengche_tool_server.app.xxx
COPY tool_server/app /app/fengche_tool_server/app

# 4) 本服务自身
COPY warning_server/app /app/fengche_warning_server/app
COPY warning_server/data /app/fengche_warning_server/data

# 5) 顶层 __init__.py，保证 fengche_tool_server / fengche_warning_server 作为 package 可被 import
RUN python -c "open('/app/fengche_tool_server/__init__.py','a').close(); \
               open('/app/fengche_warning_server/__init__.py','a').close()"

EXPOSE 8766

CMD ["uvicorn", "fengche_warning_server.app.main:app", "--host", "0.0.0.0", "--port", "8766"]

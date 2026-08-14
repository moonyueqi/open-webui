# Initialize device type args
# use build args in the docker build command with --build-arg="BUILDARG=true"
ARG USE_CUDA=false
ARG USE_OLLAMA=false
ARG USE_SLIM=false
ARG USE_PERMISSION_HARDENING=false
# Tested with cu117 for CUDA 11 and cu121 for CUDA 12 (default)
ARG USE_CUDA_VER=cu128
# any sentence transformer model; models to use can be found at https://huggingface.co/models?library=sentence-transformers
# Leaderboard: https://huggingface.co/spaces/mteb/leaderboard 
# for better performance and multilangauge support use "intfloat/multilingual-e5-large" (~2.5GB) or "intfloat/multilingual-e5-base" (~1.5GB)
# IMPORTANT: If you change the embedding model (sentence-transformers/all-MiniLM-L6-v2) and vice versa, you aren't able to use RAG Chat with your previous documents loaded in the WebUI! You need to re-embed them.
ARG USE_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ARG USE_RERANKING_MODEL=""
ARG USE_AUXILIARY_EMBEDDING_MODEL=TaylorAI/bge-micro-v2

ARG BUILD_HASH=dev-build
# Override at your own risk - non-root configurations are untested
ARG UID=0
ARG GID=0

######## WebUI frontend ########
FROM --platform=$BUILDPLATFORM node:22-alpine3.20 AS build
ARG BUILD_HASH

# Set Node.js options (heap limit Allocation failed - JavaScript heap out of memory)
# ENV NODE_OPTIONS="--max-old-space-size=4096"

WORKDIR /app

# === 国内镜像加速：Alpine apk + npm ===
# 1) Alpine 包源换成中科大镜像
# 2) npm registry 换成 npmmirror（淘宝源）
RUN sed -i 's|dl-cdn.alpinelinux.org|mirrors.ustc.edu.cn|g' /etc/apk/repositories && \
    apk add --no-cache git && \
    npm config set registry https://registry.npmmirror.com

# Pyodide 在 prepare-pyodide.js 里会下载 Pyodide 运行时和一组 Python wheel
# 通过环境变量改走国内镜像（jsdelivr 国内镜像 + 清华 PyPI）
ENV PYODIDE_BASE_URL="https://cdn.jsdelivr.net.cn/pyodide/v0.28.2/full/" \
    PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"

COPY package.json package-lock.json ./
# --legacy-peer-deps: 绕过 peer dependency 严格检查（tiptap 部分扩展是 2.26.1，
# 与 @tiptap/core@3.0.7 的 peer 要求不匹配，但实际运行可用）
# 注：长期方案是把 @tiptap/extension-bubble-menu 和 extension-floating-menu 升级到 3.x
RUN npm install --legacy-peer-deps --no-audit --no-fund

COPY . .
ENV APP_BUILD_HASH=${BUILD_HASH}
RUN npm run build

######## WebUI backend ########
FROM python:3.11.14-slim-bookworm AS base

# Use args
ARG USE_CUDA
ARG USE_OLLAMA
ARG USE_CUDA_VER
ARG USE_SLIM
ARG USE_PERMISSION_HARDENING
ARG USE_EMBEDDING_MODEL
ARG USE_RERANKING_MODEL
ARG USE_AUXILIARY_EMBEDDING_MODEL
ARG UID
ARG GID

# Python settings
ENV PYTHONUNBUFFERED=1

## Basis ##
ENV ENV=prod \
    PORT=8080 \
    # pass build args to the build
    USE_OLLAMA_DOCKER=${USE_OLLAMA} \
    USE_CUDA_DOCKER=${USE_CUDA} \
    USE_SLIM_DOCKER=${USE_SLIM} \
    USE_CUDA_DOCKER_VER=${USE_CUDA_VER} \
    USE_EMBEDDING_MODEL_DOCKER=${USE_EMBEDDING_MODEL} \
    USE_RERANKING_MODEL_DOCKER=${USE_RERANKING_MODEL} \
    USE_AUXILIARY_EMBEDDING_MODEL_DOCKER=${USE_AUXILIARY_EMBEDDING_MODEL}

## Basis URL Config ##
ENV OLLAMA_BASE_URL="/ollama" \
    OPENAI_API_BASE_URL=""

## API Key and Security Config ##
ENV OPENAI_API_KEY="" \
    WEBUI_SECRET_KEY="" \
    SCARF_NO_ANALYTICS=true \
    DO_NOT_TRACK=true \
    ANONYMIZED_TELEMETRY=false \
    # Disable per-model access control so every user can use every connected
    # model out of the box. Override with `-e BYPASS_MODEL_ACCESS_CONTROL=false`
    # if you need role/grant based gating.
    BYPASS_MODEL_ACCESS_CONTROL=true

#### Other models #########################################################
## whisper TTS model settings ##
ENV WHISPER_MODEL="base" \
    WHISPER_MODEL_DIR="/app/backend/data/cache/whisper/models"

## RAG Embedding model settings ##
ENV RAG_EMBEDDING_MODEL="$USE_EMBEDDING_MODEL_DOCKER" \
    RAG_RERANKING_MODEL="$USE_RERANKING_MODEL_DOCKER" \
    AUXILIARY_EMBEDDING_MODEL="$USE_AUXILIARY_EMBEDDING_MODEL_DOCKER" \
    SENTENCE_TRANSFORMERS_HOME="/app/backend/data/cache/embedding/models"

## Tiktoken model settings ##
# 注意：缓存路径放在 /opt/cache 而不是 /app/backend/data 下
# 原因：/app/backend/data 是命名卷挂载点，如果运维把它换成 bind mount，
# 镜像里烘焙的 cl100k_base 字典会被空目录覆盖，导致运行期联网拉失败
ENV TIKTOKEN_ENCODING_NAME="cl100k_base" \
    TIKTOKEN_CACHE_DIR="/opt/cache/tiktoken"

## Hugging Face download cache ##
ENV HF_HOME="/app/backend/data/cache/embedding/models"

## Torch Extensions ##
# ENV TORCH_EXTENSIONS_DIR="/.cache/torch_extensions"

#### Other models ##########################################################

WORKDIR /app/backend

ENV HOME=/root
# Create user and group if not root
RUN if [ $UID -ne 0 ]; then \
    if [ $GID -ne 0 ]; then \
    addgroup --gid $GID app; \
    fi; \
    adduser --uid $UID --gid $GID --home $HOME --disabled-password --no-create-home app; \
    fi

RUN mkdir -p $HOME/.cache/chroma
RUN echo -n 00000000-0000-0000-0000-000000000000 > $HOME/.cache/chroma/telemetry_user_id

# Make sure the user has access to the app and root directory
RUN chown -R $UID:$GID /app $HOME

# === 国内镜像加速：Debian apt + pip ===
# 1) Debian 软件源换成清华镜像（bookworm 同时换 main 和 security）
# 2) pip 全局换成清华 PyPI 镜像
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null || true && \
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list 2>/dev/null || true && \
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set install.trusted-host pypi.tuna.tsinghua.edu.cn

# Install common system dependencies
# 注：tzdata 是定时任务（automations）和日历提醒（calendar）正确工作的必要依赖。
# 代码使用 stdlib 的 zoneinfo，需要从 /usr/share/zoneinfo 读时区文件；
# slim 镜像里该目录为空，缺失会让 ZoneInfo('Asia/Shanghai') 抛 ZoneInfoNotFoundError，
# 直接导致 RRULE 的下次执行时间与日历提醒时间偏离 8 小时。
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git build-essential pandoc gcc netcat-openbsd curl jq \
    python3-dev \
    ffmpeg libsm6 libxext6 zstd \
    tzdata \
    libreoffice-core libreoffice-writer libreoffice-impress libreoffice-calc \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 默认容器时区设为东八区；docker-compose 里可用 TZ 环境变量覆盖
ENV TZ=Asia/Shanghai

# install python dependencies
COPY --chown=$UID:$GID ./backend/requirements.txt ./requirements.txt

# === 国内镜像加速：HuggingFace 镜像（仅 USE_SLIM=false 时构建期下载模型才用得到） ===
# hf-mirror.com 是国内常用的 HuggingFace 镜像站
ENV HF_ENDPOINT="https://hf-mirror.com"

# === NLTK 数据存放路径 ===
# nltk 默认从 raw.githubusercontent.com 下载数据，国内基本不通
# 构建期把 punkt_tab.zip 解压到 NLTK_DATA 目录，运行期不联网
# RAG 文档分块（部分 langchain loader）会用到 punkt_tab，无论 USE_SLIM 是否为 true 都需要
# 同样放在 /opt/cache 而不是 /app/backend/data 下，避免被卷挂载覆盖
ENV NLTK_DATA="/opt/cache/nltk_data"

# set -eux: 任何命令失败立即中止整条 RUN，避免之前嵌套 if/fi 把退出码吞掉
# （历史教训：uv pip install 失败但构建继续，导致 nltk/tiktoken 这类纯 Python 包都没装上）
RUN set -eux; \
    pip3 install --no-cache-dir uv; \
    if [ "$USE_CUDA" = "true" ]; then \
        # CUDA：torch 走阿里云 pytorch-wheels 镜像；其他依赖走清华 PyPI
        pip3 install 'torch<=2.9.1' torchvision torchaudio \
            --find-links https://mirrors.aliyun.com/pytorch-wheels/$USE_CUDA_DOCKER_VER/ \
            --index-url https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir; \
        uv pip install --system -r requirements.txt --no-cache-dir \
            --index-url https://pypi.tuna.tsinghua.edu.cn/simple; \
        python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['RAG_EMBEDDING_MODEL'], device='cpu')"; \
        python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ.get('AUXILIARY_EMBEDDING_MODEL', 'TaylorAI/bge-micro-v2'), device='cpu')"; \
        python -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ['WHISPER_MODEL'], device='cpu', compute_type='int8', download_root=os.environ['WHISPER_MODEL_DIR'])"; \
    else \
        # CPU：torch 走阿里云 pytorch-wheels CPU 子站；其他依赖走清华 PyPI
        pip3 install 'torch<=2.9.1' torchvision torchaudio \
            --find-links https://mirrors.aliyun.com/pytorch-wheels/cpu/ \
            --index-url https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir; \
        uv pip install --system -r requirements.txt --no-cache-dir \
            --index-url https://pypi.tuna.tsinghua.edu.cn/simple; \
        if [ "$USE_SLIM" != "true" ]; then \
            python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['RAG_EMBEDDING_MODEL'], device='cpu')"; \
            python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ.get('AUXILIARY_EMBEDDING_MODEL', 'TaylorAI/bge-micro-v2'), device='cpu')"; \
            python -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ['WHISPER_MODEL'], device='cpu', compute_type='int8', download_root=os.environ['WHISPER_MODEL_DIR'])"; \
        fi; \
    fi; \
    # 强制验证关键依赖是否真的装上（uv 偶发静默吞错的最后一道防线）
    python -c "import nltk, tiktoken, fastapi, uvicorn" && echo "core deps OK"; \
    mkdir -p /app/backend/data && chown -R $UID:$GID /app/backend/data/; \
    rm -rf /var/lib/apt/lists/*

# === 离线注入 NLTK 数据（RAG 文档分块 + unstructured pptx/docx 解析必需） ===
# 需要在项目根目录预先放置以下 zip：
#   1) punkt_tab.zip                      —— langchain RAG 分块用
#      下载：https://gh-proxy.com/https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip
#   2) averaged_perceptron_tagger_eng.zip —— unstructured 解析 pptx/docx 时 pos_tag 用
#      下载：https://gh-proxy.com/https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/taggers/averaged_perceptron_tagger_eng.zip
# 这样构建期完全不联网，避免 raw.githubusercontent.com 被墙的问题
# 用 Python 内置 zipfile 解压，避免引入 unzip 包，省一层镜像
COPY --chown=$UID:$GID punkt_tab.zip /tmp/punkt_tab.zip
COPY --chown=$UID:$GID averaged_perceptron_tagger_eng.zip /tmp/averaged_perceptron_tagger_eng.zip
RUN set -eux; \
    mkdir -p "$NLTK_DATA/tokenizers" "$NLTK_DATA/taggers"; \
    python -c "import zipfile, os; zipfile.ZipFile('/tmp/punkt_tab.zip').extractall(os.environ['NLTK_DATA'] + '/tokenizers/')"; \
    python -c "import zipfile, os; zipfile.ZipFile('/tmp/averaged_perceptron_tagger_eng.zip').extractall(os.environ['NLTK_DATA'] + '/taggers/')"; \
    rm /tmp/punkt_tab.zip /tmp/averaged_perceptron_tagger_eng.zip; \
    chown -R $UID:$GID "$NLTK_DATA"; \
    python -c "import nltk; nltk.data.find('tokenizers/punkt_tab'); nltk.data.find('taggers/averaged_perceptron_tagger_eng')" && echo "nltk data OK"

# === 离线注入 tiktoken cl100k_base（GPT-3.5/GPT-4 的 BPE 编码字典）===
# 需要在项目根目录预先放置 cl100k_base.tiktoken：
#   下载：curl -O https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken
#   位置：<repo_root>/cl100k_base.tiktoken
# tiktoken 缓存的文件名是下载 URL 的 SHA1：
#   sha1("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
#   = 9b5ad71b2ce5302211f9c61530b329a4922fc6a4
# 直接以这个名字放进 TIKTOKEN_CACHE_DIR，运行期就不会触发联网下载
COPY --chown=$UID:$GID cl100k_base.tiktoken /tmp/cl100k_base.tiktoken
RUN set -eux; \
    mkdir -p "$TIKTOKEN_CACHE_DIR"; \
    cp /tmp/cl100k_base.tiktoken "$TIKTOKEN_CACHE_DIR/9b5ad71b2ce5302211f9c61530b329a4922fc6a4"; \
    rm /tmp/cl100k_base.tiktoken; \
    chown -R $UID:$GID "$TIKTOKEN_CACHE_DIR"; \
    python -c "import os; import tiktoken; tiktoken.get_encoding(os.environ['TIKTOKEN_ENCODING_NAME'])" && echo "cl100k_base OK"

# Install Ollama if requested
RUN if [ "$USE_OLLAMA" = "true" ]; then \
    date +%s > /tmp/ollama_build_hash && \
    echo "Cache broken at timestamp: `cat /tmp/ollama_build_hash`" && \
    curl -fsSL https://ollama.com/install.sh | sh && \
    rm -rf /var/lib/apt/lists/*; \
    fi

# copy embedding weight from build
# RUN mkdir -p /root/.cache/chroma/onnx_models/all-MiniLM-L6-v2
# COPY --from=build /app/onnx /root/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx

# copy built frontend files
COPY --chown=$UID:$GID --from=build /app/build /app/build
COPY --chown=$UID:$GID --from=build /app/CHANGELOG.md /app/CHANGELOG.md
COPY --chown=$UID:$GID --from=build /app/package.json /app/package.json

# copy backend files
COPY --chown=$UID:$GID ./backend .

# === 烘焙业务资产 ===
# weather_templates：天气报告 docx 模板（各文稿生成工具引用，更新频率极低，进镜像最稳）
# 注：tools/*.py 不再烘焙进镜像。
#     运行期工具从数据库加载，调试好后到 "工作空间 → 工具" 处粘贴源码即可。
#     镜像里留副本只会和数据库版本不一致，反而成为排错时的混淆源。
#     （.dockerignore 也已经排除 tools/，即使误加 COPY 也复制不到东西）
COPY --chown=$UID:$GID ./weather_templates /app/weather_templates

EXPOSE 8080

HEALTHCHECK CMD curl --silent --fail http://localhost:${PORT:-8080}/health | jq -ne 'input.status == true' || exit 1

# Minimal, atomic permission hardening for OpenShift (arbitrary UID):
# - Group 0 owns /app and /root
# - Directories are group-writable and have SGID so new files inherit GID 0
RUN if [ "$USE_PERMISSION_HARDENING" = "true" ]; then \
    set -eux; \
    chgrp -R 0 /app /root || true; \
    chmod -R g+rwX /app /root || true; \
    find /app -type d -exec chmod g+s {} + || true; \
    find /root -type d -exec chmod g+s {} + || true; \
    fi

USER $UID:$GID

ARG BUILD_HASH
ENV WEBUI_BUILD_VERSION=${BUILD_HASH}
ENV DOCKER=true

CMD [ "bash", "start.sh"]

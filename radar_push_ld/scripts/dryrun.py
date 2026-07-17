"""本地空跑验证：用本地样例数据走一遍完整调度逻辑（不真发企业微信）。

用法（在 radar_push/ 目录，需 leadsee-webui 环境）：
    DATA_SOURCE=local LOCAL_BASE_DIR=./data_samples WECOM_WEBHOOK_URL= \
        python scripts/dryrun.py

会注入一个"当前时间"对齐样例日期，调用 RadarPushWorker.scan_once() 全流程：
找文件 -> 读 nc -> 掩膜 -> 强回波检测 -> 外推 -> 去重 -> 文本生成 ->（webhook 空则只打印）。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 默认用本地样例（可被外部环境变量覆盖）
os.environ.setdefault("DATA_SOURCE", "local")
os.environ.setdefault("LOCAL_BASE_DIR", os.path.join(os.path.dirname(__file__), "..", "data_samples"))
os.environ.setdefault("WECOM_WEBHOOK_URL", "")  # 留空 -> notifier 只打日志不真发

from app import main as main_mod  # noqa: E402
from app import radar_finder  # noqa: E402


# 样例时间戳对应的 UTC 时刻（让 finder 扫到 20260604 目录）
SAMPLE_NOW_UTC = datetime(2026, 6, 4, 2, 0, 0, tzinfo=timezone.utc)

_orig_find = radar_finder.find_latest_z


def _patched_find(ds, now_utc=None):
    return _orig_find(ds, now_utc=SAMPLE_NOW_UTC)


def run():
    # 把 main 模块里引用的 find_latest_z 也替换（main 用 from ... import）
    main_mod.find_latest_z = _patched_find  # type: ignore

    worker = main_mod.RadarPushWorker()
    print("=" * 70)
    print("DRY RUN: data_source =", worker.ds.kind)
    print("=" * 70)

    # 第一次扫描：应检测到强回波并"推送"（webhook 空 -> 打日志）
    worker.scan_once()
    print("\n--- runtime after scan #1 ---")
    for k, v in main_mod._runtime.items():
        print(f"  {k}: {v}")

    # 第二次扫描同一文件：应被"已处理该时刻"短路，不重复
    print("\n>>> second scan (same file, should be skipped) ...")
    worker.scan_once()
    print("  last_processed_ts:", main_mod._runtime["last_processed_ts"],
          "scans:", main_mod._runtime["scans"])


if __name__ == "__main__":
    run()

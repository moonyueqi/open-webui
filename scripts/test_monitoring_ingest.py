"""本地预览监测预警数据解析效果，不用等真实 FTP 挂载和 docker 部署。

用法：
    python scripts/test_monitoring_ingest.py
    python scripts/test_monitoring_ingest.py --root "_workspace/sample-data/alarm"

行为：
    - 优先尝试完整链路（写入 backend/data/webui.db，跟真实服务器一致）。
      这条路径需要装好后端依赖（fastapi/sqlalchemy/alembic 等）。
    - 如果当前环境没装那些依赖（比如只是想快速看一眼解析对不对），
      自动降级成"只解析不落库"模式：直接动态加载
      backend/open_webui/utils/monitoring_parse.py（纯标准库，零第三方依赖），
      跑一遍扫描并把结果摘要打印出来。

这个脚本只是开发期工具，不参与镜像构建（同 tools/*.py 的约定）。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ROOT = os.path.join(REPO, "_workspace", "sample-data", "alarm")
BACKEND_DIR = os.path.join(REPO, "backend")


def _load_module(module_name: str, py_path: str):
    spec = importlib.util.spec_from_file_location(module_name, py_path)
    mod = importlib.util.module_from_spec(spec)
    # dataclasses 内部会用 sys.modules[cls.__module__] 反查所在模块，动态加载时
    # 必须先注册到 sys.modules 再 exec，否则 @dataclass 装饰器会报错。
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fmt_ns(ns) -> str:
    if not ns:
        return "--"
    import datetime

    return datetime.datetime.fromtimestamp(ns / 1_000_000_000).strftime(
        "%Y-%m-%d %H:%M"
    )


def _print_ground_summary(items, limit: int = 10) -> None:
    all_rows = []
    for item in items:
        for row in item.rows:
            all_rows.append((item.meta, row))

    print(f"\n[地面监测-自动站报警] 命中文件 {len(items)} 个，解析出 {len(all_rows)} 条记录")
    if not all_rows:
        return

    level_count: dict[str, int] = {}
    for _, row in all_rows:
        level_count[row.level or "未知"] = level_count.get(row.level or "未知", 0) + 1
    print(f"  按等级分布: {level_count}")

    stations = {row.station_id for _, row in all_rows}
    counties = {row.county for _, row in all_rows if row.county}
    print(f"  涉及站点数: {len(stations)}，涉及区县数: {len(counties)}")

    latest_by_station: dict[str, tuple] = {}
    for meta, row in all_rows:
        prev = latest_by_station.get(row.station_id)
        if prev is None or (row.observed_at or 0) > (prev[1].observed_at or 0):
            latest_by_station[row.station_id] = (meta, row)

    ordered = sorted(
        latest_by_station.values(), key=lambda mr: mr[1].observed_at or 0, reverse=True
    )
    print(f"  最新告警（当前状态，取前 {min(limit, len(ordered))} 条）：")
    for meta, row in ordered[:limit]:
        print(
            f"    - [{row.level}色] {row.station_name}（{row.county}） "
            f"{_fmt_ns(row.observed_at)}  30分钟雨量={row.rain_30m}mm"
        )


def _print_lightning_summary(items, limit: int = 10) -> None:
    total_events = sum(len(item.events) for item in items)
    print(f"\n[高空预警-闪电跃增预警] 命中推送 {len(items)} 次，解析出 {total_events} 条跳增摘要")
    if not items:
        return

    with_json = sum(1 for i in items if i.json_path)
    with_png = sum(1 for i in items if i.png_path)
    print(f"  配套 json 齐全: {with_json}/{len(items)}，配套 png 齐全: {with_png}/{len(items)}")

    ordered = sorted(items, key=lambda i: i.meta.push_time or 0, reverse=True)
    seen = set()
    shown = 0
    print(f"  最新跳增事件（去重后，最多 {limit} 条）：")
    for item in ordered:
        for event in item.events:
            key = (event.region, event.jump_times)
            if key in seen:
                continue
            seen.add(key)
            print(
                f"    - {event.region} · 跳增时刻 {event.jump_times}"
                f"（推送于 {_fmt_ns(item.meta.push_time)}）"
            )
            shown += 1
            if shown >= limit:
                break
        if shown >= limit:
            break

    latest_push = ordered[0]
    print(
        f"  最新一次推送: {_fmt_ns(latest_push.meta.push_time)}"
        f"，png={'有' if latest_push.png_path else '无'}"
        f"（{latest_push.png_path or '-'}）"
    )


def run_parse_only(root: str) -> None:
    print(f"[降级模式：只解析不落库]（未检测到完整后端依赖，跳过写库这一步）")
    parse_mod = _load_module(
        "_monitoring_parse_standalone",
        os.path.join(BACKEND_DIR, "open_webui", "utils", "monitoring_parse.py"),
    )
    ground_items = parse_mod.scan_ground_alarms(root)
    lightning_items = parse_mod.scan_lightning_pushes(root)
    _print_ground_summary(ground_items)
    _print_lightning_summary(lightning_items)


def run_full_ingest(root: str) -> None:
    print("[完整模式：解析并写入 backend/data/webui.db]")
    os.environ.setdefault("DATA_DIR", os.path.join(BACKEND_DIR, "data"))
    os.environ["MONITORING_DATA_ROOT"] = root
    sys.path.insert(0, BACKEND_DIR)

    import open_webui.config  # noqa: F401  # 触发 alembic 迁移，确保新表已建好

    from open_webui.utils.monitoring_ingest import (
        scan_ground_alarms,
        scan_lightning_pushes,
    )
    from open_webui.models.monitoring import GroundAlarms, LightningPushes

    ground_inserted = scan_ground_alarms(root)
    lightning_inserted = scan_lightning_pushes(root)
    print(f"  本轮新增：地面告警 {ground_inserted} 条，闪电跳增事件 {lightning_inserted} 条")

    summary = GroundAlarms.get_summary()
    print(
        f"  当前活跃地面告警: {summary.active_count} 条，"
        f"按等级: {summary.by_level}，涉及区县: {summary.county_count}"
    )

    latest = GroundAlarms.list_alarms(latest_only=True, limit=10)
    print(f"  最新地面告警（前 {len(latest.items)} 条）：")
    for a in latest.items:
        print(
            f"    - [{a.level}色] {a.station_name}（{a.county}） "
            f"{_fmt_ns(a.observed_at)}  30分钟雨量={a.rain_30m}mm"
        )

    pushes = LightningPushes.list_pushes(limit=5)
    print(f"  最新闪电跳增推送（前 {len(pushes.items)} 条）：")
    for p in pushes.items:
        print(
            f"    - 推送于 {_fmt_ns(p.push_time)}，跳增单体 {p.event_count} 个，"
            f"png={'有' if p.png_path else '无'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=DEFAULT_ROOT,
        help=f"监测预警样例数据根目录（默认 {DEFAULT_ROOT}）",
    )
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    root = os.path.abspath(args.root)
    print(f"数据根目录: {root}")
    if not os.path.isdir(root):
        print(f"目录不存在，请检查 --root 参数")
        sys.exit(1)

    try:
        run_full_ingest(root)
    except ModuleNotFoundError as e:
        print(f"（完整模式不可用: 缺少依赖 {e.name}）")
        run_parse_only(root)


if __name__ == "__main__":
    main()

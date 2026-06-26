"""历史数据回放：在服务器上用历史 nc 按时间顺序"逐帧"重跑完整推送逻辑（真发）。

为什么需要它
------------
生产 worker 每轮只扫"今天/昨天目录里时间戳最大的 Z"（find_latest_z），且推送决策
里的节流/里程碑/过期都基于墙钟时间。直接拿历史数据跑会有两个问题：
  1. 只能看到最新一帧，看不到一次过程是"何时、因为什么"触发推送；
  2. 脚本秒级跑完所有帧 → 墙钟几乎不变 → 第一帧推后，后续帧被节流误杀、过期重置
     永不触发，回放结果失真，且可能瞬间向群里灌一堆消息。

本脚本的做法
------------
完全复用 RadarPushWorker 的真实决策链与数据源（默认就是生产 SFTP），只做注入：
  · 自己用 ds.list_dir 枚举数据目录里"指定起始时间之后"的所有 Z 时次并排序，逐帧
    把"当前最新文件"喂给 worker；
  · 每帧把 main 模块里的 time.time() 冻结到该帧观测时刻 → 节流/里程碑/过期严格按
    历史真实间隔推进（避免把本该跨 12 分钟的多次推送在一秒内全产出）；
  · 不发企业微信：把 worker.notifier 替换为"落盘版"——每当决策命中要推送时，把
    该时次的【文案 .txt + 雷达图 .png】写到本地输出目录（文件名带观测时刻）；
  · 缺失数据沿用生产行为：Et/TreRef 缺失则跳过该帧待"落盘"；实况(obs)缺失时该
    「实况提醒」行整行省略，其余文案照常输出，不阻塞推送。

用法（在服务器 radar_push/ 目录，沿用部署用的 .env / 环境变量）
--------------------------------------------------------------
    # 从 2026-06-26 08:30(北京时) 开始回放到最新，结果存到 ./replay_out：
    python scripts/replay.py --from "2026-06-26 08:30"

    # 指定起止（北京时）+ 自定义输出目录：
    python scripts/replay.py --from "2026-06-26 08:30" --to "2026-06-26 10:00" --out /app/state/replay

    # 同时在终端打印每次推送的完整文案：
    python scripts/replay.py --from "2026-06-26 08:30" --show-text

时间参数说明
------------
--from / --to 接受「北京时」(Asia/Shanghai)，格式 "YYYY-MM-DD HH:MM" 或
"YYYY-MM-DD HH:MM:SS"，也可直接给 14 位 UTC 时间戳（如 20260626003000）。
内部统一换算为 UTC 时间戳与文件名比较。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time as _time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_FNAME_RE = re.compile(r"^Mosaic(\d{14})_(Z|Cr|Et|TreRef)\.nc$")


class FileNotifier:
    """落盘版 notifier：把推送内容写到本地目录，替代企业微信真发。

    与 WecomNotifier 接口一致（enabled / send_alert），故可直接替换
    worker.notifier，无需改动业务逻辑。每次 send_alert 命中即写一份
    {prefix}.txt（文案）与 {prefix}.png（雷达图，若有）；返回 True 让
    去重状态正常推进（与真发成功等价）。
    """

    enabled = True

    def __init__(self, out_dir: str):
        self.out_dir = os.path.abspath(out_dir)
        os.makedirs(self.out_dir, exist_ok=True)
        self._cur_prefix = "alert"  # 由回放循环按帧观测时刻设置
        self.saved = []

    def set_prefix(self, prefix: str) -> None:
        self._cur_prefix = prefix

    def send_alert(self, text: str, png_bytes=None) -> bool:
        txt_path = os.path.join(self.out_dir, f"{self._cur_prefix}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        png_path = None
        if png_bytes:
            png_path = os.path.join(self.out_dir, f"{self._cur_prefix}.png")
            with open(png_path, "wb") as f:
                f.write(png_bytes)
        self.saved.append((txt_path, png_path))
        print(f"    已保存: {txt_path}" + (f"  +  {png_path}" if png_path else "  (无图)"))
        return True


def _parse_user_time(s: str, tz: ZoneInfo) -> str:
    """把用户输入（北京时字符串 或 14位UTC时间戳）统一解析为 14 位 UTC 时间戳。"""
    s = s.strip()
    if re.fullmatch(r"\d{14}", s):
        return s  # 已是 UTC 时间戳
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            dt_local = datetime.strptime(s, fmt).replace(tzinfo=tz)
            return dt_local.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")
        except ValueError:
            continue
    raise SystemExit(f"无法解析时间: {s!r}（用 'YYYY-MM-DD HH:MM' 北京时 或 14位UTC时间戳）")


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def _date_dirs_for_range(ts_from: str, ts_to: str | None) -> list[str]:
    """覆盖 [from, to] 的 UTC 日期目录列表（YYYYMMDD），含端点当天。"""
    d0 = _parse_ts(ts_from).date()
    d1 = (_parse_ts(ts_to) if ts_to else datetime.now(timezone.utc)).date()
    out, cur = [], d0
    from datetime import timedelta
    while cur <= d1:
        out.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return out


def _collect_frames(ds, rf_module, ts_from: str, ts_to: str | None):
    """用数据源枚举 [from, to] 区间内所有 Z 时次，按时间升序返回 RadarFile 列表。"""
    frames = []
    for date_dir in _date_dirs_for_range(ts_from, ts_to):
        for name in ds.list_dir(f"{date_dir}/Z"):
            m = _FNAME_RE.match(name)
            if not m or m.group(2) != "Z":
                continue
            ts = m.group(1)
            if ts < ts_from:
                continue
            if ts_to and ts > ts_to:
                continue
            frames.append(rf_module.RadarFile(
                timestamp=ts,
                dt_utc=_parse_ts(ts),
                date_dir=date_dir,
                z_rel_path=f"{date_dir}/Z/{name}",
                cr_rel_path=f"{date_dir}/Cr/Mosaic{ts}_Cr.nc",
                et_rel_path=f"{date_dir}/Et/Mosaic{ts}_Et.nc",
                treref_rel_path=f"{date_dir}/TreRef/Mosaic{ts}_TreRef.nc",
            ))
    frames.sort(key=lambda r: r.timestamp)
    return frames


def main() -> int:
    ap = argparse.ArgumentParser(description="历史 nc 数据回放（逐帧重跑推送逻辑）")
    ap.add_argument("--from", dest="ts_from", required=True,
                    help="起始时间（北京时 'YYYY-MM-DD HH:MM' 或 14位UTC时间戳），含")
    ap.add_argument("--to", dest="ts_to", default=None,
                    help="结束时间（同上格式，含）；不填则到最新")
    ap.add_argument("--out", default=None,
                    help="结果输出目录（存 文案.txt + 雷达图.png）；默认 ./replay_out")
    ap.add_argument("--show-text", action="store_true", help="推送时打印完整文案")
    ap.add_argument("--reset-state", action="store_true", help="回放前清空去重状态文件")
    args = ap.parse_args()

    # 回放只落盘、不发企业微信，也不上传 FTP。
    os.environ["WECOM_WEBHOOK_URL"] = ""
    os.environ["FTP_UPLOAD_ENABLED"] = "false"
    # 风掣等待置 0：回放时 time.time 被冻结到帧观测时刻，若仍按"距观测 N 分钟"等待，
    #   未就绪的帧会 return False 被无限重试而卡死。回放下风掣文件要么有要么永久没有，
    #   故不等待——找不到即按"超时放弃"处理（风掣行省略），与生产语义一致且不卡。
    os.environ["FENGCHE_WAIT_MINUTES"] = "0"

    from app import main as main_mod
    from app import radar_finder as rf_module

    worker = main_mod.RadarPushWorker()
    tz_local = worker.tz if isinstance(worker.tz, ZoneInfo) else ZoneInfo(str(worker.tz))

    out_dir = os.path.abspath(
        args.out or os.path.join(os.path.dirname(__file__), "..", "replay_out")
    )
    notifier = FileNotifier(out_dir)
    worker.notifier = notifier  # 替换为落盘版，复用全部决策逻辑

    ts_from = _parse_user_time(args.ts_from, tz_local)
    ts_to = _parse_user_time(args.ts_to, tz_local) if args.ts_to else None

    print("=" * 78)
    print(f"REPLAY  data_source={worker.ds.kind}  输出目录={out_dir}（不发企业微信）")
    print(f"区间(UTC时间戳): {ts_from} ~ {ts_to or '最新'}")
    print("=" * 78)

    if args.reset_state:
        try:
            if worker.dedup.path.exists():
                worker.dedup.path.unlink()
            worker.dedup.state = worker.dedup._load()
            print(f"已清空去重状态: {worker.dedup.path}")
        except Exception as e:
            print(f"清空状态失败（忽略）: {e}")

    print("枚举历史时次中 ...")
    frames = _collect_frames(worker.ds, rf_module, ts_from, ts_to)
    print(f"共发现 {len(frames)} 帧 Z 时次")
    if not frames:
        print("区间内无 Z 文件。请检查起止时间，以及数据源/目录是否正确。")
        return 1

    pushes_before = int(main_mod._runtime["pushes"])

    for i, rf in enumerate(frames, 1):
        observe_local = rf.dt_utc.astimezone(tz_local)
        frame_epoch = rf.dt_utc.timestamp()

        # 固定"当前最新文件"为这一帧；把 main 模块里的 time.time 冻结到帧观测时刻，
        # 使 dedup 的节流/里程碑/过期严格按历史真实间隔推进。
        main_mod.find_latest_z = lambda ds, now_utc=None, _rf=rf: _rf  # type: ignore
        main_mod.time.time = lambda _e=frame_epoch: _e  # type: ignore

        # 本帧若推送，落盘文件名前缀用观测时刻（北京时）。
        notifier.set_prefix(f"radar_{observe_local:%Y%m%d_%H%M}")

        worker._last_ts = None  # 防止"与上次相同"短路

        p0 = int(main_mod._runtime["pushes"])
        s0 = int(main_mod._runtime["dedup_suppressed"])
        t0 = int(main_mod._runtime["throttled"])

        header = f"[{i:>3}/{len(frames)}] {observe_local:%Y-%m-%d %H:%M} (北京时, ts={rf.timestamp})"
        try:
            worker.scan_once()
        except Exception as e:
            print(f"{header}  ERROR: {e}")
            continue

        pushed = int(main_mod._runtime["pushes"]) > p0
        throttled = int(main_mod._runtime["throttled"]) > t0
        suppressed = int(main_mod._runtime["dedup_suppressed"]) > s0

        if pushed:
            print(f"{header}  >>> 已推送")
            if args.show_text:
                last = main_mod._runtime["last_push"]
                if isinstance(last, dict):
                    print("    " + "-" * 60)
                    for ln in str(last.get("text", "")).splitlines():
                        print("    " + ln)
                    print("    " + "-" * 60)
        elif throttled:
            print(f"{header}  (节流抑制)")
        elif suppressed:
            print(f"{header}  (去重/覆盖抑制)")
        else:
            print(f"{header}  -")

    main_mod.time.time = _time.time  # type: ignore 恢复真实时间

    total = int(main_mod._runtime["pushes"]) - pushes_before
    print("=" * 78)
    print(f"回放结束：触发推送 {total} 次 / 共 {len(frames)} 帧；已保存 {len(notifier.saved)} 份到 {out_dir}")
    print(f"  节流抑制累计: {main_mod._runtime['throttled']}  "
          f"去重/覆盖抑制累计: {main_mod._runtime['dedup_suppressed']}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

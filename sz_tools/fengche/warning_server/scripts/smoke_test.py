"""端到端冒烟测试：直接调用业务函数，模拟 /fengche_warning 请求。

用法（在仓库根目录、leadsee-webui 环境下）：
    python -m fengche_warning_server.scripts.smoke_test

可选参数：
    SMOKE_REQUEST_TIME=2026-05-07T15:38:00+08:00 python -m fengche_warning_server.scripts.smoke_test
"""

from __future__ import annotations

import json
import logging
import os
import sys


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    # 直接调用 main._do_warning，避免起 uvicorn
    from fengche_warning_server.app.main import WarningRequest, _do_warning

    request_time = os.environ.get("SMOKE_REQUEST_TIME", "2026-05-07T15:00:00+08:00")
    print(f"=== smoke test, request_time={request_time} ===\n")

    # --- 1) 默认（任意格点达标即触发）---
    req = WarningRequest(request_time_iso=request_time)
    resp = _do_warning(req)
    _print_outline("default (any_point_hit)", resp)

    # --- 2) 传入历史的覆盖率参数，应当被忽略，结果与 1) 完全一致 ---
    req2 = WarningRequest(
        request_time_iso=request_time,
        gs_coverage_ratio=0.3,
        rain_coverage_ratio=0.3,
    )
    resp2 = _do_warning(req2)
    _print_outline("legacy coverage_ratio=0.3 (ignored)", resp2)

    # --- 3) 完整打印默认参数下的响应 ---
    print("\n=== full response ===")
    print(json.dumps(resp, ensure_ascii=False, indent=2, default=str))

    print("\n=== summary text ===")
    print(resp.get("summary", ""))

    return 0


def _print_outline(label: str, resp: dict) -> None:
    print(f"--- {label} ---")
    print(f"  issue_time     = {resp['forecast_source']['issue_time']}")
    print(f"  fallback_back  = {resp['forecast_source']['fallback_steps_back']}")
    for code, block in resp["districts"].items():
        sc = block["strong_convection"]["segments"]
        rs = block["rainstorm"]["segments"]
        print(
            f"  [{code} {block['name']}] grid={block['grid_points_in_district']} "
            f"strong_convection={len(sc)}seg rainstorm={len(rs)}seg"
        )
        for seg in sc:
            print(
                f"      sc: {seg['level']} {seg['start_time'][:16]}~{seg['end_time'][:16]} "
                f"hours={len(seg['hour_metrics'])}"
            )
        for seg in rs:
            print(
                f"      rs: {seg['level']} ({seg['triggered_by']}) "
                f"{seg['start_time'][:16]}~{seg['end_time'][:16]} hours={len(seg['hour_metrics'])}"
            )
    print()


if __name__ == "__main__":
    sys.exit(main())

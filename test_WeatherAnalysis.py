import os
import sys
from datetime import datetime

# ================= 配置区域 =================
BASE_DIR_EC = "/data/ecmwf"
BASE_DIR_GRAPES = "/data/grapes_gmf"

# 各要素对应的子目录模板
PATH_TEMPLATES = {
    "500hPa": "{base_dir}/{base_time}/h500w/h500w850",
    "850hPa": "{base_dir}/{base_time}/h500w/h500w850",
    "Precip_12h": "{base_dir}/{base_time}/rain/rain12",
    "Wind_10m": "{base_dir}/{base_time}/10mwind",
    "RH_2m": "{base_dir}/{base_time}/rh/2m",
    "RH_850hPa": "{base_dir}/{base_time}/rh/h850"
}

ELEMENTS_TO_FIND = ["500hPa", "850hPa", "Precip_12h", "Wind_10m", "RH_2m","RH_850hPa"]


def get_latest_base_time(base_dir):
    """扫描基础目录，返回最新的起报时次文件夹名称"""
    if not os.path.exists(base_dir):
        return None
    # 过滤出符合 YYYYMMDDHH 格式的文件夹
    folders = [f for f in os.listdir(base_dir) if
               os.path.isdir(os.path.join(base_dir, f)) and len(f) == 10 and f.isdigit()]
    if not folders:
        return None
    return sorted(folders)[-1]


def find_closest_file(target_dir, target_hour):
    """
    在指定目录下，找到最接近且 >= target_hour 的文件
    target_hour: 计算出的目标绝对预报时效（小时）
    """
    if not os.path.exists(target_dir):
        return None

    files = os.listdir(target_dir)
    valid_files = []

    for f in files:
        # 提取文件名末尾下划线后的数字部分（去除扩展名）
        if "_" in f:
            try:
                hour_part = f.split("_")[-1].split(".")[0]
                file_hour = int(hour_part)  # 提取出纯数字，如 090 -> 90

                # 核心逻辑：寻找大于等于目标时效的文件
                if file_hour >= target_hour:
                    valid_files.append((file_hour, f))
            except ValueError:
                continue

    if not valid_files:
        return None

    # 按时效从小到大排序，取第一个（即最接近目标的较大值）
    valid_files.sort(key=lambda x: x[0])
    closest_file = valid_files[0][1]

    return os.path.abspath(os.path.join(target_dir, closest_file))


def main():
    # 1. 获取用户输入
    user_input = input("请输入想要【未来多少小时】的预报（例如输入72）：").strip()
    if not user_input.isdigit():
        print("输入错误，请输入纯数字。")
        sys.exit(1)

    future_hours = int(user_input)

    # 获取当前系统时间
    now_dt = datetime.now()
    current_hour_val = now_dt.hour  # 当前的小时数（如 16）
    current_time_str = now_dt.strftime("%Y%m%d%H")

    print(f"\n当前系统时间: {current_time_str}")
    print("-" * 60)

    # 2. 分别处理 EC 和 GRAPES 数据
    for source_name, base_dir in [("ECMWF", BASE_DIR_EC), ("GRAPES", BASE_DIR_GRAPES)]:
        print(f"\n正在查找 【{source_name}】 最新数据...")

        latest_base_time = get_latest_base_time(base_dir)
        if not latest_base_time:
            print(f"  未能在 {base_dir} 中找到有效的起报时次文件夹！")
            continue

        # 提取最新起报时次的小时数（如 '2026060200' -> 0）
        base_hour_val = int(latest_base_time[-2:])

        # 核心公式：目标时效 = (当前小时 - 起报小时) + 未来所需小时
        target_hour = (current_hour_val - base_hour_val) + future_hours

        print(f"  最新起报时次: {latest_base_time}")
        print(f"  目标时效计算: ({current_hour_val} - {base_hour_val}) + {future_hours} = {target_hour} 小时")

        found_paths = {}

        # 3. 遍历各个要素进行查找
        for element in ELEMENTS_TO_FIND:
            template = PATH_TEMPLATES.get(element)
            if not template:
                continue

            dir_path = template.format(base_dir=base_dir, base_time=latest_base_time)
            # 传入计算出的目标绝对时效进行查找
            abs_path = find_closest_file(dir_path, target_hour)

            if abs_path:
                found_paths[element] = abs_path
            else:
                found_paths[element] = f"未找到 >= {target_hour}小时 的文件"

        # 4. 打印结果
        print(f"\n  --- {source_name} 匹配结果 (目标时效: >= {target_hour}h) ---")
        for elem, path in found_paths.items():
            print(f"  [{elem:<12}] : {path}")


if __name__ == "__main__":
    main()
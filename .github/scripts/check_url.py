#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from datetime import datetime, timedelta, timezone
import requests
import sys

URL = os.environ.get("TARGET_URL")
if not URL:
    print("TARGET_URL 未设置")
    sys.exit(1)

MAX_AGE_DAYS = int(os.environ.get("MAX_AGE_DAYS", 7))
IS_MANUAL = os.environ.get("IS_MANUAL", "false").lower() == "true"
HISTORY_FILE = "history/records.json"
README_FILE = "README.md"

BEIJING_TZ = timezone(timedelta(hours=8))

def load_records():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_records(records):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def clean_old_records(records):
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=MAX_AGE_DAYS)
    return [r for r in records if datetime.fromisoformat(r["time_utc"]) >= cutoff]

def simplify_error(e_str):
    e_str = str(e_str).lower()
    if "timed out" in e_str or "timeout" in e_str:
        if "read" in e_str:
            return "读取超时"
        return "连接超时"
    if "max retries" in e_str:
        return "重试耗尽"
    if "connection" in e_str or "newconnection" in e_str:
        return "连接失败"
    if "ssl" in e_str or "certificate" in e_str:
        return "证书错误"
    if "proxy" in e_str:
        return "代理错误"
    return "网络异常"

def append_record(records, success, status, error_msg=""):
    now_utc = datetime.now(timezone.utc)
    now_bj = now_utc.astimezone(BEIJING_TZ)

    rec = {
        "time_utc": now_utc.isoformat(timespec="seconds"),
        "time_bj_short": now_bj.strftime("%d %H:%M"),
        "success": success,
        "status": status,
        "error": simplify_error(error_msg) if error_msg else "",
        "trigger": "手动" if IS_MANUAL else "定时"
    }
    records.append(rec)
    return records

def generate_readme_section(records):
    if not records:
        return "暂无记录。\n"

    lines = [
        "## 最近访问记录（最近7天）\n",
        "| 时间     | 方式 | 结果   | 码  | 错误     |\n",
        "|----------|------|--------|-----|----------|\n"
    ]

    for r in sorted(records, key=lambda x: x["time_utc"], reverse=True):
        status_str = "✅ 成功" if r["success"] else "❌ 失败"
        error = r["error"] if r["error"] else "—"
        trigger_emoji = "✋" if r["trigger"] == "手动" else "⏰"
        lines.append(
            f"| {r['time_bj_short']} | {trigger_emoji} | {status_str} | {r['status']} | {error} |\n"
        )

    return "".join(lines)

def main():
    records = load_records()
    records = clean_old_records(records)

    try:
        resp = requests.get(URL, timeout=15, allow_redirects=True)
        status = resp.status_code
        success = 200 <= status < 300
        error_msg = "" if success else str(resp.reason)
    except Exception as e:
        success = False
        status = 0
        error_msg = str(e)

    records = append_record(records, success, status, error_msg)
    print(f"完成：{'成功' if success else '失败'} - {status} - {simplify_error(error_msg) if error_msg else '无错误'}")

    save_records(records)

    table_md = generate_readme_section(records)

    marker_start = "<!-- RECORDS-START -->"
    marker_end = "<!-- RECORDS-END -->"

    if os.path.exists(README_FILE):
        with open(README_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = """# urlcheck

定时检查目标端点可用性。

每天北京时间 04:00 和 16:00 自动运行，支持手动触发。

记录保留最近7天。

"""

    if marker_start in content and marker_end in content:
        parts = content.split(marker_start, 1)
        before = parts[0]
        after = parts[1].split(marker_end, 1)[1] if len(parts[1].split(marker_end, 1)) > 1 else ""
        new_content = f"{before}{marker_start}\n{table_md}\n{marker_end}{after}"
    else:
        new_content = f"{content.rstrip()}\n\n{marker_start}\n{table_md}\n{marker_end}\n"

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)

if __name__ == "__main__":
    main()

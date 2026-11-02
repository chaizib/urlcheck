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
INDEX_FILE = "index.html"

# 电报配置
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_USER_ID = os.environ.get("TG_USER_ID")

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

def send_telegram_notification(status, error_msg):
    if not TG_BOT_TOKEN or not TG_USER_ID:
        print("未配置电报通知的 TG_BOT_TOKEN 或 TG_USER_ID，跳过发送")
        return

    now_bj = datetime.now(timezone.utc).astimezone(BEIJING_TZ)
    time_str = now_bj.strftime("%Y-%m-%d %H:%M:%S")
    trigger_type = "手动触发" if IS_MANUAL else "定时触发"

    # 电报私聊推送保留完整明文，仅你自己可见
    text = (
        "⚠️ **URL 监控告警通知**\n\n"
        f"• **目标网址**: `{URL}`\n"
        f"• **触发方式**: {trigger_type}\n"
        f"• **检查时间**: {time_str} (北京时间)\n"
        f"• **HTTP 状态码**: `{status}`\n"
        f"• **错误原因**: `{error_msg if error_msg else '响应异常'}`"
    )

    api_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_USER_ID,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        resp = requests.post(api_url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("电报告警通知发送成功")
        else:
            print(f"电报告警通知发送失败: {resp.text}")
    except Exception as e:
        print(f"发送电报通知异常: {e}")

def append_record(records, success, status, error_msg=""):
    now_utc = datetime.now(timezone.utc)
    now_bj = now_utc.astimezone(BEIJING_TZ)

    rec = {
        "time_utc": now_utc.isoformat(timespec="seconds"),
        "time_bj_short": now_bj.strftime("%m-%d %H:%M"),
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

def generate_index_html(records):
    latest = records[-1] if records else None
    is_healthy = latest["success"] if latest else True
    status_text = "运行正常" if is_healthy else "服务异常"
    status_class = "healthy" if is_healthy else "unhealthy"
    update_time = datetime.now(timezone.utc).astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")

    rows_html = ""
    for r in sorted(records, key=lambda x: x["time_utc"], reverse=True):
        badge_class = "badge-success" if r["success"] else "badge-danger"
        badge_text = "成功" if r["success"] else "失败"
        trigger_emoji = "✋" if r["trigger"] == "手动" else "⏰"
        error_text = r["error"] if r["error"] else "—"
        
        rows_html += f"""
        <tr>
            <td class="col-time">{r['time_bj_short']}</td>
            <td><span class="badge {badge_class}">{badge_text}</span></td>
            <td><code>{r['status']}</code></td>
            <td class="col-error">{error_text}</td>
            <td style="text-align: right; padding-right: 8px;">{trigger_emoji}</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>站点状态监控看板</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border-color: #334155;
            --success-color: #22c55e;
            --danger-color: #ef4444;
        }}
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 12px;
            -webkit-font-smoothing: antialiased;
        }}
        .container {{
            max-width: 100%;
            width: 100%;
            margin: 0 auto;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            padding: 0 2px;
        }}
        h1 {{
            font-size: 1.1rem;
            margin: 0;
            font-weight: 600;
        }}
        .status-pill {{
            display: inline-flex;
            align-items: center;
            padding: 3px 8px;
            border-radius: 9999px;
            font-size: 0.7rem;
            font-weight: 500;
        }}
        .status-pill.healthy {{
            background-color: rgba(34, 197, 94, 0.15);
            color: var(--success-color);
        }}
        .status-pill.unhealthy {{
            background-color: rgba(239, 68, 68, 0.15);
            color: var(--danger-color);
        }}
        .card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 12px;
        }}
        .meta-item {{
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 0;
        }}
        .meta-item span {{
            color: var(--text-main);
            font-weight: 500;
        }}
        .table-wrap {{
            border-radius: 8px;
            border: 1px solid var(--border-color);
            overflow: hidden;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.75rem;
            text-align: left;
            table-layout: fixed;
        }}
        th {{
            background-color: #0f172a;
            color: var(--text-muted);
            padding: 8px 6px;
            font-weight: 600;
            border-bottom: 1px solid var(--border-color);
        }}
        td {{
            padding: 8px 6px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-main);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        th:nth-child(1), td.col-time {{ width: 28%; }}
        th:nth-child(2), td:nth-child(2) {{ width: 18%; }}
        th:nth-child(3), td:nth-child(3) {{ width: 16%; }}
        th:nth-child(4), td.col-error {{ width: 24%; }}
        th:nth-child(5), td:nth-child(5) {{ width: 14%; text-align: right; padding-right: 8px; }}
        th:nth-child(5) {{ text-align: right; padding-right: 8px; }}

        .badge {{
            display: inline-block;
            padding: 1px 4px;
            border-radius: 3px;
            font-size: 0.65rem;
            font-weight: 600;
        }}
        .badge-success {{
            background-color: rgba(34, 197, 94, 0.2);
            color: var(--success-color);
        }}
        .badge-danger {{
            background-color: rgba(239, 68, 68, 0.2);
            color: var(--danger-color);
        }}
        footer {{
            text-align: center;
            font-size: 0.7rem;
            color: var(--text-muted);
            margin-top: 16px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔍 站点监控</h1>
            <div class="status-pill {status_class}">{status_text}</div>
        </header>

        <div class="card">
            <div class="meta-item">更新：<span>{update_time}</span></div>
        </div>

        <div class="card" style="padding: 0; overflow: hidden;">
            <div style="padding: 10px 12px; border-bottom: 1px solid var(--border-color); font-weight: 600; font-size: 0.8rem;">
                最近访问记录（7天）
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>时间</th>
                            <th>结果</th>
                            <th>状态</th>
                            <th>错误</th>
                            <th style="text-align: right; padding-right: 8px;">方式</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html if rows_html else '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">暂无记录</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>

        <footer>
            GitHub Actions & Vercel
        </footer>
    </div>
</body>
</html>
"""
    return html_content

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

    # 失败时私聊告警（私聊中保留真实网址，方便排查）
    if not success:
        send_telegram_notification(status, simplify_error(error_msg) if error_msg else str(status))

    records = append_record(records, success, status, error_msg)
    print(f"完成：{'成功' if success else '失败'} - {status} - {simplify_error(error_msg) if error_msg else '无错误'}")

    save_records(records)

    # 生成并写入 README.md
    table_md = generate_readme_section(records)
    marker_start = "<!-- RECORDS-START -->"
    marker_end = "<!-- RECORDS-END -->"

    if os.path.exists(README_FILE):
        with open(README_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = """# urlcheck

定时检查目标端点可用性。
每天 04:00 和 13:00 自动运行，支持手动触发。
记录保留最近7天。

## 配置方式
Secrets,Actions：
`TARGET_URL` `TG_BOT_TOKEN` `TG_USER_ID`

---
"""

    if marker_start in content and marker_end in content:
        parts = content.split(marker_start, 1)
        before = parts[0]
        after = parts[1].split(marker_end, 1)[1] if len(parts[1].split(marker_end, 1)) > 1 else ""
        new_readme = f"{before}{marker_start}\n{table_md}\n{marker_end}{after}"
    else:
        new_readme = f"{content.rstrip()}\n\n{marker_start}\n{table_md}\n{marker_end}\n"

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(new_readme)

    # 生成并写入彻底脱敏（不含任何目标网址）的 index.html
    html_content = generate_index_html(records)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)
    print("index.html 页面生成成功（已彻底移除目标网址）")

if __name__ == "__main__":
    main()

import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import threading
import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session

# ================= 基礎設定區 =================
TOKEN = os.getenv('DISCORD_TOKEN')
WEB_PASSWORD = os.getenv('WEB_PWD', 'admin888') 
MY_GUILD_ID = 1492797387008376852
BACKUP_CHANNEL_ID = 1496886906544324738
ANNOUNCE_CHANNEL_ID = 1492888316809318561 
WARN_LOG_CHANNEL_ID = 1497470602888613918 
DATA_FILE = "data.json"
ROLE_ID = 1492939910641090710 
# =============================================

def init_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"target_message_id": "無", "current_emoji": "🤡", "warn_records": {}, "violation_records": {}}, f, indent=4)

init_data()

# --- 側邊欄版 HTML 模板 ---
HTML_TPL = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>機器人管理後台</title>
    <style>
        :root { --sidebar-width: 240px; --primary-color: #4f46e5; --bg-light: #f9fafb; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; display: flex; background: var(--bg-light); color: #1f2937; }
        
        /* 側邊欄 */
        .sidebar { width: var(--sidebar-width); background: #ffffff; height: 100vh; border-right: 1px solid #e5e7eb; position: fixed; display: flex; flex-direction: column; }
        .sidebar-header { padding: 20px; font-size: 20px; font-weight: bold; border-bottom: 1px solid #f3f4f6; color: var(--primary-color); }
        .sidebar-menu { padding: 10px; flex-grow: 1; }
        .menu-item { padding: 12px 15px; text-decoration: none; color: #4b5563; display: block; border-radius: 8px; margin-bottom: 5px; cursor: pointer; border: none; background: none; width: 100%; text-align: left; font-size: 16px; }
        .menu-item:hover { background: #f3f4f6; color: var(--primary-color); }
        .logout-btn { color: #ef4444; border-top: 1px solid #f3f4f6; padding: 20px; text-decoration: none; font-weight: bold; }

        /* 主內容區 */
        .main-content { margin-left: var(--sidebar-width); padding: 40px; width: 100%; }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 25px; border: 1px solid #f3f4f6; }
        h2 { margin-top: 0; font-size: 1.5rem; border-left: 4px solid var(--primary-color); padding-left: 10px; }
        
        /* 表單與按鈕 */
        input, textarea { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; }
        button { background: var(--primary-color); color: white; border: none; padding: 12px 20px; border-radius: 6px; cursor: pointer; font-weight: 600; transition: 0.2s; }
        button:hover { opacity: 0.9; }
        .btn-orange { background: #f59e0b; }
        
        /* 表格 */
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #f3f4f6; }
        th { background: #f9fafb; color: #6b7280; font-weight: 600; }

        /* 登入頁 */
        .login-container { display: flex; justify-content: center; align-items: center; height: 100vh; width: 100%; background: #f3f4f6; }
        .login-card { background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); width: 350px; text-align: center; }
    </style>
</head>
<body>

{% if not logged_in %}
    <div class="login-container">
        <div class="login-card">
            <h1 style="color: var(--primary-color);">Gryn Clan</h1>
            <p>請輸入管理員密碼</p>
            <form method="post" action="/login">
                <input type="password" name="pwd" placeholder="密碼" required>
                <button type="submit" style="width: 100%;">登入系統</button>
            </form>
        </div>
    </div>
{% else %}
    <div class="sidebar">
        <div class="sidebar-header">控制台</div>
        <nav class="sidebar-menu">
            <a href="#status" class="menu-item">📌 系統狀態</a>
            <a href="#announce" class="menu-item">📢 公告發送</a>
            <a href="#warning" class="menu-item">⚠️ 警告名單</a>
            <a href="#data" class="menu-item">💾 數據備份</a>
        </nav>
        <a href="/logout" class="logout-btn">🚪 登出系統</a>
    </div>

    <div class="main-content">
        <div id="status" class="card">
            <h2>📌 目前狀態</h2>
            <p>目前身分組訊息 ID：<strong>{{ db.target_message_id }}</strong></p>
            <p>目前按鈕表情符號：<span style="font-size: 24px;">{{ db.current_emoji }}</span></p>
        </div>

        <div id="announce" class="card">
            <h2>📢 發送全大字公告</h2>
            <form action="/announce" method="post">
                <textarea name="content" rows="4" placeholder="在這裡輸入公告內容..." required></textarea>
                <button type="submit">立即發送至 Discord</button>
            </form>
        </div>

        <div id="warning" class="card">
            <h2>⚠️ 警告與累犯紀錄</h2>
            <table>
                <thead>
                    <tr><th>用戶 ID</th><th>警告數</th><th>累犯次數</th></tr>
                </thead>
                <tbody>
                    {% for uid, count in db.warn_records.items() %}
                    <tr>
                        <td><code>{{ uid }}</code></td>
                        <td><span style="color: #d97706; font-weight: bold;">{{ count }} 支</span></td>
                        <td>{{ db.violation_records.get(uid, 0) }} 次</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div id="data" class="card">
            <h2>💾 數據管理</h2>
            <div style="display: flex; gap: 10px;">
                <form action="/backup" method="post" style="flex: 1;">
                    <button type="submit" style="width: 100%;">發送備份檔案</button>
                </form>
                <form action="/restore" method="post" enctype="multipart/form-data" style="flex: 1;">
                    <input type="file" name="file" accept=".json" required style="margin: 0; padding: 8px;">
                    <button type="submit" class="btn-orange" style="width: 100%; margin-top: 10px;">上傳 JSON 還原</button>
                </form>
            </div>
        </div>
    </div>
{% endif %}

</body>
</html>
"""

# ... (後續的 RoleView, IntegratedBot, Flask Routes 與 Discord Commands 邏輯與前一版完全相同，請維持不變) ...
# 注意：請確保將此 HTML_TPL 替換掉原本 6.py 裡的 HTML_TPL 部分。

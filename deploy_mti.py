import os
import sys
import re
import socket
import subprocess
import webbrowser
import time
import json
import urllib.request
import urllib.parse
from datetime import datetime

# Configurable settings
WECHAT_CONTACT = "Alex_石"
BLOG_DOMAIN = "https://1atk.space"
UPLOAD_BASE_URL = "https://1atk.space/upload_mti"  # will use trailing slash in URLs
TOKEN = "mti_secret_2026"
BLOG_ROOT = r"C:\Users\1atk\Documents\antigravity\wonderful-volta"

# Automatically switch to Hugo blog root directory (critical for Desktop .exe execution)
if os.path.exists(BLOG_ROOT):
    os.chdir(BLOG_ROOT)
else:
    print(f"⚠️ 未找到博客根目录 {BLOG_ROOT}，将在当前运行目录执行。")

def make_request(url, method='GET'):
    # Standard Chrome User-Agent to prevent Cloudflare from blocking python-urllib with 403 Forbidden
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    return urllib.request.Request(url, headers=headers, method=method)


# HTML template for QR code page on PC
QR_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>MTI Upload QR Code</title>
    <script src="https://cdn.jsdelivr.net/npm/davidshimjs-qrcodejs@0.0.2/qrcode.min.js"></script>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            background-color: #f5f7fb;
            margin: 0;
        }
        .card {
            background: white;
            padding: 30px;
            border-radius: 16px;
            box-shadow: 0 4px 25px rgba(0,0,0,0.06);
            text-align: center;
            max-width: 380px;
        }
        #qrcode {
            margin: 24px 0;
            display: flex;
            justify-content: center;
        }
        h2 { color: #4F46E5; margin-top: 0; font-size: 22px; }
        p { color: #555; font-size: 14px; line-height: 1.5; }
        .url-box {
            background-color: #F3F4F6;
            padding: 8px 12px;
            border-radius: 8px;
            font-family: monospace;
            font-size: 13px;
            color: #374151;
            word-break: break-all;
            margin-top: 12px;
        }
    </style>
</head>
<body>
    <div class="card">
        <h2>MTI 扫码上传通道</h2>
        <p>请使用手机扫描下方二维码，或直接打开书签上传手写照片：</p>
        <div id="qrcode"></div>
        <div class="url-box">{{UPLOAD_URL}}</div>
        <p style="color: #9CA3AF; font-size: 11px; margin-top: 20px;">照片上传成功后，回到电脑终端按【回车键】即可自动下载并发布。</p>
    </div>
    <script>
        new QRCode(document.getElementById("qrcode"), {
            text: "{{UPLOAD_URL}}",
            width: 200,
            height: 200
        });
    </script>
</body>
</html>
"""

def copy_to_clipboard(text):
    try:
        import ctypes
        
        # Windows Clipboard Constants
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        
        # Open Clipboard
        if not ctypes.windll.user32.OpenClipboard(None):
            return False
            
        try:
            ctypes.windll.user32.EmptyClipboard()
            
            # Encode text to UTF-16 LE (null-terminated)
            data = text.encode('utf-16-le') + b'\x00\x00'
            
            # Allocate global memory
            h_global_mem = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h_global_mem:
                return False
                
            # Lock memory and copy data
            lp_global_mem = ctypes.windll.kernel32.GlobalLock(h_global_mem)
            ctypes.memmove(lp_global_mem, data, len(data))
            ctypes.windll.kernel32.GlobalUnlock(h_global_mem)
            
            # Set clipboard data
            if not ctypes.windll.user32.SetClipboardData(CF_UNICODETEXT, h_global_mem):
                return False
        finally:
            ctypes.windll.user32.CloseClipboard()
        return True
    except Exception as e:
        print(f"复制剪贴板失败: {e}")
        return False

def send_wechat_notification(contact, text):
    try:
        import wxauto
        print(f"正在尝试使用 wxauto 发送打卡私信给: {contact}...")
        wx = wxauto.WeChat()
        wx.ChatWith(contact)
        wx.SendMsg(text)
        print("✓ 微信私信打卡已成功发送！")
        return True
    except ImportError:
        print("提示: 未安装 wxauto 库，无法自动发送微信私信。")
        return False
    except Exception as e:
        print(f"微信自动发送失败: {e}")
        return False

def get_vps_status():
    url = f"{UPLOAD_BASE_URL}/status?token={TOKEN}"
    try:
        req = make_request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"❌ 无法从 VPS 获取上传状态: {e}")
        return None

def download_file_from_vps(cat, filename):
    encoded_file = urllib.parse.quote(filename)
    url = f"{UPLOAD_BASE_URL}/download?cat={cat}&file={encoded_file}&token={TOKEN}"
    try:
        req = make_request(url)
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read()
    except Exception as e:
        print(f"❌ 下载文件失败 ({cat}/{filename}): {e}")
        return None

def clear_vps_uploads():
    url = f"{UPLOAD_BASE_URL}/clear?token={TOKEN}"
    try:
        req = make_request(url, method='POST')
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8') == "OK"
    except Exception as e:
        print(f"⚠️ 无法清除 VPS 缓存目录: {e}")
        return False

def generate_hugo_post(date_str, summary_text, files_list, dry_run=False):
    post_dir_name = f"mti-{date_str}"
    post_dir_path = os.path.join("content", "posts", post_dir_name)
    
    if not dry_run:
        os.makedirs(post_dir_path, exist_ok=True)
    
    markdown_lines = []
    
    # Create Frontmatter
    markdown_lines.append("---")
    markdown_lines.append(f'title: "MTI 备考打卡 ({date_str})"')
    current_time_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    markdown_lines.append(f"date: {current_time_iso}")
    markdown_lines.append("draft: false")
    markdown_lines.append('categories: ["MTI"]')
    markdown_lines.append('tags: ["MTI打卡"]')
    markdown_lines.append("---")
    markdown_lines.append("")
    markdown_lines.append(f"今日备考摘要：**{summary_text}**")
    markdown_lines.append("")
    
    categories = [
        ("notes", "📝 笔记整理", "notes"),
        ("translation", "✍️ 翻译练习", "translation"),
        ("vocab", "📱 单词背诵截图", "vocab")
    ]
    
    for field, title, prefix in categories:
        uploaded_files = files_list.get(field, [])
        if uploaded_files:
            markdown_lines.append(f"## {title}")
            for idx, filename in enumerate(uploaded_files, 1):
                ext = os.path.splitext(filename)[1]
                if not ext:
                    ext = ".jpg"
                new_filename = f"{prefix}_{idx}{ext.lower()}"
                
                # Download file content from VPS
                if not dry_run:
                    file_content = download_file_from_vps(field, filename)
                    if file_content:
                        file_path = os.path.join(post_dir_path, new_filename)
                        with open(file_path, 'wb') as f:
                            f.write(file_content)
                        print(f"✓ 已下载并保存图片: {file_path}")
                    else:
                        print(f"❌ 无法从 VPS 下载图片: {filename}")
                else:
                    print(f"[测试模式] 拟从 VPS 下载图片: {field}/{filename} -> {post_dir_path}/{new_filename}")
                
                # Append image to markdown
                markdown_lines.append(f"![{title} {idx}]({new_filename})")
                markdown_lines.append("")
            markdown_lines.append("")
            
    # Write index.md
    markdown_content = "\n".join(markdown_lines)
    index_md_path = os.path.join(post_dir_path, "index.md")
    
    if not dry_run:
        with open(index_md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        print(f"✓ 已生成博客文章: {index_md_path}")
    else:
        print(f"[测试模式] 拟生成博客文章 {index_md_path}，内容如下:\n{markdown_content}")
        
    return post_dir_name

def execute_git_commands(post_dir_name):
    print("正在推送至 GitHub 仓库...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"feat: MTI check-in {post_dir_name}"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("✓ Git 提交与推送成功！GitHub Actions 自动部署中...")
        return True
    except Exception as e:
        print(f"❌ Git 操作失败: {e}")
        return False

def main():
    print("=" * 50)
    print("      MTI 备考工作流一键打卡助手 (VPS 中转版)      ")
    print("=" * 50)
    
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("[🔔 运行状态] 当前处于 测试模式 (Dry-run)，不会真正提交Git或发送微信。")
    
    # Get summary text first
    summary_text = input("✍️ 请输入今日打卡描述（简短摘要）：").strip()
    if not summary_text:
        summary_text = "完成今日 MTI 备考任务"
        
    # Generate QR code HTML on PC and open browser
    qr_content = QR_HTML_TEMPLATE.replace("{{UPLOAD_URL}}", UPLOAD_BASE_URL)
    qr_file_path = "qr_code.html"
    with open(qr_file_path, "w", encoding="utf-8") as f:
        f.write(qr_content)
        
    # Open local page to show QR code
    webbrowser.open(os.path.abspath(qr_file_path))
    print(f"📱 电脑浏览器已弹出二维码。请使用手机扫码（或打开浏览器书签）上传图片。")
    
    # Wait for user confirmation in console
    input("\n[⏳ 请在手机上选择照片并上传。上传完成后，在此处按【回车键/Enter】继续...]")
    
    # Clean up local QR HTML page
    if os.path.exists(qr_file_path):
        try:
            os.remove(qr_file_path)
        except Exception:
            pass
            
    print("正在连接 VPS 检查上传的数据...")
    vps_files = get_vps_status()
    
    if not vps_files:
        print("❌ 无法与 VPS 建立通信，发布中止。")
        input("\n[按回车键退出...]")
        return
        
    total_files = sum(len(v) for v in vps_files.values())
    if total_files == 0:
        print("❌ VPS 上没有检测到任何已上传的图片。请确保您在手机上点击了上传。")
        input("\n[按回车键退出...]")
        return
        
    print(f"✓ 成功检测到 VPS 缓存中的 {total_files} 张照片。")
    
    # Generate Hugo Page Bundle and download images
    date_str = datetime.now().strftime("%Y-%m-%d")
    post_dir_name = generate_hugo_post(date_str, summary_text, vps_files, dry_run=dry_run)
    
    # Clear uploads on VPS
    if not dry_run:
        clear_vps_uploads()
        print("✓ 已清空 VPS 临时缓存目录。")
    else:
        print("[测试模式] 跳过清空 VPS 缓存步骤。")
        
    # Git Deploy
    deploy_success = False
    if not dry_run:
        deploy_success = execute_git_commands(post_dir_name)
    else:
        print("[测试模式] 跳过 Git 提交与推送步骤。")
        deploy_success = True
        
    # WeChat Check-in text generation
    blog_post_url = f"{BLOG_DOMAIN}/posts/{post_dir_name}/"
    checkin_text = (
        f"师哥好，今天的 MTI 备考打卡已发布！\n"
        f"📅 日期：{date_str}\n"
        f"📝 摘要：{summary_text}\n"
        f"🔗 详情链接（含手稿大图及背诵截图，可在微信中直接点击）：\n"
        f"{blog_post_url}"
    )
    
    print("\n--- 生成的微信打卡文案 ---")
    print(checkin_text)
    print("-------------------------\n")
    
    # Send notification
    sent = False
    if not dry_run:
        sent = send_wechat_notification(WECHAT_CONTACT, checkin_text)
        
    if not sent:
        copy_success = copy_to_clipboard(checkin_text)
        if copy_success:
            print("💡 [打卡提示] 微信打卡文案已成功复制到系统剪贴板！由于未自动发送，请直接打开微信粘贴发送给 [Alex_石] 即可。")
        else:
            print("⚠️ 无法写入剪贴板，请手动复制上述控制台输出的文案发送。")
            
    print("\n🎉 备考助手运行完成。今天的任务也辛苦啦，请继续加油！")
    input("\n[输入任意键或回车退出...]")

if __name__ == "__main__":
    main()

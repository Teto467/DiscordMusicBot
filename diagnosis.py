#!/usr/bin/env python
import os
import sys
import subprocess
import discord
import yt_dlp

def check_env_vars():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if token:
        print("✅ DISCORD_BOT_TOKEN が設定されています。")
    else:
        print("❌ エラー: DISCORD_BOT_TOKEN が設定されていません。")

def check_python_version():
    print("Python バージョン:", sys.version)

def check_discord_version():
    try:
        version = discord.__version__
        print("discord.py バージョン:", version)
    except AttributeError:
        print("❌ discord.py のバージョンが取得できませんでした。")

def check_yt_dlp_version():
    try:
        # yt_dlp のバージョンは __version__ で取得できる場合があります
        version = yt_dlp.__version__
        print("yt_dlp バージョン:", version)
    except AttributeError:
        print("❌ yt_dlp のバージョン情報が取得できませんでした。")

def check_ffmpeg():
    try:
        # ffmpeg -version を実行して確認
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ ffmpeg がインストールされています。")
        else:
            print("❌ ffmpeg の実行に失敗しました。")
    except FileNotFoundError:
        print("❌ エラー: ffmpeg が見つかりません。インストールが必要です。")

def main():
    print("=== 環境診断プログラム ===\n")
    check_env_vars()
    check_python_version()
    check_discord_version()
    check_yt_dlp_version()
    check_ffmpeg()

if __name__ == "__main__":
    main()

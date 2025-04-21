# refresh_libs.py
import subprocess
import sys
import platform

def run_pip_command(command, ignore_errors=False):
    """指定されたpipコマンドを実行し、出力を表示する"""
    # sys.executable を使うことで、現在実行中のPython環境のpipを使う
    full_command = [sys.executable, '-m', 'pip'] + command
    print(f"\n>>> Running: {' '.join(full_command)}")
    try:
        # check=True でエラー時に例外を発生させる
        # capture_output=False (または指定なし) で出力をリアルタイム表示
        result = subprocess.run(full_command, check=not ignore_errors, text=True, encoding='utf-8')
        print(f"<<< Command successful.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"!!! Command failed: {' '.join(full_command)}")
        print(f"!!! Error: {e}")
        return False
    except FileNotFoundError:
        print(f"!!! Error: '{sys.executable} -m pip' command not found.")
        print(f"!!! Make sure pip is installed correctly in your Python environment.")
        return False
    except Exception as e:
        print(f"!!! An unexpected error occurred while running the command: {e}")
        return False

# --- メイン処理 ---
print("--- Starting Library Refresh Script ---")
print(f"Using Python interpreter: {sys.executable}")
print(f"Platform: {platform.system()} {platform.release()}")

# 1. 既存ライブラリのアンインストール (-y で確認をスキップ)
#    アンインストールはライブラリが存在しなくてもエラーにならないように ignore_errors=True を使う手もあるが、
#    CalledProcessError をキャッチして警告に留める方が状況が分かりやすい。
#    ここでは uninstall の失敗は警告とし、処理を継続する。
print("\n[Step 1/3] Uninstalling potentially conflicting libraries...")
uninstall_command = ['uninstall', '-y', 'discord.py', 'discord', 'py-cord']
run_pip_command(uninstall_command, ignore_errors=True) # 失敗しても処理を続ける

# 2. 最新の py-cord[voice] をインストール/アップデート
print("\n[Step 2/3] Installing/Updating py-cord with voice support...")
install_pycord_command = ['install', '-U', 'py-cord[voice]']
if not run_pip_command(install_pycord_command):
    print("\n--- Script stopped due to error during py-cord installation. ---")
    input("Press Enter to exit...")
    sys.exit(1) # エラーがあればここで終了

# 3. 他の依存ライブラリをインストール/アップデート
print("\n[Step 3/3] Installing/Updating other dependencies...")
install_others_command = ['install', '-U', 'yt-dlp', 'python-dotenv']
if not run_pip_command(install_others_command):
    print("\n--- Script stopped due to error during dependency installation. ---")
    input("Press Enter to exit...")
    sys.exit(1) # エラーがあればここで終了

print("\n--- Library refresh completed successfully! ---")
input("Press Enter to exit...")
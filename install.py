#!/usr/bin/env python
# install.py - 対話型セットアップアシスタント

import os
import sys
import subprocess
import platform
import shutil # コマンドの存在確認用
import venv # 仮想環境作成用

# --- 定数 ---
VENV_NAME = ".venv"
REQUIREMENTS_FILE = "requirements.txt" # このファイルが存在することを前提とする
ENV_FILE = ".env"
ENV_FILE_EXAMPLE_CONTENT = "DISCORD_BOT_TOKEN=YOUR_VERY_SECRET_BOT_TOKEN_HERE\n"
YT_DLP_EXE_NAME = "yt-dlp.exe"
MIN_PYTHON_VERSION = (3, 8) # Python 3.8以上を推奨

# --- ターミナルカラー (VT100エスケープシーケンス) ---
class TermColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    @staticmethod
    def enable_colors():
        """Windowsの古いCMDでANSIカラーを有効にする試み"""
        if platform.system() == "Windows":
            os.system('') # VT100 Escape Sequence for CMD

    @staticmethod
    def clear_screen():
        """ターミナル画面をクリアする"""
        os.system('cls' if platform.system() == 'Windows' else 'clear')

# --- プリントヘルパー ---
def print_header(message):
    print(f"\n{TermColors.HEADER}{TermColors.BOLD}=== {message} ==={TermColors.ENDC}")

def print_subheader(message):
    print(f"\n{TermColors.OKBLUE}{TermColors.BOLD}--- {message} ---{TermColors.ENDC}")

def print_success(message):
    print(f"{TermColors.OKGREEN}✅ {message}{TermColors.ENDC}")

def print_warning(message):
    print(f"{TermColors.WARNING}⚠️  {message}{TermColors.ENDC}")

def print_error(message):
    print(f"{TermColors.FAIL}❌ {message}{TermColors.ENDC}")

def print_info(message):
    print(f"{TermColors.OKCYAN}ℹ️  {message}{TermColors.ENDC}")

def print_command_to_copy(command_to_print):
    """ユーザーがコピーすべきコマンドを強調表示する"""
    print(f"{TermColors.OKGREEN}👉 次のコマンドをコピーして実行してください:{TermColors.ENDC}")
    print(f"   {TermColors.BOLD}{command_to_print}{TermColors.ENDC}")

def ask_yes_no(question, default_yes=True):
    """ユーザーに Yes/No で質問し、bool値を返す。"""
    choices = " [Y/n]" if default_yes else " [y/N]"
    prompt = f"{TermColors.WARNING}{question}{choices}:{TermColors.ENDC} "
    while True:
        try:
            user_input = input(prompt).strip().lower()
            if not user_input:
                return default_yes
            if user_input in ['y', 'yes']:
                return True
            if user_input in ['n', 'no']:
                return False
            print_warning("無効な入力です。「y」または「n」で答えてください。")
        except EOFError: # Ctrl+Dなどで入力が終わった場合
            return default_yes
        except KeyboardInterrupt: # Ctrl+Cで中断された場合
            print_error("\nセットアップが中断されました。")
            sys.exit(1)

def press_enter_to_continue():
    try:
        input(f"{TermColors.OKCYAN}\nエンターキーを押して次に進む...{TermColors.ENDC}")
    except KeyboardInterrupt:
        print_error("\nセットアップが中断されました。")
        sys.exit(1)

# --- チェック関数 ---
def check_python_version():
    print_subheader("Python バージョンチェック")
    current_version = sys.version_info
    if current_version >= MIN_PYTHON_VERSION:
        print_success(f"Python {platform.python_version()} は適切です (推奨: {'.'.join(map(str, MIN_PYTHON_VERSION))}+)。")
        return True
    else:
        print_error(f"Pythonのバージョンが古すぎます。現在のバージョン: {platform.python_version()}")
        print_warning(f"このBotにはPython {'.'.join(map(str, MIN_PYTHON_VERSION))} 以上が必要です。")
        print_info("Python公式サイトから最新版をインストールしてください: https://www.python.org/downloads/")
        return False

def is_in_venv():
    """現在のPythonが仮想環境内で実行されているか判定する"""
    return (hasattr(sys, 'real_prefix') or
            (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) or
            os.environ.get("VIRTUAL_ENV") is not None)

def manage_virtual_environment():
    print_subheader("仮想環境 (Virtual Environment) のセットアップ")
    venv_path = os.path.join(os.getcwd(), VENV_NAME)

    if is_in_venv():
        print_success(f"仮想環境 ({os.environ.get('VIRTUAL_ENV', VENV_NAME)}) 内で実行中です。")
        return True

    print_warning("仮想環境外で実行されています。")
    print_info("プロジェクトの依存関係をクリーンに保つため、仮想環境の作成を強く推奨します。")

    if os.path.exists(venv_path):
        print_info(f"既存の仮想環境フォルダ '{VENV_NAME}' が見つかりました。")
        if ask_yes_no(f"この既存の仮想環境 '{VENV_NAME}' を使用 (アクティベートを試みます) か、再作成しますか？ (Yes=使用, No=再作成)", default_yes=True):
            activate_venv_and_exit(venv_path, created_now=False) # 既存を使う場合もアクティベートを促す
            return False # スクリプトはここで終了
        else:
            if ask_yes_no(f"警告: 既存の '{VENV_NAME}' フォルダを削除して再作成しますか？ (フォルダ内の内容は失われます)", default_yes=False):
                try:
                    print_info(f"フォルダ '{VENV_NAME}' を削除中...")
                    shutil.rmtree(venv_path)
                    print_success(f"フォルダ '{VENV_NAME}' を削除しました。")
                except OSError as e:
                    print_error(f"'{VENV_NAME}' の削除に失敗しました: {e}")
                    print_info("手動で削除してから再試行してください。")
                    return False
            else:
                print_info("既存の仮想環境を使用しない、かつ再作成もしない場合、手動で環境を準備するか、このスクリプトを中断してください。")
                return False


    if ask_yes_no(f"仮想環境 '{VENV_NAME}' を作成しますか？", default_yes=True):
        try:
            print_info(f"仮想環境 '{VENV_NAME}' を作成中...")
            venv.create(venv_path, with_pip=True)
            print_success(f"仮想環境 '{VENV_NAME}' を作成しました。")
            activate_venv_and_exit(venv_path, created_now=True)
            return False # スクリプトはここで終了し、ユーザーに再実行を促す
        except Exception as e:
            print_error(f"仮想環境の作成に失敗しました: {e}")
            return False
    else:
        print_warning("仮想環境なしで続行します。依存関係の競合に注意してください。")
        return True # ユーザーが拒否した場合、そのまま続行（非推奨）

def activate_venv_and_exit(venv_path, created_now=True):
    if created_now:
        print_info("仮想環境が作成されました。次に、この仮想環境を" + TermColors.BOLD + "アクティベート" + TermColors.ENDC + "する必要があります。")
    else:
        print_info("既存の仮想環境を使用するため、" + TermColors.BOLD + "アクティベート" + TermColors.ENDC + "を試みてください。")
    print_info("アクティベート後、再度このセットアップスクリプトを実行してください。")
    print_info("-" * 50) # 区切り線

    if platform.system() == "Windows":
        print_info("お使いのターミナルに合わせて、以下のいずれかのコマンドを実行してください。")

        print_subheader("コマンドプロンプト (cmd.exe) の場合:")
        activate_script_cmd = os.path.join(venv_path, "Scripts", "activate.bat")
        print_command_to_copy(f".\\{os.path.relpath(activate_script_cmd)}")

        print_subheader("PowerShell の場合:")
        activate_script_ps = os.path.join(venv_path, "Scripts", "Activate.ps1")
        print_command_to_copy(f".\\{os.path.relpath(activate_script_ps)}")
        print_warning("PowerShellで上記コマンド実行時にエラーが出る場合、実行ポリシーの変更が必要かもしれません。")
        print_warning("例: Set-ExecutionPolicy RemoteSigned -Scope Process (このターミナルセッションのみ変更)")

    else: # macOS or Linux
        print_subheader("Linux / macOS (bash/zshなど) の場合:")
        activate_script_unix = os.path.join(venv_path, "bin", "activate")
        print_command_to_copy(f"source ./{os.path.relpath(activate_script_unix)}")

    print_info("-" * 50) # 区切り線
    print_info("仮想環境をアクティベートしたら、" + TermColors.BOLD + "同じターミナルで" + TermColors.ENDC + "、再度以下のコマンドを実行してセットアップを続行してください。")
    script_name = os.path.basename(__file__)
    print_command_to_copy(f"python {script_name}")
    print_info("このスクリプトはここで一旦終了します。")
    sys.exit(0)


def check_command_exists(command_name):
    """指定されたコマンドがPATH上または指定の実行ファイルとして存在するか確認"""
    if command_name.lower() == "ffmpeg":
        return shutil.which("ffmpeg") is not None
    if command_name.lower() == "yt-dlp": # yt-dlp.exe は個別チェック
        return shutil.which("yt-dlp") is not None
    return shutil.which(command_name) is not None

def check_ffmpeg():
    print_subheader("FFmpeg チェック")
    if check_command_exists("ffmpeg"):
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
            first_line = result.stdout.splitlines()[0] if result.stdout.splitlines() else "バージョン情報取得失敗"
            print_success(f"FFmpeg が見つかりました。 ({first_line.split(' Copyright')[0]})")
            return True
        except Exception as e:
            print_warning(f"FFmpeg は見つかりましたが、バージョン確認中にエラー: {e}")
            return True
    else:
        print_error("FFmpeg が見つかりません。")
        print_info("FFmpeg は音声処理に必須です。インストールしてPATHを通してください。")
        print_info("README.md の「必要な生贄 (前提条件)」セクションを参照してください。")
        if platform.system() == "Windows":
            print_info("例: `winget install ffmpeg` または https://ffmpeg.org/download.html からダウンロード。")
        elif platform.system() == "Darwin": # macOS
            print_info("例: `brew install ffmpeg`")
        else: # Linux
            print_info("例: `sudo apt update && sudo apt install ffmpeg` (Debian/Ubuntu系)")
        return False

def check_yt_dlp():
    print_subheader(f"{'yt-dlp (または yt-dlp.exe)'} チェック")
    # Windowsの場合、まずプロジェクトルートの yt-dlp.exe を確認
    if platform.system() == "Windows" and os.path.exists(YT_DLP_EXE_NAME):
        print_success(f"'{YT_DLP_EXE_NAME}' がプロジェクトルートに存在します。これを使用する設定がBot側にあるか確認してください。")
        print_info(f"注意: bot.pyがライブラリ版のyt-dlpを使用する場合、この'{YT_DLP_EXE_NAME}'は直接使われません。")
        # yt-dlpライブラリがインストールされるかも確認するので、ここではTrueを返して良い
        return True
    
    # 次にPATH上の yt-dlp コマンド (またはライブラリインストールの確認)
    if check_command_exists("yt-dlp"): # shutil.which は .exe も見つける
        print_success("yt-dlp (コマンドまたはライブラリ経由で利用可能なもの) が認識されています。")
        return True
    else: # requirements.txt でインストールされることを期待
        print_warning("yt-dlp コマンドが直接は見つかりませんでしたが、依存ライブラリとしてインストールされる予定です。")
        print_info(f"もし '{REQUIREMENTS_FILE}' に yt-dlp が含まれていれば問題ありません。")
        if platform.system() == "Windows" and not os.path.exists(YT_DLP_EXE_NAME):
             print_info(f"また、プロジェクトルートに '{YT_DLP_EXE_NAME}' も見つかりませんでした。")
        # この段階ではまだエラーとせず、ライブラリインストール後に期待
        return True # 依存関係インストールで解決することを期待


def install_dependencies():
    print_subheader("依存ライブラリのインストール")
    if not os.path.exists(REQUIREMENTS_FILE):
        print_error(f"'{REQUIREMENTS_FILE}' が見つかりません。Botの動作に必要なライブラリをインストールできません。")
        print_info("プロジェクトのルートに 'requirements.txt' ファイルを配置してください。")
        return False

    print_info(f"'{REQUIREMENTS_FILE}' を使ってライブラリをインストールします...")
    # 仮想環境内のpython.exeからpipモジュールを実行するのが最も確実
    pip_executable_parts = [sys.executable, "-m", "pip"]
    command = pip_executable_parts + ["install", "-r", REQUIREMENTS_FILE]

    # ユーザーに表示するコマンドは短縮形
    display_command = f"pip install -r {REQUIREMENTS_FILE}"
    if is_in_venv():
        display_command = f"({VENV_NAME}) {display_command}"
    print_info(f"実行コマンド (内部): {' '.join(command)}")
    print_info(f"実行イメージ: {display_command}")


    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
        print_info("--- pip install の出力ここから ---")
        for line in iter(process.stdout.readline, ''):
            print(f"   {line.strip()}") # pipの出力をインデントして表示
        process.stdout.close()
        return_code = process.wait()
        print_info("--- pip install の出力ここまで ---")


        if return_code == 0:
            print_success("依存ライブラリのインストールが完了しました。")
            return True
        else:
            print_error(f"依存ライブラリのインストール中にエラーが発生しました (終了コード: {return_code})。")
            print_warning("上記のpipの出力を確認してください。")
            return False
    except FileNotFoundError:
        print_error(f"'{sys.executable} -m pip' コマンドの実行に失敗しました。Pythonまたはpipの環境に問題がある可能性があります。")
        if not is_in_venv(): print_warning("仮想環境外で実行しているため、pipのパスが正しくない可能性があります。")
        return False
    except Exception as e:
        print_error(f"依存ライブラリのインストール中に予期せぬエラー: {e}")
        return False

def configure_env_file():
    print_subheader(".env ファイル (Discord Bot Token) の設定")
    if os.path.exists(ENV_FILE):
        print_info(f"'{ENV_FILE}' ファイルが既に存在します。")
        try:
            with open(ENV_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            if "DISCORD_BOT_TOKEN=" in content and not content.strip().endswith("DISCORD_BOT_TOKEN="):
                token_value = content.split("DISCORD_BOT_TOKEN=", 1)[1].split("\n")[0].strip()
                if token_value and token_value != "YOUR_VERY_SECRET_BOT_TOKEN_HERE":
                    print_success("DISCORD_BOT_TOKEN が設定されているようです。")
                    if ask_yes_no("トークンを上書きまたは確認しますか？", default_yes=False):
                        pass
                    else:
                        return True
                else:
                    print_warning("DISCORD_BOT_TOKEN は存在するものの、値が設定されていないか初期値のままです。")
        except Exception as e:
            print_warning(f"'{ENV_FILE}' の読み込み中にエラー: {e}")

    print_info(f"'{ENV_FILE}' ファイルに Discord Bot Token を設定します。")
    print_info("Discord Developer Portal (https://discord.com/developers/applications) で")
    print_info("あなたのBotのトークンを取得してください。")

    while True:
        try:
            token = input(f"{TermColors.WARNING}Discord Bot Token を入力してください:{TermColors.ENDC} ").strip()
            if not token:
                if ask_yes_no("トークンが入力されませんでした。スキップしますか？ (Botは起動できません)", default_yes=False):
                    print_warning(f"トークンが設定されませんでした。Botを起動する前に '{ENV_FILE}' を編集してください。")
                    if not os.path.exists(ENV_FILE):
                        with open(ENV_FILE, 'w', encoding='utf-8') as f:
                            f.write(ENV_FILE_EXAMPLE_CONTENT)
                        print_info(f"'{ENV_FILE}' にテンプレートを作成しました。")
                    return False
                else:
                    continue
            # 簡単なトークン形式チェック (オプション) - より厳密なチェックも可能
            if not (len(token) > 50 and (token.startswith("M") or token.startswith("N") or token.startswith("O"))):
                if not ask_yes_no(f"入力されたトークン「{token[:10]}...」は通常の形式と異なるようです。このまま使用しますか？", default_yes=False):
                    continue
            break
        except KeyboardInterrupt:
            print_error("\nトークン設定が中断されました。")
            return False

    try:
        with open(ENV_FILE, 'w', encoding='utf-8') as f:
            f.write(f"DISCORD_BOT_TOKEN={token}\n")
        print_success(f"Bot Token を '{ENV_FILE}' に保存しました。")
        print_warning(f"重要: '{ENV_FILE}' ファイルは絶対にGitなどにコミットしないでください！")
        
        gitignore_path = ".gitignore"
        try:
            gitignore_content = ""
            if os.path.exists(gitignore_path):
                with open(gitignore_path, 'r', encoding='utf-8') as f_git:
                    gitignore_content = f_git.read()
            
            needs_update = False
            append_content = ""
            if f"/{VENV_NAME}/" not in gitignore_content and f"{VENV_NAME}/" not in gitignore_content :
                 append_content += f"\n/{VENV_NAME}/" # / で始まるか、単にフォルダ名
                 needs_update = True
            if ENV_FILE not in gitignore_content:
                 append_content += f"\n{ENV_FILE}"
                 needs_update = True
            
            if needs_update:
                if ask_yes_no(f"'{gitignore_path}' に '{VENV_NAME}/' や '{ENV_FILE}' を追記しますか？", default_yes=True):
                    with open(gitignore_path, 'a', encoding='utf-8') as f_git_append:
                        f_git_append.write(append_content.strip()+"\n")
                    print_success(f"'{gitignore_path}' を更新しました。")

        except Exception as e_git:
            print_warning(f"'{gitignore_path}' の処理中にエラー: {e_git}")
        return True
    except Exception as e:
        print_error(f"'{ENV_FILE}' の書き込み中にエラー: {e}")
        return False

# --- メイン処理 ---
def main():
    TermColors.enable_colors()
    TermColors.clear_screen()
    print_header("Discord Music Bot - セットアップアシスタント")
    print_info(f"ようこそ！このスクリプトはBotの基本的なセットアップをお手伝いします。")
    press_enter_to_continue()

    all_steps_ok = True
    total_steps = 6 # Python, Venv, FFmpeg, yt-dlp, Dependencies, .env

    # 1. Python バージョンチェック
    TermColors.clear_screen()
    print_header(f"ステップ 1/{total_steps}: Python バージョン")
    if not check_python_version():
        all_steps_ok = False
    press_enter_to_continue()

    # 2. 仮想環境のセットアップ
    TermColors.clear_screen()
    print_header(f"ステップ 2/{total_steps}: 仮想環境")
    if not manage_virtual_environment() and not is_in_venv():
        all_steps_ok = False
        print_error("仮想環境のセットアップが完了していません。スクリプトを終了します。")
        sys.exit(1)
    if not is_in_venv():
        print_warning("仮想環境を使用していません。強く推奨されません。")
    press_enter_to_continue()

    # 3. FFmpeg チェック
    TermColors.clear_screen()
    print_header(f"ステップ 3/{total_steps}: FFmpeg")
    if not check_ffmpeg():
        if not ask_yes_no("FFmpegが見つかりませんでした。無視して続行しますか？ (Botは音楽を再生できません)", default_yes=False):
            all_steps_ok = False
        else:
            print_warning("FFmpegなしで続行します。音楽再生機能は動作しません。")
    press_enter_to_continue()

    # 4. yt-dlp チェック
    TermColors.clear_screen()
    print_header(f"ステップ 4/{total_steps}: yt-dlp")
    if not check_yt_dlp(): # この関数は依存関係インストールで解決期待なので、Falseを返すのはまれ
        if not ask_yes_no("yt-dlpの確認で問題がありました。無視して続行しますか？ (Botは動画情報を取得できない可能性)", default_yes=False):
            all_steps_ok = False
        else:
            print_warning("yt-dlpの問題を無視して続行します。")
    press_enter_to_continue()

    # 5. 依存ライブラリのインストール (仮想環境内でのみ実行を推奨)
    TermColors.clear_screen()
    print_header(f"ステップ 5/{total_steps}: 依存ライブラリ")
    if not os.path.exists(REQUIREMENTS_FILE):
        print_error(f"致命的エラー: '{REQUIREMENTS_FILE}' が見つかりません。セットアップを続行できません。")
        print_info(f"このファイルはBotの動作に必要なライブラリをリストしたものです。プロジェクトのルートに作成またはコピーしてください。")
        all_steps_ok = False
    elif is_in_venv() or ask_yes_no("仮想環境外です。依存ライブラリをグローバルにインストールしますか？ (非推奨)", default_yes=False):
        if not install_dependencies():
            all_steps_ok = False
    else:
        print_warning("依存ライブラリのインストールをスキップしました。")
        all_steps_ok = False
    press_enter_to_continue()

    # 6. .env ファイル (Discord Bot Token) の設定
    TermColors.clear_screen()
    print_header(f"ステップ 6/{total_steps}: .env (Bot Token) 設定")
    if not configure_env_file():
        print_warning("Bot Token が正しく設定されませんでした。BotはDiscordに接続できません。")
        # all_steps_ok はここでは直接変更しないが、最終メッセージで考慮

    # --- 最終結果 ---
    TermColors.clear_screen()
    print_header("セットアップアシスタント完了")
    
    token_configured = False
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, 'r', encoding='utf-8') as f_env:
                env_content = f_env.read()
                if "DISCORD_BOT_TOKEN=" in env_content and \
                   not env_content.strip().endswith("DISCORD_BOT_TOKEN=") and \
                   "YOUR_VERY_SECRET_BOT_TOKEN_HERE" not in env_content:
                    token_configured = True
        except:
            pass # エラー時はfalseのまま

    if all_steps_ok and token_configured:
        print_success("基本的なセットアップが完了しました！")
        print_info(f"Botを起動するには、このターミナルで `python bot.py` を実行してください。")
        if is_in_venv():
             print_info(f"現在アクティブな仮想環境: {os.environ.get('VIRTUAL_ENV')}")
             print_info("Botの使用が終わったら `deactivate` コマンドで仮想環境を終了できます。")
        else:
             print_warning("仮想環境を使用していません。再度セットアップを実行し、仮想環境を作成することを強く推奨します。")
    else:
        print_error("セットアップ中にいくつかの問題が発生したか、未完了のステップがあります。")
        print_warning("上記のエラーメッセージや警告を確認し、必要な対応を行ってください。")
        if not all_steps_ok:
            print_info("問題解決後、再度このスクリプトを実行するか、手動で設定を完了してください。")
        if not token_configured:
            print_warning(f"'{ENV_FILE}' に有効なDiscord Bot Tokenが設定されていないようです。Botは起動できません。")
            print_info(f"再度このスクリプトを実行してトークンを設定するか、手動で '{ENV_FILE}' を編集してください。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_error("\n\nセットアップがユーザーによって中断されました。")
        sys.exit(1)
    except Exception as e:
        print_error(f"\n\n予期せぬエラーが発生しました: {e}")
        print_warning("エラーの詳細情報を開発者に報告すると、問題解決に役立つ場合があります。")
        # デバッグ用にトレースバックを表示することも検討
        # import traceback
        # traceback.print_exc()
        sys.exit(1)
    finally:
        print(TermColors.ENDC) # 念のため最後にカラーをリセット
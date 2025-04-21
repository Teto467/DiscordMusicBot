import subprocess
import sys
import importlib.util

# インストール/更新対象のライブラリ (import名: pipでのパッケージ名)
# 標準ライブラリは除外
libraries_to_manage = {
    "discord": "discord.py",
    "yt_dlp": "yt-dlp",
    "dotenv": "python-dotenv",
    # "asyncio": None, # 標準ライブラリ
    # "os": None,      # 標準ライブラリ
    # "collections": None, # 標準ライブラリ
    # "logging": None, # 標準ライブラリ
    # "time": None,    # 標準ライブラリ
}

def check_and_install_libraries(libs):
    """
    指定されたライブラリのリストをチェックし、
    存在しない場合や更新が必要な場合にインストール/更新を行う。
    """
    print("--- ライブラリのインストール/更新を開始します ---")
    installed_count = 0
    updated_count = 0
    failed_count = 0
    failed_libs = []

    # pipコマンドのパスを取得 (実行中のPython環境に対応するpipを使用)
    pip_command = [sys.executable, "-m", "pip"]

    for import_name, package_name in libs.items():
        if package_name is None:
            print(f"[*] '{import_name}' は標準ライブラリのためスキップします。")
            continue

        print(f"\n[+] '{package_name}' (import名: {import_name}) の処理を開始...")

        # ライブラリが既にインストールされているか簡易チェック (必須ではないがあると親切)
        # spec = importlib.util.find_spec(import_name)
        # if spec:
        #     print(f"    '{package_name}' は既にインストールされているようです。更新を試みます。")
        # else:
        #     print(f"    '{package_name}' はインストールされていません。インストールを試みます。")

        # pip install --upgrade コマンドを実行
        # --upgrade オプションにより、未インストールならインストール、
        # インストール済みなら最新版に更新される
        command = pip_command + ["install", "--upgrade", package_name]
        print(f"    実行コマンド: {' '.join(command)}")

        try:
            # サブプロセスとしてpipを実行
            # capture_output=True で標準出力/エラー出力をキャプチャ
            # text=True で出力をテキストとして扱う
            # check=True でエラー時(終了コードが0以外)に CalledProcessError を発生させる
            # encoding='utf-8' で文字化けを防ぐ (環境による)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace' # エンコードエラー時に文字を置換
            )

            # pipの出力に "Successfully installed" や "Requirement already satisfied" が含まれるかで判断
            output_lower = result.stdout.lower()
            if f"successfully installed {package_name.lower()}" in output_lower:
                print(f"    ✅ '{package_name}' のインストールが成功しました。")
                installed_count += 1
            elif "requirement already satisfied" in output_lower:
                print(f"    ✅ '{package_name}' は既に最新バージョンです (または更新されました)。")
                updated_count += 1
            else:
                # 上記以外でも成功している場合があるので、成功メッセージは出す
                print(f"    ✅ '{package_name}' の処理が完了しました。")
                # 詳細が必要ならpipの出力を表示
                # print("--- pip output ---")
                # print(result.stdout)
                # print("------------------")
                updated_count += 1 # 更新/確認済みとしてカウント

        except subprocess.CalledProcessError as e:
            print(f"    ❌ エラー: '{package_name}' のインストール/更新に失敗しました。")
            print("    --- エラー詳細 ---")
            print(e.stderr)
            print("    ------------------")
            failed_count += 1
            failed_libs.append(package_name)
        except FileNotFoundError:
            print(f"❌ エラー: '{sys.executable} -m pip' コマンドが見つかりません。")
            print("    Pythonとpipが正しくインストールされ、PATHが通っているか確認してください。")
            print("    スクリプトを中断します。")
            sys.exit(1) # スクリプトを終了
        except Exception as e:
            print(f"    ❌ 予期せぬエラーが発生しました ({package_name}): {e}")
            failed_count += 1
            failed_libs.append(package_name)

    print("\n--- 結果 ---")
    print(f"インストール成功: {installed_count}")
    print(f"更新/確認済み: {updated_count}")
    print(f"失敗: {failed_count}")
    if failed_libs:
        print(f"失敗したライブラリ: {', '.join(failed_libs)}")
    print("------------")

    if failed_count > 0:
        print("\nいくつかのライブラリの処理に失敗しました。上記のエラーメッセージを確認してください。")
        sys.exit(1) # エラーがあった場合は終了コード1で終了
    else:
        print("\nすべての指定されたライブラリの処理が正常に完了しました。")

# スクリプトの実行
if __name__ == "__main__":
    check_and_install_libraries(libraries_to_manage)

    print("\n--- 追加の推奨事項 ---")
    print("プロジェクトの依存関係を管理するために 'requirements.txt' ファイルの使用を検討してください。")
    print("現在の環境のライブラリリストを作成するには、ターミナルで以下のコマンドを実行します:")
    print("  pip freeze > requirements.txt")
    print("その後、他の環境で 'pip install -r requirements.txt' を実行すると、")
    print("同じバージョンのライブラリを一括でインストールできます。")
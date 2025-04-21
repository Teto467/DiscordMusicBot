# --- START OF FILE bot.py (Loop機能削除版, np重複修正版) ---

import discord
import asyncio
import yt_dlp
import os
from collections import deque
from dotenv import load_dotenv
import logging
import time # 再生時間計算用

# --- ロギング設定 ---
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
# ルートロガーのレベルを DEBUG に設定して詳細なログを見る
logging.basicConfig(level=logging.DEBUG, handlers=[console_handler])
logger = logging.getLogger(__name__)
# ライブラリのログレベルは WARNING のまま（必要なら INFO に変更）
logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('yt_dlp').setLevel(logging.WARNING)

# .envファイルから環境変数を読み込む（任意）
load_dotenv()

# Discord Bot Tokenを環境変数から取得
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not DISCORD_BOT_TOKEN:
    logger.critical("エラー: 環境変数 'DISCORD_BOT_TOKEN' が設定されていません。")
    exit()

# yt-dlp の設定 (メタデータ取得用)
ydl_opts_meta = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': True, # プレイリスト内のエラーエントリをスキップ
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extract_flat': 'in_playlist', # プレイリスト取得を高速化
}

# 再生時に使うffmpegオプション (安定性向上)
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', # 再接続オプション
    'options': '-vn' # 音声のみを抽出
}

# yt-dlp インスタンス (メタデータ取得用)
ytdl_meta = yt_dlp.YoutubeDL(ydl_opts_meta)

# yt-dlp インスタンス (個別のストリームURL取得用)
ydl_opts_stream = ydl_opts_meta.copy()
ydl_opts_stream['ignoreerrors'] = False # 個別の曲のエラーは検知する
ydl_opts_stream['extract_flat'] = False # 個別取得時はFalseに
# ydl_opts_stream['format'] = 'bestaudio[abr<=128]/bestaudio/best' # 必要なら調整
ytdl_stream = yt_dlp.YoutubeDL(ydl_opts_stream)


# --- データ構造 ---
class Song:
    """再生する曲の情報を保持するクラス"""
    def __init__(self, source: discord.FFmpegPCMAudio, title: str, url: str, requester: discord.Member | None, duration: float | None = None):
        self.source = source
        self.title = title
        self.url = url
        self.requester = requester
        self.duration = duration # 秒単位 or None

class GuildMusicState:
    """サーバーごとの音楽再生状態を管理するクラス"""
    _logger = logging.getLogger(__qualname__)

    def __init__(self, loop: asyncio.AbstractEventLoop, guild_id: int):
        self.guild_id = guild_id
        self.queue = deque() # 曲情報辞書のキュー {'webpage_url': ..., 'title': ..., 'requester': ..., 'duration': ...}
        self.voice_client: discord.VoiceClient | None = None
        self.current_song: Song | None = None
        self.loop = loop
        self.play_next_song = asyncio.Event() # 次の曲へ進むトリガー
        self.audio_player_task: asyncio.Task | None = None # 再生ループタスク
        self.last_text_channel_id: int | None = None # 最後にコマンドが使われたチャンネルID
        self.playback_start_time: float | None = None # 現在の曲の再生開始時刻 (time.time())
        self._playback_was_successful: bool = False # 再生成功フラグ (キュー処理用だったが残す)
        self._logger.info(f"Guild {self.guild_id}: Music state initialized.")

    async def notify_channel(self, message: str, embed: discord.Embed | None = None, delete_after: float | None = None):
        """最後にコマンドが使われたチャンネルにメッセージを送信する"""
        if not self.last_text_channel_id:
            self._logger.debug(f"Guild {self.guild_id}: No last text channel ID, cannot send notification.")
            return

        try:
            guild = bot.get_guild(self.guild_id)
            if not guild: return
            channel = guild.get_channel(self.last_text_channel_id)
            if isinstance(channel, discord.TextChannel):
                await channel.send(content=message if not embed else None, embed=embed, delete_after=delete_after)
            else:
                 self._logger.warning(f"Guild {self.guild_id}: Channel {self.last_text_channel_id} not found/not text.")
        except discord.errors.Forbidden:
            self._logger.error(f"Guild {self.guild_id}: Missing permissions in channel {self.last_text_channel_id}.")
        except Exception as e:
            self._logger.exception(f"Guild {self.guild_id}: Failed to send notification: {e}")

    def update_last_channel(self, channel_id: int):
        """最後に使用されたテキストチャンネルIDを更新する"""
        self.last_text_channel_id = channel_id

    def start_player_task(self):
        """オーディオプレーヤータスクを開始または再開する"""
        if self.audio_player_task is None or self.audio_player_task.done():
           if self.audio_player_task and self.audio_player_task.cancelled():
               self._logger.info(f"Guild {self.guild_id}: Previous audio player task cancelled. Creating new.")
           elif self.audio_player_task and self.audio_player_task.done() and self.audio_player_task.exception():
                exc = self.audio_player_task.exception()
                self._logger.error(f"Guild {self.guild_id}: Previous audio player task finished with error: {exc}")
           self._logger.info(f"Guild {self.guild_id}: Starting audio player task.")
           self.audio_player_task = self.loop.create_task(self.audio_player())
        else:
           self._logger.debug(f"Guild {self.guild_id}: Audio player task already running.")

    async def audio_player(self):
        """キューを監視し、曲を再生するメインループ (ループ機能削除版)"""
        self._logger.info(f"Guild {self.guild_id}: === Audio player task started ===")

        while True: # メイン再生ループ
            self.play_next_song.clear()
            self._playback_was_successful = False # 各サイクルの開始時にリセット

            self._logger.debug(f"Guild {self.guild_id}: --- Player loop cycle start --- Queue size: {len(self.queue)}")

            # --- 次の曲の準備 ---
            next_song_info: dict | None = None
            if self.queue:
                # キューから取得
                next_song_info = self.queue.popleft()
                self._logger.debug(f"Guild {self.guild_id}: Popped from queue: {next_song_info.get('title')}")
            else: # キューが空
                self._logger.debug(f"Guild {self.guild_id}: Queue empty. Entering wait state.")
                self.current_song = None # 再生対象がないのでクリア
                self.playback_start_time = None
                # イベントがセットされるまで待機
                await self.play_next_song.wait()
                self._logger.debug(f"Guild {self.guild_id}: Player task woken up after wait.")
                # ループの先頭に戻る
                continue # 次のサイクルへ

            # --- 曲オブジェクト作成と再生 ---
            try:
                if not next_song_info:
                    self._logger.warning(f"Guild {self.guild_id}: next_song_info is None unexpectedly. Skipping cycle.")
                    # ループの先頭に戻る
                    continue # 次のサイクルへ

                original_url = next_song_info.get('webpage_url', 'N/A')
                requester = next_song_info.get('requester') # ここではまだ Member or ID or None
                title_hint = next_song_info.get('title', 'N/A')

                self._logger.info(f"Guild {self.guild_id}: Preparing song object for: '{title_hint}' (URL: {original_url})")
                # create_song_object 呼び出し (requesterを渡す)
                self.current_song = await self.create_song_object(original_url, requester)

                if self.current_song is None:
                    self._logger.warning(f"Guild {self.guild_id}: Failed to create song object for '{title_hint}'. Skipping.")
                    await self.notify_channel(f"❌ 曲「{title_hint}」読込失敗、スキップ。", delete_after=15)
                    # ループの先頭に戻る
                    continue # 次のサイクルへ

                # --- VC接続確認と再生開始 ---
                if self.voice_client and self.voice_client.is_connected():
                    self._logger.info(f"Guild {self.guild_id}: Playing '{self.current_song.title}' (Dur: {self.format_duration(self.current_song.duration)}) Req by {self.current_song.requester.name if self.current_song.requester else 'Unknown'}")
                    self.playback_start_time = time.time()
                    # play() 呼び出し
                    self.voice_client.play(self.current_song.source, after=lambda e: self.handle_after_play(e))

                    # 再生開始通知
                    duration_str = self.format_duration(self.current_song.duration)
                    embed = discord.Embed(
                        description=f"🎵 **[{self.current_song.title}]({self.current_song.url})**\n"
                                    f"👤 Req: {self.current_song.requester.mention if self.current_song.requester else '不明'} | ⏱️ Len: {duration_str}",
                        color=discord.Color.green()
                    )
                    display_duration = self.current_song.duration if self.current_song.duration and self.current_song.duration < 3600 else None
                    await self.notify_channel("", embed=embed, delete_after=display_duration)

                    self._logger.debug(f"Guild {self.guild_id}: Waiting for play_next_song event...")
                    # wait() 呼び出し
                    await self.play_next_song.wait() # 再生終了 or スキップ待ち
                    self._logger.debug(f"Guild {self.guild_id}: play_next_song event received. Successful flag: {self._playback_was_successful}")

                else: # VC未接続
                    self._logger.error(f"Guild {self.guild_id}: VC disconnected before playing. Cleaning up.")
                    self.queue.clear()
                    if self.voice_client: self.voice_client = None
                    remove_guild_state(self.guild_id)
                    # タスク自体を終了
                    break # whileループを抜ける

                # --- 再生終了後の処理 ---
                # self._playback_was_successful フラグは handle_after_play でセットされている
                playback_successful = self._playback_was_successful # フラグをローカル変数にコピー

                # ループ機能がないため、再生後の特別な処理は不要
                if playback_successful:
                     self._logger.debug(f"Guild {self.guild_id}: Playback successful.")
                else:
                     self._logger.debug(f"Guild {self.guild_id}: Playback not successful (skipped or error).")

            except asyncio.CancelledError:
                 self._logger.info(f"Guild {self.guild_id}: Audio player task cancelled.")
                 # タスク自体を終了
                 break # whileループを抜ける
            except Exception as e:
                self._logger.exception(f"Guild {self.guild_id}: Unexpected error in player loop cycle: {e}")
                await self.notify_channel(f"⚠️ プレーヤーエラー発生: `{e}`", delete_after=30)
                # エラーが発生しても次の曲へ進むためにループは継続
                await asyncio.sleep(1) # 少し待機
                # ループの先頭に戻る
                continue # 次のサイクルへ

            finally:
                 # 各サイクルの最後に必ず通る
                 self._logger.debug(f"Guild {self.guild_id}: End of loop cycle. Cleaning up current song state.")
                 self.current_song = None
                 self.playback_start_time = None
                 # _playback_was_successful は次のサイクルの最初にリセットされる

            # 自然に次のループサイクルへ
            self._logger.debug(f"Guild {self.guild_id}: --- Proceeding to the next player loop cycle ---")


        # --- while ループが break で抜けられた場合 ---
        self._logger.info(f"Guild {self.guild_id}: === Audio player task finished (exited while loop) ===")
        # 終了時のクリーンアップ (念のため)
        self.queue.clear()
        self.current_song = None
        self.playback_start_time = None
        # VC切断や状態削除は remove_guild_state に任せる


    def handle_after_play(self, error):
        """再生終了時のコールバック (再生成功フラグ設定追加)"""
        log_prefix = f"Guild {self.guild_id}: [AfterPlay]"
        # コールバック実行時点の曲名をログに残す
        current_title_for_log = self.current_song.title if self.current_song else 'N/A (state might be ahead)'
        self._logger.debug(f"{log_prefix} Callback entered. Error: {error}. Current song for log: '{current_title_for_log}'")

        if error:
            self._playback_was_successful = False # エラー時は False
            if isinstance(error, discord.errors.ConnectionClosed): self._logger.warning(f"{log_prefix} Player conn closed: {error}")
            elif 'Not connected' in str(error): self._logger.warning(f"{log_prefix} Player not connected: {error}")
            else: self._logger.error(f'{log_prefix} Player error: {error}')
            # エラー通知 (非同期実行)
            asyncio.run_coroutine_threadsafe(
                self.notify_channel(f"⚠️ 再生エラー発生: {current_title_for_log}\n`{error}`", delete_after=30),
                self.loop
            )
        else:
            self._playback_was_successful = True # 正常終了時は True
            self._logger.info(f"{log_prefix} Finished playing '{current_title_for_log}' successfully.")

        # 次の曲への進行をトリガー
        self._logger.debug(f"{log_prefix} Setting play_next_song event.")
        self.loop.call_soon_threadsafe(self.play_next_song.set)
        self._logger.debug(f"{log_prefix} Callback finished.")


    async def create_song_object(self, url: str, requester: discord.Member | int | None) -> Song | None:
        """URLから再生に必要なSongオブジェクトを作成する (Requester型対応)"""
        # RequesterがIDの場合、Memberオブジェクトを取得試行
        requester_member: discord.Member | None = None
        if isinstance(requester, discord.Member):
             requester_member = requester
        elif isinstance(requester, int): # IDの場合
             guild = bot.get_guild(self.guild_id)
             if guild:
                 try:
                     requester_member = await guild.fetch_member(requester)
                     self._logger.debug(f"Guild {self.guild_id}: Successfully fetched member for ID {requester}")
                 except discord.errors.NotFound: self._logger.warning(f"Guild {self.guild_id}: Requester ID {requester} not found in guild.")
                 except discord.errors.HTTPException: self._logger.warning(f"Guild {self.guild_id}: Failed to fetch requester ID {requester} due to HTTP error.")
             else: self._logger.warning(f"Guild {self.guild_id}: Cannot fetch member, guild not found.")
        # else requester is None or other type

        self._logger.debug(f"Guild {self.guild_id}: Creating song object for URL: {url}. Requester obj: {requester_member}")
        try:
            loop = asyncio.get_event_loop()
            self._logger.debug(f"Guild {self.guild_id}: Running ytdl_stream.extract_info in executor for {url}...")
            data = await loop.run_in_executor(None, lambda: ytdl_stream.extract_info(url, download=False))
            self._logger.debug(f"Guild {self.guild_id}: ytdl_stream.extract_info finished.")

            if not data:
                 self._logger.warning(f"Guild {self.guild_id}: ytdl_stream returned no data for {url}.")
                 return None

            if 'entries' in data and data['entries']:
                self._logger.debug(f"Guild {self.guild_id}: Playlist URL passed, using first entry.")
                if not data['entries']: return None
                data = data['entries'][0]
                if not data: return None

            stream_url = data.get('url')
            if not stream_url:
                 formats = data.get('formats', [])
                 self._logger.debug(f"Guild {self.guild_id}: No direct stream URL. Checking {len(formats)} formats...")
                 audio_formats = [f for f in formats if f.get('url') and f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                 if audio_formats:
                      best_audio = max(audio_formats, key=lambda f: f.get('abr', 0) if f.get('acodec') == 'opus' else (f.get('abr', 0) - 1000) if f.get('acodec') == 'aac' else -2000)
                      stream_url = best_audio.get('url')
                      self._logger.debug(f"Guild {self.guild_id}: Found audio-only stream (acodec: {best_audio.get('acodec')}).")
                 else:
                      mixed_formats = [f for f in formats if f.get('url') and f.get('acodec') != 'none']
                      if mixed_formats:
                           best_mixed = max(mixed_formats, key=lambda f: f.get('abr', 0))
                           stream_url = best_mixed.get('url')
                           self._logger.debug(f"Guild {self.guild_id}: Found mixed stream (acodec: {best_mixed.get('acodec')}).")
                 if not stream_url:
                     self._logger.error(f"Guild {self.guild_id}: Could not extract stream URL for {data.get('webpage_url', url)}.")
                     return None

            title = data.get('title', '不明なタイトル')
            webpage_url = data.get('webpage_url', url)
            duration = data.get('duration')

            self._logger.debug(f"Guild {self.guild_id}: Creating FFmpegPCMAudio source for '{title}'. Duration: {duration}")
            source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_options)
            self._logger.info(f"Guild {self.guild_id}: Successfully created song object: '{title}' from {webpage_url}")
            # requester_member を渡す (Memberオブジェクト or None)
            return Song(source, title, webpage_url, requester_member, duration)

        except yt_dlp.utils.DownloadError as e:
             self._logger.warning(f"Guild {self.guild_id}: yt-dlp error creating song object for {url}: {e}")
             asyncio.run_coroutine_threadsafe(self.notify_channel(f"❌ 曲「{url}」読込失敗: `{e}`", delete_after=30), self.loop)
             return None
        except Exception as e:
            self._logger.exception(f"Guild {self.guild_id}: Unexpected error creating song object for {url}: {e}")
            asyncio.run_coroutine_threadsafe(self.notify_channel(f"❌ 曲「{url}」読込中エラー: `{e}`", delete_after=30), self.loop)
            return None

    async def add_to_queue(self, url_or_search: str, requester: discord.Member, ctx: discord.ApplicationContext):
        """キューに曲を追加する (UX向上版 - ブロッキング対策)"""
        self.update_last_channel(ctx.channel_id)
        self._logger.info(f"Guild {self.guild_id}: Adding to queue requested by {requester.name} ({requester.id}): '{url_or_search}'") # IDもログに
        loop = asyncio.get_event_loop()
        added_count = 0
        is_playlist = False
        playlist_title = None
        songs_to_add = []
        initial_message: discord.WebhookMessage | None = None

        try:
            # 初期応答はdeferしているので、followupで応答する
            initial_message = await ctx.followup.send(f"⏳ '{url_or_search}' 検索中...")

            self._logger.debug(f"Guild {self.guild_id}: Running ytdl_meta.extract_info in executor...")
            # extract_flat=Trueでメタデータを高速取得
            data = await loop.run_in_executor(None, lambda: ytdl_meta.extract_info(url_or_search, download=False, process=False))
            self._logger.debug(f"Guild {self.guild_id}: ytdl_meta finished. Type: {data.get('_type') if data else 'None'}")

            if not data:
                 self._logger.warning(f"Guild {self.guild_id}: No data found for '{url_or_search}'.")
                 await initial_message.edit(content=f"❌ '{url_or_search}' 情報が見つかりません。")
                 return 0

            if data.get('_type') == 'playlist':
                is_playlist = True
                playlist_title = data.get('title', 'プレイリスト')
                self._logger.info(f"Guild {self.guild_id}: Playlist: '{playlist_title}'. Processing entries...")
                await initial_message.edit(content=f"⏳ Playlist「{playlist_title}」処理中...")

                entries = data.get('entries')
                if not entries:
                     self._logger.warning(f"Guild {self.guild_id}: Playlist entries missing.")
                     await initial_message.edit(content=f"⚠️ Playlist「{playlist_title}」に曲なし。")
                     return 0

                self._logger.debug(f"Guild {self.guild_id}: Converting entries to list in executor...")
                # entries はジェネレータの場合があるのでリスト化
                entries_list = await loop.run_in_executor(None, list, entries)
                original_entry_count = len(entries_list)
                self._logger.info(f"Guild {self.guild_id}: Converted {original_entry_count} entries.")
                await initial_message.edit(content=f"⏳ Playlist「{playlist_title}」({original_entry_count}曲) 処理中...")

                for entry in entries_list:
                    if not entry: continue
                    entry_title = entry.get('title')
                    webpage_url = None
                    entry_id = entry.get('id')
                    # yt-dlpのextract_flatではURLがないことがあるので、IDから復元を試みる
                    if entry_id and entry.get('ie_key') == 'Youtube': webpage_url = f"https://www.youtube.com/watch?v={entry_id}"
                    else: webpage_url = entry.get('url') # フォールバック

                    if webpage_url and entry_title and entry_title != '[Unavailable Video]' and entry_title != '[Deleted video]':
                        # キューには Member オブジェクトではなく ID を格納する (再接続時の fetch 用)
                        songs_to_add.append({'webpage_url': webpage_url,'title': entry_title,'requester': requester.id,'duration': entry.get('duration')})
                        added_count += 1
                    else:
                        self._logger.warning(f"Guild {self.guild_id}: Skipping invalid playlist entry (ID:'{entry_id}', Title:'{entry_title}', URL: {webpage_url})")

            else: # 単一 or 検索
                 # extract_flat=True の場合、単一動画でも title などが不足することがある
                 # process=False で取得した場合、再取得が必要
                 if data.get('_type') == 'url' or not data.get('title') or not data.get('duration'):
                      self._logger.info(f"Guild {self.guild_id}: Re-fetching full info in executor for single entry...")
                      await initial_message.edit(content=f"⏳ '{url_or_search}' 情報取得中...")
                      try:
                          # extract_flat=False で詳細情報を取得
                          fetched_data = await loop.run_in_executor(None, lambda: ytdl_stream.extract_info(url_or_search, download=False))
                          if not fetched_data: raise yt_dlp.utils.DownloadError("Failed to fetch full info.")
                          # 検索結果の場合、最初のものを採用
                          if fetched_data.get('entries'):
                              if not fetched_data['entries']: raise yt_dlp.utils.DownloadError("Search result empty.")
                              data = fetched_data['entries'][0]
                          else: data = fetched_data # 単一動画の詳細情報
                      except yt_dlp.utils.DownloadError as dl_error:
                           self._logger.warning(f"Guild {self.guild_id}: Failed re-fetch: {dl_error}")
                           await initial_message.edit(content=f"❌ 情報取得失敗: `{dl_error}`")
                           return 0
                      except Exception as e:
                           self._logger.exception(f"Guild {self.guild_id}: Error during re-fetch: {e}")
                           await initial_message.edit(content=f"❌ 情報取得中エラー: `{e}`")
                           return 0

                 self._logger.info(f"Guild {self.guild_id}: Processing as single entry.")
                 entry_title = data.get('title')
                 webpage_url = data.get('webpage_url') or data.get('original_url') or data.get('url')
                 duration = data.get('duration')

                 if webpage_url and entry_title and entry_title != '[Unavailable Video]' and entry_title != '[Deleted video]':
                     # キューには Member オブジェクトではなく ID を格納
                     songs_to_add.append({'webpage_url': webpage_url,'title': entry_title,'requester': requester.id,'duration': duration})
                     added_count = 1
                     self._logger.info(f"Guild {self.guild_id}: Identified single song: '{entry_title}'.")
                     # 単一曲の場合は initial_message を削除しても良いかもしれないが、編集で完了を示す
                     # await initial_message.delete() # 削除する場合
                 else:
                     self._logger.warning(f"Guild {self.guild_id}: Failed to get valid video data. Title: {entry_title}, URL: {webpage_url}")
                     errmsg = f"❌ 曲情報取得失敗。"
                     if not webpage_url: errmsg += " (URL不明)"
                     if not entry_title or entry_title == '[Unavailable Video]' or entry_title == '[Deleted video]': errmsg += " (タイトル/動画無効)"
                     await initial_message.edit(content=errmsg)
                     return 0

            # --- キューへの追加と通知 ---
            if songs_to_add:
                self.queue.extend(songs_to_add)
                self._logger.info(f"Guild {self.guild_id}: Added {added_count} song(s) to queue. Queue size: {len(self.queue)}")
                final_message_content = ""
                if is_playlist: final_message_content = f"✅ Playlist「{playlist_title}」から {added_count} 曲をキューに追加。"
                else: final_message_content = f"✅ キュー追加: **{songs_to_add[0]['title']}** ({self.format_duration(songs_to_add[0]['duration'])})"
                try:
                     await initial_message.edit(content=final_message_content)
                except discord.errors.NotFound: logger.warning(f"Guild {self.guild_id}: Failed to edit final confirmation (message deleted?).")
                except Exception as e: logger.exception(f"Guild {self.guild_id}: Error editing final confirmation: {e}")
            elif is_playlist: # プレイリストだが追加されなかった場合
                 self._logger.warning(f"Guild {self.guild_id}: No valid songs added from playlist '{playlist_title}'.")
                 final_message_content = f"⚠️ Playlist「{playlist_title}」から有効な曲を追加できませんでした。"
                 try:
                     await initial_message.edit(content=final_message_content)
                 except discord.errors.NotFound: pass
                 except Exception as e: logger.exception(f"Guild {self.guild_id}: Error editing playlist empty confirmation: {e}")
            else: # 単一曲でも追加されなかった場合 (上のエラー処理でメッセージは編集済のはず)
                self._logger.warning(f"Guild {self.guild_id}: No songs were added for '{url_or_search}'.")


        except yt_dlp.utils.DownloadError as e:
             self._logger.warning(f"Guild {self.guild_id}: yt-dlp error adding to queue: {e}")
             try:
                 if "Unsupported URL" in str(e): errmsg = f"❌ サポート外URL。"
                 elif "Unable to download webpage" in str(e): errmsg = f"❌ URLアクセス失敗。"
                 elif "Video unavailable" in str(e): errmsg = f"❌ 動画利用不可。"
                 else: errmsg = f"❌ 情報取得失敗: `{e}`"
                 await initial_message.edit(content=errmsg)
             except Exception as e_inner: logger.exception(f"Guild {self.guild_id}: Error handling DownloadError: {e_inner}")
             return 0
        except Exception as e:
             self._logger.exception(f"Guild {self.guild_id}: Unexpected error adding to queue: {e}")
             try:
                 await initial_message.edit(content=f"予期せぬエラー発生: `{type(e).__name__}`。")
             except Exception as e_inner: logger.exception(f"Guild {self.guild_id}: Error handling unexpected error: {e_inner}")
             return 0

        # --- 再生開始トリガー ---
        if added_count > 0 and self.voice_client and self.voice_client.is_connected():
             # プレーヤーがアイドル状態の場合のみ再生を開始/再開
             if not self.voice_client.is_playing() and not self.voice_client.is_paused():
                 self._logger.info(f"Guild {self.guild_id}: Player idle, triggering next song.")
                 # プレーヤータスクがなければ開始、あればイベントをセット
                 if self.audio_player_task is None or self.audio_player_task.done():
                     self.start_player_task()
                 else:
                     self.play_next_song.set() # audio_playerループを起こす
             else:
                 self._logger.debug(f"Guild {self.guild_id}: Player is active, new song added to queue.")

        return added_count

    @staticmethod
    def format_duration(seconds: float | int | None) -> str:
        if seconds is None: return "不明"
        try:
            seconds = int(seconds)
            minutes, seconds = divmod(seconds, 60)
            hours, minutes = divmod(minutes, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
        except (ValueError, TypeError): return "不明"


# --- BOT本体 ---
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.members = True # fetch_member を使うために追加推奨 (Privileged Gateway Intent)

bot = discord.Bot(intents=intents)

guild_states: dict[int, GuildMusicState] = {}

def get_guild_state(guild_id: int) -> GuildMusicState:
    if guild_id not in guild_states:
        logger.info(f"Creating new GuildMusicState for Guild {guild_id}")
        guild_states[guild_id] = GuildMusicState(asyncio.get_event_loop(), guild_id)
    return guild_states[guild_id]

def remove_guild_state(guild_id: int):
    if guild_id in guild_states:
        logger.info(f"Removing GuildMusicState for Guild {guild_id}")
        state = guild_states.pop(guild_id, None)
        if state:
            # タスクのキャンセルを試みる
            if state.audio_player_task and not state.audio_player_task.done():
                logger.info(f"Guild {guild_id}: Cancelling audio player task during state removal.")
                state.audio_player_task.cancel()
            # VC切断は非同期で行う
            if state.voice_client and state.voice_client.is_connected():
                 logger.info(f"Guild {guild_id}: Disconnecting VC during state removal.")
                 bot.loop.create_task(state.voice_client.disconnect(force=True)) # loop.create_taskで非同期実行
                 state.voice_client = None # 参照を切る
        logger.info(f"Guild {guild_id}: GuildMusicState removed.")


@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    logger.info(f'Py-cord version: {discord.__version__}')
    logger.info('Bot is ready and online.')
    logger.info('------')
    # 起動時に古い状態が残らないようにクリア
    guild_states.clear()
    logger.info("Cleared existing guild states on ready.")

# --- スラッシュコマンド定義 ---
@bot.slash_command(name="play", description="YouTubeの動画やプレイリストを再生します (URL or 検索ワード)")
async def play(ctx: discord.ApplicationContext, query: str):
    logger.info(f"Guild {ctx.guild_id}: /play invoked by {ctx.author} with query: '{query}'")
    if not ctx.author.voice:
        await ctx.respond("VCに参加してください。", ephemeral=True)
        return
    if not ctx.guild:
        await ctx.respond("サーバー内でのみ使用可能です。", ephemeral=True)
        return # DMなどでは動作しないように

    guild_state = get_guild_state(ctx.guild_id)
    guild_state.update_last_channel(ctx.channel_id)
    voice_channel = ctx.author.voice.channel

    await ctx.defer() # 長時間かかる可能性があるのでまずdefer

    try:
        if guild_state.voice_client is None or not guild_state.voice_client.is_connected():
            logger.info(f"Guild {ctx.guild_id}: Connecting to VC: {voice_channel.name}")
            guild_state.voice_client = await voice_channel.connect(timeout=15.0)
            logger.info(f"Guild {ctx.guild_id}: Connected.")
        elif guild_state.voice_client.channel != voice_channel:
             logger.info(f"Guild {ctx.guild_id}: Moving to VC: {voice_channel.name}")
             # 移動前に再生を停止する必要がある場合がある
             if guild_state.voice_client.is_playing() or guild_state.voice_client.is_paused():
                 guild_state.voice_client.stop()
             await guild_state.voice_client.move_to(voice_channel)
             logger.info(f"Guild {ctx.guild_id}: Moved.")
             # followupで応答 (defer済のため)
             await ctx.followup.send(f"{voice_channel.name} に移動。", ephemeral=True, delete_after=10)
    except asyncio.TimeoutError:
         logger.error(f"Guild {ctx.guild_id}: Timeout connecting/moving.")
         await ctx.followup.send(f"接続/移動タイムアウト。", ephemeral=True)
         # 接続失敗時は状態を削除
         if not guild_state.voice_client or not guild_state.voice_client.is_connected():
             remove_guild_state(ctx.guild_id)
         return
    except discord.errors.ClientException as e:
         logger.error(f"Guild {ctx.guild_id}: ClientException during connect/move: {e}")
         # すでに接続済みだがチャンネルが違う場合など
         if "Already connected" in str(e) and guild_state.voice_client and guild_state.voice_client.channel != voice_channel:
              logger.warning(f"Guild {ctx.guild_id}: Already connected mismatch? Force disconnect and retry.")
              await guild_state.voice_client.disconnect(force=True)
              guild_state.voice_client = None # voice_clientをリセット
              try: # 再接続を試みる
                 guild_state.voice_client = await voice_channel.connect(timeout=15.0)
                 logger.info(f"Guild {ctx.guild_id}: Reconnected after mismatch.")
              except Exception as recon_e:
                 logger.error(f"Guild {ctx.guild_id}: Failed to reconnect after mismatch: {recon_e}")
                 await ctx.followup.send("接続状態リセット失敗。再試行してください。", ephemeral=True)
                 remove_guild_state(ctx.guild_id)
                 return
         elif "Already connecting" in str(e):
             await ctx.followup.send("接続処理中です。少し待ってから再試行してください。", ephemeral=True)
             return
         else:
             await ctx.followup.send(f"接続エラー: {e}", ephemeral=True)
             # 不明な ClientException の場合も状態をクリーンアップ
             remove_guild_state(ctx.guild_id)
             return
    except Exception as e:
        logger.exception(f"Guild {ctx.guild_id}: Failed connect/move: {e}")
        await ctx.followup.send(f"接続/移動失敗: {e}", ephemeral=True)
        remove_guild_state(ctx.guild_id) # 失敗したら状態削除
        return

    # キュー追加処理 (defer済なので ctx.followup を内部で使用)
    await guild_state.add_to_queue(query, ctx.author, ctx)

@bot.slash_command(name="stop", description="再生を停止し、BOTがVCから切断します")
async def stop(ctx: discord.ApplicationContext):
    logger.info(f"Guild {ctx.guild_id}: /stop invoked by {ctx.author}")
    guild_state = guild_states.get(ctx.guild_id)
    if guild_state and guild_state.voice_client and guild_state.voice_client.is_connected():
        guild_state.update_last_channel(ctx.channel_id)
        logger.info(f"Guild {ctx.guild_id}: Stopping playback and disconnecting.")
        # キューと現在の曲情報をクリア
        guild_state.queue.clear()
        guild_state.current_song = None
        guild_state.playback_start_time = None
        # オーディオプレーヤータスクをキャンセル
        if guild_state.audio_player_task and not guild_state.audio_player_task.done():
            guild_state.audio_player_task.cancel()
            logger.debug(f"Guild {ctx.guild_id}: Cancelled audio player task.")
        # VCの再生を停止し、切断
        guild_state.voice_client.stop()
        await guild_state.voice_client.disconnect(force=True)
        # 状態を削除
        remove_guild_state(ctx.guild_id)
        await ctx.respond("⏹️ 再生停止＆切断。")
    else:
        await ctx.respond("BOT未接続か、既に対象の状態が存在しません。", ephemeral=True)
        # 念のため、もし状態だけ残っていたら削除
        if ctx.guild_id in guild_states:
            remove_guild_state(ctx.guild_id)

@bot.slash_command(name="skip", description="現在の曲をスキップします")
async def skip(ctx: discord.ApplicationContext):
    logger.info(f"Guild {ctx.guild_id}: /skip invoked by {ctx.author}")
    if not ctx.guild: await ctx.respond("サーバー内でのみ使用可能です。", ephemeral=True); return
    guild_state = get_guild_state(ctx.guild_id) # state がなければ作成
    guild_state.update_last_channel(ctx.channel_id)

    if guild_state.voice_client and guild_state.voice_client.is_connected():
        if guild_state.voice_client.is_playing() or guild_state.current_song: # 再生中か、再生準備完了状態
            logger.info(f"Guild {ctx.guild_id}: Skipping current song.")
            guild_state.voice_client.stop() # after コールバックが呼ばれ、play_next_songがセットされる
            await ctx.respond("⏭️ スキップ。")
        elif guild_state.queue: # プレーヤーはアイドルだがキューに曲がある場合
             logger.info(f"Guild {ctx.guild_id}: Player idle, but queue has songs. Forcing next.")
             # audio_player が wait 状態の場合、イベントをセットして起こす
             guild_state.play_next_song.set()
             # audio_playerタスクが存在しないか終了している場合は開始する
             guild_state.start_player_task()
             await ctx.respond("⏭️ 次の曲へ...")
        else: # 再生中でもなくキューも空
            await ctx.respond("スキップ対象の曲がありません。", ephemeral=True)
    else: # VC未接続
        await ctx.respond("BOTがボイスチャンネルに接続していません。", ephemeral=True)

@bot.slash_command(name="pause", description="再生を一時停止します")
async def pause(ctx: discord.ApplicationContext):
    logger.info(f"Guild {ctx.guild_id}: /pause invoked by {ctx.author}")
    if not ctx.guild: await ctx.respond("サーバー内でのみ使用可能です。", ephemeral=True); return
    guild_state = get_guild_state(ctx.guild_id)
    guild_state.update_last_channel(ctx.channel_id)

    if guild_state.voice_client and guild_state.voice_client.is_playing():
        guild_state.voice_client.pause()
        await ctx.respond("⏸️ 一時停止。")
    elif guild_state.voice_client and guild_state.voice_client.is_paused():
        await ctx.respond("既に一時停止中です。", ephemeral=True)
    else:
        await ctx.respond("現在再生中ではありません。", ephemeral=True)

@bot.slash_command(name="resume", description="再生を再開します")
async def resume(ctx: discord.ApplicationContext):
    logger.info(f"Guild {ctx.guild_id}: /resume invoked by {ctx.author}")
    if not ctx.guild: await ctx.respond("サーバー内でのみ使用可能です.", ephemeral=True); return
    guild_state = get_guild_state(ctx.guild_id)
    guild_state.update_last_channel(ctx.channel_id)

    if guild_state.voice_client and guild_state.voice_client.is_paused():
        guild_state.voice_client.resume()
        await ctx.respond("▶️ 再開。")
    elif guild_state.voice_client and guild_state.voice_client.is_playing():
        await ctx.respond("既に再生中です。", ephemeral=True)
    else:
        await ctx.respond("一時停止していません。", ephemeral=True)

@bot.slash_command(name="queue", description="現在の再生キューを表示します")
async def queue_cmd(ctx: discord.ApplicationContext):
    logger.info(f"Guild {ctx.guild_id}: /queue invoked by {ctx.author}")
    if not ctx.guild: await ctx.respond("サーバー内でのみ使用可能です.", ephemeral=True); return
    guild_state = get_guild_state(ctx.guild_id)
    guild_state.update_last_channel(ctx.channel_id)

    queue_list = list(guild_state.queue) # dequeをリストに変換

    if not guild_state.current_song and not queue_list:
        await ctx.respond("キューは空です。", ephemeral=True)
        return

    embed = discord.Embed(title="再生キュー", color=discord.Color.blue())
    footer_text = f"Req by {ctx.author.display_name}"
    if ctx.author.display_avatar:
        embed.set_footer(text=footer_text, icon_url=ctx.author.display_avatar.url)
    else:
        embed.set_footer(text=footer_text)

    # 現在再生中の曲情報を表示
    if guild_state.current_song:
         elapsed = time.time() - guild_state.playback_start_time if guild_state.playback_start_time else None
         duration = guild_state.current_song.duration
         progress = f"{guild_state.format_duration(elapsed)}/{guild_state.format_duration(duration)}" if elapsed and duration else guild_state.format_duration(duration)
         # Requester情報を取得 (Memberオブジェクト or 不明)
         requester_display = '不明'
         if guild_state.current_song.requester:
             requester_display = guild_state.current_song.requester.mention
         elif isinstance(guild_state.current_song.requester, int): # IDだけの場合（エラーケースだが念のため）
             requester_display = f'ID: {guild_state.current_song.requester}'

         value = f"[{guild_state.current_song.title}]({guild_state.current_song.url})\nReq: {requester_display} | Len: {progress}"
         if len(value) > 1024: value = value[:1021] + "..." # Embed Field Value Limit
         embed.add_field(name="🎵 現在再生中", value=value, inline=False)

    # キューの内容を表示
    if queue_list:
        queue_text = ""
        max_queue_display = 10
        total_songs = len(queue_list)
        # キュー内の曲の合計時間を計算
        total_duration_seconds = sum(s.get('duration', 0) for s in queue_list if s.get('duration') is not None and isinstance(s['duration'], (int, float)))

        # キューの先頭から表示
        for i, song_info in enumerate(queue_list[:max_queue_display]):
            duration_str = guild_state.format_duration(song_info.get('duration'))
            # キュー内のリクエスタIDからメンションを作成 (fetchはしない)
            req_mention = f"<@{song_info['requester']}>" if song_info.get('requester') else '不明'

            entry_text = f"{i+1}. [{song_info['title']}]({song_info['webpage_url']}) ({duration_str}) Req: {req_mention}\n"
            # Embed Field Value Limit (1024) を超えないようにチェック
            if len(queue_text) + len(entry_text) > 1024:
                remaining_count = total_songs - i
                queue_text += f"\n...他{remaining_count}曲"
                break
            queue_text += entry_text
        else: # ループが break せずに終わった場合 (表示上限以下)
             if total_songs > max_queue_display:
                 queue_text += f"\n...他{total_songs - max_queue_display}曲"

        total_duration_str = guild_state.format_duration(total_duration_seconds) if total_duration_seconds > 0 else "不明"
        embed.add_field(name=f"🗒️ 次の曲 ({total_songs} 曲, 合計: {total_duration_str})", value=queue_text if queue_text else "キューは空です。", inline=False)

    elif guild_state.current_song: # 再生中だがキューは空の場合
        embed.add_field(name="🗒️ 次の曲", value="キューは空です。", inline=False)

    await ctx.respond(embed=embed)

@bot.slash_command(name="leave", description="BOTがボイスチャンネルから切断します (キューは保持)")
async def leave(ctx: discord.ApplicationContext):
    logger.info(f"Guild {ctx.guild_id}: /leave invoked by {ctx.author}")
    if not ctx.guild: await ctx.respond("サーバー内でのみ使用可能です.", ephemeral=True); return
    guild_state = guild_states.get(ctx.guild_id)

    if not guild_state: # stateが存在しない場合
         await ctx.respond("BOTはどのボイスチャンネルにも接続していません。", ephemeral=True)
         return

    guild_state.update_last_channel(ctx.channel_id)
    if guild_state.voice_client and guild_state.voice_client.is_connected():
        logger.info(f"Guild {ctx.guild_id}: Disconnecting VC (leave command).")
        # 再生中の場合は停止
        if guild_state.voice_client.is_playing() or guild_state.voice_client.is_paused():
             guild_state.voice_client.stop()
             # プレーヤータスクもキャンセルする
             if guild_state.audio_player_task and not guild_state.audio_player_task.done():
                 guild_state.audio_player_task.cancel()
                 logger.debug(f"Guild {ctx.guild_id}: Cancelled audio player task on leave.")
        # 現在再生中の情報をクリア (キューは保持)
        guild_state.current_song = None
        guild_state.playback_start_time = None
        # VCから切断
        await guild_state.voice_client.disconnect(force=True)
        guild_state.voice_client = None # voice_clientオブジェクトへの参照をクリア
        logger.info(f"Guild {ctx.guild_id}: Disconnected from VC. Guild state (queue) kept.")
        await ctx.respond("👋 ボイスチャンネルから切断しました (キューは保持されています)。")
    else: # stateはあるがVCに接続していない場合
        await ctx.respond("BOTはどのボイスチャンネルにも接続していません。", ephemeral=True)
        # voice_client が None になっているか確認し、なっていなければ None にする
        if guild_state.voice_client is not None:
            guild_state.voice_client = None
            logger.warning(f"Guild {ctx.guild_id}: Found non-None voice_client despite not being connected. Resetting.")

@bot.slash_command(name="nowplaying", description="現在再生中の曲情報を表示します")
async def nowplaying(ctx: discord.ApplicationContext):
    logger.info(f"Guild {ctx.guild_id}: /nowplaying invoked by {ctx.author}")
    await now_playing_impl(ctx)

@bot.slash_command(name="np", description="現在再生中の曲情報を表示します (nowplayingのエイリアス)")
async def np(ctx: discord.ApplicationContext):
    logger.info(f"Guild {ctx.guild_id}: /np invoked by {ctx.author}")
    await now_playing_impl(ctx)

# /np と /nowplaying の共通処理
async def now_playing_impl(ctx: discord.ApplicationContext):
    if not ctx.guild: await ctx.respond("サーバー内でのみ使用可能です.", ephemeral=True); return
    guild_state = get_guild_state(ctx.guild_id)
    guild_state.update_last_channel(ctx.channel_id)

    if guild_state.current_song and guild_state.voice_client and (guild_state.voice_client.is_playing() or guild_state.voice_client.is_paused()):
        song = guild_state.current_song
        elapsed = time.time() - guild_state.playback_start_time if guild_state.playback_start_time else None
        duration = song.duration
        progress_bar = ""

        # プログレスバー生成
        if elapsed and duration and duration > 0:
            percentage = min(elapsed / duration, 1.0)
            filled_blocks = int(percentage * 20)
            empty_blocks = 20 - filled_blocks
            # プログレスバー用の文字 (例: ▬ と ―)
            progress_bar = f"[`{guild_state.format_duration(elapsed)}`] {'▬' * filled_blocks}{'―' * empty_blocks} [`{guild_state.format_duration(duration)}`]"
        else: # 時間情報がない場合
            progress_bar = f"長さ: {guild_state.format_duration(duration)}"

        # リクエスタ情報
        requester_display = '不明'
        if song.requester:
            requester_display = song.requester.mention
        elif isinstance(song.requester, int): # IDのみの場合 (フォールバック)
            requester_display = f'<@{song.requester}>' # メンション形式で表示試行

        embed = discord.Embed(
            title="🎵 現在再生中",
            description=f"**[{song.title}]({song.url})**\n{progress_bar}",
            color=discord.Color.green()
        )
        embed.add_field(name="リクエスト", value=requester_display, inline=True)
        # 必要ならサムネイルなどを追加
        # if song.thumbnail_url: embed.set_thumbnail(url=song.thumbnail_url)

        await ctx.respond(embed=embed)
    else:
        await ctx.respond("現在再生中の曲はありません。", ephemeral=True)


@bot.slash_command(name="remove", description="キューから指定した番号の曲を削除します")
async def remove(ctx: discord.ApplicationContext, number: discord.Option(int, "削除するキューの番号", min_value=1)):
    logger.info(f"Guild {ctx.guild_id}: /remove {number} invoked by {ctx.author}")
    if not ctx.guild: await ctx.respond("サーバー内でのみ使用可能です.", ephemeral=True); return
    guild_state = get_guild_state(ctx.guild_id)
    guild_state.update_last_channel(ctx.channel_id)

    queue_len = len(guild_state.queue)
    if queue_len == 0:
        await ctx.respond("キューは空です。", ephemeral=True)
        return
    # number は 1-based index なので、内部では 0-based に変換
    index_to_remove = number - 1
    if not (0 <= index_to_remove < queue_len):
        await ctx.respond(f"無効な番号です。1から{queue_len}の間で指定してください。", ephemeral=True)
        return

    try:
        # deque は直接インデックスで pop できないのでリストに変換して操作
        queue_list = list(guild_state.queue)
        removed_song = queue_list.pop(index_to_remove) # 指定インデックスの要素を削除＆取得
        guild_state.queue = deque(queue_list) # dequeに戻す

        logger.info(f"Guild {ctx.guild_id}: Removed '{removed_song['title']}' from queue at position {number}.")
        await ctx.respond(f"✅ キューの{number}番目の曲「{removed_song['title']}」を削除しました。")
    except IndexError:
        # これは上記の範囲チェックで防げるはずだが念のため
        logger.error(f"Guild {ctx.guild_id}: IndexError during remove despite check. Index: {index_to_remove}, QueueLen: {queue_len}")
        await ctx.respond(f"番号{number}の曲が見つかりませんでした（内部エラー）。", ephemeral=True)
    except Exception as e:
        logger.exception(f"Guild {ctx.guild_id}: Error removing song from queue: {e}")
        await ctx.respond(f"キューからの削除中にエラーが発生しました: {e}", ephemeral=True)

@bot.slash_command(name="clearqueue", description="再生中の曲を除き、キューを空にします")
async def clearqueue(ctx: discord.ApplicationContext):
    logger.info(f"Guild {ctx.guild_id}: /clearqueue invoked by {ctx.author}")
    if not ctx.guild: await ctx.respond("サーバー内でのみ使用可能です.", ephemeral=True); return
    guild_state = get_guild_state(ctx.guild_id)
    guild_state.update_last_channel(ctx.channel_id)

    queue_len = len(guild_state.queue)
    if queue_len == 0:
        await ctx.respond("キューは既に空です。", ephemeral=True)
        return

    guild_state.queue.clear()
    logger.info(f"Guild {ctx.guild_id}: Queue cleared ({queue_len} songs removed).")
    await ctx.respond(f"🧹 キューを空にしました ({queue_len} 曲削除)。")

@bot.slash_command(name="help", description="利用可能なコマンドの一覧を表示します")
async def help_command(ctx: discord.ApplicationContext):
    logger.info(f"Guild {ctx.guild_id}: /help invoked by {ctx.author}")
    embed = discord.Embed(title="🎶 再生BOT ヘルプ", description="スラッシュコマンド一覧:", color=discord.Color.purple())
    if bot.user and bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)
    bot_name = bot.user.name if bot.user else "再生BOT"
    embed.set_footer(text=f"{bot_name}")

    # コマンド説明
    embed.add_field(name="`/play <URL または 検索ワード>`", value="指定された曲やプレイリストを再生/キューに追加します。", inline=False)
    embed.add_field(name="`/stop`", value="再生を停止し、キューを空にしてVCから切断します。", inline=False)
    embed.add_field(name="`/skip`", value="現在再生中の曲をスキップします。", inline=False)
    embed.add_field(name="`/pause`", value="再生を一時停止します。", inline=False)
    embed.add_field(name="`/resume`", value="一時停止中の再生を再開します。", inline=False)
    embed.add_field(name="`/queue`", value="現在の再生キューを表示します。", inline=False)
    embed.add_field(name="`/nowplaying` (または `/np`)", value="現在再生中の曲の詳細情報を表示します。", inline=False)
    embed.add_field(name="`/remove <番号>`", value="キューから指定された番号の曲を削除します。", inline=False)
    embed.add_field(name="`/clearqueue`", value="再生中の曲を除き、キューをすべて削除します。", inline=False)
    embed.add_field(name="`/leave`", value="VCから切断します（キューは保持されます）。", inline=False)
    embed.add_field(name="`/help`", value="このヘルプメッセージを表示します。", inline=False)

    await ctx.respond(embed=embed, ephemeral=False) # ヘルプは通常表示

# --- エラーハンドリング ---
@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error: discord.DiscordException):
    # defer() 後にエラーが発生した場合 followup で応答、そうでなければ respond
    responder = ctx.followup.send if ctx.interaction.response.is_done() else ctx.respond
    ephemeral = True # エラーメッセージは基本的に ephemeral で送信

    # エラーの種類によってログレベルやメッセージを調整
    if isinstance(error, discord.errors.CheckFailure):
        logger.warning(f"Cmd CheckFail '{ctx.command.name}' by {ctx.author} G:{ctx.guild_id}: {error}")
        await responder("コマンド実行に必要な権限がありません。", ephemeral=ephemeral)
    elif isinstance(error, discord.errors.NotFound) and "Interaction" in str(error):
         # インタラクションがタイムアウトしたか、見つからない場合
         logger.warning(f"Guild {ctx.guild_id}: Interaction timed out or not found for command '{ctx.command.name}'.")
         # response.is_done() が False の場合でも NotFound が発生しうる (e.g., defer 前にタイムアウト)
         # 応答しようとするとさらにエラーになる可能性があるので、ここでは応答しない方が安全かもしれない
         # try: await responder("インタラクションの応答に失敗しました。", ephemeral=ephemeral)
         # except discord.errors.NotFound: pass # 応答できない場合は無視
    elif isinstance(error, discord.ApplicationCommandInvokeError):
         # コマンド実行中のエラー
         original = error.original
         logger.error(f"Error invoking command '{ctx.command.name}' G:{ctx.guild_id}: {type(original).__name__}: {original}", exc_info=original)
         errmsg = f"コマンド実行中にエラーが発生しました: `{type(original).__name__}`"
         # 特定のエラーに対するユーザーフレンドリーなメッセージ
         if isinstance(original, yt_dlp.utils.DownloadError): errmsg = "動画/プレイリスト情報の取得またはダウンロードに失敗しました。"
         elif isinstance(original, asyncio.TimeoutError): errmsg = "処理がタイムアウトしました。時間をおいて再試行してください。"
         elif isinstance(original, discord.errors.ClientException) and "Not connected" in str(original): errmsg = "ボイスチャンネルに接続していません。"
         elif isinstance(original, discord.errors.ClientException) and "Already connected" in str(original): errmsg = "既に他のボイスチャンネルに接続中です。"
         elif isinstance(original, IndexError): errmsg = "指定されたキューの番号が無効です。"
         # 他にもハンドリングしたいエラーがあれば追加
         await responder(errmsg, ephemeral=ephemeral)
    elif isinstance(error, discord.errors.ApplicationCommandError):
        # ApplicationCommand の引数エラーなど
        logger.warning(f"AppCmd Error '{ctx.command.name}' G:{ctx.guild_id}: {error}")
        if isinstance(error.original, ValueError): await responder(f"不正な引数: {error.original}", ephemeral=ephemeral)
        else: await responder(f"コマンドエラー: {error}", ephemeral=ephemeral)
    else:
        # その他の予期しない Discord API エラーなど
        logger.error(f"Unhandled Error in command '{ctx.command.name}' G:{ctx.guild_id}", exc_info=error)
        await responder(f"予期せぬ Discord API エラーが発生しました: `{error}`", ephemeral=ephemeral)

# --- 自動切断機能 ---
async def check_activity():
    await bot.wait_until_ready()
    logger.info("Starting activity check loop...")
    while not bot.is_closed():
        await asyncio.sleep(60) # 60秒ごとにチェック
        try:
            inactive_guilds = []
            # guild_states のコピーに対してループ (ループ中に削除される可能性があるため)
            current_guild_states = list(guild_states.items())

            for guild_id, state in current_guild_states:
                 # stateやvoice_clientが存在し、VCに接続しているか確認
                 if not state or not state.voice_client or not state.voice_client.is_connected():
                     continue

                 vc = state.voice_client.channel
                 # VCにBot以外のメンバーがいるか確認
                 human_members = [m for m in vc.members if not m.bot]

                 if not human_members:
                     # 人間が誰もいなければ非アクティブとみなす
                     logger.info(f"Guild {guild_id}: No human members found in VC '{vc.name}'. Marking for inactivity disconnect.")
                     inactive_guilds.append(guild_id)

            # 非アクティブなギルドの処理
            for guild_id in inactive_guilds:
                 if guild_id in guild_states: # 再度存在確認
                      state_to_remove = guild_states[guild_id]
                      logger.info(f"Guild {guild_id}: Disconnecting due to inactivity.")
                      # 通知チャンネルがあれば通知
                      await state_to_remove.notify_channel("誰もいなくなったためVCから切断しました。", delete_after=30)
                      # VCから切断し、状態を削除
                      if state_to_remove.voice_client and state_to_remove.voice_client.is_connected():
                           # disconnect は create_task 不要 (stop 内で await しているため)
                           # await state_to_remove.voice_client.disconnect(force=True)
                           # stop コマンドと同様のクリーンアップを実行
                           state_to_remove.queue.clear()
                           state_to_remove.current_song = None
                           state_to_remove.playback_start_time = None
                           if state_to_remove.audio_player_task and not state_to_remove.audio_player_task.done():
                               state_to_remove.audio_player_task.cancel()
                           state_to_remove.voice_client.stop()
                           await state_to_remove.voice_client.disconnect(force=True)
                      remove_guild_state(guild_id) # 状態を削除
                 else:
                     logger.warning(f"Guild {guild_id}: State already removed before inactivity disconnect.")

        except Exception as e:
            # ループ自体が止まらないように例外をキャッチ
            logger.exception(f"Error during activity check loop: {e}")
            await asyncio.sleep(60) # エラー発生時も少し待つ

# --- Bot起動 ---
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("エラー: 環境変数 'DISCORD_BOT_TOKEN' が設定されていません。")
        logger.critical("エラー: 環境変数 'DISCORD_BOT_TOKEN' が設定されていません。")
    else:
        try:
            logger.info("Starting bot...")
            # バックグラウンドタスクとしてアクティビティチェックを開始
            bot.loop.create_task(check_activity())
            # Botを実行
            bot.run(DISCORD_BOT_TOKEN)
        except discord.errors.LoginFailure:
            logger.critical("!!! LOGIN FAILURE: Invalid Discord Bot Token provided. Check your token. !!!")
        except discord.errors.PrivilegedIntentsRequired:
            logger.critical("!!! MISSING INTENTS: Enable 'Server Members Intent' in the Discord Developer Portal for your bot. !!!")
        except Exception as e:
            logger.critical(f"!!! Bot runtime error: {e}", exc_info=True)

# --- END OF FILE bot.py (Loop機能削除版, np重複修正版) ---
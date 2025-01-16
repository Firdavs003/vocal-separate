# --------------------------------------------------------------------------
# Janis Rubins step 1:
# Below is an improved version of the Flask + Spleeter code with very deep
# logging and explanatory comments (in "Janis Rubins" style). The goal is
# to preserve the original logic while translating all Chinese text into
# English, enhancing code readability, maintainability, and especially
# logging – so the user knows exactly what is happening at each step.
# This code should run smoothly on Linux, macOS, and Windows, assuming
# all dependencies (Python, FFmpeg, Spleeter, etc.) are properly installed.
# --------------------------------------------------------------------------

import logging
import threading
import os
import subprocess
import sys

# Janis Rubins step 2:
# Here we import Flask and relevant modules for creating a web server,
# handling file uploads, returning JSON, and so on.
from flask import Flask, request, render_template, jsonify, send_from_directory

# Janis Rubins step 3:
# We import gevent WSGIServer for production-level serving, and use a
# custom request handler to override some default behaviors.
from gevent.pywsgi import WSGIServer, WSGIHandler

# Janis Rubins step 4:
# RotatingFileHandler for logging to file with a maximum size and backups.
from logging.handlers import RotatingFileHandler

# Janis Rubins step 5:
# Importing local modules from 'vocal' directory. 'cfg' is config, 'tool'
# has helper functions. 'vocal' might have version info, etc.
import vocal
from vocal import cfg, tool
from vocal.cfg import ROOT_DIR

# Janis Rubins step 6:
# Spleeter is the library to separate audio into stems.
from spleeter.separator import Separator

# Janis Rubins step 7:
# Create a custom request handler to disable default request logging,
# since we'll use our own extensive logging approach.
class CustomRequestHandler(WSGIHandler):
    def log_request(self):
        # We override this method to avoid noisy default logs.
        pass

# Janis Rubins step 8:
# Set up a separate logger for the Werkzeug server logs, so they don’t
# conflict with our custom logs. Set the level to WARNING to reduce
# verbosity from Werkzeug.
log = logging.getLogger('werkzeug')
log.handlers[:] = []
log.setLevel(logging.WARNING)

# Janis Rubins step 9:
# Initialize the Flask application. We define static_folder and
# template_folder as sub-directories of ROOT_DIR for a consistent structure.
app = Flask(
    __name__,
    static_folder=os.path.join(ROOT_DIR, 'static'),
    static_url_path='/static',
    template_folder=os.path.join(ROOT_DIR, 'templates')
)

# Janis Rubins step 10:
# We configure the "root" logger to ensure it won't print too much, as
# we will manually handle deep logging ourselves.
root_log = logging.getLogger()
root_log.handlers = []
root_log.setLevel(logging.WARNING)

# Janis Rubins step 11:
# We set the Flask app’s logger level to WARNING. Later, we’ll attach
# RotatingFileHandler to store logs in a file if needed.
app.logger.setLevel(logging.WARNING)

# Janis Rubins step 12:
# Configure RotatingFileHandler. We store logs in 'vocal.log' with a max
# size of ~1 MB and keep 5 backups.
file_handler = RotatingFileHandler(
    os.path.join(ROOT_DIR, 'vocal.log'),
    maxBytes=1024 * 1024,
    backupCount=5
)

# Janis Rubins step 13:
# Format for the logs. This includes timestamp, module, log level,
# and the actual message.
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Janis Rubins step 14:
# Set up the level and the formatter for our file handler, then add it
# to the Flask app’s logger.
file_handler.setLevel(logging.WARNING)
file_handler.setFormatter(formatter)
app.logger.addHandler(file_handler)

# Janis Rubins step 15:
# Add a second logger for console output with a deep logging approach.
# This ensures we see detailed logs in the terminal as well.
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter(
    '[%(asctime)s] [%(levelname)s] %(message)s'
)
console_handler.setFormatter(console_formatter)
app.logger.addHandler(console_handler)


# --------------------------------------------------------------------------
# STATIC FILES ROUTE
# --------------------------------------------------------------------------
@app.route('/static/<path:filename>')
def static_files(filename):
    """
    Janis Rubins step 16:
    This route serves static files from the specified static folder.
    We add a debug log so we can see whenever a static file is requested.
    """
    app.logger.debug(f'[static_files] Request for static file: {filename}')
    return send_from_directory(app.config['STATIC_FOLDER'], filename)


# --------------------------------------------------------------------------
# INDEX ROUTE
# --------------------------------------------------------------------------
@app.route('/')
def index():
    """
    Janis Rubins step 17:
    This is the main route returning the index.html template. We inject
    variables such as version, CUDA, language, etc.
    """
    app.logger.debug('[index] Rendering index.html with context variables')
    return render_template(
        "index.html",
        version=vocal.version_str,
        cuda=cfg.cuda,
        language=cfg.LANG,
        root_dir=ROOT_DIR.replace('\\', '/')
    )


# --------------------------------------------------------------------------
# UPLOAD ROUTE
# --------------------------------------------------------------------------
@app.route('/upload', methods=['POST'])
def upload():
    """
    Janis Rubins step 18:
    This route handles file uploads. We take the uploaded file from the
    request, determine if it’s audio or video, and convert to WAV if needed
    using FFmpeg.
    """
    try:
        app.logger.debug('[upload] Starting file upload process...')
        audio_file = request.files['audio']
        noextname, ext = os.path.splitext(audio_file.filename)
        ext = ext.lower()
        wav_file = os.path.join(cfg.TMP_DIR, f'{noextname}.wav')

        app.logger.debug(f'[upload] Uploaded file name: {audio_file.filename}, '
                         f'Extension: {ext}, Target WAV path: {wav_file}')

        # If the WAV already exists and has non-zero size, skip reprocessing
        if os.path.exists(wav_file) and os.path.getsize(wav_file) > 0:
            app.logger.debug('[upload] WAV file already exists, skipping reprocessing')
            return jsonify({
                'code': 0,
                'msg': cfg.transobj['lang1'],  # e.g. "File uploaded successfully."
                "data": os.path.basename(wav_file)
            })

        msg = ""
        if ext in ['.mp4', '.mov', '.avi', '.mkv', '.mpeg', '.mp3', '.flac']:
            # Save the uploaded file to a temporary location
            video_file = os.path.join(cfg.TMP_DIR, f'{noextname}{ext}')
            audio_file.save(video_file)
            app.logger.debug(f'[upload] Saved file to: {video_file}')

            # Build FFmpeg params
            params = [
                "-i",
                video_file,
            ]
            # If not an audio-only file (mp3/flac), remove video track
            if ext not in ['.mp3', '.flac']:
                params.append('-vn')
            params.append(wav_file)

            app.logger.debug(f'[upload] Running FFmpeg with params: {params}')
            rs = tool.runffmpeg(params)
            if rs != 'ok':
                app.logger.error(f'[upload] FFmpeg error: {rs}')
                return jsonify({"code": 1, "msg": rs})
            # e.g. "File uploaded successfully, Video file converted."
            msg = "," + cfg.transobj['lang9']
        elif ext == '.wav':
            # Directly save the WAV
            audio_file.save(wav_file)
            app.logger.debug('[upload] Directly saved WAV, no FFmpeg needed')
        else:
            # Unsupported file format
            err_msg = f"{cfg.transobj['lang3']} {ext}"  # e.g. "Unsupported format"
            app.logger.warning(f'[upload] Unsupported format: {err_msg}')
            return jsonify({"code": 1, "msg": err_msg})

        # Success
        success_msg = cfg.transobj['lang1'] + msg  # e.g. "File uploaded successfully"
        app.logger.debug(f'[upload] Successfully processed upload: {success_msg}')
        return jsonify({
            'code': 0,
            'msg': success_msg,
            "data": os.path.basename(wav_file)
        })
    except Exception as e:
        app.logger.error(f'[upload] Unexpected error: {e}', exc_info=True)
        return jsonify({'code': 2, 'msg': cfg.transobj['lang2']})  # e.g. "An error occurred."


# --------------------------------------------------------------------------
# PROCESS ROUTE
# --------------------------------------------------------------------------
@app.route('/process', methods=['GET', 'POST'])
def process():
    """
    Janis Rubins step 19:
    This route processes the WAV file with Spleeter, splitting it into
    different stems (vocals, accompaniment, drums, etc.).
    """
    try:
        app.logger.debug('[process] Starting process route...')
        wav_name = request.form.get("wav_name", "").strip()
        model = request.form.get("model", "").strip()
        wav_file = os.path.join(cfg.TMP_DIR, wav_name)
        noextname = wav_name[:-4] if wav_name.lower().endswith('.wav') else wav_name

        app.logger.debug(f'[process] Received wav_name: {wav_name}, model: {model}')
        app.logger.debug(f'[process] Constructed wav_file path: {wav_file}')

        # Check if the WAV file exists
        if not os.path.exists(wav_file):
            err_msg = f"{wav_file} {cfg.langlist['lang5']}"  # e.g. "File not found."
            app.logger.error(f'[process] WAV file does not exist: {err_msg}')
            return jsonify({"code": 1, "msg": err_msg})

        # Check if the model exists
        if not os.path.exists(os.path.join(cfg.MODEL_DIR, model, 'model.meta')):
            err_msg = f"{model} {cfg.transobj['lang4']}"  # e.g. "Model does not exist."
            app.logger.error(f'[process] Model does not exist: {err_msg}')
            return jsonify({"code": 1, "msg": err_msg})

        # Use ffprobe to get duration
        try:
            app.logger.debug('[process] Using ffprobe to detect WAV duration...')
            p = subprocess.run(
                [
                    'ffprobe', '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    wav_file
                ],
                capture_output=True,
                check=False
            )
            if p.returncode == 0:
                sec = float(p.stdout)
            else:
                app.logger.warning('[process] ffprobe did not return 0, setting sec=1800')
                sec = 1800.0
        except Exception as e_ffprobe:
            app.logger.warning(f'[process] ffprobe exception: {e_ffprobe}, setting sec=1800', exc_info=True)
            sec = 1800.0

        app.logger.debug(f'[process] Audio duration (sec): {sec}')

        # Initialize Spleeter Separator
        separator = Separator(f'spleeter:{model}', multiprocess=False)
        dirname = os.path.join(cfg.FILES_DIR, noextname)

        app.logger.debug(f'[process] Output directory: {dirname}')
        os.makedirs(dirname, exist_ok=True)

        # Separate audio
        app.logger.debug('[process] Starting spleeter separation...')
        separator.separate_to_file(
            wav_file,
            destination=dirname,
            filename_format="{instrument}.{codec}",
            duration=sec
        )
        app.logger.debug('[process] Spleeter separation completed.')

        # Mapping for the separated stems, now in English
        status = {
            "accompaniment": "accompaniment",
            "bass":          "bass",
            "drums":         "drums",
            "piano":         "piano",
            "vocals":        "vocals",
            "other":         "other"
        }

        data = []
        urllist = []
        for it in os.listdir(dirname):
            if it.endswith('.wav'):
                app.logger.debug(f'[process] Found separated track: {it}')
                instrument_name = it[:-4]  # e.g. "accompaniment", "vocals", etc.
                # If the user’s language is not 'en', they may have some other logic,
                # but we remove all Chinese text here and keep it in English:
                display_name = status.get(instrument_name, instrument_name)
                data.append(display_name)

                # Build the URL to the separated WAV
                track_url = f'http://{cfg.web_address}/static/files/{noextname}/{it}'
                urllist.append(track_url)

        return jsonify({
            "code": 0,
            "msg": cfg.transobj['lang6'],  # e.g. "Separation completed."
            "data": data,
            "urllist": urllist,
            "dirname": dirname
        })
    except Exception as e:
        app.logger.error(f'[process] Unexpected error: {e}', exc_info=True)
        return jsonify({"code": 1, "msg": str(e)})


# --------------------------------------------------------------------------
# API ROUTE
# --------------------------------------------------------------------------
@app.route('/api', methods=['POST'])
def api():
    """
    Janis Rubins step 20:
    Similar to '/upload' and '/process' combined: we accept a file and
    immediately process it via Spleeter, then return the resulting stems.
    """
    try:
        app.logger.debug('[api] Starting /api route...')
        audio_file = request.files['file']
        model = request.form.get("model", "").strip()

        noextname, ext = os.path.splitext(audio_file.filename)
        ext = ext.lower()
        wav_file = os.path.join(cfg.TMP_DIR, f'{noextname}.wav')

        app.logger.debug(f'[api] Received file: {audio_file.filename}, '
                         f'Model: {model}, WAV path: {wav_file}')

        # Only process if the WAV doesn't exist or is empty
        if not os.path.exists(wav_file) or os.path.getsize(wav_file) == 0:
            # If it’s a known video or audio format, convert to WAV
            if ext in ['.mp4', '.mov', '.avi', '.mkv', '.mpeg', '.mp3', '.flac']:
                video_file = os.path.join(cfg.TMP_DIR, f'{noextname}{ext}')
                audio_file.save(video_file)
                app.logger.debug(f'[api] Saved file to: {video_file}')

                params = ["-i", video_file]
                if ext not in ['.mp3', '.flac']:
                    params.append('-vn')
                params.append(wav_file)

                app.logger.debug(f'[api] Running FFmpeg: {params}')
                rs = tool.runffmpeg(params)
                if rs != 'ok':
                    app.logger.error(f'[api] FFmpeg error: {rs}')
                    return jsonify({"code": 1, "msg": rs})
            elif ext == '.wav':
                audio_file.save(wav_file)
                app.logger.debug('[api] File is WAV, saved directly')
            else:
                err_msg = f"{cfg.transobj['lang3']} {ext}"  # e.g. "Unsupported format"
                app.logger.warning(f'[api] Unsupported format: {err_msg}')
                return jsonify({"code": 1, "msg": err_msg})

        # Double-check that WAV now exists
        if not os.path.exists(wav_file):
            err_msg = f"{wav_file} {cfg.langlist['lang5']}"  # e.g. "File not found."
            app.logger.error(f'[api] WAV file does not exist after conversion: {err_msg}')
            return jsonify({"code": 1, "msg": err_msg})

        # Check if the model is valid
        if not os.path.exists(os.path.join(cfg.MODEL_DIR, model, 'model.meta')):
            err_msg = f"{model} {cfg.transobj['lang4']}"  # e.g. "Model does not exist."
            app.logger.error(f'[api] Model not found: {err_msg}')
            return jsonify({"code": 1, "msg": err_msg})

        # Attempt ffprobe to get duration
        try:
            app.logger.debug('[api] Running ffprobe to detect WAV duration...')
            p = subprocess.run(
                [
                    'ffprobe', '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    wav_file
                ],
                capture_output=True,
                check=False
            )
            if p.returncode == 0:
                sec = float(p.stdout)
            else:
                app.logger.warning('[api] ffprobe returned a non-zero exit code. Setting sec=1800.')
                sec = 1800.0
        except Exception as e_ffprobe:
            app.logger.warning(f'[api] ffprobe exception: {e_ffprobe}, setting sec=1800', exc_info=True)
            sec = 1800.0

        app.logger.debug(f'[api] Audio duration: {sec}')

        # Spleeter separation
        separator = Separator(f'spleeter:{model}', multiprocess=False)
        dirname = os.path.join(cfg.FILES_DIR, noextname)
        os.makedirs(dirname, exist_ok=True)

        app.logger.debug('[api] Starting Spleeter separation...')
        separator.separate_to_file(
            wav_file,
            destination=dirname,
            filename_format="{instrument}.{codec}",
            duration=sec
        )
        app.logger.debug('[api] Spleeter separation completed.')

        # Build the status dictionary in English:
        status = {
            "accompaniment.wav": "accompaniment audio",
            "bass.wav":          "bass audio",
            "drums.wav":         "drums audio",
            "piano.wav":         "piano audio",
            "vocals.wav":        "vocals audio",
            "other.wav":         "other audio"
        }

        urllist = []
        for it in os.listdir(dirname):
            if it.endswith('.wav'):
                track_url = f'http://{cfg.web_address}/static/files/{noextname}/{it}'
                urllist.append(track_url)
                app.logger.debug(f'[api] Found separated track: {it}, URL: {track_url}')

        return jsonify({
            "code": 0,
            "msg": cfg.transobj['lang6'],  # e.g. "Separation completed."
            "data": urllist,
            "status_text": status
        })
    except Exception as e:
        app.logger.error(f'[api] Unexpected error: {e}', exc_info=True)
        return jsonify({'code': 2, 'msg': cfg.transobj['lang2']})  # e.g. "An error occurred."


# --------------------------------------------------------------------------
# CHECK UPDATE ROUTE
# --------------------------------------------------------------------------
@app.route('/checkupdate', methods=['GET', 'POST'])
def checkupdate():
    """
    Janis Rubins step 21:
    Simple route that returns the update info from the config (if any).
    """
    app.logger.debug('[checkupdate] Checking for updates...')
    return jsonify({'code': 0, "msg": cfg.updatetips})


# --------------------------------------------------------------------------
# MAIN ENTRY POINT
# --------------------------------------------------------------------------
if __name__ == '__main__':
    # Janis Rubins step 22:
    # We wrap our server in a try/except to gracefully handle startup errors.
    http_server = None
    try:
        app.logger.debug('[main] Starting background thread for checkupdate...')
        threading.Thread(target=tool.checkupdate).start()

        try:
            app.logger.debug('[main] Parsing host and port from cfg.web_address...')
            host = cfg.web_address.split(':')
            app.logger.debug(f'[main] Creating WSGIServer at {host[0]}:{host[1]}')

            # Create gevent WSGIServer with our CustomRequestHandler
            http_server = WSGIServer(
                (host[0], int(host[1])),
                app,
                handler_class=CustomRequestHandler
            )

            # We open the web page in the default browser in a separate thread.
            app.logger.debug('[main] Opening browser with provided web address...')
            threading.Thread(target=tool.openweb, args=(cfg.web_address,)).start()

            # Start serving forever
            app.logger.info(f'[main] Starting server at http://{cfg.web_address}')
            http_server.serve_forever()
        finally:
            # If we exit, ensure http_server is stopped.
            if http_server:
                app.logger.warning('[main] Stopping HTTP server...')
                http_server.stop()
    except Exception as e:
        # Log any top-level exceptions
        if http_server:
            http_server.stop()
        app.logger.error(f'[main] Critical error during startup: {str(e)}', exc_info=True)
        print("Critical startup error:", str(e))

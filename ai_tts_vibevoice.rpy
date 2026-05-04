init -999 python:
    import sys
    renpy.log("VIBEVOICE PROBE: ai_tts_vibevoice.rpy loaded")
    renpy.log("VIBEVOICE PROBE: python = %r" % sys.version)


init 999 python:
    import os
    import re
    import json
    import hashlib

    try:
        import threading
    except Exception:
        threading = None

    try:
        from urllib import request as urllib_request
    except ImportError:
        import urllib2 as urllib_request

    try:
        text_type = unicode
    except NameError:
        text_type = str

    try:
        _vibevoice_state_base = NoRollback
    except NameError:
        _vibevoice_state_base = object

    renpy.log("VIBEVOICE TTS: init block reached")

    VIBEVOICE_ENABLED = True
    VIBEVOICE_URL = "http://localhost:8880/v1/audio/speech"
    VIBEVOICE_MODEL = "tts-1-hd"
    VIBEVOICE_RESPONSE_FORMAT = "mp3"
    VIBEVOICE_TIMEOUT = 120
    VIBEVOICE_CACHE_VERSION = "vibevoice-realtime-openai-v1"

    VIBEVOICE_CHANNEL = "vibevoice"
    VIBEVOICE_CACHE_DIR_NAME = "tts_cache_vibevoice"
    VIBEVOICE_DEFAULT_VOICE = "Emma"

    # Speaker name reading mode.
    # Options:
    # "always" = read the speaker name before every line.
    # "never" = never read speaker names.
    # "on_speaker_change" = read the name only when the speaker changes.
    VIBEVOICE_READ_SPEAKER_NAMES = "on_speaker_change"

    # False stores generated audio in Ren'Py's save/user area when possible.
    # True stores generated audio in game/tts_cache_vibevoice when possible.
    VIBEVOICE_STORE_AUDIO_IN_GAME_DIR = False

    VIBEVOICE_AVAILABLE_VOICES = (
        "alloy",
        "echo",
        "fable",
        "onyx",
        "nova",
        "shimmer",
        "Carter",
        "Davis",
        "Emma",
        "Frank",
        "Grace",
        "Mike",
        "Samuel",
    )

    VIBEVOICE_VOICE_BY_SPEAKER = {
        "Narrator": "Davis",
        "MC": "Mike",
		"Daniel": "Mike",
    }


    class VibeVoiceTTSState(_vibevoice_state_base):
        def __init__(self):
            self.worker_started = False
            self.request_id = 0
            self.active_id = 0
            self.pending = None
            self.last_speech_mode = None
            self.last_spoken_speaker = None
            self.pending_speaker = None

            if threading is not None:
                self.lock = threading.RLock()
                self.condition = threading.Condition(self.lock)
            else:
                self.lock = None
                self.condition = None


    _vibevoice_state = VibeVoiceTTSState()


    def vibevoice_to_text(value):
        if value is None:
            return u""

        try:
            return text_type(value)
        except Exception:
            try:
                return str(value)
            except Exception:
                return u""


    def vibevoice_clean_text(text):
        text = vibevoice_to_text(text)

        if not text:
            return u""

        text = re.sub(r"\{[^}]*\}", "", text)
        text = text.replace("[", "").replace("]", "")
        text = re.sub(r"\s+", " ", text)

        return text.strip()


    def vibevoice_self_voicing_mode():
        try:
            return renpy.game.preferences.self_voicing
        except Exception:
            return False


    def vibevoice_speech_mode_active():
        mode = vibevoice_self_voicing_mode()
        return mode is True or mode == True


    def vibevoice_sorted_speakers():
        speakers = []

        for speaker in VIBEVOICE_VOICE_BY_SPEAKER.keys():
            name = vibevoice_clean_text(speaker)

            if name:
                speakers.append(name)

        return sorted(speakers, key=len, reverse=True)


    def vibevoice_name_read_mode():
        mode = VIBEVOICE_READ_SPEAKER_NAMES

        if mode is True:
            return "always"

        if mode is False or mode is None:
            return "never"

        mode_text = vibevoice_clean_text(mode).lower().replace("_", " ").replace("-", " ")

        if mode_text in ("true", "yes", "always", "on"):
            return "always"

        if mode_text in ("false", "no", "never", "off"):
            return "never"

        if mode_text in (
            "on speaker change",
            "on speaker changes",
            "on speaker changed",
            "on speakerchange",
            "onspeakerchange",
            "speaker change",
            "speaker changes",
            "when speaker changes",
            "when the speaker changes",
            "when it changes",
            "when changes",
            "on change",
            "change",
            "changes",
        ):
            return "change"

        renpy.log("VIBEVOICE TTS: unknown VIBEVOICE_READ_SPEAKER_NAMES value %r, using 'on_speaker_change'" % mode)
        return "change"


    def vibevoice_known_speaker_match(clean):
        for speaker in vibevoice_sorted_speakers():
            if clean == speaker:
                return speaker, u""

            if not clean.startswith(speaker):
                continue

            rest = clean[len(speaker):]
            stripped = rest.lstrip()

            if not stripped:
                continue

            if stripped[0] in (":", ".", "-"):
                return speaker, vibevoice_clean_text(stripped[1:])

            if rest.startswith(" "):
                return speaker, vibevoice_clean_text(rest)

        return None, clean


    def vibevoice_unknown_speaker_match(clean):
        match = re.match(r"^([^:]{1,40}):\s+(.+)$", clean)

        if match:
            speaker = vibevoice_clean_text(match.group(1))
            body = vibevoice_clean_text(match.group(2))

            if speaker and body:
                return speaker, body

        match = re.match(r"^(.{1,40}?)\s+-\s+(.+)$", clean)

        if match:
            speaker = vibevoice_clean_text(match.group(1))
            body = vibevoice_clean_text(match.group(2))

            if speaker and body:
                return speaker, body

        return None, clean


    def vibevoice_split_speaker_text(text):
        clean = vibevoice_clean_text(text)

        if not clean:
            return None, u""

        speaker, body = vibevoice_known_speaker_match(clean)

        if speaker is not None:
            return speaker, body

        return vibevoice_unknown_speaker_match(clean)


    def vibevoice_voice_for_speaker(speaker):
        if speaker:
            voice = VIBEVOICE_VOICE_BY_SPEAKER.get(speaker, None)

            if voice is not None:
                return voice

            for speaker_name, mapped_voice in VIBEVOICE_VOICE_BY_SPEAKER.items():
                if vibevoice_clean_text(speaker_name) == speaker:
                    return mapped_voice

        return VIBEVOICE_DEFAULT_VOICE


    def vibevoice_apply_name_policy(speaker, body):
        state = _vibevoice_state
        mode = vibevoice_name_read_mode()
        read_name = False

        if mode == "always":
            read_name = True
        elif mode == "change":
            read_name = speaker != state.last_spoken_speaker

        state.last_spoken_speaker = speaker

        if read_name:
            if body:
                speech_text = speaker + ". " + body
            else:
                speech_text = speaker
        else:
            speech_text = body

        return vibevoice_clean_text(speech_text), vibevoice_voice_for_speaker(speaker), speaker


    def vibevoice_prepare_text_and_voice(text):
        state = _vibevoice_state
        clean = vibevoice_clean_text(text)
        speaker, body = vibevoice_split_speaker_text(clean)

        if speaker is not None:
            if not body:
                state.pending_speaker = speaker
                return u"", vibevoice_voice_for_speaker(speaker), speaker

            state.pending_speaker = None
            return vibevoice_apply_name_policy(speaker, body)

        if state.pending_speaker is not None:
            speaker = state.pending_speaker
            state.pending_speaker = None
            return vibevoice_apply_name_policy(speaker, clean)

        state.last_spoken_speaker = None
        return clean, VIBEVOICE_DEFAULT_VOICE, None


    def vibevoice_cache_key(text, voice):
        raw = u"%s|%s|%s|%s|%s|%s" % (
            VIBEVOICE_CACHE_VERSION,
            VIBEVOICE_URL,
            VIBEVOICE_MODEL,
            VIBEVOICE_RESPONSE_FORMAT,
            voice,
            text,
        )

        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


    def vibevoice_make_dir(path):
        if not os.path.exists(path):
            os.makedirs(path)

        probe = os.path.join(path, ".write_test")

        with open(probe, "wb") as f:
            f.write(b"ok")

        try:
            os.remove(probe)
        except Exception:
            pass


    def vibevoice_select_cache_dir():
        candidates = []

        gamedir = getattr(config, "gamedir", None)
        savedir = getattr(config, "savedir", None)
        basedir = getattr(config, "basedir", None)

        if VIBEVOICE_STORE_AUDIO_IN_GAME_DIR:
            if gamedir:
                candidates.append((
                    os.path.join(gamedir, VIBEVOICE_CACHE_DIR_NAME),
                    VIBEVOICE_CACHE_DIR_NAME,
                ))

            if basedir:
                basedir_cache = os.path.join(basedir, VIBEVOICE_CACHE_DIR_NAME)
                candidates.append((basedir_cache, basedir_cache))

            if savedir:
                savedir_cache = os.path.join(savedir, VIBEVOICE_CACHE_DIR_NAME)
                candidates.append((savedir_cache, savedir_cache))

        else:
            if savedir:
                savedir_cache = os.path.join(savedir, VIBEVOICE_CACHE_DIR_NAME)
                candidates.append((savedir_cache, savedir_cache))

            if basedir:
                basedir_cache = os.path.join(basedir, VIBEVOICE_CACHE_DIR_NAME)
                candidates.append((basedir_cache, basedir_cache))

            if gamedir:
                candidates.append((
                    os.path.join(gamedir, VIBEVOICE_CACHE_DIR_NAME),
                    VIBEVOICE_CACHE_DIR_NAME,
                ))

        for disk_dir, play_prefix in candidates:
            try:
                vibevoice_make_dir(disk_dir)
                return disk_dir, play_prefix
            except Exception as e:
                renpy.log("VIBEVOICE TTS: cache dir unavailable %r: %r" % (disk_dir, e))

        raise Exception("VIBEVOICE TTS: no writable cache directory")


    TTS_CACHE_DIR, TTS_CACHE_PLAY_PREFIX = vibevoice_select_cache_dir()
    renpy.log("VIBEVOICE TTS: cache dir = %r" % TTS_CACHE_DIR)


    def vibevoice_play_name(filename):
        if TTS_CACHE_PLAY_PREFIX == VIBEVOICE_CACHE_DIR_NAME:
            value = os.path.join(TTS_CACHE_PLAY_PREFIX, filename)
        else:
            value = os.path.join(TTS_CACHE_DIR, filename)

        return value.replace("\\", "/")


    def vibevoice_fetch_audio(text, voice):
        payload = {
            "model": VIBEVOICE_MODEL,
            "input": text,
            "voice": voice,
            "response_format": VIBEVOICE_RESPONSE_FORMAT,
        }

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib_request.Request(
            VIBEVOICE_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
            }
        )

        response = urllib_request.urlopen(req, timeout=VIBEVOICE_TIMEOUT)

        try:
            return response.read()
        finally:
            try:
                response.close()
            except Exception:
                pass


    def vibevoice_get_audio_file(text, voice):
        key = vibevoice_cache_key(text, voice)
        filename = key + "." + VIBEVOICE_RESPONSE_FORMAT
        path = os.path.join(TTS_CACHE_DIR, filename)

        if os.path.exists(path) and os.path.getsize(path) > 0:
            renpy.log("VIBEVOICE TTS: cache HIT | %r" % path)
            return vibevoice_play_name(filename), key

        renpy.log("VIBEVOICE TTS: cache MISS | voice=%r | text=%r" % (voice, text))

        audio = vibevoice_fetch_audio(text, voice)

        if not audio:
            raise Exception("VibeVoice returned no audio data")

        tmp_path = path + ".tmp"

        with open(tmp_path, "wb") as f:
            f.write(audio)

        os.rename(tmp_path, path)

        renpy.log("VIBEVOICE TTS: saved %r (%d bytes)" % (path, len(audio)))

        return vibevoice_play_name(filename), key


    def vibevoice_pump_audio():
        try:
            pump = getattr(renpy.music, "pump", None)

            if pump is not None:
                pump()
        except Exception as e:
            renpy.log("VIBEVOICE TTS: audio pump failed: %r" % e)


    def vibevoice_stop_playback(reason):
        try:
            renpy.music.stop(channel=VIBEVOICE_CHANNEL, fadeout=0)
            vibevoice_pump_audio()
            renpy.log("VIBEVOICE TTS: stopped playback | %s" % reason)
        except Exception as e:
            renpy.log("VIBEVOICE TTS: stop failed | %s | %r" % (reason, e))


    def vibevoice_cancel_and_stop(reason, reset_speaker=False):
        state = _vibevoice_state

        if state.condition is not None:
            with state.condition:
                state.request_id += 1
                state.active_id = state.request_id
                state.pending = None
                state.condition.notify()

        if reset_speaker:
            state.last_spoken_speaker = None
            state.pending_speaker = None

        vibevoice_stop_playback(reason)


    def vibevoice_play_ready(request_id, play_name, text):
        state = _vibevoice_state

        if not vibevoice_speech_mode_active():
            renpy.log("VIBEVOICE TTS: stale audio ignored; self-voicing is off | text=%r" % text)
            return

        if state.condition is not None:
            with state.condition:
                if request_id != state.active_id:
                    renpy.log("VIBEVOICE TTS: stale audio ignored | request=%r active=%r" % (
                        request_id,
                        state.active_id,
                    ))
                    return

        try:
            renpy.music.play(
                play_name,
                channel=VIBEVOICE_CHANNEL,
                loop=False,
                fadeout=0,
            )
            vibevoice_pump_audio()
            renpy.log("VIBEVOICE TTS: playback started | %r" % play_name)
        except Exception as e:
            renpy.log("VIBEVOICE TTS ERROR: playback failed | %r | %r" % (play_name, e))


    def vibevoice_worker_loop(state):
        renpy.log("VIBEVOICE TTS: worker started")

        while True:
            with state.condition:
                while state.pending is None:
                    state.condition.wait()

                request_id, text, voice = state.pending
                state.pending = None

            try:
                play_name, audio_key = vibevoice_get_audio_file(text, voice)
                renpy.invoke_in_main_thread(vibevoice_play_ready, request_id, play_name, text)
            except Exception as e:
                renpy.log("VIBEVOICE TTS ERROR: generation failed | request=%r | voice=%r | text=%r | %r" % (
                    request_id,
                    voice,
                    text,
                    e,
                ))


    def vibevoice_ensure_worker():
        state = _vibevoice_state

        if state.condition is None:
            renpy.log("VIBEVOICE TTS: threading unavailable; cannot run non-blocking TTS")
            return False

        if not hasattr(renpy, "invoke_in_thread") or not hasattr(renpy, "invoke_in_main_thread"):
            renpy.log("VIBEVOICE TTS: Ren'Py thread helpers unavailable; cannot run non-blocking TTS")
            return False

        should_start = False

        with state.condition:
            if not state.worker_started:
                state.worker_started = True
                should_start = True

        if should_start:
            try:
                renpy.invoke_in_thread(vibevoice_worker_loop, state)
            except Exception as e:
                with state.condition:
                    state.worker_started = False
                renpy.log("VIBEVOICE TTS: worker start failed: %r" % e)
                return False

        return True


    def vibevoice_queue_text(text, voice):
        state = _vibevoice_state

        if not vibevoice_ensure_worker():
            return

        with state.condition:
            state.request_id += 1
            request_id = state.request_id
            state.active_id = request_id
            state.pending = (request_id, text, voice)
            state.condition.notify()

        vibevoice_stop_playback("new TTS request")

        renpy.log("VIBEVOICE TTS: queued | request=%r | voice=%r | text=%r" % (
            request_id,
            voice,
            text,
        ))


    def vibevoice_tts_function(text):
        if not VIBEVOICE_ENABLED:
            return

        if text is None:
            vibevoice_cancel_and_stop("empty TTS request")
            return

        if not vibevoice_speech_mode_active():
            vibevoice_cancel_and_stop("self-voicing is not in speech mode", reset_speaker=True)
            return

        clean = vibevoice_clean_text(text)

        if not clean:
            vibevoice_cancel_and_stop("blank TTS request")
            return

        speech_text, voice, speaker = vibevoice_prepare_text_and_voice(clean)

        if not speech_text:
            renpy.log("VIBEVOICE TTS: speaker name skipped | speaker=%r | source=%r" % (
                speaker,
                clean,
            ))
            return

        vibevoice_queue_text(speech_text, voice)


    def vibevoice_watch_self_voicing(*args, **kwargs):
        state = _vibevoice_state
        active = vibevoice_speech_mode_active()

        if state.last_speech_mode and not active:
            vibevoice_cancel_and_stop("self-voicing turned off", reset_speaker=True)

        state.last_speech_mode = active


    try:
        renpy.music.register_channel(
            VIBEVOICE_CHANNEL,
            mixer="voice" if getattr(config, "has_voice", True) else "sfx",
            loop=False,
            stop_on_mute=True,
            tight=False
        )
        renpy.log("VIBEVOICE TTS: vibevoice channel registered")
    except Exception as e:
        renpy.log("VIBEVOICE TTS: vibevoice channel register skipped/failed: %r" % e)

    try:
        if hasattr(config, "tts_voice_channels") and VIBEVOICE_CHANNEL not in config.tts_voice_channels:
            config.tts_voice_channels.append(VIBEVOICE_CHANNEL)
    except Exception as e:
        renpy.log("VIBEVOICE TTS: could not add tts voice channel: %r" % e)

    try:
        if vibevoice_watch_self_voicing not in config.interact_callbacks:
            config.interact_callbacks.append(vibevoice_watch_self_voicing)
    except Exception as e:
        renpy.log("VIBEVOICE TTS: interact watcher registration failed: %r" % e)

    try:
        if hasattr(config, "periodic_callbacks") and vibevoice_watch_self_voicing not in config.periodic_callbacks:
            config.periodic_callbacks.append(vibevoice_watch_self_voicing)
    except Exception as e:
        renpy.log("VIBEVOICE TTS: periodic watcher registration failed: %r" % e)

    config.tts_function = vibevoice_tts_function

    renpy.log("VIBEVOICE TTS: config.tts_function patched")

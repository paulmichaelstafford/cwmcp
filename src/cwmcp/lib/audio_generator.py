# src/cwmcp/lib/audio_generator.py
"""Generate audio from chapter.md via cwtts/Mistral Voxtral/Fish Audio.

Caches audio.mp3, marks.json, marks_in_milliseconds.json next to chapter.md.
EN uses cwtts/cwbe (Kokoro, local). FR uses Mistral Voxtral. All others use Fish Audio.
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import uuid


PAUSE_BETWEEN_PARAGRAPHS = 800
PAUSE_WITHIN_PARAGRAPH = 300
MAX_WORDS = 250

# Voice IDs for external TTS providers (non-EN languages)
FISH_AUDIO_VOICES: dict[str, str] = {
    "ES": "f53102becdf94a51af6d64010bc658f2",
    "DE": "a42859a3e3674c58b73be590f62152eb",
    "IT": "4d45631184584ce1b2eda4e06ae14e5f",
    "PT": "4d72497e3ceb4c75a7c5563900975afd",
    "ZH": "e0cbb35d7cc2420c87f2ea6ad623b61a",
    "JA": "0221478a85aa4703a410ccb405afb872",
    "KO": "4194b66c6ec24dc3be72a0cbd2547b61",
}

MISTRAL_VOICE_ID = "e0580ce5-e63c-4cbe-88c8-a983b80c5f1f"  # Marie Curious


def parse_chapter(filepath: str) -> tuple[str, list[dict]]:
    """Parse chapter.md into title and segments."""
    with open(filepath) as f:
        content = f.read()

    title = "Untitled"
    if content.startswith("---"):
        end = content.index("---", 3)
        front_matter = content[3:end]
        title_match = re.search(r"title:\s*(.+)", front_matter)
        if title_match:
            title = title_match.group(1).strip()
        content = content[end + 3 :].strip()

    segments = []
    paragraph_idx = 0
    prev_was_blank = False

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            if segments:
                prev_was_blank = True
            continue

        if prev_was_blank:
            paragraph_idx += 1
            prev_was_blank = False

        if line.startswith("[") and "]" in line:
            bracket_end = line.index("]")
            speaker = line[1:bracket_end].lower()
            text = line[bracket_end + 1 :].strip()
            if text:
                segments.append({"speaker": speaker, "text": text, "paragraph_idx": paragraph_idx})

    return title, segments


def generate_via_cwtts(cwtts_url: str, text: str, language: str) -> tuple[bytes, list[dict]]:
    """Generate TTS via cwtts service directly. Returns (audio_bytes, sentences)."""
    payload = json.dumps({"text": text, "language": language}).encode()
    req = urllib.request.Request(
        f"{cwtts_url}/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    audio_bytes = base64.b64decode(data["audio_base64"])
    return audio_bytes, data["sentences"]


def generate_via_cwbe(client, text: str, language: str) -> tuple[bytes, list[dict]]:
    """Generate TTS via cwbe /api/service/tts endpoint. Returns (audio_bytes, sentences)."""
    data = client.generate_tts(text=text, language=language)
    audio_bytes = base64.b64decode(data["audio_base64"])
    return audio_bytes, data["sentences"]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on '. ', '? ', '! ', and end-of-string punctuation."""
    # Split on sentence-ending punctuation followed by a space or end of string.
    # We keep the punctuation attached to the sentence.
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    # Filter out empty strings
    return [p.strip() for p in parts if p.strip()]


def _get_mp3_duration_ms(audio_bytes: bytes) -> int:
    """Get the duration of MP3 audio in milliseconds using mutagen."""
    from mutagen.mp3 import MP3

    buf = io.BytesIO(audio_bytes)
    mp3 = MP3(buf)
    return int(mp3.info.length * 1000)


def _build_estimated_sentences(text: str, audio_bytes: bytes) -> list[dict]:
    """Build sentence dicts with estimated timings from audio duration and character count.

    Returns list of {"text": str, "start_ms": int, "end_ms": int} matching cwtts format.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    duration_ms = _get_mp3_duration_ms(audio_bytes)
    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        # Edge case: distribute evenly
        per_sentence = duration_ms // len(sentences)
        result = []
        for i, s in enumerate(sentences):
            result.append({
                "text": s,
                "start_ms": i * per_sentence,
                "end_ms": (i + 1) * per_sentence,
            })
        return result

    # Distribute duration proportionally by character count
    result = []
    offset = 0
    for s in sentences:
        char_fraction = len(s) / total_chars
        seg_duration = int(duration_ms * char_fraction)
        result.append({
            "text": s,
            "start_ms": offset,
            "end_ms": offset + seg_duration,
        })
        offset += seg_duration
    return result


def generate_via_mistral(api_key: str, text: str) -> tuple[bytes, list[dict]]:
    """Generate TTS via Mistral Voxtral API (FR only). Returns (audio_bytes, sentences)."""
    payload = json.dumps({
        "model": "voxtral-mini-tts-latest",
        "input": text,
        "voice": MISTRAL_VOICE_ID,
        "response_format": "mp3",
    }).encode()
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/audio/speech",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        resp_data = json.loads(resp.read())
    audio_bytes = base64.b64decode(resp_data["audio_data"])

    sentences = _build_estimated_sentences(text, audio_bytes)
    return audio_bytes, sentences


FISH_AUDIO_TONE = "soft, warm, calm storytelling narrator"


def generate_via_fish_audio(api_key: str, text: str, language: str) -> tuple[bytes, list[dict]]:
    """Generate TTS via Fish Audio API. Returns (audio_bytes, sentences)."""
    voice_id = FISH_AUDIO_VOICES.get(language.upper())
    if not voice_id:
        raise ValueError(f"No Fish Audio voice configured for language: {language}")

    tts_text = f"[{FISH_AUDIO_TONE}] {text}"

    payload = json.dumps({
        "text": tts_text,
        "reference_id": voice_id,
        "format": "mp3",
        "mp3_bitrate": 128,
    }).encode()
    req = urllib.request.Request(
        "https://api.fish.audio/v1/tts",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        audio_bytes = resp.read()

    sentences = _build_estimated_sentences(text, audio_bytes)
    return audio_bytes, sentences


def build_marks_from_cwtts(
    segments: list[dict], segment_sentences: list[list[dict]], segment_offsets_ms: list[int]
) -> tuple[list[dict], dict]:
    """Build marks and marks_in_milliseconds from cwtts sentence timings."""
    marks = []
    marks_in_ms = {}

    for i, seg in enumerate(segments):
        offset_ms = segment_offsets_ms[i]
        paragraph_idx = seg["paragraph_idx"]
        sentences = segment_sentences[i]

        for sentence_idx, sentence in enumerate(sentences):
            mark_id = str(uuid.uuid4())
            marks.append({
                "id": mark_id,
                "sentence": sentence_idx,
                "paragraph": paragraph_idx,
                "text": sentence["text"],
            })
            marks_in_ms[mark_id] = sentence["start_ms"] + offset_ms

    return marks, marks_in_ms


def merge_audio_with_ffmpeg(audio_segments: list[bytes], pause_durations: list[int]) -> bytes:
    """Merge audio segments with silence gaps using ffmpeg."""
    tmpdir = tempfile.mkdtemp()
    try:
        segment_files = []
        for i, audio_bytes in enumerate(audio_segments):
            path = os.path.join(tmpdir, f"seg_{i:04d}.mp3")
            with open(path, "wb") as f:
                f.write(audio_bytes)
            segment_files.append(path)

        silence_files = []
        for i, pause_ms in enumerate(pause_durations):
            if pause_ms > 0:
                path = os.path.join(tmpdir, f"silence_{i:04d}.mp3")
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-f", "lavfi",
                        "-i", f"anullsrc=r=44100:cl=mono",
                        "-t", f"{pause_ms / 1000:.3f}",
                        "-c:a", "libmp3lame", "-b:a", "128k",
                        path,
                    ],
                    capture_output=True,
                    check=True,
                )
                silence_files.append(path)
            else:
                silence_files.append(None)

        concat_list_path = os.path.join(tmpdir, "concat.txt")
        with open(concat_list_path, "w") as f:
            for i, seg_path in enumerate(segment_files):
                f.write(f"file '{seg_path}'\n")
                if i < len(silence_files) and silence_files[i] is not None:
                    f.write(f"file '{silence_files[i]}'\n")

        output_path = os.path.join(tmpdir, "merged.mp3")
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list_path,
                "-c", "copy",
                output_path,
            ],
            capture_output=True,
            check=True,
        )

        with open(output_path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmpdir)


def _generate_segment_audio(
    seg_text: str,
    language: str,
    cwtts_url: str,
    cwbe_client=None,
    mistral_api_key: str = "",
    fish_audio_api_key: str = "",
) -> tuple[bytes, list[dict]]:
    """Route a single segment to the appropriate TTS engine based on language."""
    lang = language.upper()

    if lang == "EN":
        if cwbe_client:
            return generate_via_cwbe(cwbe_client, seg_text, language)
        return generate_via_cwtts(cwtts_url, seg_text, language)
    elif lang == "FR":
        if not mistral_api_key:
            raise ValueError("mistral_api_key required for FR TTS")
        return generate_via_mistral(mistral_api_key, seg_text)
    elif lang in FISH_AUDIO_VOICES:
        if not fish_audio_api_key:
            raise ValueError("fish_audio_api_key required for non-EN/FR TTS")
        return generate_via_fish_audio(fish_audio_api_key, seg_text, lang)
    else:
        raise ValueError(f"Unsupported language for TTS: {lang}")


def generate_chapter_audio(
    cwtts_url: str,
    chapter_md_path: str,
    language: str,
    cwbe_client=None,
    mistral_api_key: str = "",
    fish_audio_api_key: str = "",
) -> dict:
    """Generate audio for a chapter.md file.

    Routes to the appropriate TTS engine based on language:
    - EN: cwtts/cwbe (Kokoro, local)
    - FR: Mistral Voxtral API
    - ES, DE, IT, PT, ZH, JA, KO: Fish Audio API

    Caches audio.mp3, marks.json, marks_in_milliseconds.json next to chapter.md.
    Skips if audio already exists.

    Returns: {"status": "ok"|"skipped"|"error", "message": ..., "marks_count": ..., "audio_bytes": ...}
    """
    chapter_dir = os.path.dirname(os.path.abspath(chapter_md_path))
    audio_cache = os.path.join(chapter_dir, "audio.mp3")
    marks_cache = os.path.join(chapter_dir, "marks.json")
    marks_ms_cache = os.path.join(chapter_dir, "marks_in_milliseconds.json")

    if os.path.exists(audio_cache) and os.path.exists(marks_cache):
        return {"status": "skipped", "message": f"Audio already cached at {audio_cache}"}

    title, segments = parse_chapter(chapter_md_path)

    total_words = sum(len(seg["text"].split()) for seg in segments)
    if total_words > MAX_WORDS:
        return {
            "status": "error",
            "message": f"Chapter has {total_words} words, max is {MAX_WORDS}. Trim before generating.",
        }

    lang = language.upper()
    use_per_mark = lang != "EN"

    if use_per_mark:
        # Non-EN: generate audio per mark (paragraph segment) for exact timestamps.
        # External TTS APIs (Fish Audio, Mistral) don't return timestamps,
        # so we generate each segment individually and merge with pauses.
        mark_audio_clips = []
        for seg in segments:
            audio_bytes, _ = _generate_segment_audio(
                seg["text"],
                language,
                cwtts_url,
                cwbe_client=cwbe_client,
                mistral_api_key=mistral_api_key,
                fish_audio_api_key=fish_audio_api_key,
            )
            mark_audio_clips.append(audio_bytes)

        pause_durations = []
        for i in range(len(segments) - 1):
            pause_durations.append(PAUSE_BETWEEN_PARAGRAPHS)

        merged_audio = merge_audio_with_ffmpeg(mark_audio_clips, pause_durations)

        marks = []
        marks_in_ms = {}
        offset_ms = 0
        for i, seg in enumerate(segments):
            mark_id = str(uuid.uuid4())
            marks.append({"id": mark_id, "sentence": 0, "paragraph": seg["paragraph_idx"], "text": seg["text"]})
            marks_in_ms[mark_id] = offset_ms

            clip_duration_ms = _get_mp3_duration_ms(mark_audio_clips[i])
            offset_ms += clip_duration_ms
            if i < len(pause_durations):
                offset_ms += pause_durations[i]
    else:
        # EN: generate per paragraph segment — Kokoro returns real sentence timestamps.
        audio_segments = []
        segment_sentences = []
        for seg in segments:
            audio_bytes, sentences = _generate_segment_audio(
                seg["text"],
                language,
                cwtts_url,
                cwbe_client=cwbe_client,
                mistral_api_key=mistral_api_key,
                fish_audio_api_key=fish_audio_api_key,
            )
            audio_segments.append(audio_bytes)
            segment_sentences.append(sentences)

        pause_durations = []
        segment_offsets_ms = [0]
        cumulative_ms = 0
        for i in range(len(segments)):
            seg_duration_ms = segment_sentences[i][-1]["end_ms"] if segment_sentences[i] else 0
            cumulative_ms += seg_duration_ms
            if i < len(segments) - 1:
                pause_ms = (
                    PAUSE_BETWEEN_PARAGRAPHS
                    if segments[i + 1]["paragraph_idx"] != segments[i]["paragraph_idx"]
                    else PAUSE_WITHIN_PARAGRAPH
                )
                pause_durations.append(pause_ms)
                cumulative_ms += pause_ms
                segment_offsets_ms.append(cumulative_ms)

        merged_audio = merge_audio_with_ffmpeg(audio_segments, pause_durations)
        marks, marks_in_ms = build_marks_from_cwtts(segments, segment_sentences, segment_offsets_ms)

    with open(audio_cache, "wb") as f:
        f.write(merged_audio)
    with open(marks_cache, "w") as f:
        json.dump(marks, f, indent=2)
    with open(marks_ms_cache, "w") as f:
        json.dump(marks_in_ms, f, indent=2)

    return {
        "status": "ok",
        "message": f"Generated {len(marks)} marks, {len(merged_audio)} bytes audio",
        "marks_count": len(marks),
        "audio_bytes": len(merged_audio),
        "title": title,
        "words": total_words,
    }

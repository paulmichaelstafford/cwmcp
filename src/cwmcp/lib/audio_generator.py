# src/cwmcp/lib/audio_generator.py
"""Generate audio from chapter.md via ElevenLabs TTS.

Caches audio.mp3, marks.json, marks_in_milliseconds.json next to chapter.md.
Requires: elevenlabs Python SDK.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid


DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # George - British storyteller
PAUSE_BETWEEN_PARAGRAPHS = 800
PAUSE_WITHIN_PARAGRAPH = 300
MAX_WORDS = 250


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


def _get_client(api_key: str):
    from elevenlabs.client import ElevenLabs

    return ElevenLabs(api_key=api_key)


def generate_audio_segment(client, text: str, voice_id: str) -> tuple[bytes, object]:
    """Generate TTS for a single text segment. Returns (audio_bytes, alignment)."""
    response = client.text_to_speech.convert_with_timestamps(
        voice_id=voice_id,
        text=text,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        voice_settings={"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True},
    )
    audio_bytes = base64.b64decode(response.audio_base_64)
    return audio_bytes, response.alignment


def build_marks_from_segments(
    segments: list[dict], segment_alignments: list, segment_offsets_ms: list[int]
) -> tuple[list[dict], dict]:
    """Build marks and marks_in_milliseconds from segment data."""
    marks = []
    marks_in_ms = {}

    for i, seg in enumerate(segments):
        alignment = segment_alignments[i]
        offset_ms = segment_offsets_ms[i]
        text = seg["text"]
        paragraph_idx = seg["paragraph_idx"]

        sentences = []
        current = []
        for ch in text:
            current.append(ch)
            if ch in ".!?\u3002\uff01\uff1f":
                sentences.append("".join(current).strip())
                current = []
        if current:
            leftover = "".join(current).strip()
            if leftover:
                sentences.append(leftover)

        starts = alignment.character_start_times_seconds

        char_offset = 0
        for sentence_idx, sentence_text in enumerate(sentences):
            sentence_start_char = text.index(sentence_text, char_offset)
            sentence_start_ms = int(starts[sentence_start_char] * 1000) + offset_ms

            mark_id = str(uuid.uuid4())
            marks.append({
                "id": mark_id,
                "sentence": sentence_idx,
                "paragraph": paragraph_idx,
                "text": sentence_text,
            })
            marks_in_ms[mark_id] = sentence_start_ms
            char_offset = sentence_start_char + len(sentence_text)

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
                        "-i", f"anullsrc=r=44100:cl=stereo",
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
                "-c:a", "libmp3lame", "-b:a", "128k",
                output_path,
            ],
            capture_output=True,
            check=True,
        )

        with open(output_path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmpdir)


def generate_chapter_audio(
    api_key: str,
    chapter_md_path: str,
    voice_id: str = DEFAULT_VOICE_ID,
) -> dict:
    """Generate audio for a chapter.md file.

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

    client = _get_client(api_key)

    audio_segments = []
    segment_alignments = []
    for seg in segments:
        audio_bytes, alignment = generate_audio_segment(client, seg["text"], voice_id)
        audio_segments.append(audio_bytes)
        segment_alignments.append(alignment)

    pause_durations = []
    segment_offsets_ms = [0]
    cumulative_ms = 0
    for i in range(len(segments)):
        seg_duration_ms = int(segment_alignments[i].character_end_times_seconds[-1] * 1000)
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
    marks, marks_in_ms = build_marks_from_segments(segments, segment_alignments, segment_offsets_ms)

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

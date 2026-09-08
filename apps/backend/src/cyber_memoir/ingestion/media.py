import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from cyber_memoir.config import settings


def metadata(url: str) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--dump-single-json",
            "--skip-download",
            "--no-playlist",
            "--no-warnings",
            "--socket-timeout",
            "10",
            "--",
            url,
        ],
        capture_output=True,
        timeout=120,
        check=True,
    )
    if len(result.stdout) > 10_000_000:
        raise ValueError("Metadata too large")
    return json.loads(result.stdout)


def asr(path: str) -> list[dict]:
    from faster_whisper import WhisperModel

    model = WhisperModel(settings().asr_model, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(path, language="zh", vad_filter=True)
    return [
        {"text": s.text, "locator": {"start_ms": round(s.start * 1000), "end_ms": round(s.end * 1000)}}
        for s in segments
    ]


def ocr(path: str) -> list[dict]:
    from paddleocr import PaddleOCR

    engine = PaddleOCR(
        use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False
    )
    output = []
    for result in engine.predict(path):
        data = result.json
        if isinstance(data, str):
            data = json.loads(data)
        data = data.get("res", data)
        for text, box in zip(data.get("rec_texts", []), data.get("rec_boxes", []), strict=True):
            output.append({"text": text, "locator": {"bbox": list(map(int, box))}})
    return output


def analyze_bytes(data: bytes, kind: str) -> list[dict]:
    suffix = ".png" if kind == "ocr" else ".media"
    with tempfile.TemporaryDirectory(prefix="memoir-") as directory:
        path = Path(directory) / f"material{suffix}"
        path.write_bytes(data)
        return ocr(str(path)) if kind == "ocr" else asr(str(path))


def analyze_url(url: str):
    """Opt-in, bounded temporary media analysis. Never retain the complete video."""
    with tempfile.TemporaryDirectory(prefix="memoir-url-") as directory:
        output = str(Path(directory) / "source.%(ext)s")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "yt_dlp",
                "--no-playlist",
                "--no-warnings",
                "--socket-timeout",
                "10",
                "--max-filesize",
                "16M",
                "--match-filter",
                "duration <= 900",
                "-f",
                "worst[ext=mp4]/worst",
                "-o",
                output,
                "--",
                url,
            ],
            capture_output=True,
            timeout=300,
            check=True,
        )
        files = [p for p in Path(directory).glob("source.*") if p.suffix not in {".part", ".ytdl"}]
        if not files:
            raise ValueError("媒体超过 V1 自动处理上限，需人工补充材料")
        path = files[0]
        if path.stat().st_size > settings().max_material_bytes:
            raise ValueError("媒体超过大小限制")
        yield "asr", asr(str(path)), None
        # At most ten frame samples, each retaining its real video timestamp.
        frames_result = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-loglevel",
                "info",
                "-i",
                str(path),
                "-vf",
                "select=isnan(prev_selected_t)+gte(t-prev_selected_t\\,30),showinfo",
                "-fps_mode",
                "vfr",
                "-frames:v",
                "10",
                str(Path(directory) / "frame-%03d.png"),
            ],
            capture_output=True,
            timeout=120,
            check=True,
        )
        timestamps = re.findall(
            r"\bn:\s*\d+.*?pts_time:([\d.-]+)", frames_result.stderr.decode(errors="replace")
        )
        frames = sorted(Path(directory).glob("frame-*.png"))
        if len(timestamps) < len(frames):
            raise ValueError("无法核对抽帧时间，不生成无定位 OCR 证据")
        for index, frame in enumerate(frames):
            cues = ocr(str(frame))
            for cue in cues:
                cue["locator"]["frame_ms"] = round(float(timestamps[index]) * 1000)
            yield "ocr", cues, frame.read_bytes()

"""Created: 2026-04-16

Purpose: Implements the command-line interface for local voice processing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from voice_processing.config import PipelineConfig
from voice_processing.pipeline import VoiceProcessingPipeline


def build_arg_parser() -> argparse.ArgumentParser:
    """Builds the command-line parser for the local pipeline."""

    parser = argparse.ArgumentParser(description="Run a fully local multi-speaker voice processing pipeline.")
    parser.add_argument("audio_path", type=Path, help="Path to the source conversation audio.")
    parser.add_argument(
        "user_voice_path",
        type=Path,
        nargs="?",
        default=None,
        help="Optional enrolled USER voice sample. Omit for clustering-only diarization.",
    )
    parser.add_argument("--output-json", type=Path, default=Path("voice_transcript.json"))
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--language", default=None)
    parser.add_argument("--user-threshold", type=float, default=0.7)
    parser.add_argument(
        "--speaker-strategy",
        choices=("unique_speaker_similarity", "centroid_similarity", "agglomerative"),
        default="unique_speaker_similarity",
        help="How unknown speakers are grouped.",
    )
    parser.add_argument("--speaker-threshold", type=float, default=0.72)
    parser.add_argument("--cluster-threshold", type=float, default=0.4)
    parser.add_argument("--vad-threshold", type=float, default=0.5)
    parser.add_argument("--min-segment-seconds", type=float, default=0.6)
    parser.add_argument("--max-segment-seconds", type=float, default=3.0)
    return parser


def main() -> None:
    """Runs the local voice processing CLI."""

    args = build_arg_parser().parse_args()
    config = PipelineConfig(
        whisper_model_name=args.whisper_model,
        language=args.language,
        user_similarity_threshold=args.user_threshold,
        speaker_assignment_strategy=args.speaker_strategy,
        speaker_similarity_threshold=args.speaker_threshold,
        cluster_distance_threshold=args.cluster_threshold,
        vad_threshold=args.vad_threshold,
        min_segment_s=args.min_segment_seconds,
        max_segment_s=args.max_segment_seconds,
        output_json_path=args.output_json,
    )
    payload = VoiceProcessingPipeline(config=config).run(args.audio_path, args.user_voice_path)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

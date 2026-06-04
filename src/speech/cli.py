"""Command-line helpers for preparing local SpeechT5 speaker embeddings."""

from __future__ import annotations

import argparse
from pathlib import Path

from .embedding_loader import save_speaker_embedding_from_audio, save_speaker_embedding_from_hf_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare speaker embeddings for local SpeechT5 voice synthesis.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    from_audio = subparsers.add_parser("from-audio", help="Compute a speaker embedding from a reference audio file.")
    from_audio.add_argument("input_audio", type=Path, help="Path to the reference audio sample.")
    from_audio.add_argument("output", type=Path, help="Path to write the `.npy` embedding file.")
    from_audio.add_argument("--device", choices=["cpu", "cuda"], default=None, help="Torch device override.")
    from_audio.add_argument("--sample-rate", type=int, default=16000, help="Target sample rate for embedding.")

    from_dataset = subparsers.add_parser(
        "from-hf-dataset",
        help="Download a speaker embedding row from a Hugging Face dataset and save it as `.npy`.",
    )
    from_dataset.add_argument("output", type=Path, help="Path to write the `.npy` embedding file.")
    from_dataset.add_argument("--dataset", default="Matthijs/cmu-arctic-xvectors", help="HF dataset name.")
    from_dataset.add_argument("--split", default="validation", help="Dataset split.")
    from_dataset.add_argument("--index", type=int, default=7306, help="Row index inside the split.")
    from_dataset.add_argument("--field", default="xvector", help="Field containing the speaker embedding.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "from-audio":
        output = save_speaker_embedding_from_audio(
            input_path=args.input_audio,
            output_path=args.output,
            device=args.device,
            sample_rate=args.sample_rate,
        )
        print(output)
        return 0

    if args.command == "from-hf-dataset":
        output = save_speaker_embedding_from_hf_dataset(
            output_path=args.output,
            dataset_name=args.dataset,
            dataset_split=args.split,
            dataset_index=args.index,
            dataset_field=args.field,
        )
        print(output)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2

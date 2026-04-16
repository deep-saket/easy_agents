"""Created: 2026-04-16

Purpose: Implements explicit speaker clustering for unknown speakers.
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F

from platform_logging.structured_logger import StructuredLogger
from voice_processing.config import PipelineConfig
from voice_processing.types import SpeakerAssignmentDecision, SpeakerSimilarityComparison, SpeechSegment


LOGGER = StructuredLogger("voice_processing")


class SpeakerClusterer:
    """Clusters unknown speaker embeddings into stable timeline labels."""

    def __init__(self, config: PipelineConfig):
        self._config = config
        self.similarity_comparisons: list[SpeakerSimilarityComparison] = []
        self.assignment_decisions: list[SpeakerAssignmentDecision] = []

    def cluster(self, segments: list[SpeechSegment]) -> None:
        """Assigns speaker labels for all non-user segments."""

        self.similarity_comparisons = []
        self.assignment_decisions = []
        unknown_segments = [segment for segment in segments if segment.speaker != "USER"]
        if not unknown_segments:
            return
        if len(unknown_segments) == 1:
            unknown_segments[0].speaker = "Speaker_0"
            return

        if self._config.speaker_assignment_strategy in {"centroid_similarity", "unique_speaker_similarity"}:
            self._assign_unique_speakers(unknown_segments)
            speaker_count = len({segment.speaker for segment in unknown_segments})
            LOGGER.info("Clustered %s unknown segments into %s speakers.", len(unknown_segments), speaker_count)
            return

        matrix = np.stack([segment.embedding for segment in unknown_segments if segment.embedding is not None], axis=0)
        cluster_ids = self._assign_cluster_ids(matrix)
        remapped = self._remap_cluster_ids(unknown_segments, cluster_ids)
        for segment, cluster_id in zip(unknown_segments, remapped, strict=False):
            segment.speaker = f"Speaker_{cluster_id}"
        self._merge_similar_speakers(unknown_segments)
        speaker_count = len({segment.speaker for segment in unknown_segments})
        LOGGER.info("Clustered %s unknown segments into %s speakers.", len(unknown_segments), speaker_count)

    def _assign_unique_speakers(self, segments: list[SpeechSegment]) -> None:
        """Assigns segments by comparing each one against unique speakers.

        This implements the explicit flow:

        1. Take the first segment and make it `Speaker_0`.
        2. For each next segment, compare its embedding with every existing
           unique speaker centroid.
        3. If the best similarity is high enough, assign the segment to that
           existing speaker.
        4. Otherwise create the next unique speaker label.

        The method records every comparison in `similarity_comparisons` so the
        notebook can print the score and decision.
        """

        unique_speakers: list[str] = []
        speaker_segments: dict[str, list[SpeechSegment]] = {}
        speaker_centroids: dict[str, np.ndarray] = {}

        for segment_index, segment in enumerate(sorted(segments, key=lambda item: item.start)):
            if segment.embedding is None:
                raise ValueError("Segment embedding is missing.")
            candidate_embedding = self._normalize(segment.embedding)
            provisional_speaker = f"Speaker_{segment_index}"

            if not unique_speakers:
                segment.speaker = "Speaker_0"
                print(f"{provisional_speaker}: first unique speaker -> assigned to {segment.speaker}")
                unique_speakers.append(segment.speaker)
                speaker_segments[segment.speaker] = [segment]
                speaker_centroids[segment.speaker] = candidate_embedding
                self.assignment_decisions.append(
                    SpeakerAssignmentDecision(
                        provisional_speaker=provisional_speaker,
                        assigned_speaker=segment.speaker,
                        similarity=None,
                        threshold=self._config.speaker_similarity_threshold,
                        confidence=None,
                        matched_existing=False,
                    )
                )
                continue

            best_speaker: str | None = None
            best_similarity = float("-inf")
            for unique_speaker in unique_speakers:
                similarity = self._cosine_similarity(candidate_embedding, speaker_centroids[unique_speaker])
                matched = similarity >= self._config.speaker_similarity_threshold
                print(
                    f"{provisional_speaker}: compare with {unique_speaker} -> "
                    f"similarity={similarity:.4f}, "
                    f"threshold={self._config.speaker_similarity_threshold:.4f}, "
                    f"confidence={self._decision_confidence(similarity):.4f}, "
                    f"matched={matched}"
                )
                self.similarity_comparisons.append(
                    SpeakerSimilarityComparison(
                        candidate_speaker=provisional_speaker,
                        unique_speaker=unique_speaker,
                        similarity=similarity,
                        threshold=self._config.speaker_similarity_threshold,
                        confidence=self._decision_confidence(similarity),
                        matched=matched,
                    )
                )
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_speaker = unique_speaker

            print(
                f"{provisional_speaker}: best match -> {best_speaker} "
                f"with similarity={best_similarity:.4f}"
            )
            if best_speaker is not None and best_similarity >= self._config.speaker_similarity_threshold:
                segment.speaker = best_speaker
                print(f"{provisional_speaker}: assigned to existing {best_speaker}")
                speaker_segments[best_speaker].append(segment)
                speaker_centroids[best_speaker] = self._speaker_centroid(speaker_segments[best_speaker])
                self.assignment_decisions.append(
                    SpeakerAssignmentDecision(
                        provisional_speaker=provisional_speaker,
                        assigned_speaker=best_speaker,
                        similarity=best_similarity,
                        threshold=self._config.speaker_similarity_threshold,
                        confidence=self._decision_confidence(best_similarity),
                        matched_existing=True,
                    )
                )
                continue

            segment.speaker = f"Speaker_{len(unique_speakers)}"
            print(f"{provisional_speaker}: created new unique speaker -> assigned to {segment.speaker}")
            unique_speakers.append(segment.speaker)
            speaker_segments[segment.speaker] = [segment]
            speaker_centroids[segment.speaker] = candidate_embedding
            self.assignment_decisions.append(
                SpeakerAssignmentDecision(
                    provisional_speaker=provisional_speaker,
                    assigned_speaker=segment.speaker,
                    similarity=best_similarity if best_speaker is not None else None,
                    threshold=self._config.speaker_similarity_threshold,
                    confidence=self._decision_confidence(best_similarity) if best_speaker is not None else None,
                    matched_existing=False,
                )
            )

    def _merge_similar_speakers(self, segments: list[SpeechSegment]) -> None:
        """Merges provisional speakers using an ordered unique-speaker list.

        The first provisional speaker becomes the first unique speaker. Each
        later provisional speaker is compared with the current unique speaker
        centroids. If the best similarity is above the configured speaker
        threshold, all of that provisional speaker's segments are relabeled to
        the matching unique speaker. Otherwise, the provisional speaker is added
        to the unique-speaker list.
        """

        grouped = self._group_segments_by_speaker(segments)
        ordered_speakers = sorted(grouped, key=lambda speaker: min(segment.start for segment in grouped[speaker]))
        if len(ordered_speakers) <= 1:
            return

        unique_speakers = [ordered_speakers[0]]
        speaker_aliases = {ordered_speakers[0]: ordered_speakers[0]}
        centroids = {ordered_speakers[0]: self._speaker_centroid(grouped[ordered_speakers[0]])}

        for candidate in ordered_speakers[1:]:
            candidate_centroid = self._speaker_centroid(grouped[candidate])
            best_speaker: str | None = None
            best_similarity = float("-inf")
            for unique_speaker in unique_speakers:
                similarity = self._cosine_similarity(candidate_centroid, centroids[unique_speaker])
                matched = similarity >= self._config.speaker_similarity_threshold
                self.similarity_comparisons.append(
                    SpeakerSimilarityComparison(
                        candidate_speaker=candidate,
                        unique_speaker=unique_speaker,
                        similarity=similarity,
                        threshold=self._config.speaker_similarity_threshold,
                        confidence=self._decision_confidence(similarity),
                        matched=matched,
                    )
                )
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_speaker = unique_speaker

            if best_speaker is not None and best_similarity >= self._config.speaker_similarity_threshold:
                speaker_aliases[candidate] = best_speaker
                grouped[best_speaker].extend(grouped[candidate])
                centroids[best_speaker] = self._speaker_centroid(grouped[best_speaker])
                continue

            unique_speakers.append(candidate)
            speaker_aliases[candidate] = candidate
            centroids[candidate] = candidate_centroid

        normalized_names = {speaker: f"Speaker_{index}" for index, speaker in enumerate(unique_speakers)}
        for segment in segments:
            if segment.speaker is None:
                continue
            canonical = speaker_aliases.get(segment.speaker, segment.speaker)
            segment.speaker = normalized_names.get(canonical, canonical)

    def _group_segments_by_speaker(self, segments: list[SpeechSegment]) -> dict[str, list[SpeechSegment]]:
        grouped: dict[str, list[SpeechSegment]] = {}
        for segment in segments:
            if segment.speaker is None:
                continue
            grouped.setdefault(segment.speaker, []).append(segment)
        return grouped

    def _speaker_centroid(self, segments: list[SpeechSegment]) -> np.ndarray:
        embeddings = [segment.embedding for segment in segments if segment.embedding is not None]
        if not embeddings:
            raise ValueError("Cannot compute speaker centroid without embeddings.")
        return self._normalize(np.mean(np.stack(embeddings, axis=0), axis=0))

    def _assign_cluster_ids(self, matrix: np.ndarray) -> np.ndarray:
        if self._config.speaker_assignment_strategy == "centroid_similarity":
            return self._centroid_similarity_assign(matrix)
        if self._config.speaker_assignment_strategy == "agglomerative":
            cluster_ids = self._agglomerative_cluster(matrix)
            return self._enforce_min_cluster_size(matrix, cluster_ids)
        raise ValueError(
            "Unsupported speaker assignment strategy: "
            f"{self._config.speaker_assignment_strategy}. "
            "Use 'unique_speaker_similarity', 'centroid_similarity', or 'agglomerative'."
        )

    def _centroid_similarity_assign(self, matrix: np.ndarray) -> np.ndarray:
        centroids: list[np.ndarray] = []
        counts: list[int] = []
        labels: list[int] = []

        for candidate_index, embedding in enumerate(matrix):
            if not centroids:
                centroids.append(self._normalize(embedding))
                counts.append(1)
                labels.append(0)
                continue

            similarities = [self._cosine_similarity(embedding, centroid) for centroid in centroids]
            for unique_index, similarity in enumerate(similarities):
                self.similarity_comparisons.append(
                    SpeakerSimilarityComparison(
                        candidate_speaker=f"Candidate_{candidate_index}",
                        unique_speaker=f"Speaker_{unique_index}",
                        similarity=similarity,
                        threshold=self._config.speaker_similarity_threshold,
                        confidence=self._decision_confidence(similarity),
                        matched=similarity >= self._config.speaker_similarity_threshold,
                    )
                )
            best_label = int(np.argmax(similarities))
            best_similarity = similarities[best_label]
            if best_similarity >= self._config.speaker_similarity_threshold:
                labels.append(best_label)
                counts[best_label] += 1
                centroids[best_label] = self._normalize(
                    centroids[best_label] * (counts[best_label] - 1) + embedding
                )
                continue

            labels.append(len(centroids))
            centroids.append(self._normalize(embedding))
            counts.append(1)

        return np.array(labels, dtype=int)

    def _agglomerative_cluster(self, matrix: np.ndarray) -> np.ndarray:
        clusters: list[list[int]] = [[index] for index in range(len(matrix))]
        while True:
            best_pair: tuple[int, int] | None = None
            best_distance = float("inf")
            for left in range(len(clusters)):
                for right in range(left + 1, len(clusters)):
                    distance = self._average_linkage_distance(matrix, clusters[left], clusters[right])
                    if distance < best_distance:
                        best_distance = distance
                        best_pair = (left, right)
            if best_pair is None or best_distance > self._config.cluster_distance_threshold:
                break
            left, right = best_pair
            clusters[left] = clusters[left] + clusters[right]
            del clusters[right]

        labels = np.empty(len(matrix), dtype=int)
        for cluster_id, cluster_members in enumerate(clusters):
            for index in cluster_members:
                labels[index] = cluster_id
        return labels

    def _enforce_min_cluster_size(self, matrix: np.ndarray, labels: np.ndarray) -> np.ndarray:
        if self._config.cluster_min_size <= 1:
            return labels
        counts = {int(label): int((labels == label).sum()) for label in np.unique(labels)}
        small_labels = [label for label, count in counts.items() if count < self._config.cluster_min_size]
        if not small_labels or len(counts) == 1:
            return labels

        adjusted = labels.copy()
        centroids = {
            int(label): F.normalize(torch.from_numpy(matrix[labels == label]).mean(dim=0), dim=0).numpy()
            for label in np.unique(labels)
        }
        for label in small_labels:
            target_labels = [
                candidate for candidate in centroids if candidate != label and counts[candidate] >= self._config.cluster_min_size
            ]
            if not target_labels:
                continue
            for index in np.where(labels == label)[0]:
                best_target = min(
                    target_labels,
                    key=lambda candidate: self._cosine_distance(matrix[index], centroids[candidate]),
                )
                adjusted[index] = best_target
        return adjusted

    def _average_linkage_distance(self, matrix: np.ndarray, left: list[int], right: list[int]) -> float:
        distances = [
            self._cosine_distance(matrix[left_index], matrix[right_index])
            for left_index in left
            for right_index in right
        ]
        return float(np.mean(distances))

    def _cosine_distance(self, left: np.ndarray, right: np.ndarray) -> float:
        return 1.0 - self._cosine_similarity(left, right)

    def _cosine_similarity(self, left: np.ndarray, right: np.ndarray) -> float:
        denominator = np.linalg.norm(left) * np.linalg.norm(right)
        if denominator == 0.0:
            return 0.0
        return float(np.dot(left, right) / denominator)

    def _normalize(self, embedding: np.ndarray) -> np.ndarray:
        denominator = np.linalg.norm(embedding)
        if denominator == 0.0:
            return embedding.astype(np.float32)
        return (embedding / denominator).astype(np.float32)

    def _decision_confidence(self, similarity: float) -> float:
        """Returns confidence in the merge or split decision.

        Similarities far from the threshold are stronger decisions than
        similarities close to the threshold. Merge decisions use the similarity
        itself as confidence; split decisions use distance below the threshold.
        """

        if similarity >= self._config.speaker_similarity_threshold:
            return min(1.0, similarity)
        return min(1.0, max(0.0, self._config.speaker_similarity_threshold - similarity))

    @staticmethod
    def _remap_cluster_ids(segments: list[SpeechSegment], cluster_ids: np.ndarray) -> list[int]:
        ordered: dict[int, float] = {}
        for segment, cluster_id in zip(segments, cluster_ids, strict=False):
            ordered.setdefault(int(cluster_id), segment.start)
            ordered[int(cluster_id)] = min(ordered[int(cluster_id)], segment.start)
        mapping = {
            original_id: new_id
            for new_id, (original_id, _) in enumerate(sorted(ordered.items(), key=lambda item: item[1]))
        }
        return [mapping[int(cluster_id)] for cluster_id in cluster_ids]

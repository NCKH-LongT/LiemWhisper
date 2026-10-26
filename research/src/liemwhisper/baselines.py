"""
LiemWhisper Baselines Engine
============================
Implements the comparative systems required by Proposal Section 4.4:
- System B0: ASR + exact matching + taxonomy lookup (Basic end-to-end reference)
- System B1: ASR + glossary prompt + lookup (Test simple contextual biasing)
- System B2: ASR + fuzzy matching + lookup (Test lexical correction alone)

All components are strictly modular, deterministic, and evaluation-ready.
"""

import os
import sys
import re
import json
import time
import site
import ctypes
from typing import List, Dict, Tuple, Any, Optional
import numpy as np
import pandas as pd

# Ensure NVIDIA CUDA DLLs are found by Windows dynamic linker
for sp in site.getsitepackages():
    for sub in ['cublas', 'cudnn', 'cuda_nvrtc']:
        p = os.path.join(sp, 'nvidia', sub, 'bin')
        if os.path.exists(p):
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(p)
                except Exception:
                    pass
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')

    cublas_bin = os.path.join(sp, 'nvidia', 'cublas', 'bin')
    if os.path.exists(cublas_bin):
        for dll_name in ['cublasLt64_12.dll', 'cublas64_12.dll']:
            dll_path = os.path.join(cublas_bin, dll_name)
            if os.path.exists(dll_path):
                try:
                    ctypes.CDLL(dll_path)
                except Exception:
                    pass

try:
    from rapidfuzz.distance import Levenshtein as rf_lev
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

# Import sibling evaluation modules
try:
    from .evaluation import (
        TextNormalizer,
        ASRMetricsCalculator,
        TerminologyOccurrence,
        TerminologyEvaluator,
        SafetyMetricsEvaluator,
        PairedBootstrapTester
    )
except (ImportError, ValueError):
    from evaluation import (
        TextNormalizer,
        ASRMetricsCalculator,
        TerminologyOccurrence,
        TerminologyEvaluator,
        SafetyMetricsEvaluator,
        PairedBootstrapTester
    )


# ==============================================================================
# 1. TAXONOMY & GLOSSARY MANAGER
# ==============================================================================

class TaxonomyManager:
    """Manages ISTQB CTFL v4.0.1 canonical terms and category lookups."""

    def __init__(self, taxonomy_path: str):
        self.taxonomy_path = taxonomy_path
        self.categories: Dict[str, List[str]] = {}
        self.term_to_category: Dict[str, str] = {}
        self.normalized_terms: Dict[str, str] = {}  # norm_term -> canonical_term
        self._load()

    def _load(self):
        if not os.path.exists(self.taxonomy_path):
            raise FileNotFoundError(f"Taxonomy file not found at: {self.taxonomy_path}")

        with open(self.taxonomy_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for cat_name, cat_data in data.get("categories", {}).items():
            terms = cat_data.get("terms", [])
            self.categories[cat_name] = terms
            for term in terms:
                self.term_to_category[term] = cat_name
                norm = TextNormalizer.normalize(term)
                self.normalized_terms[norm] = term

    @property
    def canonical_terms(self) -> List[str]:
        return list(self.term_to_category.keys())

    def get_category(self, term: str) -> str:
        norm = TextNormalizer.normalize(term)
        canonical = self.normalized_terms.get(norm, term)
        return self.term_to_category.get(canonical, "Unassigned")

    def create_glossary_prompt(self, prefix: str = "Các thuật ngữ kiểm thử phần mềm ISTQB: ") -> str:
        """
        Creates a contextual prompt string for Whisper containing domain terminology.
        """
        # Order terms systematically
        terms = sorted(self.canonical_terms)
        return prefix + ", ".join(terms) + "."


# ==============================================================================
# 2. SYSTEM B0: EXACT MATCHING & LOOKUP
# ==============================================================================

class ExactMatchingBaseline:
    """
    System B0: Case-insensitive exact substring matching of canonical terms
    within the ASR hypothesis.
    """

    def __init__(self, taxonomy: TaxonomyManager):
        self.taxonomy = taxonomy
        # Pre-sort normalized terms by word length descending (longest match priority)
        self.sorted_terms = sorted(
            self.taxonomy.canonical_terms,
            key=lambda t: len(t.split()),
            reverse=True
        )

    def extract_terms(self, text: str) -> List[TerminologyOccurrence]:
        if not text or pd.isna(text):
            return []

        norm_text = TextNormalizer.normalize(text)
        if not norm_text:
            return []

        # Find non-overlapping occurrences
        occurrences = []
        occupied_indices = set()

        for term in self.sorted_terms:
            norm_term = TextNormalizer.normalize(term)
            pattern = r'\b' + re.escape(norm_term) + r'\b'

            for m in re.finditer(pattern, norm_text):
                start, end = m.span()
                # Check for overlap
                span_indices = set(range(start, end))
                if not (span_indices & occupied_indices):
                    occupied_indices.update(span_indices)
                    occurrences.append(
                        TerminologyOccurrence(
                            term=term,
                            category=self.taxonomy.get_category(term)
                        )
                    )

        return occurrences


# ==============================================================================
# 3. SYSTEM B1: GLOSSARY PROMPTING ASR
# ==============================================================================

class GlossaryPromptingASR:
    """
    System B1: Contextual Biasing via Whisper initial_prompt.
    Injects domain terminology into the decoder context during beam search.
    """

    def __init__(
        self,
        taxonomy: TaxonomyManager,
        model_size: str = "small",
        device: str = "cuda",
        compute_type: str = "float16"
    ):
        self.taxonomy = taxonomy
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None
        self.prompt = self.taxonomy.create_glossary_prompt()
        self.exact_matcher = ExactMatchingBaseline(taxonomy)

    def load_model(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            try:
                print(f"[B1] Loading Whisper '{self.model_size}' on {self.device} ({self.compute_type})...")
                self.model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            except Exception as e:
                print(f"[B1] Failed to load on {self.device} ({e}), falling back to CPU int8...")
                self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def transcribe(
        self,
        audio_path: str,
        beam_size: int = 5
    ) -> Dict[str, Any]:
        self.load_model()
        t0 = time.time()

        segments, info = self.model.transcribe(
            audio_path,
            language="vi",
            task="transcribe",
            beam_size=beam_size,
            initial_prompt=self.prompt,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        seg_list = list(segments)
        full_text = " ".join([s.text.strip() for s in seg_list])
        avg_logprob = (
            sum([s.avg_logprob for s in seg_list]) / len(seg_list)
            if seg_list else -99.0
        )
        inf_time = round(time.time() - t0, 3)

        # Extract terms using exact matching on the prompted transcript
        extracted_terms = self.exact_matcher.extract_terms(full_text)

        return {
            "transcript": full_text,
            "avg_logprob": round(avg_logprob, 3),
            "inference_seconds": inf_time,
            "extracted_terms": extracted_terms
        }


# ==============================================================================
# 4. SYSTEM B2: LEXICAL FUZZY MATCHING
# ==============================================================================

class LexicalFuzzyMatcher:
    """
    System B2: Lexical-only Correction via Levenshtein / Token Similarity.
    Scans transcript n-gram windows and matches against glossary entries
    without acoustic or sentence context grounding.
    """

    def __init__(
        self,
        taxonomy: TaxonomyManager,
        similarity_threshold: float = 0.75,
        min_word_len: int = 3
    ):
        self.taxonomy = taxonomy
        self.threshold = similarity_threshold
        self.min_word_len = min_word_len
        self.canonical_terms = taxonomy.canonical_terms
        self.norm_terms = {
            t: TextNormalizer.normalize(t) for t in self.canonical_terms
        }
        self.term_word_counts = {
            t: len(self.norm_terms[t].split()) for t in self.canonical_terms
        }

    def _calc_similarity(self, s1: str, s2: str) -> float:
        if HAS_RAPIDFUZZ:
            return rf_lev.normalized_similarity(s1, s2)
        # Fallback to standard Python Levenshtein
        from .evaluation import compute_levenshtein_alignment
        s_c, d_c, i_c = compute_levenshtein_alignment(list(s1), list(s2))
        max_len = max(len(s1), len(s2))
        return 1.0 - ((s_c + d_c + i_c) / max_len) if max_len > 0 else 1.0

    def extract_terms(self, text: str) -> List[TerminologyOccurrence]:
        if not text or pd.isna(text):
            return []

        words = TextNormalizer.word_tokenize(text)
        n_words = len(words)
        if n_words == 0:
            return []

        candidates = []

        # Scan windows of length 1 to 4 words
        for w_len in range(1, min(5, n_words + 1)):
            for start_idx in range(n_words - w_len + 1):
                end_idx = start_idx + w_len
                span_words = words[start_idx:end_idx]
                span_text = " ".join(span_words)

                if len(span_text) < self.min_word_len:
                    continue

                for canonical, norm_t in self.norm_terms.items():
                    # Pruning: skip if word count differs by more than 1
                    t_w_len = self.term_word_counts[canonical]
                    if abs(w_len - t_w_len) > 1:
                        continue

                    sim = self._calc_similarity(span_text, norm_t)
                    if sim >= self.threshold:
                        candidates.append({
                            "canonical": canonical,
                            "category": self.taxonomy.get_category(canonical),
                            "similarity": sim,
                            "start": start_idx,
                            "end": end_idx,
                            "span_len": w_len
                        })

        if not candidates:
            return []

        # Sort candidates by:
        # 1. Similarity descending
        # 2. Span length descending (longer matches preferred)
        candidates.sort(key=lambda x: (x["similarity"], x["span_len"]), reverse=True)

        # Non-overlapping greedy selection
        occupied_word_indices = set()
        selected_occurrences = []

        for cand in candidates:
            cand_indices = set(range(cand["start"], cand["end"]))
            if not (cand_indices & occupied_word_indices):
                occupied_word_indices.update(cand_indices)
                selected_occurrences.append(
                    TerminologyOccurrence(
                        term=cand["canonical"],
                        category=cand["category"]
                    )
                )

        return selected_occurrences

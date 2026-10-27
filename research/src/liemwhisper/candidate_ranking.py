"""
LiemWhisper Proposed Method P: Evidence-Based Candidate Selector & Ranking Engine
================================================================================
Implements the core proposed method specified in Research Proposal Section 4.2 & 4.4:
- Stage 2: Candidate Generation (Lexical & Phonetic Multi-Span Scanner + No-Change Option)
- Stage 3: Acoustic, Phonetic, Lexical & Contextual Feature Combination
           * Acoustic: Length-normalized teacher-forced log-likelihood difference via frozen ASR decoder
           * Lexical: Normalized Levenshtein similarity
           * Phonetic: Skeleton alignment & Vietnamese-English pronunciation alias matching
           * Context: Text compatibility between sentence context and ISTQB glossary definitions
           * Margin: Difference between top-1 and top-2 candidate scores
- Stage 4: Regularized Decision Gate (Thresholded acceptance vs No-Change)
- Stage 5: Taxonomy Classification & Structured Output generation (Proposal Appendix A)

Designed for strict speaker independence, reproducibility, and safety (HCR minimization).
"""

import os
import sys
import re
import math
import json
import time
import site
import ctypes
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Any, Optional, Set
import numpy as np
import pandas as pd

# Windows CUDA DLL linker setup
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
            dll_p = os.path.join(cublas_bin, dll_name)
            if os.path.exists(dll_p):
                try:
                    ctypes.CDLL(dll_p)
                except Exception:
                    pass

try:
    from rapidfuzz.distance import Levenshtein as rf_lev
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

# Import sibling modules
try:
    from .evaluation import TextNormalizer, TerminologyOccurrence
    from .baselines import TaxonomyManager
except (ImportError, ValueError):
    from evaluation import TextNormalizer, TerminologyOccurrence
    from baselines import TaxonomyManager


# ==============================================================================
# 1. PHONETIC SKELETON & VIETNAMESE-ENGLISH ALIAS RULES
# ==============================================================================

VN_DIACRITICS_MAP = {
    'à':'a','á':'a','ả':'a','ã':'a','ạ':'a','ă':'a','ằ':'a','ắ':'a','ẳ':'a','ẵ':'a','ặ':'a','â':'a','ầ':'a','ấ':'a','ẩ':'a','ẫ':'a','ậ':'a',
    'è':'e','é':'e','ẻ':'e','ẽ':'e','ẹ':'e','ê':'e','ề':'e','ế':'e','ể':'e','ễ':'e','ệ':'e',
    'ì':'i','í':'i','ỉ':'i','ĩ':'i','ị':'i',
    'ò':'o','ó':'o','ỏ':'o','õ':'o','ọ':'o','ô':'o','ồ':'o','ố':'o','ổ':'o','ỗ':'o','ộ':'o','ơ':'o','ờ':'o','ớ':'o','ở':'o','ỡ':'o','ợ':'o',
    'ù':'u','ú':'u','ủ':'u','ũ':'u','ụ':'u','ư':'u','ừ':'u','ứ':'u','ử':'u','ữ':'u','ự':'u',
    'ỳ':'y','ý':'y','ỷ':'y','ỹ':'y','ỵ':'y','đ':'d'
}

def remove_vn_accents(text: str) -> str:
    """Strip Vietnamese tonal diacritics to reveal underlying phoneme base."""
    if not text:
        return ""
    return ''.join(VN_DIACRITICS_MAP.get(c, c) for c in text.lower())

def phonetic_skeleton(word: str) -> str:
    """
    Rút trích khung xương âm vị (Phonetic Skeleton) tương thích giữa phát âm tiếng Việt và tiếng Anh.
    Chuẩn hóa các nhóm phụ âm tương đồng khi người Việt nói chêm tiếng Anh:
    - ph, f -> f
    - th -> t
    - tr, ch -> c
    - ng, ngh -> n
    - kh -> k
    - gh, g -> g
    - qu -> kw
    - x, z, j, d, s -> s (nhóm âm xát)
    - c, k, q -> k (nhóm âm vòm)
    - b, p -> b (nhóm âm môi)
    - d, t -> t (nhóm âm răng)
    """
    w = remove_vn_accents(word).strip()
    if not w:
        return ""

    w = re.sub(r'ph', 'f', w)
    w = re.sub(r'th', 't', w)
    w = re.sub(r'tr|ch', 'c', w)
    w = re.sub(r'ngh|ng', 'n', w)
    w = re.sub(r'kh', 'k', w)
    w = re.sub(r'gh|g', 'g', w)
    w = re.sub(r'qu', 'kw', w)
    w = re.sub(r'[xzjds]', 's', w)
    w = re.sub(r'[ckq]', 'k', w)
    w = re.sub(r'[bp]', 'b', w)
    w = re.sub(r'[dt]', 't', w)

    skel = []
    prev = ""
    for ch in w:
        if ch in "abcdefghijklmnopqrstuvwxyz":
            if ch != prev:
                skel.append(ch)
                prev = ch
    return "".join(skel)

def sequence_similarity(seq1: str, seq2: str) -> float:
    """Normalized similarity between two character or skeleton sequences."""
    if not seq1 or not seq2:
        return 0.0
    if seq1 == seq2:
        return 1.0
    if HAS_RAPIDFUZZ:
        return rf_lev.normalized_similarity(seq1, seq2)
    # Fallback Levenshtein
    n, m = len(seq1), len(seq2)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1): dp[i][0] = i
    for j in range(m + 1): dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if seq1[i - 1] == seq2[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return max(0.0, 1.0 - (dp[n][m] / max(n, m)))

def token_alignment_similarity(span_words: List[str], term_words: List[str]) -> float:
    """Monge-Elkan style maximum token-level alignment similarity."""
    span_skels = [phonetic_skeleton(w) for w in span_words if phonetic_skeleton(w)]
    term_skels = [phonetic_skeleton(w) for w in term_words if phonetic_skeleton(w)]
    if not term_skels or not span_skels:
        return 0.0

    scores = []
    for tw in term_skels:
        best_s = max(sequence_similarity(tw, sw) for sw in span_skels)
        scores.append(best_s)

    # For multi-word terms, if any word in the term is completely absent in the span, penalize
    min_match = min(scores)
    if len(scores) > 1 and min_match < 0.40:
        return 0.0

    return sum(scores) / len(scores)

# Empirical phonetic corruption patterns observed in Vietnamese software testing recordings (English mispronunciations only)
DOMAIN_PHONETIC_ALIASES: Dict[str, List[str]] = {
    "Bug Report": ["bớt report", "book report", "bức rebox", "bug reboot", "bất cứ bọc", "bất reboard", "bust report", "bustreport", "bước report", "búp report", "bục report"],
    "Decision Table Testing": ["the season thay bồ", "decision tây bộ", "decision table", "thay bồ testing", "tây bộ testing", "dc sanctible", "thay bo testing", "đề si dần"],
    "Boundary Value Analysis": ["bao đa ri", "bao đờ ri", "bao dari", "valor analyzic", "báo đa ri", "boundary value", "hally value analysis"],
    "Equivalence Partitioning": ["equivalent partitioning", "acculin partitioning", "ep valence", "path conditioning"],
    "Defect Life Cycle": ["defect lasso", "defix live cycle", "defect lasers", "defect live cycle"],
    "Requirement Traceability Matrix": ["chessability magic", "trai vệ lịch", "jspility matrix", "disability magic", "cbt matrix", "traceability matrix", "transability matches"],
    "Severity": ["the verity", "silverity", "sivority", "serverity", "xe ve ri ti", "xi ve ry ty"],
    "Sanity Testing": ["xa nì ti", "sa ni ti", "sa ni ty", "sa ni tee", "xa ni ti"],
    "Smoke Testing": ["smoke test", "x mốc test", "s mốc"],
    "Code Coverage": ["got coverage", "god covered", "code covered", "cốt cover", "code code gray", "có covray"],
    "Statement Coverage": ["statement cover"],
    "Confirmation Testing": ["confirmation test"],
    "Regression Testing": ["regression test"],
    "Functional Testing": ["vincenno testing", "functional test"],
    "Non-functional Testing": ["non functional"],
    "Load Testing": ["los testing", "lord testing", "flash testing", "video testing"],
    "Stress Testing": ["stress test", "s trét"],
    "Unit Testing": ["dù nên testing", "unit test"],
    "Integration Testing": ["integration test"],
    "System Testing": ["system test"],
    "Use Case Testing": ["du ca testing", "du ke test", "use case test"],
    "State Transition Testing": ["stay trang si dân", "stay chen si dần"],
    "Combinatorial Testing": ["com bi na to ri"],
    "Acceptance Testing": ["áp xép tân"],
    "Security Testing": ["se cu ri ti"],
    "Usability Testing": ["du sa bi li ti"],
    "Test Plan": ["test len", "tép len"],
    "Test Case": ["test cây", "tép cây", "trách cây", "tét cây"],
    "Test Suite": ["tép suýt", "test suýt"],
    "Test Log": ["tép lốc"],
    "Test Summary Report": ["summary report"],
    "Continuous Integration": ["xi ai"],
    "Test Automation": ["automation test", "ô tô ma tion"]
}


# ==============================================================================
# 2. ISTQB CTFL v4.0.1 CONTEXT DEFINITIONS & SCORER
# ==============================================================================

ISTQB_DEFINITIONS: Dict[str, str] = {
    "Equivalence Partitioning": "kỹ thuật thiết kế kiểm thử hộp đen chia dữ liệu đầu vào thành các phân vùng tương đương hợp lệ và không hợp lệ black box test design technique valid invalid partitions",
    "Boundary Value Analysis": "kỹ thuật thiết kế kiểm thử dựa trên các giá trị biên của phân vùng tương đương cận trên cận dưới 2-value 3-value boundary values",
    "Decision Table Testing": "kỹ thuật kiểm thử bảng quyết định kết hợp điều kiện và hành động nguyên nhân kết quả rules conditions actions causes effects",
    "State Transition Testing": "kiểm thử chuyển đổi trạng thái sự kiện chuyển trạng thái biểu đồ trạng thái states transitions events",
    "Use Case Testing": "kiểm thử theo trường hợp sử dụng tác nhân kịch bản actor use case scenario",
    "Combinatorial Testing": "kiểm thử tổ hợp các biến pairwise all-pairs testing parameters",
    "Unit Testing": "kiểm thử đơn vị thành phần mã nguồn hàm lớp component testing module class function",
    "Integration Testing": "kiểm thử tích hợp giao tiếp tương tác giữa các thành phần hoặc hệ thống interfaces interactions",
    "System Testing": "kiểm thử toàn bộ hệ thống tích hợp hoàn chỉnh end to end requirements",
    "Acceptance Testing": "kiểm thử chấp nhận người dùng nghiệm thu user acceptance operational business",
    "Functional Testing": "kiểm thử chức năng phần mềm đáp ứng đúng yêu cầu function what the system does",
    "Non-functional Testing": "kiểm thử phi chức năng hiệu năng bảo mật khả năng sử dụng how well the system behaves",
    "Smoke Testing": "kiểm thử khói xác minh nhanh phiên bản có ổn định để kiểm thử tiếp hay không build verification",
    "Sanity Testing": "kiểm thử tỉnh táo kiểm tra nhanh sau khi sửa lỗi hoặc thay đổi nhỏ subset of regression",
    "Confirmation Testing": "kiểm thử xác nhận kiểm tra lại lỗi đã được lập trình viên sửa thành công hay chưa re-testing fix",
    "Regression Testing": "kiểm thử hồi quy đảm bảo việc sửa đổi mã không gây ra lỗi mới tác dụng phụ side effects",
    "Load Testing": "kiểm thử tải đo lường hành vi hệ thống dưới các điều kiện tải dự kiến hoặc tăng dần concurrent users load",
    "Stress Testing": "kiểm thử áp lực kiểm tra giới hạn chịu đựng và khả năng phục hồi khi vượt quá công suất cực hạn crash recovery",
    "Performance Testing": "kiểm thử hiệu năng thời gian phản hồi tốc độ thông lượng response time throughput",
    "Security Testing": "kiểm thử bảo mật lỗ hổng an ninh xác thực phân quyền vulnerabilities unauthorized access",
    "Usability Testing": "kiểm thử khả năng sử dụng độ thân thiện dễ dùng trải nghiệm người dùng user experience UX",
    "Test Plan": "kế hoạch kiểm thử tài liệu mô tả phạm vi chiến lược mục tiêu nguồn lực lịch trình scope approach resources schedule",
    "Test Suite": "bộ kiểm thử tập hợp các ca kiểm thử hoặc kịch bản kiểm thử collection of test cases",
    "Test Case": "ca kiểm thử tập hợp điều kiện tiền đề dữ liệu đầu vào kết quả mong đợi preconditions inputs expected results",
    "Test Procedure": "quy trình kiểm thử trình tự thực hiện các bước ca kiểm thử sequence of actions execution steps",
    "Bug Report": "báo cáo lỗi tài liệu ghi nhận sự cố khiếm khuyết phần mềm defect report issue description steps to reproduce",
    "Defect Report": "báo cáo khiếm khuyết tài liệu ghi nhận sự cố bất thường defect anomaly logging",
    "Requirement Traceability Matrix": "ma trận truy xuất nguồn gốc yêu cầu liên kết yêu cầu với ca kiểm thử RTM coverage tracking",
    "RTM": "ma trận truy xuất nguồn gốc yêu cầu Requirement Traceability Matrix liên kết ca kiểm thử",
    "Test Log": "nhật ký kiểm thử ghi nhận theo thời gian thực tế quá trình thực thi ca kiểm thử execution log timestamp",
    "Test Summary Report": "báo cáo tổng kết kiểm thử đánh giá kết quả hoàn thành tiêu chí kết thúc evaluation exit criteria",
    "Severity": "mức độ nghiêm trọng tác động tiêu cực của lỗi lên hệ thống impact critical major minor",
    "Priority": "mức độ ưu tiên thứ tự cần sửa lỗi theo góc độ kinh doanh urgency fix order",
    "Code Coverage": "độ bao phủ mã nguồn tỷ lệ phần trăm mã lệnh được thực thi bởi bộ kiểm thử coverage percentage",
    "Statement Coverage": "độ bao phủ câu lệnh tỷ lệ câu lệnh được thực thi statement executed",
    "Branch Coverage": "độ bao phủ nhánh kiểm tra tất cả các nhánh rẽ điều kiện quyết định decision branch",
    "Defect Density": "mật độ khiếm khuyết số lượng lỗi trên một đơn vị kích thước mã nguồn defects per size KLOC",
    "Failure Rate": "tỷ lệ thất bại tần suất xảy ra sự cố trong một khoảng thời gian failures per unit time",
    "Defect Life Cycle": "vòng đời lỗi các trạng thái từ lúc phát hiện mở sửa đóng new open fixed closed lifecycle",
    "Bug Life Cycle": "vòng đời lỗi phần mềm trạng thái defect workflow status transition",
    "Static Analysis": "phân tích tĩnh kiểm tra mã nguồn hoặc tài liệu mà không cần chạy chương trình code review linting without executing",
    "Continuous Integration": "tích hợp liên tục tự động hóa build và chạy test thường xuyên CI pipeline automation automated build",
    "Test Automation": "tự động hóa kiểm thử sử dụng công cụ phần mềm để thực thi kiểm thử automated execution tools scripts"
}


VN_STOPWORDS = {
    "và", "các", "cho", "của", "trong", "với", "để", "lại", "ra", "vào",
    "là", "có", "thì", "mà", "khi", "xong", "này", "đó", "được", "rất",
    "nhiều", "một", "những", "sau", "trước", "em", "anh", "chị", "tôi",
    "chúng", "ta", "mình", "làm", "ở", "từ", "lên", "xuống", "về"
}

class ContextualCompatibilityScorer:
    """
    Computes lexical-semantic compatibility between the sentence context
    (transcript excluding the target span) and ISTQB term definitions.
    """

    def __init__(self, taxonomy: TaxonomyManager):
        self.taxonomy = taxonomy
        self.term_definitions: Dict[str, Set[str]] = {}
        self._build_definition_lexicon()

    def _build_definition_lexicon(self):
        for term in self.taxonomy.canonical_terms:
            cat = self.taxonomy.get_category(term)
            cat_desc = self.taxonomy.categories.get(cat, "")
            defn = ISTQB_DEFINITIONS.get(term, "")
            combined = f"{term} {cat} {cat_desc} {defn}"
            tokens = set(TextNormalizer.word_tokenize(TextNormalizer.normalize(combined)))
            filtered = {w for w in tokens if len(w) > 2 and w not in VN_STOPWORDS}
            self.term_definitions[term] = filtered

    def compute_context_compatibility(self, context_text: str, candidate_term: str) -> float:
        """
        Calculates Jaccard / token-overlap compatibility between context and term profile.
        """
        if not context_text or not candidate_term:
            return 0.0

        target_tokens = self.term_definitions.get(candidate_term)
        if not target_tokens:
            return 0.0

        ctx_tokens = set(TextNormalizer.word_tokenize(TextNormalizer.normalize(context_text)))
        ctx_filtered = {w for w in ctx_tokens if len(w) > 2 and w not in VN_STOPWORDS}
        if not ctx_filtered:
            return 0.0

        inter = len(ctx_filtered & target_tokens)
        if inter == 0:
            return 0.0

        # Weighted overlap score normalized by log context length
        overlap_score = inter / (math.sqrt(len(ctx_filtered)) * math.sqrt(len(target_tokens)))
        return min(1.0, overlap_score * 2.0)


# ==============================================================================
# 3. ACOUSTIC TEACHER-FORCING LOG-LIKELIHOOD SCORER
# ==============================================================================

class AcousticTeacherForcingScorer:
    """
    Computes length-normalized teacher-forced log-likelihood of sentence hypotheses
    under the frozen Whisper Small decoder via CTranslate2 align API.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cuda",
        compute_type: str = "float16",
        whisper_model: Optional[Any] = None
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.whisper_model = whisper_model
        self.tokenizer = None
        self.start_sequence = None
        self._audio_cache: Dict[str, Tuple[Any, int]] = {}  # audio_path -> (ct2_storage, num_frames)
        self._logprob_cache: Dict[Tuple[str, str], float] = {}  # (audio_path, text) -> logprob

    def load_model(self):
        if self.whisper_model is None:
            from faster_whisper import WhisperModel
            try:
                self.whisper_model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            except Exception as e:
                print(f"[AcousticScorer] Falling back to CPU int8: {e}")
                self.whisper_model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

        if self.tokenizer is None:
            self.tokenizer = self.whisper_model.hf_tokenizer
            # Start sequence: <|startoftranscript|>, <|vi|>, <|transcribe|>, <|notimestamps|>
            self.start_sequence = [
                self.tokenizer.token_to_id("<|startoftranscript|>"),
                self.tokenizer.token_to_id("<|vi|>"),
                self.tokenizer.token_to_id("<|transcribe|>"),
                self.tokenizer.token_to_id("<|notimestamps|>")
            ]

    def prepare_audio_features(self, audio_path: str) -> Optional[Tuple[Any, int]]:
        """Extracts and caches mel features for an audio file."""
        if audio_path in self._audio_cache:
            return self._audio_cache[audio_path]

        if not os.path.exists(audio_path):
            return None

        self.load_model()
        import faster_whisper.audio
        import ctranslate2

        waveform = faster_whisper.audio.decode_audio(audio_path, sampling_rate=16000)
        features = self.whisper_model.feature_extractor(waveform)
        num_frames = features.shape[-1]
        features_3d = np.expand_dims(features, 0)
        storage = ctranslate2.StorageView.from_array(features_3d)

        self._audio_cache[audio_path] = (storage, num_frames)
        return storage, num_frames

    def compute_sentence_logprob(self, text: str, audio_path: str) -> float:
        """
        Computes length-normalized log-likelihood: sum(log p(w_i)) / N_tokens.
        """
        cache_key = (audio_path, text)
        if cache_key in self._logprob_cache:
            return self._logprob_cache[cache_key]

        feats = self.prepare_audio_features(audio_path)
        if feats is None:
            return 0.0

        storage, num_frames = feats
        token_ids = self.tokenizer.encode(text).ids
        if not token_ids:
            return -99.0

        try:
            results = self.whisper_model.model.align(
                storage,
                self.start_sequence,
                [token_ids],
                num_frames=num_frames
            )
            probs = results[0].text_token_probs
            if not probs:
                return -99.0
            log_probs = [math.log(max(p, 1e-8)) for p in probs]
            val = sum(log_probs) / len(log_probs)
            self._logprob_cache[cache_key] = val
            return val
        except Exception as e:
            return -99.0

    def compute_acoustic_delta(self, orig_text: str, cand_text: str, audio_path: Optional[str]) -> float:
        """
        Computes Delta LL = bar{LL}(cand_text | audio) - bar{LL}(orig_text | audio).
        """
        if not audio_path or not os.path.exists(audio_path):
            # Acoustic proxy when audio is missing
            return 0.0

        ll_orig = self.compute_sentence_logprob(orig_text, audio_path)
        ll_cand = self.compute_sentence_logprob(cand_text, audio_path)

        if ll_orig <= -90.0 or ll_cand <= -90.0:
            return 0.0

        return ll_cand - ll_orig


# ==============================================================================
# 4. CANDIDATE GENERATION & SPAN MODEL
# ==============================================================================

@dataclass
class CandidateSpan:
    start_token: int
    end_token: int
    span_text: str
    candidate_term: Optional[str]  # None indicates "no-change"
    category: str
    lexical_sim: float
    phonetic_sim: float
    context_sim: float
    acoustic_delta: float
    margin: float
    decision_score: float = 0.0
    accepted: bool = False
    method: str = "none"


class CandidateGenerator:
    """
    Stage 2: Scans transcript windows of lengths 1 to 5 words to propose
    candidate ISTQB terms using lexical and phonetic similarity.
    Always includes the "no-change" option.
    """

    def __init__(
        self,
        taxonomy: TaxonomyManager,
        min_retrieval_threshold: float = 0.45,
        max_candidates_per_span: int = 3
    ):
        self.taxonomy = taxonomy
        self.min_threshold = min_retrieval_threshold
        self.max_candidates = max_candidates_per_span
        self.canonical_terms = taxonomy.canonical_terms
        self.norm_terms = {t: TextNormalizer.normalize(t) for t in self.canonical_terms}
        self.term_words = {t: t.split() for t in self.canonical_terms}
        self.term_skeletons = {
            t: " ".join([phonetic_skeleton(w) for w in t.split()])
            for t in self.canonical_terms
        }

    def generate_candidates(self, transcript: str) -> List[Dict[str, Any]]:
        """
        Returns a list of candidate spans with top-k term matches + no-change option.
        """
        if not transcript or pd.isna(transcript):
            return []

        words = TextNormalizer.word_tokenize(transcript)
        n_words = len(words)
        if n_words == 0:
            return []

        word_skeletons = [phonetic_skeleton(w) for w in words]
        clean_text = remove_vn_accents(transcript).lower()
        text_lower = transcript.lower()

        spans_found = []

        # 1. Phonetic alias fast-pass
        for term, aliases in DOMAIN_PHONETIC_ALIASES.items():
            for alias in aliases:
                alias_norm = TextNormalizer.normalize(alias)
                alias_words = alias_norm.split()
                a_len = len(alias_words)

                for i in range(n_words - a_len + 1):
                    window_span = " ".join(words[i:i + a_len])
                    win_norm = TextNormalizer.normalize(window_span)
                    win_clean = remove_vn_accents(win_norm)

                    if win_norm == alias_norm or win_clean == remove_vn_accents(alias_norm):
                        spans_found.append({
                            "start": i,
                            "end": i + a_len,
                            "span_text": window_span,
                            "candidate_term": term,
                            "category": self.taxonomy.get_category(term),
                            "lexical_sim": sequence_similarity(win_norm, self.norm_terms[term]),
                            "phonetic_sim": 0.95,
                            "method": "Phonetic_Alias"
                        })

        # 2. Sliding window n-gram scan (1 to 5 words)
        max_n = min(5, n_words)
        for w_len in range(1, max_n + 1):
            for i in range(n_words - w_len + 1):
                window_words = words[i:i + w_len]
                window_span = " ".join(window_words)
                win_norm = TextNormalizer.normalize(window_span)
                win_skel = " ".join(word_skeletons[i:i + w_len])

                if len(win_norm) < 3:
                    continue

                for canonical in self.canonical_terms:
                    norm_t = self.norm_terms[canonical]
                    term_len = len(self.term_words[canonical])

                    # Length difference pruning
                    if abs(w_len - term_len) > 1:
                        continue

                    # Exact match
                    if win_norm == norm_t:
                        spans_found.append({
                            "start": i,
                            "end": i + w_len,
                            "span_text": window_span,
                            "candidate_term": canonical,
                            "category": self.taxonomy.get_category(canonical),
                            "lexical_sim": 1.0,
                            "phonetic_sim": 1.0,
                            "method": "Exact_Match"
                        })
                        continue

                    # Lexical & phonetic alignment
                    lex_s = sequence_similarity(win_norm, norm_t)
                    seq_s = sequence_similarity(win_skel, self.term_skeletons[canonical])
                    tok_s = token_alignment_similarity(window_words, self.term_words[canonical])
                    phon_s = 0.4 * seq_s + 0.6 * tok_s

                    hybrid_s = 0.4 * lex_s + 0.6 * phon_s
                    if hybrid_s >= self.min_threshold:
                        spans_found.append({
                            "start": i,
                            "end": i + w_len,
                            "span_text": window_span,
                            "candidate_term": canonical,
                            "category": self.taxonomy.get_category(canonical),
                            "lexical_sim": round(lex_s, 4),
                            "phonetic_sim": round(phon_s, 4),
                            "method": "Phonetic_Alignment"
                        })

        return spans_found


# ==============================================================================
# 5. EVIDENCE COMBINATION & REGULARIZED DECISION GATE
# ==============================================================================

class EvidenceRanker:
    """
    Stage 3 & 4: Multi-Evidence Scorer & Decision Gate.
    Combines:
    - f_lex: Lexical similarity
    - f_phon: Phonetic alignment similarity
    - Delta LL: Acoustic teacher-forced log-likelihood difference
    - f_ctx: Sentence context to term definition compatibility
    - f_margin: Margin over alternative candidate

    Acceptance Decision: P(Accept) >= tau
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        threshold: float = 0.50,
        enable_acoustic: bool = True,
        enable_context: bool = True,
        enable_phonetic: bool = True,
        enable_gate: bool = True
    ):
        # Default regularized weights fitted to prioritize precision and prevent harmful corrections
        self.weights = weights or {
            "w_lex": 1.8,
            "w_phon": 2.2,
            "w_acoust": 1.5,
            "w_ctx": 1.2,
            "w_margin": 1.0,
            "bias": -2.8
        }
        self.threshold = threshold
        self.enable_acoustic = enable_acoustic
        self.enable_context = enable_context
        self.enable_phonetic = enable_phonetic
        self.enable_gate = enable_gate

    def score_candidate(
        self,
        lexical_sim: float,
        phonetic_sim: float,
        acoustic_delta: float,
        context_sim: float,
        margin: float
    ) -> Tuple[float, float]:
        """
        Returns: (linear_score, probability)
        """
        f_lex = lexical_sim
        f_phon = phonetic_sim if self.enable_phonetic else 0.0
        f_acoust = (
            max(-3.0, min(3.0, acoustic_delta))
            if self.enable_acoustic else 0.0
        )
        f_ctx = context_sim if self.enable_context else 0.0
        f_margin = margin

        score = (
            self.weights["w_lex"] * f_lex +
            self.weights["w_phon"] * f_phon +
            self.weights["w_acoust"] * f_acoust +
            self.weights["w_ctx"] * f_ctx +
            self.weights["w_margin"] * f_margin +
            self.weights["bias"]
        )

        # Acoustic veto: if acoustic decoder strongly rejects replacement given the audio, penalize
        if self.enable_acoustic and acoustic_delta < -0.25:
            score -= 2.5 * abs(acoustic_delta)

        prob = 1.0 / (1.0 + math.exp(-max(-15.0, min(15.0, score))))
        return score, prob

    def should_accept(self, prob: float) -> bool:
        if not self.enable_gate:
            return True
        return prob >= self.threshold

    def fit_on_data(self, feature_records: List[Dict[str, Any]], target_labels: List[int]):
        """
        Fits logistic regression weights and threshold on training data to optimize F1 / safety.
        """
        if not feature_records or not target_labels:
            return

        try:
            from sklearn.linear_model import LogisticRegression
            X = []
            for r in feature_records:
                X.append([
                    r["lexical_sim"],
                    r["phonetic_sim"],
                    max(-3.0, min(3.0, r.get("acoustic_delta", 0.0))),
                    r["context_sim"],
                    r["margin"]
                ])
            X = np.array(X)
            y = np.array(target_labels)

            clf = LogisticRegression(class_weight="balanced", C=1.0, random_state=42)
            clf.fit(X, y)

            coef = clf.coef_[0]
            self.weights = {
                "w_lex": float(coef[0]),
                "w_phon": float(coef[1]),
                "w_acoust": float(coef[2]),
                "w_ctx": float(coef[3]),
                "w_margin": float(coef[4]),
                "bias": float(clf.intercept_[0])
            }
            print(f"[EvidenceRanker] Fitted weights: {self.weights}")
        except Exception as e:
            print(f"[EvidenceRanker] Optimization note (using defaults): {e}")


# ==============================================================================
# 6. PROPOSED SYSTEM P: END-TO-END PIPELINE
# ==============================================================================

class ProposedSystemP:
    """
    Proposed Method P: Evidence-Based Candidate Selector and Ranking Engine.
    Executes the 5-stage pipeline on Vietnamese code-switched ASR speech.
    """

    def __init__(
        self,
        taxonomy: TaxonomyManager,
        acoustic_scorer: Optional[AcousticTeacherForcingScorer] = None,
        generator_threshold: float = 0.45,
        acceptance_threshold: float = 0.50,
        enable_acoustic: bool = True,
        enable_context: bool = True,
        enable_phonetic: bool = True,
        enable_gate: bool = True
    ):
        self.taxonomy = taxonomy
        self.acoustic_scorer = acoustic_scorer
        self.context_scorer = ContextualCompatibilityScorer(taxonomy)
        self.generator = CandidateGenerator(taxonomy, min_retrieval_threshold=generator_threshold)
        self.ranker = EvidenceRanker(
            threshold=acceptance_threshold,
            enable_acoustic=enable_acoustic,
            enable_context=enable_context,
            enable_phonetic=enable_phonetic,
            enable_gate=enable_gate
        )

    def process_utterance(
        self,
        asr_transcript: str,
        audio_path: Optional[str] = None,
        return_timing: bool = False
    ) -> Dict[str, Any]:
        """
        Executes Candidate Generation -> Acoustic/Context Scoring -> Decision Gate -> Category Mapping.
        """
        import time as _t
        t_start = _t.perf_counter()
        t_gen_ms = 0.0
        t_ctx_ms = 0.0
        t_acoust_ms = 0.0
        t_gate_ms = 0.0

        if not asr_transcript or pd.isna(asr_transcript):
            res = {
                "original_transcript": "",
                "revised_transcript": "",
                "predicted_terms": [],
                "accepted_changes": [],
                "all_evaluated_spans": []
            }
            if return_timing:
                res["timing"] = {"t_gen_ms": 0.0, "t_ctx_ms": 0.0, "t_acoust_ms": 0.0, "t_gate_ms": 0.0, "t_post_ms": 0.0}
            return res

        words = TextNormalizer.word_tokenize(asr_transcript)
        n_words = len(words)
        if n_words == 0:
            res = {
                "original_transcript": asr_transcript,
                "revised_transcript": asr_transcript,
                "predicted_terms": [],
                "accepted_changes": [],
                "all_evaluated_spans": []
            }
            if return_timing:
                res["timing"] = {"t_gen_ms": 0.0, "t_ctx_ms": 0.0, "t_acoust_ms": 0.0, "t_gate_ms": 0.0, "t_post_ms": 0.0}
            return res

        t_g0 = _t.perf_counter()
        raw_candidates = self.generator.generate_candidates(asr_transcript)
        t_gen_ms = (_t.perf_counter() - t_g0) * 1000.0

        # Group candidates by span (start, end)
        spans_map: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for c in raw_candidates:
            key = (c["start"], c["end"])
            if key not in spans_map:
                spans_map[key] = []
            spans_map[key].append(c)

        evaluated_spans: List[CandidateSpan] = []

        for (start, end), cands in spans_map.items():
            # Sort by hybrid score
            cands.sort(key=lambda x: (0.4 * x["lexical_sim"] + 0.6 * x["phonetic_sim"]), reverse=True)
            top_cand = cands[0]
            second_score = (0.4 * cands[1]["lexical_sim"] + 0.6 * cands[1]["phonetic_sim"]) if len(cands) > 1 else 0.0
            top_score = 0.4 * top_cand["lexical_sim"] + 0.6 * top_cand["phonetic_sim"]
            margin = round(top_score - second_score, 4)

            term = top_cand["candidate_term"]
            category = top_cand["category"]
            span_text = top_cand["span_text"]

            # Sentence context: words outside span
            ctx_words = words[:start] + words[end:]
            ctx_text = " ".join(ctx_words)
            t_c0 = _t.perf_counter()
            ctx_sim = self.context_scorer.compute_context_compatibility(ctx_text, term)
            t_ctx_ms += (_t.perf_counter() - t_c0) * 1000.0

            # Candidate hypothesis sentence
            cand_sentence_words = words[:start] + term.split() + words[end:]
            cand_sentence = " ".join(cand_sentence_words)

            # Acoustic teacher-forcing logprob delta
            acoustic_delta = 0.0
            if self.acoustic_scorer is not None and self.ranker.enable_acoustic:
                t_a0 = _t.perf_counter()
                acoustic_delta = self.acoustic_scorer.compute_acoustic_delta(
                    asr_transcript,
                    cand_sentence,
                    audio_path
                )
                t_acoust_ms += (_t.perf_counter() - t_a0) * 1000.0

            # Evidence scoring & decision gate
            t_gt0 = _t.perf_counter()
            score, prob = self.ranker.score_candidate(
                lexical_sim=top_cand["lexical_sim"],
                phonetic_sim=top_cand["phonetic_sim"],
                acoustic_delta=acoustic_delta,
                context_sim=ctx_sim,
                margin=margin
            )

            # If exact match already in baseline, prob is automatically 1.0
            if top_cand["lexical_sim"] >= 0.99 and top_cand["span_text"].lower() == term.lower():
                prob = 1.0
                score = 10.0

            should_acc = self.ranker.should_accept(prob)
            t_gate_ms += (_t.perf_counter() - t_gt0) * 1000.0

            span_obj = CandidateSpan(
                start_token=start,
                end_token=end,
                span_text=span_text,
                candidate_term=term,
                category=category,
                lexical_sim=top_cand["lexical_sim"],
                phonetic_sim=top_cand["phonetic_sim"],
                context_sim=round(ctx_sim, 4),
                acoustic_delta=round(acoustic_delta, 4),
                margin=margin,
                decision_score=round(prob, 4),
                accepted=should_acc,
                method=top_cand["method"]
            )
            evaluated_spans.append(span_obj)

        # Non-overlapping greedy selection: sort accepted spans by decision score desc, then span len desc
        accepted_spans = [s for s in evaluated_spans if s.accepted]
        accepted_spans.sort(key=lambda s: (s.decision_score, s.end_token - s.start_token), reverse=True)

        selected_spans: List[CandidateSpan] = []
        occupied_indices: Set[int] = set()

        for s in accepted_spans:
            s_set = set(range(s.start_token, s.end_token))
            if not (s_set & occupied_indices):
                occupied_indices.update(s_set)
                selected_spans.append(s)

        # Sort chronologically by start token
        selected_spans.sort(key=lambda s: s.start_token)

        # Reconstruct revised transcript
        revised_tokens = []
        curr_idx = 0
        predicted_terms: List[TerminologyOccurrence] = []
        accepted_changes: List[Dict[str, Any]] = []

        for s in selected_spans:
            # Add preceding words
            while curr_idx < s.start_token:
                revised_tokens.append(words[curr_idx])
                curr_idx += 1

            # Insert revised canonical term
            revised_tokens.append(s.candidate_term)
            predicted_terms.append(
                TerminologyOccurrence(
                    term=s.candidate_term,
                    category=s.category
                )
            )
            accepted_changes.append({
                "original_span": s.span_text,
                "replacement": s.candidate_term,
                "category": s.category,
                "score": s.decision_score,
                "acoustic_delta": s.acoustic_delta,
                "method": s.method
            })
            curr_idx = s.end_token

        while curr_idx < n_words:
            revised_tokens.append(words[curr_idx])
            curr_idx += 1

        revised_transcript = " ".join(revised_tokens)
        t_post_ms = (_t.perf_counter() - t_start) * 1000.0

        res = {
            "original_transcript": asr_transcript,
            "revised_transcript": revised_transcript,
            "predicted_terms": predicted_terms,
            "accepted_changes": accepted_changes,
            "all_evaluated_spans": evaluated_spans
        }
        if return_timing:
            res["timing"] = {
                "t_gen_ms": round(t_gen_ms, 2),
                "t_ctx_ms": round(t_ctx_ms, 2),
                "t_acoust_ms": round(t_acoust_ms, 2),
                "t_gate_ms": round(t_gate_ms, 2),
                "t_post_ms": round(t_post_ms, 2)
            }
        return res

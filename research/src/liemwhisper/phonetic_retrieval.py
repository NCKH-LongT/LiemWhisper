"""
LiemWhisper Phonetic Retrieval Engine
Extracts, scores, and ranks technical domain candidates from Vietnamese code-switched ASR transcripts.
Addresses phonetic corruptions (e.g. 'bớt report' -> 'Bug Report', 'The Season thay bồ testing' -> 'Decision Table Testing').
"""

import re
import json
from typing import List, Dict, Tuple, Any

# Bảng quy đổi ký tự tiếng Việt có dấu sang không dấu
VN_DIACRITICS_MAP = {
    'à':'a','á':'a','ả':'a','ã':'a','ạ':'a','ă':'a','ằ':'a','ắ':'a','ẳ':'a','ẵ':'a','ặ':'a','â':'a','ầ':'a','ấ':'a','ẩ':'a','ẫ':'a','ậ':'a',
    'è':'e','é':'e','ẻ':'e','ẽ':'e','ẹ':'e','ê':'e','ề':'e','ế':'e','ể':'e','ễ':'e','ệ':'e',
    'ì':'i','í':'i','ỉ':'i','ĩ':'i','ị':'i',
    'ò':'o','ó':'o','ỏ':'o','õ':'o','ọ':'o','ô':'o','ồ':'o','ố':'o','ổ':'o','ỗ':'o','ộ':'o','ơ':'o','ờ':'o','ớ':'o','ở':'o','ỡ':'o','ợ':'o',
    'ù':'u','ú':'u','ủ':'u','ũ':'u','ụ':'u','ư':'u','ừ':'u','ứ':'u','ử':'u','ữ':'u','ự':'u',
    'ỳ':'y','ý':'y','ỷ':'y','ỹ':'y','ỵ':'y','đ':'d'
}

def remove_vn_accents(text: str) -> str:
    return ''.join(VN_DIACRITICS_MAP.get(c, c) for c in text.lower())

def phonetic_skeleton(word: str) -> str:
    """
    Rút trích khung xương âm vị (Phonetic Skeleton) tương thích giữa phát âm tiếng Việt và tiếng Anh.
    Chuẩn hóa các cặp âm đồng âm hoặc dễ nhầm lẫn trong ngữ cảnh Việt:
    - ph, f -> F
    - th -> T
    - tr, ch -> C
    - d, gi, r, z, s, x -> S (nhóm âm xát)
    - b, p -> B (nhóm âm môi)
    - c, k, q -> K (nhóm âm vòm)
    - g, gh -> G
    """
    w = remove_vn_accents(word).strip()
    if not w:
        return ""
    
    # Thay the cac cum phu am tieng Viet / Anh dac thu
    w = re.sub(r'ph', 'f', w)
    w = re.sub(r'th', 't', w)
    w = re.sub(r'tr|ch', 'c', w)
    w = re.sub(r'ngh|ng', 'n', w)
    w = re.sub(r'kh', 'k', w)
    w = re.sub(r'gh|g', 'g', w)
    w = re.sub(r'qu', 'kw', w)
    w = re.sub(r'[xzjds]', 's', w)
    w = re.sub(r'[c kq]', 'k', w)
    w = re.sub(r'[bp]', 'b', w)
    w = re.sub(r'[dt]', 't', w)
    
    # Giu lai nguyen am dau va cac phu am dai dien
    skel = []
    prev = ""
    for ch in w:
        if ch in "abcdefghijklmnopqrstuvwxyz":
            # Loai bo trung lap phu am lien tiep
            if ch != prev:
                skel.append(ch)
                prev = ch
    return "".join(skel)

def sequence_similarity(seq1: str, seq2: str) -> float:
    """Tinh do tuong dong Levenshtein chuan hoa giua 2 chuoi am vi [0.0 - 1.0]."""
    if not seq1 or not seq2:
        return 0.0
    if seq1 == seq2:
        return 1.0
    
    n, m = len(seq1), len(seq2)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
        
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if seq1[i - 1] == seq2[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
            
    dist = dp[n][m]
    max_len = max(n, m)
    return max(0.0, 1.0 - (dist / max_len))

def token_alignment_similarity(span_words: List[str], term_words: List[str]) -> float:
    """Tinh do tuong dong Monge-Elkan giua cac token am vi cua span va thuat ngu."""
    span_skels = [phonetic_skeleton(w) for w in span_words if phonetic_skeleton(w)]
    term_skels = [phonetic_skeleton(w) for w in term_words if phonetic_skeleton(w)]
    if not term_skels or not span_skels:
        return 0.0
    
    scores = []
    for tw in term_skels:
        best_s = max(sequence_similarity(tw, sw) for sw in span_skels)
        scores.append(best_s)
    return sum(scores) / len(scores)

# Bang quy uoc cac mau bien dang phat am dac thu giua tieng Anh va tieng Viet (Phonetic Alias Map)
DOMAIN_PHONETIC_ALIASES = {
    "Bug Report": ["bớt report", "book report", "bức rebox", "bug reboot", "bất cứ bọc", "bất reboard", "bust report", "bustreport", "bước report"],
    "Decision Table Testing": ["the season thay bồ", "decision tây bộ", "decision table", "thay bồ testing", "tây bộ testing", "dc sanctible", "thay bo testing"],
    "Boundary Value Analysis": ["bao đa ri", "bao đờ ri", "bao dari", "valor analyzic", "báo đa ri", "boundary value", "giá trị biên"],
    "Equivalence Partitioning": ["equivalent partitioning", "acculin partitioning", "ep valence", "phân vùng tương đương"],
    "Defect Life Cycle": ["defect lasso", "defix live cycle", "defect lasers", "defect live cycle", "vòng đời lỗi"],
    "Requirement Traceability Matrix": ["chessability magic", "trai vệ lịch", "jspility matrix", "disability magic", "cbt matrix", "traceability matrix", "ma trận truy xuất"],
    "Severity": ["the verity", "silverity", "sivority", "serverity", "xe ve ri ti"],
    "Sanity Testing": ["xa nì ti", "sa ni ti", "sa ni ty", "sa ni tee", "xa ni ti"],
    "Smoke Testing": ["smoke test", "x mốc test", "s mốc"],
    "Code Coverage": ["got coverage", "god covered", "code covered", "cốt cover", "code code gray", "độ bao phủ mã"],
    "Statement Coverage": ["statement cover", "độ bao phủ câu lệnh"],
    "Confirmation Testing": ["confirmation test", "kiểm thử xác nhận"],
    "Regression Testing": ["regression test", "kiểm thử hồi quy"],
    "Functional Testing": ["vincenno testing", "functional test", "kiểm thử chức năng"],
    "Non-functional Testing": ["non functional", "phi chức năng"],
    "Load Testing": ["los testing", "lord testing", "kiểm thử tải"],
    "Stress Testing": ["stress test", "s trét"],
    "Unit Testing": ["dù nên testing", "unit test"],
    "Integration Testing": ["integration test", "kiểm thử tích hợp"],
    "System Testing": ["system test", "kiểm thử hệ thống"]
}

class LiemWhisperPhoneticRetrieval:
    def __init__(self, taxonomy_path: str):
        with open(taxonomy_path, "r", encoding="utf-8") as f:
            tax = json.load(f)
            
        self.term_to_category = {}
        self.canonical_terms = []
        self.term_skeletons = {}
        self.term_words = {}
        
        for cat, data in tax["categories"].items():
            for term in data["terms"]:
                self.canonical_terms.append(term)
                self.term_to_category[term] = cat
                words = term.split()
                self.term_words[term] = words
                skel_words = [phonetic_skeleton(w) for w in words]
                self.term_skeletons[term] = " ".join(skel_words)

    def retrieve_candidates(self, transcript: str, top_k: int = 5, min_threshold: float = 0.50) -> List[Dict[str, Any]]:
        if not transcript or not transcript.strip():
            return []
            
        clean_text = remove_vn_accents(transcript)
        words = transcript.strip().split()
        if not words:
            return []
            
        word_skeletons = [phonetic_skeleton(w) for w in words]
        candidates_scores = {}

        # 1. Tra cứu theo Alias Map (Heuristic Fast-Path)
        text_lower = transcript.lower()
        for term, aliases in DOMAIN_PHONETIC_ALIASES.items():
            for alias in aliases:
                if alias in text_lower or alias in clean_text:
                    score = 0.95
                    if term not in candidates_scores or score > candidates_scores[term]["score"]:
                        candidates_scores[term] = {
                            "term": term,
                            "category": self.term_to_category.get(term, "General"),
                            "score": score,
                            "matched_span": alias,
                            "method": "Phonetic_Alias_Rule"
                        }

        # 2. Sliding window n-gram kết hợp Skeleton & Token-level Alignment
        max_n = min(5, len(words))
        for n in range(1, max_n + 1):
            for i in range(len(words) - n + 1):
                window_words = words[i:i+n]
                window_skel = " ".join(word_skeletons[i:i+n])
                raw_span = " ".join(window_words)
                
                for term in self.canonical_terms:
                    term_skel = self.term_skeletons[term]
                    
                    # Exact match
                    if term.lower() in raw_span.lower():
                        score = 1.0
                        method = "Exact_Match"
                    else:
                        seq_s = sequence_similarity(window_skel, term_skel)
                        tok_s = token_alignment_similarity(window_words, self.term_words[term])
                        score = 0.4 * seq_s + 0.6 * tok_s
                        method = "Phonetic_Alignment"
                        
                    if score >= min_threshold:
                        if term not in candidates_scores or score > candidates_scores[term]["score"]:
                            candidates_scores[term] = {
                                "term": term,
                                "category": self.term_to_category.get(term, "General"),
                                "score": round(score, 4),
                                "matched_span": raw_span,
                                "method": method
                            }
                            
        sorted_candidates = sorted(candidates_scores.values(), key=lambda x: x["score"], reverse=True)
        return sorted_candidates[:top_k]

"""
LiemWhisper Open-Vocabulary Synthetic Parallel Corpus Generator
==============================================================
Generates large-scale paired training data (X_noisy, Y_clean) for
End-to-End Neural Code-Switched ASR Post-Correction without dictionary lookup.

Simulates realistic cross-lingual Vietnamese loanword phonology:
- Vowel lengthening & Magic-E shifts
- Syllable splitting (polysyllabic English -> monosyllabic Vietnamese)
- Coda unvoicing and cluster simplification
- Whisper acoustic homophone confusions in bilingual software engineering contexts
"""

import os
import sys
import re
import json
import random
from typing import List, Tuple, Dict, Any

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Extensive Open-Vocabulary Technical Concepts (across QA, Dev, DevOps, Security, Cloud, Data)
TECHNICAL_ENTITIES: Dict[str, List[str]] = {
    # QA & Testing Concepts
    "Unit Testing": ["dù nên testing", "unit test", "du nịt test", "du nít test", "du nịt testing"],
    "Integration Testing": ["integration test", "in te gờ rây sần", "in te gray sần", "in te gờ ray sần"],
    "Regression Testing": ["regression test", "ri gét sần", "ri gót sừn", "re gres sion", "ri gét sơn"],
    "Smoke Testing": ["smoke test", "x mốc test", "s mốc", "x mốc testing"],
    "Sanity Testing": ["xa nì ti", "sa ni ti", "sa ni ty", "sa ni ti testing"],
    "Load Testing": ["los testing", "lord testing", "lốt testing", "lót test"],
    "Stress Testing": ["stress test", "s trét", "x trét testing", "x trét test"],
    "Boundary Value Analysis": ["bao đa ri", "bao đờ ri", "báo đa ri", "báo đơ ri", "ban đơ ri", "bao da ri value"],
    "Equivalence Partitioning": ["equivalent partitioning", "ep valence", "i qui va len", "ê qui va len", "e quy va len"],
    "Decision Table Testing": ["the season thay bồ", "decision tây bộ", "decision table", "thay bồ testing", "đề si dần tây bồ"],
    "State Transition Testing": ["stay trang si dân", "stay chen si dần", "stage transition testing", "steit tran si son"],
    "Exploratory Testing": ["ếch bờ lo ra to ri", "ếch lo ra to ri", "exploratory test", "ếch plo ra to ri"],
    "Bug Report": ["bớt report", "book report", "bức rebox", "bug reboot", "bất reboard", "bớt rì pọt"],
    "Test Plan": ["test len", "tép len", "tét len", "kế hoạch test len"],
    "Test Case": ["test cây", "tép cây", "trách cây", "tét cây"],
    "Test Suite": ["tép suýt", "test suýt", "tét suýt"],
    "Code Coverage": ["got coverage", "god covered", "cốt cover", "cốt covray", "có covray"],
    "Defect Density": ["đi phếch đen xi ti", "đi phét đen si ti", "defect đen si ti"],
    
    # Software Architecture & Concurrency
    "Race Condition": ["ray condition", "freq condition", "rây condition", "reit condition", "rây con đi sần"],
    "Deadlock": ["đét lốc", "đét lock", "đẹt lốc", "dead lock", "đết lốc"],
    "Idempotency": ["emdem potency", "ai đem po tân si", "ai đem bô tân si", "ai đem potency", "em dem potency"],
    "Error Handling": ["aaron handling", "e rơ handling", "e ro handling", "e rơ hen đơ lin", "e rơ hen đinh"],
    "Timeout Handling": ["tham áo hand over link", "tai mau handling", "tai mờ ao handling", "time out handling"],
    "Data Consistency": ["data consistent", "đây ta con sít tân si", "đây ta con sít tân", "đata consistency"],
    "Data Integrity": ["data entity", "đây ta in te gờ ri ti", "đata in te gờ ri ti", "đây ta in te gờ ti"],
    "Latency": ["lay tân xi", "lây tân si", "lay ten cy", "lê tân si"],
    "Throughput": ["thơ rút bứt", "tru pút", "thu rút pút", "thô rút bứt"],
    "Concurrency": ["con cơ rơn si", "con cu ren cy", "cơn cơ rần si"],
    "Microservices": ["mai cờ rô xơ vít", "mai cro sơ vịt", "micro service", "mai cờ rô sơ vịt"],
    "API Gateway": ["a pi ai gét guây", "api gết guây", "a pi ai get way"],
    "Load Balancer": ["lốt ba lăng xơ", "lốt ba lơn sơ", "lốt ba lăng sơ"],
    "Reverse Proxy": ["ri vớt p rốc xi", "ri vớt bờ rốc xi", "reverse bờ rốc xi"],
    "Webhook": ["oép húc", "uép húc", "web húc", "góp húc"],
    "Message Broker": ["mét xịt bờ râu cơ", "mét xịt bờ rốc cơ", "méc sít broker"],
    "Cache Invalidation": ["cát in va li đê sần", "ke in va li đê sừn", "két in va li đay sần"],
    "Read Replica": ["rít rép li ca", "read rép li ca", "rít rép li cờ"],
    "Sharding": ["xát đinh", "xa đinh", "xạc đinh"],
    
    # Security & Vulnerabilities
    "Authentication": ["o ten ti cây sần", "authentication", "ót then ti cây sừn", "ót ten ti ca sần"],
    "Authorization": ["o tô rai cây sần", "authorization", "ót to rai cây sần", "o tho rai zây sừn"],
    "Privilege Escalation": ["revalence excavulation", "pri vi le j es ka ley son", "bờ ri vi lịt ét ca la sần"],
    "Session Hijacking": ["session ejection", "xét sừn hai giắc kinh", "xét sần hai dách kinh", "session hai giắc kinh"],
    "SQL Injection": ["sva injection", "ét quy eo in dếch sần", "xít cu lờ in dếch sần", "sql in dếch sần"],
    "Cross-Site Scripting": ["cross size rift binh", "cờ rốt xai xờ cờ ríp tinh", "cờ rốt sai scrip tin", "cross site scrip tin"],
    "XSS": ["ích ét ét", "ếch ét ét", "xét ét"],
    "CSRF": ["xi ét a rếp", "xi ét a ref", "xi ét a ép"],
    "Brute Force": ["bờ rút phốt", "bờ rút pho", "bu rút phốt"],
    "Rate Limiting": ["rết li mi ting", "rây li mít ting", "rết li mít đinh"],
    "Zero Trust": ["di rô trớt", "ze ro trớt", "di rô trót"],
    "Firewall": ["phai o quô", "phai o oal", "phai qua"],
    
    # DevOps & Infrastructure
    "Continuous Integration": ["xi ai", "xi ai si đi", "ci cd", "con ti nu ớt in te gray sần"],
    "Test Automation": ["automation test", "ô tô ma tion", "ô tô may sừn", "ô tô may sần"],
    "Docker Container": ["đốc cơ con tai nơ", "đốc cơ cơn tê nơ", "đốc cơ con ten nơ"],
    "Kubernetes": ["cu bơ ne tít", "cu bơ nét tịt", "k8s", "cu bơ nết tít"],
    "Rolling Update": ["râu linh úp đết", "rô linh úp đết", "rô linh update"],
    "Autoscaling": ["ô tô scây linh", "ô tô skey lin", "ô tô sờ cây linh"],
    "Service Mesh": ["xơ vít mét", "sơ vịt mét", "sơ vít mesh"]
}

ASR_CONTEXT_CORRUPTIONS: Dict[str, str] = {
    "kiểm thử": "kiểm tự",
    "hệ thống": "hệ hỏng",
    "quản lý": "bản lý",
    "cần xác minh": "cần sắc minh",
    "lỗ hổng": "lo hộp",
    "đồng thời": "động thòi",
    "tiềm ẩn": "tùy mẩn",
    "trực tuyến": "trực tiếp",
    "khi client": "khi cờ lai ừn",
    "gửi request": "gửi rì quét",
    "kết nối mạng": "kết đó mạng"
}

SENTENCE_TEMPLATES = [
    # QA Testing Templates
    "Trong quá trình kiểm thử {domain}, QA cần thực hiện {term1} để phát hiện các lỗi tiềm ẩn, đồng thời kiểm tra khả năng xử lý {term2}, tính nhất quán dữ liệu ({term3}) và cơ chế {term4} khi nhiều giao dịch được gửi đồng thời.",
    "Khi kiểm thử API {domain}, QA cần đánh giá khả năng xử lý {term1}, phát hiện các trường hợp {term2}, kiểm tra cơ chế {term3} và xác minh tính toàn vẹn dữ liệu ({term4}) khi client liên tục gửi request trong điều kiện kết nối mạng không ổn định.",
    "Hôm nay sau khi dev deploy bản build mới, team tester đã tiến hành chạy {term1} và phát hiện một {term2} nghiêm trọng cần lập {term3} ngay.",
    "Để đảm bảo chất lượng phát hành, chúng ta bắt buộc phải đo lường {term1}, áp dụng kỹ thuật {term2} và kết hợp {term3} cho toàn bộ các module thanh toán.",
    "Khi xây dựng tài liệu kiểm thử cho sprint này, QA lead yêu cầu cập nhật lại {term1}, rà soát toàn bộ {term2} và chuẩn bị {term3} cho buổi nghiệm thu.",
    
    # Software Architecture & Backend Templates
    "Hệ thống backend sử dụng kiến trúc {term1} kết hợp với {term2} nhằm giảm thiểu {term3} và tối ưu hóa {term4} cho hàng triệu người dùng cùng lúc.",
    "Để tránh sự cố xung đột dữ liệu giữa các tiến trình, lập trình viên cần triển khai cơ chế {term1}, phòng tránh rủi ro {term2} và thiết lập chính sách {term3} một cách chặt chẽ.",
    "Khi nhiều worker cùng cập nhật vào cơ sở dữ liệu phân tán, việc xử lý {term1} và duy trì {term2} là điều kiện bắt buộc để bảo toàn {term3}.",
    "Kiến trúc sư hệ thống đề xuất bổ sung {term1} phía trước cụm dịch vụ, đồng thời kích hoạt cơ chế {term2} để bảo vệ hệ thống khi {term3} vượt ngưỡng cho phép.",
    
    # Security Templates
    "Khi kiểm thử hệ thống quản lý người dùng, QA cần xác minh cơ chế {term1}, {term2}, kiểm tra khả năng ngăn chặn {term3}, phát hiện lỗ hổng {term4} và đánh giá khả năng bảo vệ dữ liệu trước các cuộc tấn công {term5} và {term6}.",
    "Nhóm an toàn thông tin đang rà soát các lỗ hổng {term1} và {term2}, đặc biệt chú trọng nguy cơ {term3} qua các endpoint công khai và nguy cơ {term4} trong phiên đăng nhập.",
    "Chính sách bảo mật của ngân hàng yêu cầu áp dụng mô hình {term1}, kích hoạt cơ chế {term2} và tiến hành {term3} định kỳ hàng quý.",
    "Khi phát hiện nghi vấn tấn công {term1}, tường lửa ứng dụng sẽ tự động kích hoạt cơ chế {term2} và ngắt các kết nối có dấu hiệu {term3} ngay lập tức.",
    
    # DevOps Templates
    "Pipeline {term1} đã được tích hợp thành công trên cụm {term2}, hỗ trợ chiến lược triển khai {term3} mà không làm gián đoạn dịch vụ của người dùng.",
    "Toàn bộ ứng dụng được đóng gói trong các {term1}, tự động mở rộng theo nhu cầu nhờ cơ chế {term2} và được quản lý tập trung qua {term3}."
]

DOMAINS = [
    "thanh toán trực tuyến",
    "đặt phòng khách sạn",
    "thương mại điện tử",
    "ví điện tử ngân hàng",
    "quản lý kho vận",
    "giao dịch chứng khoán",
    "đặt xe công nghệ",
    "quản lý chuỗi cung ứng"
]

class SyntheticCorpusGenerator:
    """
    Generates realistic paired training samples (corrupted_input, clean_target)
    for training Seq2Seq Neural Error Correction models.
    """

    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.entities = TECHNICAL_ENTITIES
        self.term_names = list(self.entities.keys())

    def corrupt_term(self, term: str) -> str:
        """Returns a realistic phonetic corruption for a technical loanword."""
        if term in self.entities and self.entities[term]:
            return random.choice(self.entities[term])
        return term.lower()

    def corrupt_sentence(self, clean_text: str, inserted_terms: List[str]) -> str:
        """
        Takes a clean sentence and applies realistic ASR phonetic corruptions
        to technical terms and probabilistic homophone shifts to surrounding context.
        """
        noisy_text = clean_text

        # 1. Corrupt technical terms
        for term in inserted_terms:
            corrupted = self.corrupt_term(term)
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            noisy_text = pattern.sub(corrupted, noisy_text, count=1)

        # 2. Probabilistically corrupt context words to mimic Whisper speech noise
        words = noisy_text.split()
        for i, w in enumerate(words):
            if random.random() < 0.08:
                for clean_kw, corrupt_kw in ASR_CONTEXT_CORRUPTIONS.items():
                    if clean_kw in w.lower():
                        words[i] = w.lower().replace(clean_kw, corrupt_kw)
                        break

        noisy_result = " ".join(words)
        if random.random() < 0.7:
            noisy_result = noisy_result[0].lower() + noisy_result[1:]
        noisy_result = noisy_result.replace("(", "").replace(")", "").replace(",", "")

        return noisy_result

    def generate_sample(self) -> Tuple[str, str]:
        """Generates a single (corrupted_input, clean_target) pair."""
        template = random.choice(SENTENCE_TEMPLATES)
        domain = random.choice(DOMAINS)

        num_terms = len(re.findall(r'\{term\d+\}', template))
        selected_terms = random.sample(self.term_names, k=min(num_terms, len(self.term_names)))

        term_kwargs = {f"term{i+1}": t for i, t in enumerate(selected_terms)}
        clean_text = template.format(domain=domain, **term_kwargs)

        noisy_text = self.corrupt_sentence(clean_text, selected_terms)
        return noisy_text, clean_text

    def generate_dataset(self, num_samples: int = 5000) -> List[Dict[str, str]]:
        """Generates a dataset of N parallel pairs."""
        dataset = []
        for _ in range(num_samples):
            noisy, clean = self.generate_sample()
            dataset.append({
                "input_text": noisy,
                "target_text": clean
            })
        return dataset

    def export_dataset(self, output_dir: str, train_size: int = 4000, val_size: int = 500, test_size: int = 500):
        """Exports train/val/test splits to jsonl files."""
        os.makedirs(output_dir, exist_ok=True)
        total = train_size + val_size + test_size
        print(f"[SyntheticGenerator] Generating {total} parallel code-switched training samples...")
        
        all_samples = self.generate_dataset(total)
        random.shuffle(all_samples)

        train_data = all_samples[:train_size]
        val_data = all_samples[train_size:train_size + val_size]
        test_data = all_samples[train_size + val_size:]

        for name, data in [("train.jsonl", train_data), ("val.jsonl", val_data), ("test.jsonl", test_data)]:
            path = os.path.join(output_dir, name)
            with open(path, "w", encoding="utf-8") as f:
                for entry in data:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(f"  -> Exported {len(data)} samples to {path}")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.abspath(os.path.join(base_dir, "..", "..", "..", "..", "..", "Data", "synthetic_neural_corpus"))
    generator = SyntheticCorpusGenerator(seed=2026)
    generator.export_dataset(out_dir, train_size=2500, val_size=300, test_size=300)

    sample_n, sample_c = generator.generate_sample()
    print("\n" + "=" * 80)
    print("SAMPLE SYNTHETIC PARALLEL PAIR PREVIEW:")
    print("=" * 80)
    print("Noisy Input (Whisper Simulation):\n ", sample_n)
    print("\nClean Target:\n ", sample_c)

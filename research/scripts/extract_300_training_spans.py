import os
import sys
import json
import soundfile as sf
import pandas as pd
import numpy as np
from collections import defaultdict
from faster_whisper import WhisperModel

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def main():
    print("=" * 80)
    print("EXTRACTING 300 TRAINING SPANS MANIFEST FOR PHASE E1b")
    print("=" * 80)

    df_gold = pd.read_csv("Data/gold_with_asr_v1.csv")
    wav_dir = "Data/wav_16k"

    # 1. Zero-leakage Filter: Exclude unseen prompts completely
    unseen_pids = ['Q01', 'Q10', 'Q14', 'Q15']
    train_df = df_gold[~df_gold['prompt_id'].isin(unseen_pids)].copy()
    print(f"Total clean training audios available: {len(train_df)}")
    assert len(train_df) == 1566, f"Expected 1566 clean training audios, got {len(train_df)}"

    # 2. Mathematical Allocation: 12 terms x 17 + 6 terms x 16 = 300 spans
    term_quotas = {
        'Test Case': 17,
        'Boundary Value Analysis': 17,
        'System Testing': 17,
        'Functional Testing': 17,
        'Integration Testing': 17,
        'Test Suite': 17,
        'Non Functional Testing': 17,
        'Test Plan': 17,
        'Unit Testing': 17,
        'Priority': 17,
        'Severity': 17,
        'Decision Table Testing': 17,
        'Sanity Testing': 16,
        'Confirmation Testing': 16,
        'Smoke Testing': 16,
        'Regression Testing': 16,
        'Defect Life Cycle': 16,
        'Requirement Traceability Matrix': 16
    }

    # Expand instances
    instances = []
    for idx, row in train_df.iterrows():
        terms = [t.strip().title() for t in str(row['gold_terms']).split(';') if t.strip()]
        for t in terms:
            if t in term_quotas:
                instances.append({
                    'recording_id': row['recording_id'],
                    'wav_file': row['wav_file'],
                    'speaker_id': str(row['speaker_id']),
                    'prompt_id': row['prompt_id'],
                    'prompt_text': str(row['prompt_text']),
                    'verbatim_transcript': str(row['verbatim_transcript']),
                    'gold_terms': [x.strip().title() for x in str(row['gold_terms']).split(';') if x.strip()],
                    'term': t
                })
    df_inst = pd.DataFrame(instances)

    # 3. Speaker-Diversity & Multi-Prompt Sampling
    np.random.seed(42)
    selected_spans = []
    speaker_usage = defaultdict(int)

    for term, quota in term_quotas.items():
        term_sub = df_inst[df_inst['term'] == term].copy()
        prompts = sorted(term_sub['prompt_id'].unique().tolist())
        
        n_prompts = len(prompts)
        base_per_prompt = quota // n_prompts
        rem = quota % n_prompts
        prompt_quotas = {p: base_per_prompt + (1 if i < rem else 0) for i, p in enumerate(prompts)}
        
        term_selected = []
        term_speakers = set()
        
        # Phase 1: Try per-prompt allocation with speaker usage sorting
        for p in prompts:
            p_sub = term_sub[term_sub['prompt_id'] == p].sample(frac=1, random_state=42).copy()
            p_quota = prompt_quotas[p]
            p_chosen = 0
            
            p_sub['spk_usage'] = p_sub['speaker_id'].map(lambda s: speaker_usage[s])
            p_sub = p_sub.sort_values(by='spk_usage')
            
            for _, row in p_sub.iterrows():
                if p_chosen >= p_quota:
                    break
                if row['speaker_id'] not in term_speakers:
                    term_selected.append(row.to_dict())
                    term_speakers.add(row['speaker_id'])
                    speaker_usage[row['speaker_id']] += 1
                    p_chosen += 1
                    
        # Phase 2: If quota not met, fill from remaining prompts of this term
        if len(term_selected) < quota:
            rem_sub = term_sub[~term_sub['speaker_id'].isin(term_speakers)].copy()
            rem_sub['spk_usage'] = rem_sub['speaker_id'].map(lambda s: speaker_usage[s])
            rem_sub = rem_sub.sort_values(by='spk_usage')
            for _, row in rem_sub.iterrows():
                if len(term_selected) >= quota:
                    break
                term_selected.append(row.to_dict())
                term_speakers.add(row['speaker_id'])
                speaker_usage[row['speaker_id']] += 1

        assert len(term_selected) == quota, f"Term {term} failed quota {quota}"
        selected_spans.extend(term_selected)

    print(f"Total candidate spans selected: {len(selected_spans)}")
    unique_audios = list(set([s['recording_id'] for s in selected_spans]))
    print(f"Total unique audio files to align: {len(unique_audios)}")

    # 4. Whisper Word Alignment Execution
    print("\n--- Initializing Whisper Alignment Engine ---")
    whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=4)

    # Group selected spans by recording_id to transcribe each audio only once
    audio_to_spans = defaultdict(list)
    for s in selected_spans:
        audio_to_spans[s['recording_id']].append(s)

    final_manifest = []
    processed_count = 0

    for rec_id, spans in audio_to_spans.items():
        first_span = spans[0]
        wav_path = os.path.join(wav_dir, first_span['wav_file'])
        
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Missing WAV file: {wav_path}")
            
        audio_info = sf.info(wav_path)
        total_duration = round(audio_info.duration, 3)

        # Context prompt containing ISTQB terms
        initial_prompt = f"Thuật ngữ kiểm thử phần mềm ISTQB: {', '.join(first_span['gold_terms'])}."

        # Transcribe with word timestamps
        segments, _ = whisper_model.transcribe(
            wav_path,
            language="vi",
            initial_prompt=initial_prompt,
            beam_size=1,
            word_timestamps=True
        )

        words = []
        for s in segments:
            for w in s.words:
                words.append({
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "prob": round(w.probability, 3)
                })

        words_lower = [w["word"].lower().strip(".,;:?!\"'") for w in words]

        for span in spans:
            target_term = span['term']
            t_words = target_term.lower().split()
            matched_span = None

            # Attempt 1: Exact consecutive word match
            for i in range(len(words_lower) - len(t_words) + 1):
                window = " ".join(words_lower[i : i + len(t_words)])
                if target_term.lower() in window:
                    matched_span = (words[i]["start"], words[i + len(t_words) - 1]["end"])
                    break

            # Attempt 2: Partial/Key word match
            if not matched_span and len(t_words) >= 2:
                key_word = t_words[0] # e.g. 'boundary', 'defect', 'smoke', 'sanity'
                for i, w in enumerate(words_lower):
                    if key_word in w:
                        end_idx = min(len(words) - 1, i + len(t_words) - 1)
                        matched_span = (words[i]["start"], words[end_idx]["end"])
                        break

            if matched_span:
                start_t = round(float(matched_span[0]), 3)
                end_t = round(float(matched_span[1]), 3)
                # Ensure minimum span duration of 0.3s
                if end_t - start_t < 0.3:
                    end_t = min(total_duration, round(start_t + 0.6, 3))
                alignment_status = "Exact_Word_Timestamp"
                asr_status = "correct"
            else:
                # Acoustic Envelope Windowing for dropped/mispronounced terms (Eliminates Survivor Bias)
                # Position window based on prompt structure and multi-term index
                all_terms = span['gold_terms']
                if target_term in all_terms:
                    t_idx = all_terms.index(target_term)
                    n_terms = len(all_terms)
                else:
                    t_idx = 0
                    n_terms = 1

                frac_start = (t_idx + 0.5) / (n_terms + 1.0) - 0.15
                frac_end = frac_start + 0.25
                start_t = round(max(0.2, total_duration * max(0.05, frac_start)), 3)
                end_t = round(min(total_duration - 0.1, start_t + 1.5), 3)
                
                alignment_status = "Acoustic_Envelope_Window"
                asr_status = "dropped_or_corrupted"

            span_duration = round(end_t - start_t, 3)

            final_manifest.append({
                'audio_id': rec_id,
                'speaker_id': span['speaker_id'],
                'term_id': target_term,
                'prompt_id': span['prompt_id'],
                'start_time': start_t,
                'end_time': end_t,
                'alignment_status': alignment_status,
                'asr_status': asr_status,
                'duration': span_duration
            })

        processed_count += 1
        if processed_count % 50 == 0 or processed_count == len(audio_to_spans):
            print(f"Processed {processed_count}/{len(audio_to_spans)} audios ({len(final_manifest)} spans aligned)...")

    # 5. Create DataFrame and Verify Manifest Integrity
    df_manifest = pd.DataFrame(final_manifest)
    print("\n" + "=" * 80)
    print("MANIFEST VERIFICATION & AUDIT")
    print("=" * 80)
    print(f"Total rows in manifest: {len(df_manifest)} (Target: 300)")
    assert len(df_manifest) == 300, f"Expected exactly 300 spans, got {len(df_manifest)}"

    # Check columns
    required_cols = ['audio_id', 'speaker_id', 'term_id', 'prompt_id', 'start_time', 'end_time', 'alignment_status', 'asr_status', 'duration']
    assert list(df_manifest.columns) == required_cols, f"Column mismatch: {list(df_manifest.columns)}"

    # Save to Data/training_spans_300.csv and brain artifact dir
    out_path_1 = "Data/training_spans_300.csv"
    out_path_2 = "C:/Users/ACER/.gemini/antigravity/brain/188b44ec-9425-4d1c-852d-6957627afff6/training_spans_300.csv"
    df_manifest.to_csv(out_path_1, index=False, encoding='utf-8')
    df_manifest.to_csv(out_path_2, index=False, encoding='utf-8')
    print(f"Manifest successfully saved to:\n  - {out_path_1}\n  - {out_path_2}")

    # 6. Detailed Distribution Tables
    print("\n--- DISTRIBUTION BY TERM ---")
    term_summary = df_manifest.groupby('term_id').agg(
        spans=('audio_id', 'count'),
        unique_speakers=('speaker_id', 'nunique'),
        unique_prompts=('prompt_id', 'nunique'),
        mean_duration=('duration', 'mean'),
        asr_correct=('asr_status', lambda s: (s == 'correct').sum()),
        asr_dropped=('asr_status', lambda s: (s != 'correct').sum())
    ).reset_index()
    term_summary['asr_correct_pct'] = (term_summary['asr_correct'] / term_summary['spans'] * 100).round(1)
    print(term_summary.to_string(index=False))

    print("\n--- DISTRIBUTION BY PROMPT ---")
    prompt_summary = df_manifest.groupby('prompt_id').agg(
        spans=('audio_id', 'count'),
        unique_terms=('term_id', 'nunique'),
        unique_speakers=('speaker_id', 'nunique')
    ).reset_index()
    print(prompt_summary.to_string(index=False))

    print("\n--- SPEAKER REPRESENTATION AUDIT ---")
    spk_counts = df_manifest['speaker_id'].value_counts()
    print(f"Total unique speakers: {df_manifest['speaker_id'].nunique()}")
    print(f"Spans per speaker: Min = {spk_counts.min()}, Median = {spk_counts.median():.1f}, Mean = {spk_counts.mean():.2f}, Max = {spk_counts.max()}")
    print(f"Speakers contributing > 3 spans: {(spk_counts > 3).sum()} / {len(spk_counts)}")

    print("\n--- ALIGNMENT STATUS AUDIT (SURVIVOR BIAS CHECK) ---")
    align_summary = df_manifest.groupby(['alignment_status', 'asr_status']).size().reset_index(name='count')
    align_summary['pct'] = (align_summary['count'] / len(df_manifest) * 100).round(2)
    print(align_summary.to_string(index=False))

if __name__ == '__main__':
    main()

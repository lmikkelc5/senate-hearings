# Fast, filtered keyword extraction across multiple sessions
# - bans generic addressing phrase(s) like 'senate committee'
# - outputs a single aggregated CSV with columns: session,date,month,day,year,title,keywords,kw_1..kw_10

import os
import gc
import numpy as np
import pandas as pd
from tqdm import tqdm

# Embeddings + candidate extraction
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer

# Note: spaCy person-entity filtering removed to preserve relevant names.

# Parameters
sessions = [119, 118]  # adjust as needed
model_name = 'all-MiniLM-L6-v2'
ngram_range = (1, 2)
max_candidates = 5000
top_n = 10
mmr_lambda = 0.7

# Banned substrings (case-insensitive)
# Includes committee boilerplate, structural phrases, and location/date noise to remove.
banned_substrings = [
    # committee/institution boilerplate
    'senate committee', 'house committee', 'committee hearing', 'hearing committee',
    'committee judiciary', 'committee finance', 'finance committee', 'committee health',
    'committee presiding', 'special committee', 'members subcommittee', 'members senate',
    'committee aging', 'use committee', 'committee thank', 'committees',
    'committee met', 'members committee', 'committee members', 'members congress', 'subcommittee', 'committee',
    # roles and greetings
    'opening statement', 'testimony', 'testified', 'chairman', 'ranking member', 'senator',
    'representative', 'congressman', 'congresswoman', 'good morning', 'good afternoon',
    'thank you', 'distinguished', 'witness', 'panel', 'hearing adjourned', 'hearing today', 'today hearing',
    'chair durbin', 'questions chair', 'chief counsel', 'commissioner', 'fcc commissioner', 'testify today',
    # structural/location/date/document noise
    'senate', 'states senate', 'congress session', 'eighteenth congress', 'congress',
    '2023 senate', '2024 budget', 'senate office', 'senate eighteenth', 'hearings',
    'congressional', 'pdf washington', 'dc committee', 'act 2023', 'gov document', 'docs fcc', 'statement fcc',
    'board directors', 'briefing', 'justices', 'government publishing', 'authorization act',
    'science act', 'prepared statement', 'written statement', 'report',
    # staffing / persons / roles and generic terms
    'republican staff', 'chair warren', 'document fcc', 'filing', 'secretary state', 'judiciary', 'policymakers',
    'menendez', 'sanders', 'murkowski',
    # overly generic single words
    'federal', 'bipartisan', 'administrations', 'assessed'
]

# Optional normalization map for final keywords (case-insensitive)
# Add common variants -> canonical forms for cleaner aggregation.
normalize_map = {
    # budget phrasing
    'president budget': "president's budget",
    "president's budget": "president's budget",
    'presidents budget': "president's budget",
    'white house budget': "president's budget",
    # agencies capitalization and acronyms
    'epa': 'EPA',
    'fcc': 'FCC',
    'federal reserve': 'Federal Reserve',
    'veterans affairs': 'Veterans Affairs',
    'va': 'Veterans Affairs',
    'department of energy': 'DOE',
    'doe': 'DOE',
    'department of transportation': 'DOT',
    'dot': 'DOT',
    'department of defense': 'DoD',
    'dod': 'DoD',
    'department of homeland security': 'Homeland Security',
    'dhs': 'Homeland Security',
    'centers for disease control': 'CDC',
    'cdc': 'CDC',
    'food and drug administration': 'FDA',
    'fda': 'FDA',
    'department agriculture': 'USDA',
    # general variants & casing
    'bipartisan infrastructure': 'Bipartisan Infrastructure',
    'bipartisan support': 'Bipartisan Support',
    'federal funding': 'Federal Funding',
    'federal agencies': 'Federal Agencies',
    'natural gas': 'Natural Gas',
    'health plans': 'Health Plans',
    'tax cuts': 'Tax Cuts',
    'tribal programs': 'Tribal Programs',
}

# Output file (single aggregated CSV)
outfile = '../data/cleaned/all_sessions_keywords_filtered.csv'
os.makedirs(os.path.dirname(outfile), exist_ok=True)

# Load embedding model once
print('Loading embedding model:', model_name)
model = SentenceTransformer(model_name)

rows = []  # collect dicts for final DataFrame

for session in sessions:
    print('\nProcessing session:', session)
    inpath = f"data/cleaned/session_{session}_cleaned.csv"
    if not os.path.exists(inpath):
        print('Missing file:', inpath)
        continue

    df = pd.read_csv(inpath)
    docs = (df['title'].fillna('') + '\n' + df['text'].fillna('')).astype(str).tolist()

    # Person-name filtering disabled (previously used spaCy NER)
    person_names = set()

    # Build candidate phrases for this session
    vectorizer = CountVectorizer(ngram_range=ngram_range, stop_words='english')
    X = vectorizer.fit_transform(docs)
    candidates = vectorizer.get_feature_names_out().tolist()
    print('Total candidate phrases:', len(candidates))

    # Optionally limit candidates by frequency
    if len(candidates) > max_candidates:
        freqs = np.asarray(X.sum(axis=0)).ravel()
        top_idx = np.argsort(freqs)[-max_candidates:]
        candidates = [candidates[i] for i in top_idx]
        candidates = [c for _, c in sorted(zip(freqs[top_idx], candidates), key=lambda x: -x[0])]
        print('Trimmed candidate phrases to:', len(candidates))

    # Filter candidates using banned substrings and person names
    def is_banned_candidate(c):
        cl = c.lower()
        for sub in banned_substrings:
            if sub in cl:
                return True
        for name in person_names:
            if name and name in cl:
                return True
        return False

    before = len(candidates)
    candidates = [c for c in candidates if not is_banned_candidate(c)]
    filtered = before - len(candidates)
    if filtered:
        print(f'Filtered out {filtered} candidates matching banned substrings or person names')

    # If no candidates left, skip session
    if len(candidates) == 0:
        print('No candidates remaining for session', session)
        continue

    # Encode documents and candidates (normalized for cosine similarity)
    print('Encoding documents...')
    doc_embs = model.encode(docs, batch_size=32, show_progress_bar=True, convert_to_numpy=True, normalize_embeddings=True)
    print('Encoding candidates...')
    cand_embs = model.encode(candidates, batch_size=128, show_progress_bar=True, convert_to_numpy=True, normalize_embeddings=True)

    # MMR selection
    def mmr_select(doc_emb, cand_embs, candidates, top_n=10, lambda_param=0.7):
        import numpy as np
        if len(candidates) == 0:
            return []
        doc_sim = np.dot(cand_embs, doc_emb)
        selected_idx = []
        idx = int(np.argmax(doc_sim))
        selected_idx.append(idx)
        while len(selected_idx) < min(top_n, len(candidates)):
            candidates_idx = [i for i in range(len(candidates)) if i not in selected_idx]
            mmr_scores = []
            for i in candidates_idx:
                relevance = doc_sim[i]
                diversity_score = max([np.dot(cand_embs[i], cand_embs[j]) for j in selected_idx]) if selected_idx else 0
                score = lambda_param * relevance - (1 - lambda_param) * diversity_score
                mmr_scores.append((score, i))
            if not mmr_scores:
                break
            next_idx = max(mmr_scores)[1]
            selected_idx.append(next_idx)
        return [candidates[i] for i in selected_idx]

    print('Selecting keywords with MMR...')
    for idx_doc, emb in enumerate(tqdm(doc_embs, desc=f'docs session {session}')):
        try:
            kws = mmr_select(emb, cand_embs, candidates, top_n=top_n, lambda_param=mmr_lambda)
        except Exception:
            kws = []

        # Final safety-filter + normalization for canonical forms
        def norm(k):
            kl = k.lower()
            return normalize_map.get(kl, k)
        kws = [norm(k) for k in kws if not is_banned_candidate(k)]

        # Fill up to top_n keywords (if fewer, pad with empty strings)
        kws = kws[:top_n]
        kws += [''] * (top_n - len(kws))

        keywords_str = '; '.join([k for k in kws if k])

        # Collect row with requested columns
        row = {
            'session': df.at[idx_doc, 'session'] if 'session' in df.columns else session,
            'date': df.at[idx_doc, 'date'] if 'date' in df.columns else '',
            'month': df.at[idx_doc, 'month'] if 'month' in df.columns else '',
            'day': df.at[idx_doc, 'day'] if 'day' in df.columns else '',
            'year': df.at[idx_doc, 'year'] if 'year' in df.columns else '',
            'title': df.at[idx_doc, 'title'] if 'title' in df.columns else '',
            'keywords': keywords_str
        }
        for j in range(top_n):
            row[f'kw_{j+1}'] = kws[j] if j < len(kws) else ''

        rows.append(row)

    # free memory
    del doc_embs, cand_embs
    gc.collect()

# Create aggregated DataFrame and save single CSV
if rows:
    out_df = pd.DataFrame(rows)
    # Ensure column order
    cols = ['session','date','month','day','year','title','keywords'] + [f'kw_{i+1}' for i in range(top_n)]
    # Add missing cols if necessary
    for c in cols:
        if c not in out_df.columns:
            out_df[c] = ''
    out_df = out_df[cols]
    out_df.to_csv(outfile, index=False)
    print('Saved aggregated keywords to', outfile)
else:
    print('No rows generated; nothing saved')

print('Done')


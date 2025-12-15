"""
Functions for keyword extraction using KeyBERT/MMR approach.
Extracted from keybert.py for modularity.
"""

import numpy as np


def is_banned_candidate(c, banned_substrings, person_names):
    """
    Check if a candidate phrase should be filtered out.
    
    Args:
        c: Candidate phrase string
        banned_substrings: List of banned substring patterns (case-insensitive)
        person_names: Set of person names to filter out
        
    Returns:
        True if candidate should be banned, False otherwise
    """
    cl = c.lower()
    for sub in banned_substrings:
        if sub in cl:
            return True
    for name in person_names:
        if name and name in cl:
            return True
    return False


def mmr_select(doc_emb, cand_embs, candidates, top_n=10, lambda_param=0.7):
    """
    Maximal Marginal Relevance (MMR) selection for diverse keyword extraction.
    
    Args:
        doc_emb: Document embedding vector
        cand_embs: Candidate phrase embeddings (2D array)
        candidates: List of candidate phrase strings
        top_n: Number of keywords to select
        lambda_param: Trade-off between relevance and diversity (0-1)
        
    Returns:
        List of selected keyword strings
    """
    if len(candidates) == 0:
        return []
    
    # Compute relevance scores (cosine similarity with document)
    doc_sim = np.dot(cand_embs, doc_emb)
    
    selected_idx = []
    # Start with most relevant candidate
    idx = int(np.argmax(doc_sim))
    selected_idx.append(idx)
    
    # Iteratively select remaining keywords balancing relevance and diversity
    while len(selected_idx) < min(top_n, len(candidates)):
        candidates_idx = [i for i in range(len(candidates)) if i not in selected_idx]
        mmr_scores = []
        
        for i in candidates_idx:
            relevance = doc_sim[i]
            # Compute max similarity to already selected candidates
            diversity_score = max([np.dot(cand_embs[i], cand_embs[j]) for j in selected_idx]) if selected_idx else 0
            # MMR formula: balance relevance and diversity
            score = lambda_param * relevance - (1 - lambda_param) * diversity_score
            mmr_scores.append((score, i))
        
        if not mmr_scores:
            break
            
        next_idx = max(mmr_scores)[1]
        selected_idx.append(next_idx)
    
    return [candidates[i] for i in selected_idx]


def normalize_keyword(k, normalize_map):
    """
    Normalize keyword to canonical form using normalization map.
    
    Args:
        k: Keyword string
        normalize_map: Dictionary mapping variants to canonical forms (case-insensitive)
        
    Returns:
        Normalized keyword string
    """
    kl = k.lower()
    return normalize_map.get(kl, k)


def filter_and_normalize_keywords(kws, banned_substrings, person_names, normalize_map, top_n=10):
    """
    Filter banned keywords and normalize to canonical forms, padding to top_n.
    
    Args:
        kws: List of keyword strings
        banned_substrings: List of banned substring patterns
        person_names: Set of person names to filter
        normalize_map: Dictionary for normalizing keywords
        top_n: Target number of keywords (will pad with empty strings if fewer)
        
    Returns:
        Tuple of (keywords_string, keywords_list) where list is padded to top_n
    """
    # Normalize and filter
    normalized_kws = [
        normalize_keyword(k, normalize_map) 
        for k in kws 
        if not is_banned_candidate(k, banned_substrings, person_names)
    ]
    
    # Trim to top_n
    normalized_kws = normalized_kws[:top_n]
    
    # Pad with empty strings if needed
    normalized_kws += [''] * (top_n - len(normalized_kws))
    
    # Create semicolon-separated string (excluding empty strings)
    keywords_str = '; '.join([k for k in normalized_kws if k])
    
    return keywords_str, normalized_kws


def trim_candidates_by_frequency(candidates, X, max_candidates):
    """
    Trim candidate phrases to max_candidates by keeping most frequent ones.
    
    Args:
        candidates: List of candidate phrase strings
        X: Sparse matrix from CountVectorizer (document-term matrix)
        max_candidates: Maximum number of candidates to keep
        
    Returns:
        Trimmed list of candidate phrases, sorted by frequency (descending)
    """
    freqs = np.asarray(X.sum(axis=0)).ravel()
    top_idx = np.argsort(freqs)[-max_candidates:]
    trimmed_candidates = [candidates[i] for i in top_idx]
    # Sort by frequency descending
    trimmed_candidates = [c for _, c in sorted(zip(freqs[top_idx], trimmed_candidates), key=lambda x: -x[0])]
    return trimmed_candidates

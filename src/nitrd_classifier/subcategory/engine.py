# ruff: noqa: E501
"""Vendored uac-nitrd scope-vocabulary engine (Task 2 subcategory proposals).

Source: uac-nitrd engine/run.py (engine-method-deterministic-v1-2026-10-23,
vocabulary-scope-only-2026-10-24), file SHA-256
73b5d78489c699b8291b319df4fb655769511c8e87a108d67ab8d3f1632df8ff. The scoring
functions below are copied unchanged (comments included); only the CLI,
the synonym loader (never used under vocabulary-scope-only), the cache/meta
writers and the freeze guard are left out. The freeze guard protects the
sealed evaluation projects, which are not in the public FY2015-2023 snapshot
these tools read. tests/test_classifier_tools.py pins this module's output to
the upstream engine's on fixed texts.

Scope file: resources/scope/nitrd_pca_scopes_fy2025.v1.json, byte-identical to
uac-nitrd scope/nitrd_pca_scopes_fy2025.v1.json (SHA-256 SCOPE_SHA256).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

SCOPE_PATH = Path(__file__).resolve().parents[1] / "resources" / "scope" / "nitrd_pca_scopes_fy2025.v1.json"
SCOPE_SHA256 = "8914f4c0d7953c366bae19683ed96ca6d2cce6043c98a227544e907683b56ea9"
UPSTREAM_ENGINE_SHA256 = "73b5d78489c699b8291b319df4fb655769511c8e87a108d67ab8d3f1632df8ff"

# --------------------------------------------------------------------------- constants
# vocabulary-scope-only-2026-10-24 (owner decision): the reveal engine uses NO synonyms.
# Vocabulary = verbatim NITRD scope text + AI definition + cross-PCA guidance only.
VOCABULARY_ID = "vocabulary-scope-only-2026-10-24"
SYNONYMS_PATH = None
PCA_CODES = ("ACNS", "AI", "CHuman", "CNPS", "CSP", "EdW", "EHCS", "ENIT", "HCIA", "IRAS", "LSDMA", "SPSQ")
AW = "AW"

# Scoring thresholds (fixed before running on the 480)
PCA_THRESHOLD = 1.0      # minimum score to propose a PCA
# ai_relevant gate (ai-gate-v2, decided 2026-10-24 before running on the 480).
# v1 summed IDF weights over the whole AI vocabulary, which includes generic words from
# the statutory definition ("systems", "models", "analysis", "human"), so almost any
# text passed. v2 requires at least AI_GATE_MIN_TERMS distinct AI-SPECIFIC terms.
AI_GATE_MIN_TERMS = 1
# AI-specific terms, each from the AI scope text, the statutory definition, or a
# cross-PCA sentence that assigns the concept to AI. Generic definition words excluded.
AI_GATE_CORE = (
    ("ai", "AI scope_text: 'research in AI and associated AI topics'"),
    ("human-ai", "AI scope_text: 'human-AI collaboration'"),
    ("artificial intelligence", "AI definition: 'The term artificial intelligence or AI'"),
    ("machine-based system", "AI definition: 'a machine-based system that can ... make predictions'"),
    ("model inference", "AI definition: 'use model inference to formulate options'"),
    ("machine vision", "cross-PCA 1: 'general methods for machine vision would fall under AI'"),
    ("intelligent autonomous systems", "cross-PCA 1: 'intelligent autonomous systems that exist only in cyberspace ... AI'"),
    ("computational linguistics", "cross-PCA 2: 'algorithms for computational linguistics would fall under AI'"),
    ("neural nets", "cross-PCA 4: 'chips optimized for neural nets would fall under AI'"),
    ("machine learning", "cross-PCA 5: 'R&D that is primarily machine learning would fall under AI'"),
)
# Synonyms with pca=AI also join the gate if MULTI-WORD and not flagged sme_review
# (gate-v2.1, pre-registered 2026-10-24 with synonym-derivation-v2, before deriving).
# NIH text writes American Indian/Alaska Native as "AI/AN"; rewrite before tokenising
# so it never reads as artificial intelligence (domain convention, not from the 480).
_AIAN_RE = re.compile(r"\bAI\s*/\s*ANs?\b", re.IGNORECASE)
PHRASE_BONUS = 3.0       # multiplier for multi-word phrase matches vs single words

# Stop words removed during normalisation
STOP = frozenset("a an and are as at be by for from has have in is it of on or "
                 "that the this to was were will with its been not can may such "
                 "these those which would should could also their than both but "
                 "into more other some most our we they all each no nor so do "
                 "does did about after between through during over under using "
                 "based upon along across among within including include includes "
                 "included related use uses used new".split())

# --------------------------------------------------------------------------- text normalisation
_WORD_RE = re.compile(r"[a-z][a-z0-9'-]*[a-z0-9]|[a-z]", re.ASCII)


def _normalise(text: str) -> list[str]:
    """Lower-case, split on non-alpha, drop stop words. No stemmer — exact scope words only."""
    return [w for w in _WORD_RE.findall(text.lower()) if w not in STOP]


def _ngrams(words: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]


# --------------------------------------------------------------------------- scope vocabulary
def _build_vocabulary(scopes: list[dict], guidance: dict) -> dict:
    """Build {pca_code: {term: (weight, source_phrase)}} from the scope text + AI guidance."""
    vocab: dict[str, dict[str, tuple[float, str]]] = {}
    doc_freq: Counter = Counter()  # term -> how many PCAs use it (for IDF)

    # Phase 1: extract terms from each PCA's scope_text
    for s in scopes:
        code = s["code"]
        if code == AW:
            continue  # AW vocabulary handled separately
        terms: dict[str, str] = {}  # normalised term -> source phrase
        text = s["scope_text"]
        words = _normalise(text)
        # single words
        for w in words:
            terms.setdefault(w, text)
        # 2-grams and 3-grams (phrases)
        for n in (2, 3):
            for ng in _ngrams(words, n):
                terms.setdefault(" ".join(ng), text)
        vocab[code] = {t: (1.0, src) for t, src in terms.items()}

    # Phase 2: AI definition and cross-PCA guidance → enrich AI vocabulary
    ai_def = guidance.get("ai_definition", {}).get("text", "")
    for w in _normalise(ai_def):
        vocab["AI"].setdefault(w, (1.0, ai_def))
    for ng in _ngrams(_normalise(ai_def), 2):
        vocab["AI"].setdefault(" ".join(ng), (1.0, ai_def))

    # Cross-PCA examples: add specific terms to the relevant PCA
    cross = guidance.get("ai_cross_pca", {}).get("items", [])
    _CROSS_MAP = [
        ("machine vision", "AI", cross[0] if len(cross) > 0 else ""),
        ("robot", "IRAS", cross[0] if len(cross) > 0 else ""),
        ("autonomous systems", "AI", cross[0] if len(cross) > 0 else ""),
        ("computational linguistics", "AI", cross[1] if len(cross) > 1 else ""),
        ("natural language processing", "CHuman", cross[1] if len(cross) > 1 else ""),
        ("human-machine interaction", "CHuman", cross[1] if len(cross) > 1 else ""),
        ("cybersecurity", "CSP", cross[2] if len(cross) > 2 else ""),
        ("neuromorphic", "EHCS", cross[3] if len(cross) > 3 else ""),
        ("neural net", "AI", cross[3] if len(cross) > 3 else ""),
        ("machine learning", "AI", cross[4] if len(cross) > 4 else ""),
        ("data management", "LSDMA", cross[4] if len(cross) > 4 else ""),
        ("data analysis", "LSDMA", cross[4] if len(cross) > 4 else ""),
    ]
    for term, pca, src in _CROSS_MAP:
        for t in [term] + list(" ".join(ng) for ng in _ngrams(_normalise(term), min(2, len(term.split())))):
            if t:
                vocab.setdefault(pca, {}).setdefault(t, (1.5, f"cross-PCA: {src[:80]}"))

    # Phase 3: compute IDF (inverse document frequency across the 12 PCAs)
    all_terms: set[str] = set()
    for code in PCA_CODES:
        all_terms.update(vocab.get(code, {}))
    for t in all_terms:
        doc_freq[t] = sum(1 for c in PCA_CODES if t in vocab.get(c, {}))
    n_docs = len(PCA_CODES)
    for code in PCA_CODES:
        for t, (w, src) in list(vocab.get(code, {}).items()):
            idf = math.log(n_docs / max(doc_freq[t], 1))
            is_phrase = " " in t
            weight = w * idf * (PHRASE_BONUS if is_phrase else 1.0)
            vocab[code][t] = (weight, src)

    # AW vocabulary (separate; only used for sub_pca tagging)
    aw_scope = next((s for s in scopes if s["code"] == AW), None)
    if aw_scope:
        aw_terms: dict[str, tuple[float, str]] = {}
        txt = aw_scope["scope_text"]
        for w in _normalise(txt):
            aw_terms.setdefault(w, (1.0, txt))
        for ng in _ngrams(_normalise(txt), 2):
            aw_terms.setdefault(" ".join(ng), (1.0, txt))
        vocab[AW] = aw_terms

    return vocab


# --------------------------------------------------------------------------- scoring
def _score_text(words: list[str], pca_vocab: dict[str, tuple[float, str]]) -> list[dict]:
    """Return matched terms with weight and text span."""
    hits = []
    seen: set[str] = set()
    text_str = " ".join(words)
    # phrases first (2-grams, 3-grams), then single words
    for n in (3, 2, 1):
        for ng in (_ngrams(words, n) if n > 1 else [(w,) for w in words]):
            t = " ".join(ng)
            if t in seen or t not in pca_vocab:
                continue
            seen.add(t)
            weight, src = pca_vocab[t]
            # find the span in the original word list
            start = text_str.find(t)
            hits.append({"term": t, "weight": round(weight, 4), "source_phrase": src,
                         "text_span": text_str[max(0, start - 30):start + len(t) + 30].strip() if start >= 0 else ""})
    return hits


def _pca_score(hits: list[dict]) -> float:
    return sum(h["weight"] for h in hits)


# --------------------------------------------------------------------------- specificity rules
# Encoded from NITRD's cross-PCA AI examples. Each rule: if (project matches BOTH),
# the more specific PCA wins.
_SPECIFICITY = [
    # (general PCA, specific PCA, source)
    ("AI", "IRAS", "robots employing machine vision → IRAS, not AI"),
    ("AI", "CHuman", "broad HCI even with NLP → CHuman, not AI"),
    ("AI", "CSP", "AI supporting cybersecurity → CSP, not AI"),
    ("AI", "EHCS", "general neuromorphic computing → EHCS, not AI"),
    ("AI", "LSDMA", "wider data ecosystem with ML element → LSDMA, not AI"),
]


def _apply_specificity(ranked: list[dict]) -> tuple[list[dict], list[dict]]:
    """Re-rank by specificity rules. Returns (re-ranked, rules_applied)."""
    if len(ranked) < 2:
        return ranked, []
    codes = {r["pca"]: r for r in ranked}
    rules_applied = []
    for gen, spec, src in _SPECIFICITY:
        if gen in codes and spec in codes:
            gs, ss = codes[gen]["score"], codes[spec]["score"]
            if gs > 0 and ss > 0 and gs >= ss * 0.5:  # both qualify; specific wins if close
                rules_applied.append({"rule": f"{spec} over {gen}", "source": src})
                codes[gen]["score"] *= 0.5  # demote the general PCA
    re_ranked = sorted(codes.values(), key=lambda r: -r["score"])
    return re_ranked, rules_applied


# --------------------------------------------------------------------------- main logic
def build_ai_gate(syn_path: Path | None) -> tuple[tuple[tuple[str, ...], str], ...]:
    """AI-specific gate terms: AI_GATE_CORE + non-pending AI synonyms, as normalised tuples."""
    terms: dict[tuple[str, ...], str] = {}
    for t, src in AI_GATE_CORE:
        terms.setdefault(tuple(_normalise(t)), src)
    if syn_path is not None and syn_path.exists():
        for e in json.loads(syn_path.read_text(encoding="utf-8")).get("synonyms", []):
            if "comment" in e or e.get("pca") != "AI" or e.get("sme_review"):
                continue
            toks = tuple(_normalise(e["term"]))
            if len(toks) < 2:  # gate-v2.1: derived single words are too ambiguous to set the flag
                continue
            terms.setdefault(toks, f"synonym: {e['expands'][:60]} ({e['source']})")
    return tuple(sorted((k, v) for k, v in terms.items() if k))


def _ai_gate_hits(words: list[str], gate) -> list[dict]:
    hits = []
    for toks, src in gate:
        n = len(toks)
        for i in range(len(words) - n + 1):
            if tuple(words[i:i + n]) == toks:
                span = " ".join(words[max(0, i - 5):i + n + 5])
                hits.append({"term": " ".join(toks), "source_phrase": src, "text_span": span})
                break
    return hits


def propose(appl_id: int, text: dict, vocab: dict, scope_sha: str, ai_gate=()) -> dict:
    """Generate one proposal with full explanation."""
    title = (text.get("title") or "").strip()
    abstract = (text.get("abstract") or "").strip()
    phr = (text.get("public_health_relevance") or "").strip()
    combined = _AIAN_RE.sub("american indian alaska native", f"{title}. {abstract} {phr}".strip())
    text_sha = hashlib.sha256(json.dumps(text, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    if not title and not abstract:
        return {"appl_id": appl_id, "text_sha256": text_sha,
                "primary_pca": "", "ai_relevant": False, "sub_pca": "",
                "ranked": [], "rules_applied": [], "ai_evidence": [],
                "abstain_reason": "no_public_text: title and abstract are both empty"}

    words = _normalise(combined)
    # Score each PCA
    ranked = []
    for code in PCA_CODES:
        hits = _score_text(words, vocab.get(code, {}))
        s = _pca_score(hits)
        if s > 0:
            ranked.append({"pca": code, "score": round(s, 4), "matched_terms": hits})
    ranked.sort(key=lambda r: -r["score"])

    # Apply specificity rules
    ranked, rules_applied = _apply_specificity(ranked)

    # AI evidence (for the ai_relevant flag): AI-specific gate terms only
    ai_hits = _ai_gate_hits(words, ai_gate)

    # Pick the winner
    primary = ""
    if ranked and ranked[0]["score"] >= PCA_THRESHOLD:
        primary = ranked[0]["pca"]

    ai_relevant = primary == "AI" or len(ai_hits) >= AI_GATE_MIN_TERMS

    # AW sub-PCA
    sub_pca = ""
    if primary == "ACNS":
        aw_hits = _score_text(words, vocab.get(AW, {}))
        if _pca_score(aw_hits) > 0:
            sub_pca = AW

    abstain = None
    if not primary:
        top = ranked[0]["score"] if ranked else 0.0
        abstain = f"below_threshold: top score {top:.2f} < {PCA_THRESHOLD}"

    return {"appl_id": appl_id, "text_sha256": text_sha,
            "primary_pca": primary, "ai_relevant": ai_relevant, "sub_pca": sub_pca,
            "ranked": [{"pca": r["pca"], "score": r["score"],
                        "matched_terms": r["matched_terms"][:15]} for r in ranked[:5]],
            "rules_applied": rules_applied,
            "ai_evidence": ai_hits[:10] if ai_relevant else [],
            "abstain_reason": abstain}


# --------------------------------------------------------------------------- MCP-side wrapper (not upstream)
@lru_cache(maxsize=1)
def load_engine(path: str = str(SCOPE_PATH)) -> tuple[dict, str, tuple]:
    """(vocabulary, scope sha256, ai gate) built exactly as upstream main() does."""
    raw = Path(path).read_bytes()
    scope_sha = hashlib.sha256(raw).hexdigest()
    scope_data = json.loads(raw.decode("utf-8"))
    vocab = _build_vocabulary(scope_data["scopes"], scope_data.get("cross_pca_guidance", {}))
    return vocab, scope_sha, build_ai_gate(SYNONYMS_PATH)


def propose_public(appl_id: int, title: str | None, abstract: str | None, phr: str | None) -> dict:
    """Run upstream propose() on one public ExPORTER record."""
    vocab, scope_sha, gate = load_engine()
    text = {"title": title or "", "abstract": abstract or "", "public_health_relevance": phr or ""}
    return propose(appl_id, text, vocab, scope_sha, gate)

"""CTC forced alignment (Viterbi over a trellis), numpy only.

Given per-frame log-probabilities from a CTC acoustic model (wav2vec2) and the token ids of a known transcript,
find the most likely time span of every token. This is the algorithm from the PyTorch forced-alignment tutorial,
written to run on long songs: O(T x N) memory in float32 with a vectorised forward pass.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TokenSpan:
    token_index: int   # index into the transcript token list
    start: int         # frame where the token is emitted (inclusive)
    emit_end: int      # frame after the token's last emission (exclusive)
    end: int           # frame after the blanks it holds until the next token (exclusive)
    score: float       # mean probability of the token at its emitted frames


def trellis(emission: np.ndarray, tokens: np.ndarray, blank: int) -> np.ndarray:
    """emission: (T, C) log-probs. tokens: (N,) ids. Returns (T+1, N+1) cumulative log-prob trellis."""
    T = emission.shape[0]
    N = len(tokens)
    tr = np.full((T + 1, N + 1), -np.inf, dtype=np.float32)
    tr[0, 0] = 0.0
    blank_lp = emission[:, blank]
    tr[1:, 0] = np.cumsum(blank_lp)
    tok_lp = emission[:, tokens]  # (T, N)
    for t in range(T):
        stay = tr[t, 1:] + blank_lp[t]
        advance = tr[t, :-1] + tok_lp[t]
        tr[t + 1, 1:] = np.maximum(stay, advance)
    return tr


def backtrack(tr: np.ndarray, emission: np.ndarray, tokens: np.ndarray, blank: int):
    """Returns (token_index, frame, prob, emitted) per frame from the token's emission to the next token."""
    T, N = tr.shape[0] - 1, tr.shape[1] - 1
    # every frame is consumed: trailing frames are blanks held by the last token
    t = T
    j = N
    path = []
    while j > 0 and t > 0:
        stay = tr[t - 1, j] + emission[t - 1, blank]
        advance = tr[t - 1, j - 1] + emission[t - 1, tokens[j - 1]]
        if advance >= stay:
            path.append((j - 1, t - 1, float(np.exp(emission[t - 1, tokens[j - 1]])), True))
            j -= 1
        else:
            path.append((j - 1, t - 1, float(np.exp(emission[t - 1, blank])), False))
        t -= 1
    if j > 0:
        raise ValueError("alignment failed: transcript longer than the audio allows")
    return path[::-1]


def token_spans(path) -> list[TokenSpan]:
    spans: list[TokenSpan] = []
    i = 0
    while i < len(path):
        j = i
        while j < len(path) and path[j][0] == path[i][0]:
            j += 1
        emitted = [p for p in path[i:j] if p[3]]
        last_emit = emitted[-1][1] if emitted else path[i][1]
        score = float(np.mean([p[2] for p in emitted])) if emitted else 0.0
        spans.append(TokenSpan(path[i][0], path[i][1], last_emit + 1, path[j - 1][1] + 1, score))
        i = j
    return spans


def align(emission: np.ndarray, tokens: list[int], blank: int) -> list[TokenSpan]:
    if len(tokens) == 0:
        return []
    tok = np.asarray(tokens, dtype=np.int64)
    if emission.shape[0] < len(tok):
        raise ValueError(f"audio too short for the text: {emission.shape[0]} frames for {len(tok)} tokens")
    tr = trellis(emission.astype(np.float32), tok, blank)
    path = backtrack(tr, emission, tok, blank)
    return token_spans(path)


def log_softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    m = x.max(axis=axis, keepdims=True)
    y = x - m
    return y - np.log(np.exp(y).sum(axis=axis, keepdims=True))

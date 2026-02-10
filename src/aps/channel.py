"""Information-theoretic computations for induced macro-channels.

Provides confusion matrix construction, mutual information,
channel capacity via Blahut-Arimoto, and three eta variants.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ConfusionMatrix:
    """Empirical confusion matrix P_hat(sigma_out | sigma_in)."""

    sigma_in_labels: list[str]
    sigma_out_labels: list[str]
    counts: np.ndarray  # shape: (|sigma_in|, |sigma_out|)

    @property
    def n_in(self) -> int:
        return len(self.sigma_in_labels)

    @property
    def n_out(self) -> int:
        return len(self.sigma_out_labels)

    @property
    def total(self) -> int:
        return int(self.counts.sum())

    def conditional_distribution(self) -> np.ndarray:
        """Row-normalized P(sigma_out | sigma_in).

        Rows with zero observations get uniform distribution (max entropy prior).
        """
        row_sums = self.counts.sum(axis=1, keepdims=True)
        # Avoid division by zero: rows with 0 observations get uniform
        mask = row_sums == 0
        safe_sums = np.where(mask, 1, row_sums)
        P = self.counts / safe_sums
        # Set zero-observation rows to uniform
        P = np.where(mask, 1.0 / self.n_out, P)
        return P


def build_confusion_matrix(
    observations: list[dict],
    sigma_in_alphabet: list[str],
    sigma_out_alphabet: list[str],
) -> ConfusionMatrix:
    """Build a confusion matrix from observation records."""
    in_idx = {s: i for i, s in enumerate(sigma_in_alphabet)}
    out_idx = {s: i for i, s in enumerate(sigma_out_alphabet)}
    counts = np.zeros((len(sigma_in_alphabet), len(sigma_out_alphabet)), dtype=np.float64)

    for obs in observations:
        i = in_idx.get(obs.get("sigma_in", ""), -1)
        j = out_idx.get(obs.get("sigma_out", ""), -1)
        if i >= 0 and j >= 0:
            counts[i, j] += 1

    return ConfusionMatrix(
        sigma_in_labels=sigma_in_alphabet,
        sigma_out_labels=sigma_out_alphabet,
        counts=counts,
    )


# ---------------------------------------------------------------------------
# Mutual Information
# ---------------------------------------------------------------------------

_LOG2_EPS = 1e-300  # avoid log(0)


def mutual_information(cm: ConfusionMatrix) -> float:
    """Compute I(X;Y) from the empirical joint distribution.

    I(X;Y) = sum_{x,y} p(x,y) * log2(p(x,y) / (p(x)*p(y)))
    Convention: 0 * log(0) = 0.
    """
    total = cm.counts.sum()
    if total == 0:
        return 0.0

    p_joint = cm.counts / total
    p_x = p_joint.sum(axis=1)  # marginal over outputs
    p_y = p_joint.sum(axis=0)  # marginal over inputs

    mi = 0.0
    for i in range(cm.n_in):
        for j in range(cm.n_out):
            pxy = p_joint[i, j]
            if pxy > 0 and p_x[i] > 0 and p_y[j] > 0:
                mi += pxy * math.log2(pxy / (p_x[i] * p_y[j]))
    return max(0.0, mi)  # numerical safety


# ---------------------------------------------------------------------------
# Channel Capacity via Blahut-Arimoto
# ---------------------------------------------------------------------------


def channel_capacity_blahut_arimoto(
    cm: ConfusionMatrix,
    max_iter: int = 200,
    tol: float = 1e-8,
) -> float:
    """Compute Shannon channel capacity C(P) = max_{p(x)} I(X;Y).

    Uses the Blahut-Arimoto algorithm which converges geometrically
    for finite alphabets. For our small alphabets (max 14 symbols),
    this converges in well under 100 iterations.
    """
    P = cm.conditional_distribution()  # P(y|x), shape (n_in, n_out)
    n_in, n_out = P.shape

    if n_in == 0 or n_out == 0:
        return 0.0

    # Check for degenerate case: all rows identical
    if n_in == 1:
        return 0.0

    # Initialize uniform input distribution
    q = np.ones(n_in) / n_in

    for _ in range(max_iter):
        # Compute r(y) = sum_x q(x) * P(y|x)
        r = q @ P  # shape (n_out,)
        r = np.maximum(r, _LOG2_EPS)

        # Compute c(x) = exp(sum_y P(y|x) * log(P(y|x) / r(y)))
        log_ratio = np.zeros_like(P)
        for i in range(n_in):
            for j in range(n_out):
                if P[i, j] > 0:
                    log_ratio[i, j] = P[i, j] * math.log(P[i, j] / r[j])
        c = np.exp(log_ratio.sum(axis=1))

        # Update q
        q_new = q * c
        q_sum = q_new.sum()
        if q_sum == 0:
            break
        q_new /= q_sum

        # Check convergence
        if np.max(np.abs(q_new - q)) < tol:
            q = q_new
            break
        q = q_new

    # Compute final capacity
    r = q @ P
    r = np.maximum(r, _LOG2_EPS)
    capacity = 0.0
    for i in range(n_in):
        if q[i] > 0:
            for j in range(n_out):
                if P[i, j] > 0:
                    capacity += q[i] * P[i, j] * math.log2(P[i, j] / r[j])

    return max(0.0, capacity)


# ---------------------------------------------------------------------------
# Informational Efficiency (3 variants)
# ---------------------------------------------------------------------------


def compute_eta_variants(
    capacity: float,
    total_cost_usd: float,
    total_tokens: int,
    total_time_s: float,
) -> dict[str, float]:
    """Compute all three informational efficiency variants.

    - eta_usd:   bits per dollar (primary, from paper)
    - eta_token:  bits per token (model-comparison metric)
    - eta_time:   bits per second (latency-sensitive metric)
    """
    return {
        "eta_usd": capacity / total_cost_usd if total_cost_usd > 0 else float("inf"),
        "eta_token": capacity / total_tokens if total_tokens > 0 else float("inf"),
        "eta_time": capacity / total_time_s if total_time_s > 0 else float("inf"),
    }

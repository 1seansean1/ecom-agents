"""Tests for APS channel information-theoretic computations."""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.aps.channel import (
    ConfusionMatrix,
    build_confusion_matrix,
    channel_capacity_blahut_arimoto,
    compute_eta_variants,
    mutual_information,
)


class TestConfusionMatrix:
    def test_basic_construction(self):
        cm = ConfusionMatrix(
            sigma_in_labels=["a", "b"],
            sigma_out_labels=["x", "y"],
            counts=np.array([[10, 0], [0, 10]], dtype=np.float64),
        )
        assert cm.n_in == 2
        assert cm.n_out == 2
        assert cm.total == 20

    def test_conditional_distribution_perfect(self):
        """Perfect channel: each input maps to exactly one output."""
        cm = ConfusionMatrix(
            sigma_in_labels=["a", "b"],
            sigma_out_labels=["x", "y"],
            counts=np.array([[10, 0], [0, 10]], dtype=np.float64),
        )
        P = cm.conditional_distribution()
        np.testing.assert_array_almost_equal(P, [[1, 0], [0, 1]])

    def test_conditional_distribution_uniform(self):
        """Noisy channel: each input maps uniformly to all outputs."""
        cm = ConfusionMatrix(
            sigma_in_labels=["a", "b"],
            sigma_out_labels=["x", "y"],
            counts=np.array([[5, 5], [5, 5]], dtype=np.float64),
        )
        P = cm.conditional_distribution()
        np.testing.assert_array_almost_equal(P, [[0.5, 0.5], [0.5, 0.5]])

    def test_zero_row_gets_uniform(self):
        """Rows with no observations get uniform distribution."""
        cm = ConfusionMatrix(
            sigma_in_labels=["a", "b"],
            sigma_out_labels=["x", "y"],
            counts=np.array([[10, 0], [0, 0]], dtype=np.float64),
        )
        P = cm.conditional_distribution()
        np.testing.assert_array_almost_equal(P[0], [1, 0])
        np.testing.assert_array_almost_equal(P[1], [0.5, 0.5])

    def test_build_from_observations(self):
        obs = [
            {"sigma_in": "a", "sigma_out": "x"},
            {"sigma_in": "a", "sigma_out": "x"},
            {"sigma_in": "b", "sigma_out": "y"},
        ]
        cm = build_confusion_matrix(obs, ["a", "b"], ["x", "y"])
        assert cm.total == 3
        assert cm.counts[0, 0] == 2  # a -> x
        assert cm.counts[1, 1] == 1  # b -> y

    def test_build_ignores_unknown_symbols(self):
        obs = [
            {"sigma_in": "a", "sigma_out": "x"},
            {"sigma_in": "UNKNOWN", "sigma_out": "UNKNOWN"},  # should be ignored
        ]
        cm = build_confusion_matrix(obs, ["a"], ["x"])
        assert cm.total == 1


class TestMutualInformation:
    def test_perfect_channel(self):
        """Perfect channel: I(X;Y) = log2(|alphabet|) = 1 bit for 2x2."""
        cm = ConfusionMatrix(
            sigma_in_labels=["a", "b"],
            sigma_out_labels=["x", "y"],
            counts=np.array([[50, 0], [0, 50]], dtype=np.float64),
        )
        mi = mutual_information(cm)
        assert abs(mi - 1.0) < 0.01

    def test_noisy_channel(self):
        """Completely noisy channel: I(X;Y) = 0."""
        cm = ConfusionMatrix(
            sigma_in_labels=["a", "b"],
            sigma_out_labels=["x", "y"],
            counts=np.array([[25, 25], [25, 25]], dtype=np.float64),
        )
        mi = mutual_information(cm)
        assert mi < 0.01

    def test_empty_counts(self):
        cm = ConfusionMatrix(
            sigma_in_labels=["a"],
            sigma_out_labels=["x"],
            counts=np.array([[0]], dtype=np.float64),
        )
        assert mutual_information(cm) == 0.0

    def test_mi_bounded(self):
        """MI should be non-negative and bounded by log2(min(|in|, |out|))."""
        cm = ConfusionMatrix(
            sigma_in_labels=["a", "b", "c"],
            sigma_out_labels=["x", "y"],
            counts=np.array([[30, 0], [0, 30], [15, 15]], dtype=np.float64),
        )
        mi = mutual_information(cm)
        assert mi >= 0
        assert mi <= math.log2(min(3, 2)) + 0.01


class TestChannelCapacity:
    def test_perfect_binary_channel(self):
        """BSC with zero error rate: capacity = 1 bit."""
        cm = ConfusionMatrix(
            sigma_in_labels=["a", "b"],
            sigma_out_labels=["x", "y"],
            counts=np.array([[50, 0], [0, 50]], dtype=np.float64),
        )
        cap = channel_capacity_blahut_arimoto(cm)
        assert abs(cap - 1.0) < 0.01

    def test_useless_channel(self):
        """Completely noisy channel: capacity = 0."""
        cm = ConfusionMatrix(
            sigma_in_labels=["a", "b"],
            sigma_out_labels=["x", "y"],
            counts=np.array([[25, 25], [25, 25]], dtype=np.float64),
        )
        cap = channel_capacity_blahut_arimoto(cm)
        assert cap < 0.01

    def test_capacity_gte_mi(self):
        """Channel capacity >= mutual information for same data."""
        cm = ConfusionMatrix(
            sigma_in_labels=["a", "b", "c"],
            sigma_out_labels=["x", "y", "z"],
            counts=np.array([
                [20, 5, 0],
                [0, 20, 5],
                [5, 0, 20],
            ], dtype=np.float64),
        )
        mi = mutual_information(cm)
        cap = channel_capacity_blahut_arimoto(cm)
        assert cap >= mi - 0.01  # small tolerance

    def test_single_input(self):
        """Single input symbol: capacity = 0."""
        cm = ConfusionMatrix(
            sigma_in_labels=["a"],
            sigma_out_labels=["x", "y"],
            counts=np.array([[10, 5]], dtype=np.float64),
        )
        cap = channel_capacity_blahut_arimoto(cm)
        assert cap == 0.0

    def test_larger_alphabet(self):
        """7-symbol channel like K1 fine."""
        counts = np.eye(7, dtype=np.float64) * 10
        cm = ConfusionMatrix(
            sigma_in_labels=[f"s{i}" for i in range(7)],
            sigma_out_labels=[f"s{i}" for i in range(7)],
            counts=counts,
        )
        cap = channel_capacity_blahut_arimoto(cm)
        # Perfect 7-symbol channel: capacity = log2(7) ≈ 2.807
        assert abs(cap - math.log2(7)) < 0.05


class TestEtaVariants:
    def test_normal(self):
        eta = compute_eta_variants(1.5, 0.01, 5000, 30.0)
        assert eta["eta_usd"] == 150.0
        assert eta["eta_token"] == pytest.approx(0.0003, abs=1e-5)
        assert eta["eta_time"] == 0.05

    def test_zero_cost(self):
        eta = compute_eta_variants(1.0, 0.0, 1000, 10.0)
        assert eta["eta_usd"] == float("inf")

    def test_zero_tokens(self):
        eta = compute_eta_variants(1.0, 0.01, 0, 10.0)
        assert eta["eta_token"] == float("inf")

    def test_zero_time(self):
        eta = compute_eta_variants(1.0, 0.01, 1000, 0.0)
        assert eta["eta_time"] == float("inf")

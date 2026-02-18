"""Tests for holly.arch.schema — Pydantic models for architecture.yaml."""

from __future__ import annotations

from holly.arch.schema import (
    ArchitectureDocument,
    Component,
    Connection,
    EdgeKind,
    LayerID,
    SADMetadata,
    SourceRef,
)


class TestSourceRef:
    def test_basic(self) -> None:
        ref = SourceRef(file="SAD.mermaid", line=42, raw="K1[\"Schema\"]")
        assert ref.line == 42


class TestComponent:
    def test_is_kernel(self) -> None:
        c = Component(
            id="K1", name="Schema Validation",
            layer=LayerID.L1_KERNEL, subgraph_id="KERNEL",
            source=SourceRef(file="SAD.mermaid", line=1),
        )
        assert c.is_kernel

    def test_not_kernel(self) -> None:
        c = Component(
            id="CONV", name="Conversation",
            layer=LayerID.L2_CORE, subgraph_id="CORE",
            source=SourceRef(file="SAD.mermaid", line=1),
        )
        assert not c.is_kernel


class TestConnection:
    def test_crosses_boundary(self) -> None:
        conn = Connection(
            source_id="CORE", target_id="KERNEL",
            kind=EdgeKind.IN_PROCESS,
            crosses_boundary=True,
            source_layer=LayerID.L2_CORE,
            target_layer=LayerID.L1_KERNEL,
            source_ref=SourceRef(file="SAD.mermaid", line=1),
        )
        assert conn.crosses_boundary


class TestArchitectureDocument:
    def test_component_count(self) -> None:
        doc = ArchitectureDocument(
            metadata=SADMetadata(sad_version="0.1.0.5", sad_file="SAD.mermaid"),
            components={
                "K1": Component(
                    id="K1", name="Schema", layer=LayerID.L1_KERNEL,
                    subgraph_id="KERNEL",
                    source=SourceRef(file="SAD.mermaid", line=1),
                ),
                "CONV": Component(
                    id="CONV", name="Conversation", layer=LayerID.L2_CORE,
                    subgraph_id="CORE",
                    source=SourceRef(file="SAD.mermaid", line=2),
                ),
            },
        )
        assert doc.component_count == 2

    def test_components_in_layer(self) -> None:
        doc = ArchitectureDocument(
            metadata=SADMetadata(sad_version="0.1.0.5", sad_file="SAD.mermaid"),
            components={
                "K1": Component(
                    id="K1", name="Schema", layer=LayerID.L1_KERNEL,
                    subgraph_id="KERNEL",
                    source=SourceRef(file="SAD.mermaid", line=1),
                ),
                "CONV": Component(
                    id="CONV", name="Conversation", layer=LayerID.L2_CORE,
                    subgraph_id="CORE",
                    source=SourceRef(file="SAD.mermaid", line=2),
                ),
            },
        )
        kernel_comps = doc.components_in_layer(LayerID.L1_KERNEL)
        assert len(kernel_comps) == 1
        assert kernel_comps[0].id == "K1"

    def test_serialization_roundtrip(self) -> None:
        doc = ArchitectureDocument(
            metadata=SADMetadata(sad_version="0.1.0.5", sad_file="SAD.mermaid"),
        )
        data = doc.model_dump(mode="json")
        doc2 = ArchitectureDocument.model_validate(data)
        assert doc2.metadata.sad_version == "0.1.0.5"

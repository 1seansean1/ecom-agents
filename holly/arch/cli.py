"""CLI for architecture extraction: SAD mermaid → architecture.yaml.

Usage:
    python -m holly.arch.cli extract docs/architecture/SAD_0.1.0.5.mermaid -o architecture.yaml
    python -m holly.arch.cli stats docs/architecture/SAD_0.1.0.5.mermaid
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from holly.arch.extract import extract_from_file, to_yaml, write_architecture_yaml
from holly.arch.sad_parser import parse_sad_file


def cmd_extract(args: argparse.Namespace) -> None:
    """Extract architecture.yaml from a SAD mermaid file."""
    sad_path = Path(args.sad_file)
    if not sad_path.exists():
        print(f"ERROR: SAD file not found: {sad_path}", file=sys.stderr)
        sys.exit(1)

    doc = extract_from_file(sad_path)

    if args.output:
        output_path = Path(args.output)
        write_architecture_yaml(doc, output_path)
        print(f"Wrote {output_path} ({doc.component_count} components, "
              f"{doc.connection_count} connections, "
              f"{doc.boundary_crossing_count} boundary crossings)")
    else:
        print(to_yaml(doc))


def cmd_stats(args: argparse.Namespace) -> None:
    """Print statistics about a SAD mermaid file."""
    sad_path = Path(args.sad_file)
    if not sad_path.exists():
        print(f"ERROR: SAD file not found: {sad_path}", file=sys.stderr)
        sys.exit(1)

    ast = parse_sad_file(sad_path)
    doc = extract_from_file(sad_path)

    print(f"SAD: {sad_path.name}")
    print(f"  Version:      {doc.metadata.sad_version}")
    print(f"  Chart:        {ast.chart_type} {ast.chart_direction}")
    print(f"  Subgraphs:    {ast.subgraph_count}")
    print(f"  Nodes:        {ast.node_count}")
    print(f"  Edges:        {ast.edge_count}")
    print(f"  Components:   {doc.component_count}")
    print(f"  Connections:  {doc.connection_count}")
    print(f"  Boundary X:   {doc.boundary_crossing_count}")
    print(f"  K-invariants: {len(doc.kernel_invariants)}")
    print()
    print("Layer distribution:")
    from holly.arch.schema import LayerID
    for layer in LayerID:
        comps = doc.components_in_layer(layer)
        if comps:
            names = ", ".join(c.id for c in comps)
            print(f"  {layer.value:12s}  ({len(comps):2d})  {names}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="holly-arch",
        description="Holly architecture extraction tooling",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # extract
    p_extract = sub.add_parser("extract", help="Extract architecture.yaml from SAD")
    p_extract.add_argument("sad_file", help="Path to SAD mermaid file")
    p_extract.add_argument("-o", "--output", help="Output YAML path (stdout if omitted)")
    p_extract.set_defaults(func=cmd_extract)

    # stats
    p_stats = sub.add_parser("stats", help="Print SAD statistics")
    p_stats.add_argument("sad_file", help="Path to SAD mermaid file")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

import argparse
import sys

import nitful

# Priting is okay for the command line.
# ruff: noqa: T201


def _strip_command(args: argparse.Namespace) -> None:
    """Remove image data to create a metadata-only file."""
    print(f"Loading {args.input}...")
    nitf = nitful.load(args.input)

    # Replace all deferred payloads with a sentinel byte sequence.
    for segment in nitf.image_segments:
        segment.data = bytes.fromhex("DEADBEEF")

    print(f"Writing stripped file to {args.output}... ")
    nitful.save(nitf, args.output)
    print("Done.")


def _dump_command(args: argparse.Namespace) -> None:
    """Dump the file as text, optionally filtering for specific extensions."""
    nitf = nitful.load(args.input)

    out = sys.stdout if not args.output else open(args.output, "w")  # noqa: SIM115

    try:
        output_text = nitful.dump(
            nitf,
            header=args.header,
            image_nums=args.image,
            tre_names=args.tre,
            des_names=args.des,
        )
        out.write(output_text)
        out.write("\n")
    finally:
        if args.output:
            out.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="nitful", description="A NITF parser and manipulator."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    strip_parser = subparsers.add_parser(
        "strip", help="Strip pixel data from a NITF file."
    )
    strip_parser.add_argument("input", help="Path to the input NITF file.")
    strip_parser.add_argument("output", help="Path to the output stripped NITF file.")
    strip_parser.set_defaults(func=_strip_command)

    dump_parser = subparsers.add_parser("dump", help="Dump NITF metadata to text.")
    dump_parser.add_argument("input", help="Path to the input NITF file.")
    dump_parser.add_argument(
        "-o", "--output", help="Path to the output text file (defaults to stdout)."
    )
    dump_parser.add_argument(
        "--header", action="store_true", help="Print the main file header."
    )
    dump_parser.add_argument(
        "--image",
        action="append",
        type=int,
        default=[],
        help="Print image segments by index (1-based). Can be used multiple times.",
    )
    dump_parser.add_argument(
        "--tre",
        action="append",
        default=[],
        help="Filter output to only show specific TREs (can be used multiple times).",
    )
    dump_parser.add_argument(
        "--des",
        action="append",
        default=[],
        help="Filter output to only show specific DESs (can be used multiple times).",
    )
    dump_parser.set_defaults(func=_dump_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

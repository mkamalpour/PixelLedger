"""Start PixelLedger; imports never reset or seed an external database."""

import argparse
import os

try:
    from shop.database import ROOT
    import uvicorn
except (ImportError, ModuleNotFoundError) as exc:
    print(
        "\nPixelLedger could not start because a required dependency is missing.\n"
        "\nUse the assigned environment and install the project requirements first:\n"
        "  conda activate base\n"
        "  python -m pip install -r requirements.txt\n"
        "\nIf you are using the managed workspace, open the project workspace for the assigned interpreter.\n"
        f"Original error: {type(exc).__name__}: {exc}\n"
    )
    raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser(description="PixelLedger game shop simulator")
    parser.add_argument("--host", default=os.getenv("PIXELLEDGER_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("PIXELLEDGER_PORT", "8000"))
    )
    parser.add_argument("--reload", action="store_true", help="Development reload")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not os.getenv(
        "PIXELLEDGER_API_KEY"
    ):
        parser.error("Set PIXELLEDGER_API_KEY before listening beyond loopback")
    os.environ["PIXELLEDGER_HOST"] = args.host
    print(f"PixelLedger: http://{args.host}:{args.port}")
    uvicorn.run("shop.api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Unified CLI runner for the Romanian OSINT Political Intelligence System.

Usage:
    python main.py --stage all
    python main.py --stage ingest
    python main.py --stage select
    python main.py --stage agents
    python main.py --stage synthesize
"""

import argparse
import logging
import sys
from datetime import datetime

# Windows console UTF-8 output protection
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.orchestrator.pipeline import MasterPipeline


def setup_logging(level_name: str = "INFO") -> None:
    """Configure system logging format and level."""
    numeric_level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_arguments() -> argparse.Namespace:
    """Parse CLI arguments for pipeline execution."""
    parser = argparse.ArgumentParser(
        description="🇷🇴 Romanian OSINT Political Intelligence System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--stage",
        choices=["all", "ingest", "select", "agents", "synthesize"],
        default="all",
        help="Pipeline stage to execute (default: all)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target publication date (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--dossier",
        type=str,
        default="dossier_for_agent_1.txt",
        help="Path to press dossier file (default: dossier_for_agent_1.txt)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Console log output level (default: INFO)",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch real-time interactive OSINT Intelligence Dashboard",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Dashboard web server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Dashboard web server port (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    return parser.parse_args()


def main() -> int:
    """Main CLI entrypoint."""
    args = parse_arguments()
    setup_logging(args.log_level)

    if args.ui:
        import uvicorn
        print("=" * 65)
        print("  🇷🇴 RO-INTEL OSINT INTELLIGENCE DASHBOARD")
        print(f"  URL: http://{args.host}:{args.port}")
        print("  Panou de control în timp real & flux SSE")
        print("=" * 65)
        uvicorn.run("src.ui.app:app", host=args.host, port=args.port, reload=args.reload)
        return 0

    print("=" * 60)
    print("  🇷🇴 SISTEM OSINT MODULAR DE INTELIGENȚĂ POLITICĂ")
    print(f"  Etapă selectată: {args.stage.upper()}")
    print(f"  Data de lucru:   {args.date or datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 60)

    try:
        pipeline = MasterPipeline()
        results = pipeline.run(
            stage=args.stage,
            target_date=args.date,
            dossier_path=args.dossier,
        )
        print("\n[+] Execuție finalizată cu succes!")
        print(f"    Run ID:   {results.get('run_id')}")
        print(f"    Timp:     {results.get('duration_seconds')} secunde")
        return 0
    except KeyboardInterrupt:
        print("\n[-] Execuție întreruptă de utilizator.")
        return 130
    except Exception as e:
        logging.getLogger("main").exception("Pipeline failed with critical error: %s", e)
        print(f"\n[!] EROARE CRITICĂ: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

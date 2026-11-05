"""No HTTP request is made without --confirm-load and an explicit target variable."""

import os

from app.operations.common import OperationError, SafeArgumentParser, print_json
from app.operations.load import LoadConfig, run_load


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(description="Isolated stateful 500-logical-user / 30-RPS scenario")
    parser.add_argument("--target-route", required=True, help="Explicit API prefix, e.g. /api/v1")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--confirm-load", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--rps", type=int, default=30)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--max-in-flight", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=5)
    parser.add_argument("--allow-remote-target", action="store_true")
    try:
        args = parser.parse_args(argv)
        config = LoadConfig(
            target=os.environ.get("OPS_LOAD_TARGET", ""), route=args.target_route,
            namespace=os.environ.get("OPS_VERIFICATION_NAMESPACE", ""),
            users=args.users, requests_per_second=args.rps, duration_seconds=args.seconds,
            max_in_flight=args.max_in_flight, timeout_seconds=args.timeout_seconds,
            allow_remote_target=args.allow_remote_target,
        )
        if not args.confirm_load:
            print_json({"dry_run": True, "conditions": config.description(),
                        "database_contacted": False, "http_requests_sent": 0,
                        "isolation_preflight_verified": False})
            return 0
        report = run_load(config)
        print_json(report)
        return 0 if report["observed_client_thresholds_met"] else 1
    except OperationError as exc:
        print_json({"status": "refused", "code": str(exc)})
        return 2
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        print_json({"status": "failed", "code": "load_driver_failed"})
        return 2

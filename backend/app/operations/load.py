"""Open-loop request pacing over isolated stateful logical users, not 500 busy threads."""

import hashlib
import ipaddress
import math
import re
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid5

from app.operations.common import OperationError, canonical_uuid, verification_namespace
from app.operations.load_http import HttpTransport, TransportError

OPERATIONS = (
    "guest", "profile", "create_session", "get_session", "draft", "attempt", "health", "finish",
)


@dataclass(frozen=True, slots=True)
class LoadConfig:
    target: str
    route: str
    namespace: str
    users: int = 500
    requests_per_second: int = 30
    duration_seconds: int = 600
    max_in_flight: int = 30
    timeout_seconds: int = 5
    allow_remote_target: bool = False

    def __post_init__(self) -> None:
        verification_namespace(self.namespace)
        try:
            parsed = urlsplit(self.target)
            port = parsed.port
        except ValueError:
            raise OperationError("invalid_load_target") from None
        if (
            parsed.scheme not in {"http", "https"} or not parsed.hostname or port is None
            or not 1 <= port <= 65535 or parsed.path or parsed.query or parsed.fragment
            or parsed.username is not None or parsed.password is not None
            or any(char.isspace() for char in self.target)
        ):
            raise OperationError("explicit_load_origin_and_port_required")
        try:
            loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            loopback = False
        if not loopback and not self.allow_remote_target:
            raise OperationError("load_target_must_be_literal_loopback")
        if not loopback and parsed.scheme != "https":
            raise OperationError("remote_load_target_requires_https")
        if not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*api/v1", self.route):
            raise OperationError("explicit_api_target_route_required")
        bounds = (
            (self.users, 1, 500), (self.requests_per_second, 1, 30),
            (self.duration_seconds, 1, 600), (self.max_in_flight, 1, 30),
            (self.timeout_seconds, 1, 10),
        )
        if any(type(value) is not int or not low <= value <= high for value, low, high in bounds):
            raise OperationError("load_conditions_out_of_bounds")

    @property
    def planned_requests(self) -> int:
        return self.duration_seconds * self.requests_per_second

    def description(self) -> dict[str, Any]:
        return {
            "target_origin": self.target, "target_route": self.route, "namespace": self.namespace,
            "logical_users": self.users, "target_rps": self.requests_per_second,
            "target_duration_seconds": self.duration_seconds,
            "planned_requests": self.planned_requests,
            "max_in_flight_http_requests": min(self.users, self.max_in_flight),
            "request_timeout_seconds": self.timeout_seconds,
            "answer_strategy": "synthetic_integer_unknown_correctness",
            "http_connection_reuse": False,
        }


@dataclass(frozen=True, slots=True)
class Observation:
    user: int
    operation: str
    status_code: int
    latency_ms: float
    outcome: str
    guest_created: bool = False


@dataclass(frozen=True, slots=True, repr=False)
class _Request:
    operation: str
    method: str
    path: str
    body: dict[str, Any] | None = None
    key: str | None = None


@dataclass(slots=True, repr=False)
class VirtualUser:
    index: int
    config: LoadConfig
    transport: Any
    phase: str = "guest"
    guest_created: bool = False
    failed: bool = False
    exhausted: bool = False
    slots: list[int] = field(default_factory=list)
    session_id: str | None = None
    tasks: list[str] = field(default_factory=list)
    task_index: int = 0
    draft_revision: int = 0
    session_number: int = 0
    retries: int = 0
    _pending: _Request | None = None

    def _key(self, operation: str) -> str:
        namespace = UUID(self.config.namespace.removeprefix("verify_load_"))
        name = f"{self.index}:{self.session_number}:{self.task_index}:{operation}"
        return str(uuid5(namespace, name))

    def _answer(self) -> str:
        # Do not inspect feedback/solutions or hard-code correct answers from the content bank.
        value = hashlib.sha256(self._key("answer").encode("ascii")).digest()
        return str(int.from_bytes(value[:2]) - 32768)

    def _request(self) -> _Request:
        root = self.config.route
        if self.phase == "guest":
            return _Request("guest", "POST", root + "/guest", {})
        if self.phase in {"profile", "health"}:
            return _Request(self.phase, "GET", root + "/" + self.phase)
        if self.phase == "create_session":
            return _Request("create_session", "POST", root + "/sessions", {
                "slots": self.slots, "length": 5, "mode": "practice",
            }, self._key("create"))
        if self.session_id is None:
            raise OperationError("load_user_has_no_owned_session")
        path = root + "/sessions/" + canonical_uuid(self.session_id)
        if self.phase == "get_session":
            return _Request("get_session", "GET", path)
        if self.phase == "finish":
            return _Request("finish", "POST", path + "/finish", {}, self._key("finish"))
        body = {
            "task_id": self.tasks[self.task_index], "answer": self._answer(), "active_seconds": 1,
        }
        if self.phase == "draft":
            return _Request("draft", "PUT", path + "/draft", {
                **body, "expected_revision": self.draft_revision,
            })
        if self.phase == "attempt":
            return _Request("attempt", "POST", path + "/attempts", {**body, "skipped": False},
                            self._key("attempt"))
        raise OperationError("invalid_load_user_phase")

    def step(self) -> Observation:
        if self.failed:
            raise OperationError("disabled_load_user")
        request = self._pending or self._request()
        self._pending = request
        started, status, outcome = time.monotonic(), 0, "transport_error"
        try:
            status, payload = self.transport.request(
                request.method, request.path, request.body, request.key,
            )
            code = payload.get("error", {}).get("code") if (
                isinstance(payload, dict) and isinstance(payload.get("error"), dict)
            ) else None
            if status == 409 and request.operation == "create_session" and code == "bank_exhausted":
                self.exhausted, self.phase = True, "health"
                self._pending = None
                outcome = "bank_exhausted"
            elif status == 200:
                try:
                    self._accept(request.operation, payload)
                    self._pending, self.retries = None, 0
                    outcome = "success"
                except (OperationError, KeyError, TypeError, ValueError, IndexError):
                    self.failed, outcome = True, "protocol_error"
            else:
                outcome = "http_error"
                if status == 409 and request.operation == "draft" and code == "draft_conflict":
                    # A lost successful draft reply may advance the revision; fetch our own session.
                    self._pending, self.phase = None, "get_session"
                elif status >= 500:
                    self._retry_or_stop(request.operation)
                else:
                    self.failed = True
        except TransportError as exc:
            status = exc.status_code
            self._retry_or_stop(request.operation)
        except OperationError:
            self._retry_or_stop(request.operation)
        return Observation(
            self.index, request.operation, status, (time.monotonic() - started) * 1000,
            outcome, self.guest_created,
        )

    def _retry_or_stop(self, operation: str) -> None:
        self.retries += 1
        # Retrying an unacknowledged guest start can create orphan guests; never do it.
        if operation == "guest" or self.retries > 2:
            self.failed = True

    def _accept(self, operation: str, body: Any) -> None:
        if not isinstance(body, dict):
            raise OperationError("invalid_load_response")
        if operation == "guest":
            canonical_uuid(body["id"])
            if not self.transport.has_cookie:
                raise OperationError("guest_cookie_not_received")
            self.guest_created, self.phase = True, "profile"
        elif operation == "profile":
            slots = [slot["number"] for slot in body["slots"]]
            if not 1 <= len(slots) <= 100 or len(set(slots)) != len(slots) or any(
                type(slot) is not int or slot < 1 for slot in slots
            ):
                raise OperationError("invalid_load_profile")
            self.slots, self.phase = slots, "health" if self.exhausted else "create_session"
        elif operation in {"create_session", "get_session"}:
            session_id = canonical_uuid(body["id"])
            if operation == "get_session" and session_id != self.session_id:
                raise OperationError("load_session_identity_mismatch")
            tasks = [task["id"] for task in body["tasks"]]
            if not 1 <= len(tasks) <= 5 or len(set(tasks)) != len(tasks) or any(
                not isinstance(task, str) or not 1 <= len(task) <= 128 for task in tasks
            ):
                raise OperationError("invalid_load_task_ids")
            if body["status"] != "active" or body["mode"] != "practice":
                raise OperationError("unexpected_load_session_state")
            draft_revision = body["draft_revision"]
            if type(draft_revision) is not int or draft_revision < self.draft_revision:
                raise OperationError("invalid_load_draft_revision")
            self.session_id, self.tasks, self.draft_revision = session_id, tasks, draft_revision
            self.phase = "get_session" if operation == "create_session" else "draft"
        elif operation == "draft":
            revision = body["draft_revision"]
            if type(revision) is not int or revision != self.draft_revision + 1:
                raise OperationError("unexpected_load_draft_revision")
            self.draft_revision, self.phase = revision, "attempt"
        elif operation == "attempt":
            if body["task_id"] != self.tasks[self.task_index] or type(body["correct"]) is not bool:
                raise OperationError("unexpected_load_attempt_response")
            self.task_index += 1
            self.phase = "health"
        elif operation == "health":
            if body.get("status") != "ok":
                raise OperationError("load_target_unhealthy")
            self.phase = "profile" if self.exhausted else (
                "finish" if self.task_index == len(self.tasks) else "get_session"
            )
        elif operation == "finish":
            if body["id"] != self.session_id or body["status"] != "completed":
                raise OperationError("unexpected_load_finish_response")
            self.session_number += 1
            self.session_id, self.tasks, self.task_index, self.draft_revision = None, [], 0, 0
            self.phase = "profile"


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return round(sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)], 3)


class LoadStatistics:
    def __init__(self) -> None:
        self.results: list[Observation] = []
        self.users_by_minute: dict[int, set[int]] = defaultdict(set)
        self.dispatched = 0
        self.missed_schedule_slots = 0
        self.max_observed_in_flight = 0

    def observe(self, observation: Observation, started_seconds: float) -> None:
        if observation.operation not in OPERATIONS:
            raise OperationError("unknown_load_operation")
        self.results.append(observation)
        self.users_by_minute[int(started_seconds // 60)].add(observation.user)

    def report(self, config: LoadConfig, elapsed_seconds: float) -> dict[str, Any]:
        operations = {}
        for name in OPERATIONS:
            group = [row for row in self.results if row.operation == name]
            latencies = [row.latency_ms for row in group]
            operations[name] = {
                "completed": len(group),
                "successes": sum(row.outcome == "success" for row in group),
                "p50_ms": percentile(latencies, 0.5), "p95_ms": percentile(latencies, 0.95),
                "max_ms": round(max(latencies), 3) if latencies else None,
            }
        statuses: dict[str, int] = defaultdict(int)
        outcomes: dict[str, int] = defaultdict(int)
        for row in self.results:
            statuses[str(row.status_code)] += 1
            outcomes[row.outcome] += 1
        server_errors = sum(row.status_code >= 500 for row in self.results)
        statuses_received = sum(row.status_code != 0 for row in self.results)
        http_completed = sum(
            row.status_code != 0 and row.outcome != "transport_error" for row in self.results
        )
        error_rate = server_errors / statuses_received if statuses_received else None
        guests = len({row.user for row in self.results if row.guest_created})
        completed_users = len({
            row.user for row in self.results
            if row.operation == "finish" and row.outcome == "success"
        })
        attempted = operations["attempt"]["p95_ms"]
        other = [item["p95_ms"] for name, item in operations.items()
                 if name != "attempt" and item["p95_ms"] is not None]
        latency_met = (
            attempted is not None and bool(other) and attempted <= 500 and max(other) <= 800
        )
        execution_complete = (
            self.dispatched == config.planned_requests == http_completed
            and not self.missed_schedule_slots and guests == config.users
            and len(self.results) == self.dispatched
        )
        workload_complete = (
            execution_complete and completed_users == config.users
            and all(row.outcome == "success" for row in self.results)
        )
        all_users_active = all(
            len(self.users_by_minute.get(minute, set())) == config.users
            for minute in range(math.ceil(config.duration_seconds / 60))
        )
        observed_met = bool(
            workload_complete and latency_met and error_rate is not None and error_rate < 0.01
        )
        latencies = [row.latency_ms for row in self.results]
        return {
            "version": "1", "conditions": config.description(), "dry_run": False,
            "isolation_preflight_verified": True,
            "elapsed_seconds_including_drain": round(elapsed_seconds, 3),
            "requests_dispatched": self.dispatched, "requests_finished": len(self.results),
            "http_statuses_received": statuses_received,
            "http_responses_completed": http_completed,
            "achieved_rps_including_drain": round(http_completed / max(elapsed_seconds, 0.001), 3),
            "missed_schedule_slots": self.missed_schedule_slots,
            "max_observed_in_flight_http_requests": self.max_observed_in_flight,
            "guest_users_created": guests,
            "users_with_completed_session": completed_users,
            "completed_sessions": operations["finish"]["successes"],
            "logical_users_touched": len({row.user for row in self.results}),
            "active_logical_users_per_minute": {str(key): len(value)
                                                for key, value in self.users_by_minute.items()},
            "disabled_users": None,  # Assigned from the final user states by run_load.
            "status_counts": dict(statuses), "outcome_counts": dict(outcomes),
            "server_errors": server_errors, "server_error_rate": error_rate,
            "bank_exhaustion_responses": outcomes.get("bank_exhausted", 0),
            "p50_ms": percentile(latencies, 0.5), "p95_ms": percentile(latencies, 0.95),
            "max_ms": round(max(latencies), 3) if latencies else None,
            "operations": operations, "execution_complete": execution_complete,
            "workload_complete": workload_complete,
            "all_users_active_every_minute": all_users_active,
            "observed_client_thresholds_met": observed_met,
            "full_control_scenario_completed": workload_complete and all_users_active and (
                config.users == 500 and config.requests_per_second == 30
                and config.duration_seconds == 600
            ),
            "latency_includes_network_and_client_processing": True,
            "acceptance": "requires_infrastructure_protocol_and_server_side_timings",
        }


def verify_empty_target(transport: Any, config: LoadConfig) -> None:
    status, body = transport.request("GET", config.route + "/operations/load-target")
    if status != 200 or not isinstance(body, dict) or (
        body.get("version") != "1" or body.get("namespace") != config.namespace
        or body.get("database_namespace") != config.namespace or body.get("empty") is not True
        or body.get("counts") != {"guests": 0, "learning_sessions": 0, "attempts": 0}
    ):
        raise OperationError("load_target_isolation_or_empty_database_not_verified")


def run_load(
    config: LoadConfig, *, transport_factory: Callable[..., Any] = HttpTransport,
) -> dict[str, Any]:
    def transport():
        return transport_factory(config.target, namespace=config.namespace,
                                 timeout_seconds=config.timeout_seconds)

    verify_empty_target(transport(), config)
    users = [VirtualUser(index, config, transport()) for index in range(config.users)]
    statistics = LoadStatistics()
    active: dict[Future[Observation], tuple[int, float]] = {}
    started, next_user = time.monotonic(), 0
    workers = min(config.max_in_flight, config.users)

    def collect() -> None:
        for future in list(active):
            if future.done():
                _, dispatched_at = active.pop(future)
                statistics.observe(future.result(), dispatched_at)

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ops-load") as pool:
        for tick in range(config.planned_requests):
            delay = started + tick / config.requests_per_second - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            collect()
            # Late ticks are dropped instead of producing a catch-up burst or hiding saturation.
            if time.monotonic() - started > (tick + 1) / config.requests_per_second:
                statistics.missed_schedule_slots += 1
                continue
            busy = {index for index, _ in active.values()}
            selected = None
            if len(active) < workers:
                for _ in range(config.users):
                    candidate = next_user
                    next_user = (next_user + 1) % config.users
                    if candidate not in busy and not users[candidate].failed:
                        selected = candidate
                        break
            if selected is None:
                statistics.missed_schedule_slots += 1
                continue
            dispatched_at = time.monotonic() - started
            active[pool.submit(users[selected].step)] = (selected, dispatched_at)
            statistics.dispatched += 1
            statistics.max_observed_in_flight = max(statistics.max_observed_in_flight, len(active))
        remainder = started + config.duration_seconds - time.monotonic()
        if remainder > 0:
            time.sleep(remainder)
    collect()
    report = statistics.report(config, time.monotonic() - started)
    report["disabled_users"] = sum(user.failed for user in users)
    report["bank_exhausted_users"] = sum(user.exhausted for user in users)
    return report

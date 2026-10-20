"""Immutable per-request receipts. Ambiguous sends are never retried."""
from contextlib import contextmanager
from dataclasses import asdict
import json
import hashlib
import os
from pathlib import Path
import time

from research.integrity import read_json
from research.gemini_backend import InferenceError


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write_exclusive(path, text):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


class AmbiguousAttempt(RuntimeError):
    pass


class ResourcePause(InferenceError):
    def __init__(self):
        super().__init__("Resource reservation unavailable", code="RESOURCE_PAUSE")


def write_json(path, data):
    write_exclusive(path, json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")


@contextmanager
def exclusive_lock(path):
    """Kernel lock releases on process death; the lock file is never deleted."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Another process owns this run/resource ledger") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class QuotaLedger:
    """Shared local rolling windows, including failed and unresolved reservations.

    UTF-8 request bytes + output cap + 1024 is a deliberately high token
    reservation, not a measured tokenizer count. Other clients sharing the
    Google project are outside this ledger's visibility.
    """
    def __init__(self, directory, *, clock=time.time, sleep=time.sleep,
                 rpm=15, tpm=15000, rpd=14000):
        if not (1 <= rpm <= 30 and 1 <= tpm <= 16000 and 1 <= rpd <= 14400):
            raise ValueError("Quota exceeds reported free-tier limits")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.clock, self.sleep, self.rpm, self.tpm, self.rpd = clock, sleep, rpm, tpm, rpd

    def _events(self, suffix):
        values = [read_json(p) for p in self.directory.glob("*." + suffix + ".json")]
        for value in values:
            if value.get("sha256") != content_hash({k: v for k, v in value.items() if k != "sha256"}):
                raise ResourcePause()
        return values

    def reservation_tokens(self, payload):
        return len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + payload["generationConfig"]["maxOutputTokens"] + 1024

    def reserve(self, attempt_id, payload):
        budget = self.reservation_tokens(payload)
        if budget > self.tpm:
            raise ResourcePause()
        waited = 0.0
        while True:
            now = self.clock()
            reservations = self._events("reserved")
            if any(r["time"] > now + 1 for r in reservations):
                raise ResourcePause()  # Clock rollback cannot free quota.
            day = [r for r in reservations if now - r["time"] < 86400]
            if len(day) >= self.rpd:
                raise ResourcePause()
            minute = [r for r in day if now - r["time"] < 61]
            cooldowns = [r["until"] for r in self._events("cooldown")]
            delay = max([0, *(until - now for until in cooldowns)])
            if len(minute) >= self.rpm or sum(r["tokens"] for r in minute) + budget > self.tpm:
                delay = max(delay, min(r["time"] for r in minute) + 61 - now)
            if delay <= 0:
                path = self.directory / (attempt_id + ".reserved.json")
                value = {"attempt_id": attempt_id, "time": now, "tokens": budget}
                value["sha256"] = content_hash(value)
                write_json(path, value)
                return waited
            step = min(delay, 30)
            self.sleep(step)
            waited += step

    def cooldown(self, attempt_id, seconds):
        value = {"until": self.clock() + max(0, min(seconds, 86400))}
        value["sha256"] = content_hash(value)
        write_json(self.directory / (attempt_id + ".cooldown.json"), value)


class RequestJournal:
    def __init__(self, directory, binding, quota=None, *, clock=time.time, allow_reasoning_tokens=False):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.binding, self.quota, self.clock = binding, quota, clock
        if type(allow_reasoning_tokens) is not bool:
            raise ValueError("Explicit boolean reasoning-usage policy required")
        self.allow_reasoning_tokens = allow_reasoning_tokens
        self.receipts = []
        self.new_transient_error = False

    def transport(self, key, send):
        def request(payload, settings):
            identity = {"binding": self.binding, "key": key}
            attempt_id = content_hash(identity)
            prefix = self.directory / attempt_id
            claim_path, done_path = prefix.with_suffix(".claim.json"), prefix.with_suffix(".done.json")
            request_hash = content_hash({"payload": payload, "settings": asdict(settings)})
            if done_path.exists() and not claim_path.exists():
                raise AmbiguousAttempt("Receipt without claim")
            if claim_path.exists():
                claim = read_json(claim_path)
                if (claim.get("identity") != identity or claim.get("request_hash") != request_hash
                        or claim.get("sha256") != content_hash({k: v for k, v in claim.items() if k != "sha256"})):
                    raise AmbiguousAttempt("Claim changed")
                if not done_path.exists():
                    raise AmbiguousAttempt("INTERRUPTED_UNRESOLVED_NO_REROLL")
                done = read_json(done_path)
                if (done.get("request_hash") != request_hash or done.get("attempt_id") != attempt_id
                        or done.get("sha256") != content_hash({k: v for k, v in done.items() if k != "sha256"})):
                    raise AmbiguousAttempt("Receipt changed")
            else:
                lock = self.quota.directory / "quota.lock" if self.quota else self.directory / "transport.lock"
                with exclusive_lock(lock):
                    # A concurrent writer must never create a second reservation/send.
                    if claim_path.exists() or done_path.exists():
                        raise AmbiguousAttempt("Concurrent claim")
                    wait = self.quota.reserve(attempt_id, payload) if self.quota else 0.0
                    claim = {"identity": identity, "request_hash": request_hash,
                             "time": self.clock(), "status": "MAY_HAVE_REACHED_PROVIDER"}
                    claim["sha256"] = content_hash(claim)
                    write_json(claim_path, claim)  # fsync completes BEFORE network.
                    start = time.perf_counter()
                    done = {"request_hash": request_hash, "attempt_id": attempt_id,
                            "quota_wait_seconds": wait}
                    try:
                        response = send(payload, settings)
                        # Never persist private thought text, including on unexpected provider output.
                        # A thought:true part may be an empty Gemma 4 ghost marker.
                        # Record structural metadata only; never persist thought text.
                        marked_parts = 0
                        nonempty_marked_parts = 0
                        for candidate in response.get("candidates", []):
                            parts = candidate.get("content", {}).get("parts", [])
                            marked = [p for p in parts if p.get("thought")]
                            marked_parts += len(marked)
                            # Accept only exactly {"thought": true} or {"thought": true, "text": ""}.
                            # Whitespace, null text, non-boolean flags, signatures, and any other
                            # fields are NOT demonstrably empty and therefore remain forbidden.
                            nonempty_marked_parts += sum(
                                p.get("thought") is not True
                                or set(p) not in ({"thought"}, {"thought", "text"})
                                or ("text" in p and p["text"] != "")
                                for p in marked)
                            # Strip ALL thought-marked parts before writing any receipt.
                            candidate.get("content", {})["parts"] = [p for p in parts if not p.get("thought")]
                        usage = response.get("usageMetadata", {})
                        reasoning = usage.get("thoughtsTokenCount")
                        positive_reasoning = type(reasoning) in (int, float) and reasoning > 0
                        malformed_reasoning_count = ("thoughtsTokenCount" in usage and
                                                     (type(reasoning) is not int or reasoning < 0))
                        done["thought_marker_diagnostic"] = {
                            "marked_parts": marked_parts,
                            "nonempty_or_extra_payload_parts": nonempty_marked_parts,
                            "thought_token_count_reported": "thoughtsTokenCount" in usage,
                            "positive_thought_token_count": positive_reasoning,
                        }
                        done.update(status="RESPONSE", response=response)
                        # Missing thinking-token metadata is UNKNOWN, not evidence of zero tokens.
                        # Empty marker compatibility is deliberately limited to response parts;
                        # it does not alter requested thinkingLevel, includeThoughts or task schema.
                        if (nonempty_marked_parts or malformed_reasoning_count
                                or (positive_reasoning and not self.allow_reasoning_tokens)):
                            done.update(status="ERROR", code="THINKING_POLICY_VIOLATION", http_status=None,
                                        retry_after_seconds=None)
                            self.new_transient_error = True  # Pause; never repair/retry under a changed policy.
                    except InferenceError as exc:
                        done.update(status="ERROR", code=exc.code, http_status=exc.http_status,
                                    retry_after_seconds=exc.retry_after_seconds)
                        if exc.provider_diagnostics is not None:
                            done["provider_diagnostics"] = exc.provider_diagnostics
                        if exc.http_status in (429, 500, 502, 503, 504) or exc.code in ("TIMEOUT", "CONNECTION_FAILURE"):
                            self.new_transient_error = True
                            if self.quota:
                                self.quota.cooldown(attempt_id, exc.retry_after_seconds or (61 if exc.http_status == 429 else 15))
                    # Unknown exceptions/interruptions intentionally leave only a claim.
                    done["provider_latency_seconds"] = time.perf_counter() - start
                    done["sha256"] = content_hash(done)
                    write_json(done_path, done)
            self.receipts.append(done)
            if done["status"] == "ERROR":
                raise InferenceError("Recorded provider failure; no retry", code=done["code"],
                                     http_status=done["http_status"], retry_after_seconds=done.get("retry_after_seconds"),
                                     provider_diagnostics=done.get("provider_diagnostics"))
            return done["response"]
        return request

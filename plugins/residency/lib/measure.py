"""Zero-token headless measures of a pending settings change, with validation and cache.

One run is `claude --settings '<json>' --no-session-persistence --output-format json
-p "/context"` in the project root (~1 s, no transcript, cost 0). `-p` goes last because
variadic flags swallow what follows them.
"""
import hashlib
import json
import subprocess
import threading
import queue
from dataclasses import dataclass, field
from pathlib import Path

import snapshot

UNTOUCHED = ("MCP server instructions", "Memory files")  # a toggle cannot change these
TIMEOUT = 60
BASE = {"__base__": True}  # cache key of the headless base itself


class MeasureError(Exception):
    """The headless run failed (missing claude, timeout, bad exit, not free, bad output)."""


@dataclass
class Delta:
    ok: bool
    total: int = 0  # base total - changed total (negative: the change raises the cost)
    categories: dict = field(default_factory=dict)  # name -> base - changed
    cached: bool = False
    reason: str = ""  # why ok is False ("unknown")


def default_cache_path():
    return Path.home() / ".claude" / "residency-cache.json"


def claude_version(runner=subprocess.run):
    try:
        p = runner(["claude", "--version"], capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        raise MeasureError("claude --version failed: %s" % e)
    if p.returncode != 0:
        raise MeasureError("claude --version exited %s" % p.returncode)
    return p.stdout.strip()


def run_context(settings, project_dir, runner=subprocess.run):
    """Run headless /context with `settings` (dict or JSON text); return a Snapshot.

    A run with cost or turns != 0 raises MeasureError and is never retried by callers.
    """
    text = settings if isinstance(settings, str) else json.dumps(settings, sort_keys=True)
    cmd = ["claude", "--settings", text, "--no-session-persistence",
           "--output-format", "json", "-p", "/context"]
    try:
        p = runner(cmd, cwd=str(project_dir), capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        raise MeasureError("claude failed: %s" % e)
    if p.returncode != 0:
        raise MeasureError("claude exited %s: %s" % (p.returncode, (p.stderr or "").strip()[:200]))
    try:
        return snapshot.read_headless(p.stdout)
    except (ValueError, KeyError) as e:
        raise MeasureError(str(e))


def _hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


class Measurer:
    """Measures changes against a base; `effective` is the settings data the base is made of."""

    def __init__(self, project_dir, effective=None, cache_path=None, runner=subprocess.run,
                 untouched=UNTOUCHED):
        self.project_dir = str(project_dir)
        self.effective = effective if effective is not None else {}
        self.cache_path = Path(cache_path) if cache_path else default_cache_path()
        self.runner = runner
        self.untouched = untouched
        self._version = None
        self._base = None
        self._lock = threading.RLock()

    # cache
    def _key(self, change):
        if self._version is None:
            self._version = claude_version(self.runner)
        return "|".join((self._version, self.project_dir, _hash(self.effective), _hash(change)))

    def _load(self):
        try:
            data = json.loads(self.cache_path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _store(self, key, delta):
        data = self._load()
        # invalidate: drop entries of another version, project or settings hash
        prefix = key.rsplit("|", 1)[0] + "|"
        data = {k: v for k, v in data.items() if k.startswith(prefix)}
        data[key] = {"total": delta.total, "categories": delta.categories}
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(data, indent=1, sort_keys=True))
        except OSError:
            pass

    def cached(self, change):
        """The cached Delta of `change`, None when not cached; never runs a measure
        (only `claude --version`, which may raise MeasureError)."""
        hit = self._load().get(self._key(change))
        if not isinstance(hit, dict) or "total" not in hit:
            return None
        return Delta(True, hit["total"], dict(hit.get("categories") or {}), cached=True)

    def cached_base(self):
        """The headless base from memory or cache (Snapshot with total and categories),
        None when it was never measured; never runs `/context`."""
        if self._base is not None:
            return self._base
        hit = self._load().get(self._key(BASE))
        if not isinstance(hit, dict) or "total" not in hit:
            return None
        self._base = snapshot.Snapshot(total=hit["total"],
                                       categories=dict(hit.get("categories") or {}))
        return self._base

    # measure
    def base(self, refresh=False):
        with self._lock:
            if not refresh and self._base is None:
                self.cached_base()
            if self._base is None or refresh:
                self._base = run_context({}, self.project_dir, self.runner)
                self._store(self._key(BASE), Delta(True, self._base.total,
                                                   dict(self._base.categories)))
            return self._base

    def _valid(self, base, snap):
        return all(base.categories.get(c) == snap.categories.get(c) for c in self.untouched)

    def delta(self, change):
        """Token delta of `change` (a `--settings` dict): base total - changed total."""
        with self._lock:
            key = self._key(change)
            hit = self._load().get(key)
            if hit:
                return Delta(True, hit["total"], hit["categories"], cached=True)
            base = self.base()
            for attempt in (0, 1):
                snap = run_context(change, self.project_dir, self.runner)
                if self._valid(base, snap):
                    cats = {c: base.categories.get(c, 0) - snap.categories.get(c, 0)
                            for c in set(base.categories) | set(snap.categories)}
                    d = Delta(True, base.total - snap.total, cats)
                    self._store(key, d)
                    return d
                if attempt == 0:
                    base = self.base(refresh=True)
            return Delta(False, reason="unknown: untouched categories differ from base")


class Background:
    """Measures many changes in a thread; `callback(name, result)` gets a Delta or a MeasureError.

    A job submitted with `change=None` measures the headless base: the callback gets the
    base Snapshot.
    """

    def __init__(self, measurer, callback):
        self.measurer, self.callback = measurer, callback
        self._q = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()

    def submit(self, name, change):
        self._q.put((name, change))

    def cancel(self):
        """Drop what is queued and stop after the run in flight."""
        self._stop.set()
        self._q.put(None)

    def join(self, timeout=None):
        self._thread.join(timeout)

    def close(self):
        """Finish what is queued, then stop."""
        self._q.put(None)

    def _work(self):
        while not self._stop.is_set():
            job = self._q.get()
            if job is None or self._stop.is_set():
                return
            name, change = job
            try:
                res = self.measurer.base() if change is None else self.measurer.delta(change)
            except MeasureError as e:
                res = e
            self.callback(name, res)

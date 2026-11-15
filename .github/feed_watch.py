#!/usr/bin/env python3
"""feed_watch.py — T626 (PLAN95 v2 T9, D14): the DAILY feed watcher. Runs on a GitHub runner from
.github/workflows/feed-watch.yml in the update repo (default branch gh-pages; the coordinator copies both files there after S3).
A failed check fails the run, and GitHub mails the repo owner.

Checks (each one line: PASS / FAIL with the named reason):
  1 the published github.io feed vs the committed gh-pages head (read by SHA): every version* key equal, once the head is more
    than 30 min old (the 11-14 failed-Pages class between deploys)
  2 the update-server feed answers 200 — a 404 = "droplet feed absent (held on purpose, or down)" (while a hold is intended, the
    coordinator disables this workflow: gh workflow disable feed-watch.yml)
  3 every platform/channel tuple of the update-server feed (version + every download-family file name / SHA-256 / size) equals the
    committed feed's at its feed_derived_from
  4 GitHub has moved past feed_derived_from for more than 2 h with a higher serial = "droplet BEHIND" (e.g. a forgotten Windows half)
  5 a cf-mitigated header on the update-server answer = "challenged by Cloudflare" (Bot Fight Mode — G3)
Every URL is an argument (the defaults are production); with KC_SCRATCH set, a production default = exit 16 before any request.
FIX95 SEC-L1: the update server's feed_derived_from is followed only when it is a 40-hex commit SHA (else checks 3 + 4 FAIL), and
every value read from a feed or a header is printed escaped + capped (safe()), so it can never start an Actions workflow-command line.
User-Agent kc-feed-watch. Python 3 stdlib only. Exit 0 = every check passed, 1 = a check failed, 16 = test marker.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

PROD = {"repo": "volovicg/K-Configurator-Update", "api": "https://api.github.com", "raw": "https://raw.githubusercontent.com",
        "pages": "https://volovicg.github.io/K-Configurator-Update/update.json", "droplet": "https://updates.k-configurator.com"}
PROFILES = [(p, m) for p in ("mac", "win", "linux") for m in ("beta", "release")]
FAMILY = {"mac": ["_mac", "_mac_pkg"], "win": ["_win"], "linux": ["_linux", "_linux_deb"]}
SHA40_RE = re.compile(r"[0-9a-f]{40}")


def safe(v, n=80):
    """A value read from a feed or a header, for one log line: printable ASCII only (a backslash, a newline or any other
    character is escaped as a backslash sequence: two backslashes, x + 2 hex digits, u + 4, U + 8), capped at n characters."""
    out = []
    for c in str(v):
        o = ord(c)
        if c == "\\":
            out.append("\\\\")
        elif 32 <= o < 127:
            out.append(c)
        elif o < 256:
            out.append("\\x%02x" % o)
        elif o < 0x10000:
            out.append("\\u%04x" % o)
        else:
            out.append("\\U%08x" % o)
    t = "".join(out)
    return t if len(t) <= n else "%s...(+%d)" % (t[:n], len(t) - n)


def tuple_of(feed, plat, mode):
    b = "_beta" if mode == "beta" else ""
    t = []
    for s in FAMILY[plat]:
        u = feed.get("download_url" + b + s)
        t.append((b + s, u.rsplit("/", 1)[-1] if isinstance(u, str) else None, feed.get("download_sha256" + b + s),
                  feed.get("download_size" + b + s)))
    return feed.get("version%s_%s" % (b, plat)), t


class Watch:
    def __init__(self, a):
        self.a = a
        self.fails = 0
        self.token = os.environ.get("GITHUB_TOKEN", "")

    def get(self, url, api=False):
        req = urllib.request.Request(url, headers={"User-Agent": "kc-feed-watch", "Cache-Control": "no-cache"})
        if api and self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        if api:
            req.add_header("Accept", "application/vnd.github+json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() or b""

    def getjson(self, url, api=False):
        st, h, body = self.get(url, api)
        if st != 200:
            raise RuntimeError("%s answered %d" % (url, st))
        return json.loads(body.decode("utf-8"))

    def result(self, n, ok, msg):
        print("%s  check %d: %s" % ("PASS" if ok else "FAIL", n, msg), flush=True)
        if not ok:
            self.fails += 1


def age_s(iso, now):
    return now - datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k, v in PROD.items():
        ap.add_argument("--" + k, default=v)
    ap.add_argument("--now", type=float, default=None, help="test clock seam (unix seconds)")
    a = ap.parse_args()
    if os.environ.get("KC_SCRATCH"):
        prod = [k for k in PROD if getattr(a, k) == PROD[k]]
        if prod:
            print("REFUSED (16): KC_SCRATCH set but production defaults in use: %s" % ", ".join(prod), file=sys.stderr)
            return 16
    now = a.now if a.now is not None else time.time()
    w = Watch(a)
    try:
        hc = w.getjson("%s/repos/%s/commits/gh-pages" % (a.api, a.repo), api=True)
        head, head_date = hc["sha"], hc["commit"]["committer"]["date"]
        head_feed = w.getjson("%s/%s/%s/update.json" % (a.raw, a.repo, head))
    except (RuntimeError, ValueError, KeyError, urllib.error.URLError) as e:
        print("FAIL  the committed gh-pages head could not be read: %s" % e)
        return 1
    # 1
    try:
        pub = w.getjson("%s?cb=%d" % (a.pages, int(now)))
        diff = [k for k in sorted(set(pub) | set(head_feed)) if k.startswith("version") and pub.get(k) != head_feed.get(k)]
        old = age_s(head_date, now) > 30 * 60
        if diff and old:
            w.result(1, False, "published github.io differs from the committed head %s (%d min old): %s" % (
                head[:12], age_s(head_date, now) // 60,
                ", ".join("%s %s vs %s" % (safe(k), safe(repr(pub.get(k))), safe(repr(head_feed.get(k)))) for k in diff)))
        else:
            w.result(1, True, "published github.io = the committed head's version keys" if not diff else
                     "the head %s is only %d min old — not judged yet" % (head[:12], age_s(head_date, now) // 60))
    except (RuntimeError, ValueError, urllib.error.URLError) as e:
        w.result(1, False, "published github.io feed unreadable: %s" % e)
    # 2 + 5
    st, h, body = w.get(a.droplet + "/update.json")
    w.result(5, "cf-mitigated" not in h, "challenged by Cloudflare (cf-mitigated: %s)" % safe(h.get("cf-mitigated")) if "cf-mitigated" in h
             else "no cf-mitigated header")
    if st == 404:
        w.result(2, False, "droplet feed absent (held on purpose, or down) — 404")
        return 1
    if st != 200:
        w.result(2, False, "the update-server feed answered %d" % st)
        return 1
    try:
        df = json.loads(body.decode("utf-8"))
    except ValueError as e:
        w.result(2, False, "the update-server feed is not JSON: %s" % e)
        return 1
    w.result(2, True, "the update-server feed answers 200 (serial %s)" % safe(df.get("feed_serial")))
    # 3 — feed_derived_from is the update server's word: followed only as a 40-hex commit SHA (never another ref or a path)
    derived = df.get("feed_derived_from")
    derived_ok = isinstance(derived, str) and SHA40_RE.fullmatch(derived) is not None
    if not derived_ok:
        w.result(3, False, "feed_derived_from %s is not a 40-hex commit SHA — not followed" % safe(repr(derived)))
    else:
        try:
            at = w.getjson("%s/%s/%s/update.json" % (a.raw, a.repo, derived))
            bad = ["%s/%s" % pm for pm in PROFILES if tuple_of(df, *pm) != tuple_of(at, *pm)]
            w.result(3, not bad, ("tuples differ from GitHub at %s: %s" % (derived[:12], ", ".join(bad))) if bad else
                     "all six platform/channel tuples equal GitHub at feed_derived_from %s" % derived[:12])
        except (RuntimeError, ValueError, urllib.error.URLError) as e:
            w.result(3, False, "GitHub at feed_derived_from %s unreadable: %s" % (derived, safe(e, 160)))
    # 4
    if not derived_ok:
        w.result(4, False, "the lag could not be measured: feed_derived_from is not a commit SHA")
    else:
        try:
            gs, ds = head_feed.get("feed_serial", 0), df.get("feed_serial", 0)
            if derived == head or not isinstance(gs, int) or not isinstance(ds, int) or gs <= ds:
                w.result(4, True, "not behind (GitHub serial %s, update server %s)" % (safe(gs), safe(ds)))
            else:
                cmp_ = w.getjson("%s/repos/%s/compare/%s...%s" % (a.api, a.repo, derived, head), api=True)
                first = (cmp_.get("commits") or [{}])[0]
                first_date = ((first.get("commit") or {}).get("committer") or {}).get("date")
                lag = age_s(first_date, now) if first_date else 0
                w.result(4, lag <= 2 * 3600, ("droplet BEHIND: GitHub moved past %s %d min ago (serial %s vs %s)" % (
                    derived[:12], lag // 60, gs, ds)) if lag > 2 * 3600 else "GitHub is ahead by %d min (< 2 h: not yet)" % (lag // 60))
        except (RuntimeError, ValueError, urllib.error.URLError) as e:
            w.result(4, False, "the lag could not be measured: %s" % safe(e, 160))
    return 1 if w.fails else 0


if __name__ == "__main__":
    sys.exit(main())

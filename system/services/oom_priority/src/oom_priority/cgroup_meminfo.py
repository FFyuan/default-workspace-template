"""The container's own memory headroom, read from its cgroup, in the form
earlyoom's ``--host-meminfo`` takes.

Under runc the container's ``/proc/meminfo`` is the host kernel's, so an
earlyoom reading it alone would act at 10% of the whole machine while the
container's cgroup OOM killer acts at the workspace's cap. The cgroup v2 memory
controller the container runs in is what it sees at ``/sys/fs/cgroup`` (a
cgroup namespace), and from it the container can compute for itself what a
gen-2 slice VM publishes from outside under gVisor: the limit as ``MemTotal``
and, as ``MemAvailable``, the limit minus the usage plus what the kernel can
reclaim (page cache and reclaimable slab). The formula mirrors the gen-2
publisher in mngr (``mngr_imbue_cloud/slices/gen2_scripts/guest.py``); keep the
two in step.

The publisher steps aside wherever the cgroup it can see is not the enforcing
one. Under gVisor (``uname -r`` names it) the sandbox's cgroupfs is its own
view and carries no ``memory.max``; on a gen-2 slice the VM publishes the file
from outside, into the host volume mount. An uncapped container (``memory.max``
is ``max``) and a lima VM (whose root cgroup has no ``memory.max``) leave no
file, so earlyoom reads ``/proc/meminfo`` alone, which is the truth there.

Stdlib-only (see ``paths``): run by a supervisord program under a plain
``python3``.
"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Final

# Where earlyoom.conf points --host-meminfo. On a gen-2 slice this directory is
# the host volume mount and the VM writes the file; on local docker it is a
# plain directory this publisher creates.
HOST_MEMINFO_PATH: Final[Path] = Path("/mngr-vol/.host-meminfo")
# The container's own cgroup v2 memory controller, as the cgroup namespace shows it.
CGROUP_DIR: Final[Path] = Path("/sys/fs/cgroup")
# Well inside the 5 s staleness earlyoom tolerates, and what the gen-2 VM uses.
PUBLISH_INTERVAL_SECONDS: Final[float] = 0.25

# What the kernel can give back under pressure before the OOM killer runs.
_RECLAIMABLE_STAT_KEYS: Final[frozenset[str]] = frozenset(
    {"active_file", "inactive_file", "slab_reclaimable"}
)

# What one publishing round did; the publisher logs each change of outcome.
OUTCOME_PUBLISHED: Final[str] = "published"
OUTCOME_UNCAPPED: Final[str] = "uncapped"
OUTCOME_GVISOR: Final[str] = "gvisor"
OUTCOME_OUTSIDE: Final[str] = "outside"


def is_gvisor_kernel(kernel_release: str) -> bool:
    """Whether ``uname -r`` names gVisor (it reports ``4.19.0-gvisor``)."""
    return "gvisor" in kernel_release.lower()


def is_published_from_outside(target_path: Path) -> bool:
    """Whether the target's directory is a mount, i.e. the gen-2 host volume the VM writes into."""
    return os.path.ismount(target_path.parent)


def _read_int(path: Path) -> int | None:
    """The file's first line as an int; None when missing, unreadable, or not a number (``max``)."""
    try:
        text = path.read_text()
    except OSError:
        return None
    first_line = text.partition("\n")[0].strip()
    return int(first_line) if first_line.isdigit() else None


def _read_reclaimable_bytes(stat_path: Path) -> int:
    try:
        lines = stat_path.read_text().splitlines()
    except OSError:
        return 0
    reclaimable = 0
    for line in lines:
        key, _, value = line.partition(" ")
        if key in _RECLAIMABLE_STAT_KEYS and value.strip().isdigit():
            reclaimable += int(value)
    return reclaimable


def read_cgroup_memory_headroom(cgroup_dir: Path) -> tuple[int, int] | None:
    """``(limit_bytes, available_bytes)`` for a capped cgroup; None when uncapped or unreadable.

    Available is the limit minus the usage plus the reclaimable memory, clamped
    to ``[0, limit]``.
    """
    limit = _read_int(cgroup_dir / "memory.max")
    if limit is None:
        return None
    usage = _read_int(cgroup_dir / "memory.current")
    if usage is None:
        return None
    reclaimable = _read_reclaimable_bytes(cgroup_dir / "memory.stat")
    available = max(0, min(limit, limit - usage + reclaimable))
    return limit, available


def render_host_meminfo(
    limit_bytes: int, available_bytes: int, timestamp_seconds: int
) -> str:
    """The file in the ``/proc/meminfo`` subset earlyoom's ``--host-meminfo`` reads."""
    return (
        f"MemTotal: {limit_bytes // 1024} kB\n"
        f"MemAvailable: {available_bytes // 1024} kB\n"
        f"Timestamp: {timestamp_seconds}\n"
    )


def write_replacing(target_path: Path, content: str) -> None:
    """Replace the file by rename, since earlyoom rereads it on every poll."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.name}.{os.getpid()}.tmp")
    temp_path.write_text(content)
    os.replace(temp_path, target_path)


def publish_once(
    cgroup_dir: Path,
    target_path: Path,
    kernel_release: str,
    now_seconds: int,
    is_outside: Callable[[Path], bool] = is_published_from_outside,
) -> str:
    """One publishing round: write the headroom, remove a stale file, or step aside.

    Returns the ``OUTCOME_*`` naming what happened. The file is left alone where
    someone else owns it (gVisor, or a directory that is a mount), and removed
    while the container is uncapped so earlyoom falls back to ``/proc/meminfo``.
    """
    if is_gvisor_kernel(kernel_release):
        return OUTCOME_GVISOR
    if is_outside(target_path):
        return OUTCOME_OUTSIDE
    headroom = read_cgroup_memory_headroom(cgroup_dir)
    if headroom is None:
        target_path.unlink(missing_ok=True)
        return OUTCOME_UNCAPPED
    limit_bytes, available_bytes = headroom
    write_replacing(
        target_path, render_host_meminfo(limit_bytes, available_bytes, now_seconds)
    )
    return OUTCOME_PUBLISHED

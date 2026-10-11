from pathlib import Path

from oom_priority import cgroup_meminfo

_GIB = 1024**3


def _write_cgroup(
    cgroup_dir: Path,
    limit: str,
    usage: int,
    stat_lines: dict[str, int],
) -> None:
    cgroup_dir.mkdir(parents=True, exist_ok=True)
    (cgroup_dir / "memory.max").write_text(f"{limit}\n")
    (cgroup_dir / "memory.current").write_text(f"{usage}\n")
    (cgroup_dir / "memory.stat").write_text(
        "".join(f"{key} {value}\n" for key, value in stat_lines.items())
    )


def test_headroom_adds_reclaimable_page_cache_and_slab_to_the_free_part(
    tmp_path: Path,
) -> None:
    _write_cgroup(
        tmp_path,
        str(8 * _GIB),
        6 * _GIB,
        {
            "anon": 5 * _GIB,
            "active_file": _GIB // 2,
            "inactive_file": _GIB // 4,
            "slab_reclaimable": _GIB // 4,
            "slab_unreclaimable": _GIB,
        },
    )
    assert cgroup_meminfo.read_cgroup_memory_headroom(tmp_path) == (8 * _GIB, 3 * _GIB)


def test_headroom_is_clamped_to_the_limit_and_to_zero(tmp_path: Path) -> None:
    # Reclaimable cache can exceed what is in use at the start of a container's life.
    _write_cgroup(tmp_path, str(_GIB), 1024, {"inactive_file": 2 * _GIB})
    assert cgroup_meminfo.read_cgroup_memory_headroom(tmp_path) == (_GIB, _GIB)
    # Usage momentarily past the limit (the kernel is mid-reclaim) reads as no headroom.
    _write_cgroup(tmp_path, str(_GIB), _GIB + 4096, {})
    assert cgroup_meminfo.read_cgroup_memory_headroom(tmp_path) == (_GIB, 0)


def test_uncapped_and_absent_cgroups_have_no_headroom(tmp_path: Path) -> None:
    _write_cgroup(tmp_path, "max", 4096, {})
    assert cgroup_meminfo.read_cgroup_memory_headroom(tmp_path) is None
    # A lima VM's root cgroup, or gVisor's v1-style tree: no memory.max at all.
    assert cgroup_meminfo.read_cgroup_memory_headroom(tmp_path / "missing") is None


def test_render_writes_the_meminfo_subset_earlyoom_reads_in_kib() -> None:
    assert cgroup_meminfo.render_host_meminfo(8 * _GIB, 3 * _GIB, 1760000000) == (
        "MemTotal: 8388608 kB\nMemAvailable: 3145728 kB\nTimestamp: 1760000000\n"
    )


def test_gvisor_is_named_by_the_kernel_release() -> None:
    assert cgroup_meminfo.is_gvisor_kernel("4.19.0-gvisor")
    assert not cgroup_meminfo.is_gvisor_kernel("7.0.0-38-generic")


def test_publish_writes_the_file_by_rename_into_a_directory_it_creates(
    tmp_path: Path,
) -> None:
    _write_cgroup(tmp_path / "cgroup", str(8 * _GIB), 6 * _GIB, {"inactive_file": _GIB})
    target = tmp_path / "mngr-vol" / ".host-meminfo"
    outcome = cgroup_meminfo.publish_once(
        tmp_path / "cgroup",
        target,
        "7.0.0-38-generic",
        1760000000,
        is_outside=lambda _: False,
    )
    assert outcome == cgroup_meminfo.OUTCOME_PUBLISHED
    assert (
        target.read_text()
        == "MemTotal: 8388608 kB\nMemAvailable: 3145728 kB\nTimestamp: 1760000000\n"
    )
    # No temp file is left beside the published one.
    assert sorted(path.name for path in target.parent.iterdir()) == [".host-meminfo"]


def test_publish_removes_the_file_once_the_container_is_uncapped(
    tmp_path: Path,
) -> None:
    _write_cgroup(tmp_path / "cgroup", "max", 4096, {})
    target = tmp_path / "mngr-vol" / ".host-meminfo"
    target.parent.mkdir()
    target.write_text("MemTotal: 1 kB\nMemAvailable: 1 kB\nTimestamp: 1\n")
    outcome = cgroup_meminfo.publish_once(
        tmp_path / "cgroup",
        target,
        "7.0.0-38-generic",
        1760000000,
        is_outside=lambda _: False,
    )
    assert outcome == cgroup_meminfo.OUTCOME_UNCAPPED
    assert not target.exists()
    # Removing an already-absent file is fine too.
    assert (
        cgroup_meminfo.publish_once(
            tmp_path / "cgroup",
            target,
            "7.0.0-38-generic",
            1760000001,
            is_outside=lambda _: False,
        )
        == cgroup_meminfo.OUTCOME_UNCAPPED
    )


def test_publish_steps_aside_under_gvisor_and_leaves_the_hosts_file_alone(
    tmp_path: Path,
) -> None:
    _write_cgroup(tmp_path / "cgroup", str(8 * _GIB), 6 * _GIB, {})
    target = tmp_path / "mngr-vol" / ".host-meminfo"
    target.parent.mkdir()
    published_by_the_vm = (
        "MemTotal: 4194304 kB\nMemAvailable: 1048576 kB\nTimestamp: 5\n"
    )
    target.write_text(published_by_the_vm)
    outcome = cgroup_meminfo.publish_once(
        tmp_path / "cgroup",
        target,
        "4.19.0-gvisor",
        1760000000,
        is_outside=lambda _: False,
    )
    assert outcome == cgroup_meminfo.OUTCOME_GVISOR
    assert target.read_text() == published_by_the_vm


def test_publish_steps_aside_when_the_directory_is_someone_elses_mount(
    tmp_path: Path,
) -> None:
    _write_cgroup(tmp_path / "cgroup", str(8 * _GIB), 6 * _GIB, {})
    target = tmp_path / "mngr-vol" / ".host-meminfo"
    outcome = cgroup_meminfo.publish_once(
        tmp_path / "cgroup",
        target,
        "7.0.0-38-generic",
        1760000000,
        is_outside=lambda _: True,
    )
    assert outcome == cgroup_meminfo.OUTCOME_OUTSIDE
    assert not target.parent.exists()

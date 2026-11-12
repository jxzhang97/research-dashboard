import subprocess
import sys
from pathlib import Path

import pytest

from rd_core import cores, registry, scheduler

ROOT = Path(__file__).resolve().parent.parent


def test_ports_are_distinct_across_projects(tmp_path: Path, rd_home: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        subprocess.check_call([sys.executable, "-m", "rd_core.cli", "init", str(d), "--name", d.name], cwd=ROOT,
                              env={**__import__("os").environ, "RD_HOME": str(rd_home)})
    # 本机可能恰好有别的程序在监听某个端口，所以只断言"不同且递增"，不断言具体数字
    ports = {r["name"]: r["port"] for r in registry.list_projects()}
    assert set(ports) == {"a", "b"} and ports["a"] < ports["b"]
    assert registry.port_taken(ports["a"], exclude=b) == "a"
    assert registry.port_taken(ports["a"], exclude=a) is None
    assert registry.free_port(exclude=tmp_path / "c") > ports["b"]


def test_own_listening_port_is_not_taken(tmp_path: Path, monkeypatch):
    """重装时课题自己的 server 还在监听，不能把自己的端口当成被别人占了。"""
    (tmp_path / "p").mkdir()
    registry.register(tmp_path / "p", "p", 8010)
    monkeypatch.setattr(registry, "port_listening", lambda port: True)
    assert registry.port_taken(8010, exclude=tmp_path / "p") is None
    assert registry.port_taken(8010, exclude=tmp_path / "q") == "p"
    assert registry.port_taken(8011, exclude=tmp_path / "p") == "其他程序"


def test_duplicate_name_rejected(tmp_path: Path):
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    registry.register(tmp_path / "x", "same", 8010)
    with pytest.raises(RuntimeError):
        registry.register(tmp_path / "y", "same", 8011)


def test_jobs_registry_is_machine_wide(project_dir: Path, tmp_path: Path):
    other = tmp_path / "other"
    subprocess.check_call([sys.executable, "-m", "rd_core.cli", "init", str(other), "--name", "other"], cwd=ROOT,
                          env={**__import__("os").environ, "RD_HOME": str(tmp_path / "rd_home")})
    jid = cores.claim(other, 3, "ed-run")
    st = cores.status(project_dir)
    assert st["claimed"] == 3
    assert "别的课题 3 核" in st["advice"]
    assert cores.release(jid)
    assert cores.status(project_dir)["claimed"] == 0


def test_write_port_edits_config(project_dir: Path):
    scheduler.write_port(project_dir, 8015)
    assert "port = 8015" in (project_dir / "config.toml").read_text()
    from rd_core import config
    assert config.load(project_dir)["server"]["port"] == 8015


def test_machine_settings_default_file(rd_home: Path):
    ms = registry.machine_settings()
    assert ms["max_agents"] == 2 and (rd_home / "machine.toml").exists()


def test_free_cores_probe_fields(project_dir: Path):
    """rd free-cores 除了核数还报 CPU 的 system 占比、内存压缩/交换、数值进程的活跃线程，并给打架警告。"""
    st = cores.status(project_dir, probe=False)
    assert "warnings" in st and "cpu" not in st
    st = cores.status(project_dir, probe=True, cache_seconds=0)
    assert isinstance(st["warnings"], list) and isinstance(st["procs"], list) and "running_threads" in st
    if st["cpu"]:
        assert set(st["cpu"]) == {"user", "sys", "idle"}
    if st["mem"]:
        assert st["mem"]["ram_gb"] > 0


def test_thread_count_reads_subthread_rows():
    """ps -M 的子线程行没有 USER/TT 两列：以前按固定列号取状态，子线程永远数不到。样本取自 2026-11-12 studio 上打架的进程。"""
    rows = [
        "jiaxin 66196   ??   88.9 R    20T   0:24.18   6:34.88 /opt/anaconda3/bin/python3 scripts/su2mf.py",
        "       66196        87.6 R    20T   4:23.49   2:39.83 ",
        "       66196        87.2 R    20T   4:23.83   2:38.75 ",
        "       66196         0.0 S    31T   0:00.01   0:00.00 ",
    ]
    assert cores.count_running_threads(rows) == 3
    # 有的版本子线程行带 TT 列；列数变了也照样认
    assert cores.count_running_threads(["       66196   ??   91.0 R    20T   0:01.00   0:02.00 "]) == 1
    assert cores.count_running_threads(["jiaxin 1 s001 0.0 S 31T 0:00.01 0:00.00 zsh", ""]) == 0


def test_perf_cores_does_not_depend_on_path(monkeypatch):
    """launchd 起的服务 PATH 里没有 /usr/sbin；找不到 sysctl 时会退回逻辑核数，把能效核也算成性能核。"""
    import os
    full = cores.perf_cores()
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert cores.perf_cores() == full
    if os.path.exists("/usr/sbin/sysctl"):
        assert cores._sbin("sysctl") == "/usr/sbin/sysctl"

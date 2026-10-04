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

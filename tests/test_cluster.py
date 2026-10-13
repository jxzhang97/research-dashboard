"""集群作业：目录约定、提交把关（排队上限、单作业核数）、登记表与调度器联动、状态同步、清单。ssh/rsync 全部换成假的。"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rd_core import cluster, cores, fm
from rd_core.project import Project


class FakeCluster:
    """假的登录节点：记住收到的命令，按命令里的关键字回话。"""

    def __init__(self, pending=0, running=0):
        self.cmds = []
        self.queue = []  # squeue 行（dict）
        self.sacct = {}  # jid → (state, elapsed, end, exit)
        self.next_id = 1000
        for _ in range(pending):
            self._add("PENDING")
        for _ in range(running):
            self._add("RUNNING")

    def _add(self, state, name="x", cpus=1):
        self.next_id += 1
        self.queue.append({"id": str(self.next_id), "name": name, "state": state, "partition": "batch", "cpus": cpus,
                           "elapsed": "0:10", "timelimit": "3-00:00:00", "reason": "Priority" if state == "PENDING" else "None",
                           "submitted": "2026-10-13T00:00:00"})
        return str(self.next_id)

    def squeue(self):
        return "\n".join("|".join(str(j[k]) for k in ("id", "name", "state", "partition", "cpus", "elapsed", "timelimit", "reason", "submitted")) for j in self.queue) + "\n"

    def ssh(self, cs, cmd, timeout=60):
        self.cmds.append(cmd)
        if "sbatch" in cmd:
            assert "cd " in cmd and "mkdir -p logs" in cmd
            name = cmd.split("-J ")[1].split()[0]
            cpus = int(cmd.split("-c ")[1].split()[0])
            jid = self._add("PENDING", name=name, cpus=cpus)
            return f"{jid}\n"
        if cmd.startswith("squeue"):
            return self.squeue()
        if cmd.startswith("sacct"):
            ids = cmd.split("-j ")[1].split()[0].split(",")
            return "".join(f"{i}|{self.sacct[i][0]}|{self.sacct[i][1]}|{self.sacct[i][2]}|{self.sacct[i][3]}\n" for i in ids if i in self.sacct)
        if cmd.startswith("scancel"):
            jid = cmd.split()[1]
            self.queue = [j for j in self.queue if j["id"] != jid]
            self.sacct[jid] = ("CANCELLED", "0:05", "2026-10-13T01:00:00", "0:0")
            return ""
        if "@@sinfo" in cmd:
            return ("@@sinfo\nbatch*|2200/40/0/2240|allocated\nbatch*|100/20/0/120|mixed\nshort|0/40/0/40|idle\n"
                    "@@squeue\n" + self.squeue() + "@@df\n10.0.50.247:/bigscratch 70T 62T 8.8T 88% /bigscratch\nbeegfs 655T 641T 15T 98% /home\n"
                    "@@share\njiaxin_zh+ 3606571 0.012832\n@@limits\n32|600|cpu=320\n")
        if "for d in" in cmd and "@@dir" in cmd:
            return ("@@dir /bigscratch/jiaxin/demo/01-first-task\n@@total 1.2G 345\nruns|1.1G|340|2026-10-13 00:10\nruns/phase3|1.1G|340|2026-10-13 00:10\n"
                    "@@files\nSMG.out|2.1M|2026-10-12 23:00\n@@dir $HOME/demo/labs/01-first-task\n@@missing\n")
        if cmd.startswith("mkdir -p"):
            return "ok\n"
        raise AssertionError(f"假集群不认识的命令: {cmd[:120]}")


@pytest.fixture
def fake(monkeypatch):
    fc = FakeCluster()
    monkeypatch.setattr(cluster, "_ssh", fc.ssh)
    rs = []
    monkeypatch.setattr(cluster, "_rsync", lambda args, timeout=3600: rs.append(args) or ">f+++++++++ results/a.json\n")
    fc.rsync_calls = rs
    return fc


def _running_lab(project_dir: Path) -> None:
    fm.update(project_dir / "labs" / "01-first-task" / "brief.md", status="running")
    old = datetime.now() - timedelta(hours=3)
    d = project_dir / ".dashboard" / "runs" / (old.strftime("%Y%m%d-%H%M%S") + "-run_lab-01")
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({"id": d.name, "kind": "run_lab", "label": "run_lab:01-first-task", "status": "done",
                                             "result": "在等集群", "started": old.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")


def test_settings_dir_from_name(project_dir: Path):
    cs = cluster.settings(project_dir)
    assert cs["dir"] == "demo" and cs["scratch_dir"] == "/bigscratch/jiaxin/demo" and cs["home_dir"] == "~/demo"
    lp = cluster.lab_paths(cs, "01-first-task")
    assert lp == {"scratch": "/bigscratch/jiaxin/demo/01-first-task", "home": "~/demo/labs/01-first-task"}
    cfg = {"project": {"name": "Magic in heavy fermion"}, "cluster": {**cluster.config.DEFAULTS["cluster"]}}
    assert cluster.settings(None, cfg)["dir"] == "Magic_in_heavy_fermion"
    assert cluster._array_size("0-9") == 10 and cluster._array_size("0-9%2") == 10 and cluster._array_size("1,3,5-6") == 4 and cluster._array_size(None) == 1


def test_submit_records_and_registers(project_dir: Path, fake: FakeCluster):
    lab = project_dir / "labs" / "01-first-task"
    (lab / "cluster").mkdir()
    (lab / "cluster" / "phase3.sbatch").write_text("#!/bin/bash\n")
    rec = cluster.submit(project_dir, "01-first-task", "cluster/phase3.sbatch", cpus=2, name="p3", args=["U=1.5"])
    assert rec["slurm_id"] == "1001" and rec["partition"] == "batch" and rec["time"] == "3-00:00:00"
    assert rec["label"].startswith("01-first-task ") and rec["cwd"] == "~/demo/labs/01-first-task"
    sb = [c for c in fake.cmds if "sbatch" in c][-1]
    assert "cd \"$HOME/demo/labs/01-first-task\"" in sb and "-c 2" in sb and "cluster/phase3.sbatch U=1.5" in sb
    # 本机记录
    recs = cluster._read_jobs(project_dir, "01-first-task")
    assert len(recs) == 1 and recs[0]["slurm_id"] == "1001" and recs[0]["state"] == "PENDING"
    # 机器级登记表：host 是集群名、不占本机的核；lab_jobs 能按标签找到
    jobs = cores.list_jobs()
    assert len(jobs) == 1 and jobs[0]["slurm_id"] == "1001" and jobs[0]["host"] == "pod" and jobs[0]["pid"] is None
    assert [j["slurm_id"] for j in cores.lab_jobs(project_dir, "01-first-task")] == ["1001"]
    st = cores.status(project_dir, probe=False)
    assert st["claimed"] == 0 and len(st["remote_jobs"]) == 1 and "集群作业" in st["advice"]
    # 测试分区
    rec2 = cluster.submit(project_dir, "01-first-task", "cluster/phase3.sbatch", test=True)
    assert rec2["partition"] == "short" and rec2["time"] == "01:30:00"


def test_submit_refuses_over_limits(project_dir: Path, fake: FakeCluster):
    lab = project_dir / "labs" / "01-first-task"
    (lab / "cluster").mkdir()
    (lab / "cluster" / "a.sbatch").write_text("#!/bin/bash\n")
    for _ in range(8):
        fake._add("PENDING")
    with pytest.raises(RuntimeError, match="排队中已有 8"):
        cluster.submit(project_dir, "01-first-task", "cluster/a.sbatch")
    assert not any("sbatch" in c for c in fake.cmds)
    fake.queue = [j for j in fake.queue if j["state"] != "PENDING"][:0]
    for _ in range(6):
        fake._add("PENDING")
    with pytest.raises(RuntimeError, match="最多再交 2"):
        cluster.submit(project_dir, "01-first-task", "cluster/a.sbatch", array="0-4")
    with pytest.raises(RuntimeError, match="单作业 40 核"):
        cluster.submit(project_dir, "01-first-task", "cluster/a.sbatch", cpus=40)
    # 在跑的不算排队
    fake.queue = []
    for _ in range(20):
        fake._add("RUNNING")
    assert cluster.submit(project_dir, "01-first-task", "cluster/a.sbatch")["slurm_id"]


def test_finished_cluster_job_wakes_resume(project_dir: Path, fake: FakeCluster):
    """登记的集群作业结束 → 登记表修剪掉它 → 调度器派续跑并在提示里说明。"""
    from rd_core import tick
    lab = project_dir / "labs" / "01-first-task"
    (lab / "cluster").mkdir()
    (lab / "cluster" / "a.sbatch").write_text("#!/bin/bash\n")
    _running_lab(project_dir)
    pr = Project(project_dir)
    rec = cluster.submit(project_dir, "01-first-task", "cluster/a.sbatch", cpus=4, label="01-first-task pod phase3")
    pr.set_lab_jobs_snapshot("01-first-task", {j["id"]: j["label"] for j in cores.lab_jobs(project_dir, "01-first-task")})
    ready, deferred = tick.actionable(pr)
    assert not ready and deferred and deferred[0]["last_status"] == "numerics" and "phase3" in deferred[0]["reason"]
    # 作业跑完：squeue 里没了（缓存过期后重新查）
    fake.queue = [j for j in fake.queue if j["id"] != rec["slurm_id"]]
    fake.sacct[rec["slurm_id"]] = ("COMPLETED", "1-02:00:00", "2026-10-14T03:00:00", "0:0")
    cache = cluster._cache_path(cluster.settings(project_dir))
    c = json.loads(cache.read_text()); c["t"] = time.time() - 1000; cache.write_text(json.dumps(c))
    assert cores.lab_jobs(project_dir, "01-first-task") == []
    ready, deferred = tick.actionable(pr)
    assert ready and ready[0]["kind"] == "resume_lab" and "phase3" in ready[0]["wake_note"]
    # 状态同步：记录变 COMPLETED，登记表已空
    recs = cluster.sync(project_dir, "01-first-task")
    assert recs[0]["state"] == "COMPLETED" and recs[0]["elapsed"] == "1-02:00:00"
    assert cores.list_jobs() == []


def test_ssh_failure_keeps_jobs(project_dir: Path, fake: FakeCluster, monkeypatch):
    lab = project_dir / "labs" / "01-first-task"
    (lab / "cluster").mkdir()
    (lab / "cluster" / "a.sbatch").write_text("#!/bin/bash\n")
    cluster.submit(project_dir, "01-first-task", "cluster/a.sbatch")
    cache = cluster._cache_path(cluster.settings(project_dir))
    cache.unlink()

    def boom(cs, cmd, timeout=60):
        raise RuntimeError("ssh 失败")
    monkeypatch.setattr(cluster, "_ssh", boom)
    assert len(cores.list_jobs()) == 1  # 查不到就不放


def test_status_init_push_pull_inventory(project_dir: Path, fake: FakeCluster):
    st = cluster.status(project_dir)
    assert st["partitions"]["batch"]["idle"] == 60 and st["partitions"]["short"]["idle"] == 40 and st["room"] == 8
    assert "最多再交 8" in st["advice"] and st["fairshare"] == "0.012832"
    out = cluster.init(project_dir)
    assert out["scratch_dir"] == "/bigscratch/jiaxin/demo" and "mkdir -p" in fake.cmds[-1] and "README.md" in fake.cmds[-1]
    (project_dir / "src" / "tool.py").write_text("x=1\n")
    done = cluster.push(project_dir, ["src", "labs/01-first-task/brief.md"])
    assert len(done) == 2 and fake.rsync_calls[0][-1] == "pod-login1.cnsi.ucsb.edu:~/demo/src/" and fake.rsync_calls[1][-1].endswith(":~/demo/labs/01-first-task/")
    with pytest.raises(FileNotFoundError):
        cluster.push(project_dir, ["nope"])
    done = cluster.pull(project_dir, "01-first-task")
    assert fake.rsync_calls[-1][-2] == "pod-login1.cnsi.ucsb.edu:~/demo/labs/01-first-task/results/" and (project_dir / "labs" / "01-first-task" / "results").is_dir()
    done = cluster.pull(project_dir, "01-first-task", ["runs/phase3"], scratch=True)
    assert fake.rsync_calls[-1][-2] == "pod-login1.cnsi.ucsb.edu:/bigscratch/jiaxin/demo/01-first-task/runs/phase3/"
    assert fake.rsync_calls[-1][-1].endswith("/01-first-task/cluster/runs/phase3/")
    p = cluster.inventory(project_dir, "01-first-task")
    text = p.read_text(encoding="utf-8")
    assert p.name == "inventory.md" and "/bigscratch/jiaxin/demo/01-first-task/" in text and "`runs/phase3`" in text and "1.2G" in text and "还没有提交过作业" in text


def test_cancel(project_dir: Path, fake: FakeCluster):
    lab = project_dir / "labs" / "01-first-task"
    (lab / "cluster").mkdir()
    (lab / "cluster" / "a.sbatch").write_text("#!/bin/bash\n")
    rec = cluster.submit(project_dir, "01-first-task", "cluster/a.sbatch")
    out = cluster.cancel(project_dir, rec["slurm_id"])
    assert out["record"]["state"] == "CANCELLED" and cores.list_jobs() == []
    assert cluster._read_jobs(project_dir, "01-first-task")[0]["state"] == "CANCELLED"

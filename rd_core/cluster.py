"""校园集群（Slurm，默认 UCSB CSC 的 Pod）：把重的数值批量分摊到集群上跑。

约定（AGENTS.md §5、skills/rd-lab/cluster.md）：
- 集群上一个课题一个文件夹（`[cluster].dir`，默认课题名、空白换下划线）：
  大的中间数据放 `scratch_root/<dir>/<lab id>/`（/bigscratch，NVMe、不备份）；
  代码与最后画图用的汇总数据放 `home_root/<dir>/`，目录结构与课题目录一致（`labs/<lab id>/`、`src/`）。
- 作业一律 sbatch；同时排队（PD）的作业不超过 `max_pending`（在跑的不算）；单作业核数不超过 `max_cpus_per_job`；
  测试用 `test_partition`（short，2 小时）。
- 每次提交记进本机 `labs/<lab>/cluster/jobs.jsonl`，并登记到 ~/.rd/jobs.json（host=集群名、slurm_id），
  调度器据此等数值、作业一结束就叫醒续跑（tick.actionable → cores.lab_jobs）。
- `rd cluster inventory` 把集群上的目录清单与作业表写进 `labs/<lab>/cluster/inventory.md`，DATA.md 链接它。"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
from pathlib import Path

from . import config, registry

CACHE_SECONDS = 300          # squeue 结果缓存：dashboard 每 15 秒扫一次待办，不能每次都 ssh
SSH_TIMEOUT = 60


# ---------- 配置 ----------
def settings(project: Path | None, cfg: dict | None = None) -> dict:
    """[cluster] 配置 + 由课题名推出的目录。project 为 None 时只用默认值（机器级登记表修剪时用）。"""
    cfg = cfg or (config.load(project) if project else config.DEFAULTS)
    cs = dict(cfg.get("cluster") or config.DEFAULTS["cluster"])
    name = (cfg.get("project") or {}).get("name") or (project.name if project else "")
    if not cs.get("dir"):
        cs["dir"] = re.sub(r"\s+", "_", name.strip()) or "project"
    cs["scratch_dir"] = f"{cs['scratch_root'].rstrip('/')}/{cs['dir']}"
    cs["home_dir"] = f"{cs['home_root'].rstrip('/')}/{cs['dir']}"
    return cs


def lab_paths(cs: dict, lab_id: str) -> dict:
    return {"scratch": f"{cs['scratch_dir']}/{lab_id}", "home": f"{cs['home_dir']}/labs/{lab_id}"}


def _sh(path: str) -> str:
    """远端 shell 里用的路径：开头的 ~ 换成 $HOME（放在双引号里展开）。"""
    return path.replace("~", "$HOME", 1) if path.startswith("~") else path


def _q(path: str) -> str:
    return f'"{_sh(path)}"'


# ---------- ssh / rsync（测试里换成假的） ----------
def _ssh(cs: dict, cmd: str, timeout: int = SSH_TIMEOUT) -> str:
    """在集群登录节点用登录 shell 跑一条命令，返回 stdout；失败抛 RuntimeError。"""
    full = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", cs["ssh"], "bash", "-lc", shlex.quote(cmd)]
    try:
        r = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ssh {cs['ssh']} 超时（{timeout}s）")
    if r.returncode != 0:
        raise RuntimeError(f"ssh {cs['ssh']} 失败（{r.returncode}）：{(r.stderr or r.stdout).strip()[:800]}")
    return r.stdout


def _rsync(args: list[str], timeout: int = 3600) -> str:
    r = subprocess.run(["rsync", *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"rsync 失败（{r.returncode}）：{(r.stderr or r.stdout).strip()[:800]}")
    return r.stdout


# ---------- 队列状态 ----------
_SQ_FMT = "%i|%j|%T|%P|%C|%M|%l|%r|%V"


def _parse_squeue(text: str) -> list[dict]:
    out = []
    for ln in text.splitlines():
        p = ln.strip().split("|")
        if len(p) < 9:
            continue
        out.append({"id": p[0], "name": p[1], "state": p[2], "partition": p[3], "cpus": int(p[4] or 0), "elapsed": p[5],
                    "timelimit": p[6], "reason": p[7], "submitted": p[8]})
    return out


def _parse_sinfo(text: str) -> dict[str, dict]:
    """sinfo -h -o '%P|%C|%T' → 每个分区的 A/I/O/T 核数与节点状态计数。"""
    parts: dict[str, dict] = {}
    for ln in text.splitlines():
        p = ln.strip().split("|")
        if len(p) < 3:
            continue
        name = p[0].rstrip("*")
        try:
            a, i, o, t = (int(x) for x in p[1].split("/"))
        except ValueError:
            continue
        d = parts.setdefault(name, {"alloc": 0, "idle": 0, "other": 0, "total": 0, "states": {}})
        d["alloc"] += a; d["idle"] += i; d["other"] += o; d["total"] += t
        d["states"][p[2]] = d["states"].get(p[2], 0) + 1
    return parts


def _cache_path(cs: dict) -> Path:
    return registry.home() / f"cluster-{cs['name']}.json"


def _write_cache(cs: dict, jobs: list[dict]) -> None:
    _cache_path(cs).write_text(json.dumps({"t": time.time(), "jobs": jobs}, ensure_ascii=False), encoding="utf-8")


def my_jobs(cs: dict, max_age: float = CACHE_SECONDS) -> list[dict] | None:
    """我在集群上排队/在跑的作业（squeue -r，数组作业按任务展开）。max_age 秒内有缓存就用缓存；
    ssh 失败且没有缓存返回 None（"不知道"，调用方当作业还活着处理）。"""
    p = _cache_path(cs)
    if p.exists() and max_age > 0:
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            if time.time() - float(c.get("t", 0)) < max_age:
                return c.get("jobs") or []
        except (ValueError, OSError):
            pass
    try:
        jobs = _parse_squeue(_ssh(cs, f"squeue -u $USER -r -h -o '{_SQ_FMT}'", timeout=45))
    except RuntimeError:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")).get("jobs") or []
            except (ValueError, OSError):
                return None
        return None
    _write_cache(cs, jobs)
    return jobs


def _is_alive(jid: str, live: list[dict]) -> bool:
    """登记的作业号（数组作业只记父号）在 squeue 里还在不在。"""
    for j in live:
        if j["id"] == jid or j["id"].split("_")[0] == jid:
            return True
    return False


def alive_ids(host_name: str, ssh: str | None = None, max_age: float = CACHE_SECONDS) -> list[dict] | None:
    """给 cores.list_jobs 修剪登记表用：某个集群上我还活着的作业；None = 查不到。"""
    cs = dict(config.DEFAULTS["cluster"])
    cs["name"] = host_name
    if ssh:
        cs["ssh"] = ssh
    return my_jobs(cs, max_age)


def status(project: Path) -> dict:
    """一次 ssh：各分区空闲核、我的作业、磁盘、公平份额，并给出"现在还能交几个"的建议。"""
    cs = settings(project)
    script = (
        "echo @@sinfo; sinfo -h -o '%P|%C|%T'; "
        f"echo @@squeue; squeue -u $USER -r -h -o '{_SQ_FMT}'; "
        f"echo @@df; df -h {_q(cs['scratch_root'])} $HOME 2>/dev/null | tail -n +2; "
        "echo @@share; sshare -u $USER -h -o 'User,RawUsage,FairShare' 2>/dev/null | awk 'NF>=3 && $1!=\"\"' | tail -1; "
        "echo @@limits; sacctmgr -n -P show qos normal format=MaxJobsPU,MaxSubmitPU,MaxTRESPU 2>/dev/null"
    )
    out = _ssh(cs, script)
    sec: dict[str, list[str]] = {}
    cur = None
    for ln in out.splitlines():
        if ln.startswith("@@"):
            cur = ln[2:].strip()
            sec[cur] = []
        elif cur:
            sec[cur].append(ln)
    parts = _parse_sinfo("\n".join(sec.get("sinfo", [])))
    jobs = _parse_squeue("\n".join(sec.get("squeue", [])))
    _write_cache(cs, jobs)
    pending = [j for j in jobs if j["state"] == "PENDING"]
    running = [j for j in jobs if j["state"] == "RUNNING"]
    room = max(0, int(cs["max_pending"]) - len(pending))
    disk = [ln.split() for ln in sec.get("df", []) if ln.strip()]
    share = (sec.get("share") or [""])[0].split()
    st = {
        "cluster": cs["name"], "ssh": cs["ssh"], "partitions": parts, "jobs": jobs,
        "pending": len(pending), "running": len(running), "max_pending": int(cs["max_pending"]), "room": room,
        "max_cpus_per_job": int(cs["max_cpus_per_job"]), "partition": cs["partition"], "test_partition": cs["test_partition"],
        "disk": [{"fs": d[0], "size": d[1], "used": d[2], "avail": d[3], "use": d[4], "mount": d[-1]} for d in disk if len(d) >= 6],
        "fairshare": share[-1] if len(share) >= 3 else None,
        "scratch_dir": cs["scratch_dir"], "home_dir": cs["home_dir"],
    }
    b = parts.get(cs["partition"], {})
    s = parts.get(cs["test_partition"], {})
    st["advice"] = (
        f"集群 {cs['name']}：分区 {cs['partition']} 空闲 {b.get('idle', 0)}/{b.get('total', 0)} 核"
        f"（节点状态 {', '.join(f'{k} {v}' for k, v in sorted(b.get('states', {}).items()))}）；"
        f"{cs['test_partition']} 空闲 {s.get('idle', 0)}/{s.get('total', 0)} 核。"
        f"我的作业：在跑 {len(running)}、排队 {len(pending)}（上限 {cs['max_pending']}）→ 现在最多再交 {room} 个；"
        f"单作业最多 {cs['max_cpus_per_job']} 核。"
    )
    if st["fairshare"]:
        st["advice"] += f" 公平份额 {st['fairshare']}（越小排得越慢，小作业更容易被回填）。"
    return st


# ---------- 目录 ----------
def init(project: Path) -> dict:
    cs = settings(project)
    cfg = config.load(project)
    readme = (
        f"# {cfg['project']['name']}\n\n"
        f"research-dashboard 课题在集群上的工作目录（由 `rd cluster init` 创建，{time.strftime('%Y-%m-%d')}）。\n\n"
        f"- 本机课题目录：`{project.resolve()}`（studio，{config.hostname()}）\n"
        f"- 代码与最后画图用的汇总数据：`{cs['home_dir']}/`（结构与课题目录一致：`labs/<lab id>/`、`src/`）\n"
        f"- 大的中间数据：`{cs['scratch_dir']}/<lab id>/`（不备份；画图要用的结果拉回本机 lab 文件夹）\n"
        f"- 每个 lab 的 `DATA.md` 与 `cluster/inventory.md`（本机）记录这里有什么。\n"
    )
    cmd = (f"mkdir -p {_q(cs['scratch_dir'])} {_q(cs['home_dir'])}/labs {_q(cs['home_dir'])}/src && "
           f"cat > {_q(cs['home_dir'])}/README.md <<'EOF'\n{readme}EOF\n"
           f"echo ok; ls -ld {_q(cs['scratch_dir'])} {_q(cs['home_dir'])}")
    out = _ssh(cs, cmd)
    return {"cluster": cs["name"], "scratch_dir": cs["scratch_dir"], "home_dir": cs["home_dir"], "output": out.strip()}


def _ensure_remote_dirs(cs: dict, dirs: list[str]) -> None:
    if dirs:
        _ssh(cs, "mkdir -p " + " ".join(_q(d) for d in dirs))


_EXCLUDES = [".git", "__pycache__", ".DS_Store", ".dashboard", "audit", "fig", "*.pyc", "*.png", "*.pdf"]


def push(project: Path, paths: list[str], delete: bool = False) -> list[str]:
    """把课题目录里的若干相对路径（代码、脚本、网格文件）同步到集群 home_dir 下同样的相对位置。"""
    cs = settings(project)
    root = project.resolve()
    done = []
    rels = []
    for p in paths:
        rel = Path(p)
        src = (root / rel).resolve()
        if not src.exists():
            raise FileNotFoundError(f"{p} 不在课题目录里")
        rels.append((src, rel.as_posix().rstrip("/")))
    _ensure_remote_dirs(cs, [f"{cs['home_dir']}/{rel}" if src.is_dir() else f"{cs['home_dir']}/{Path(rel).parent.as_posix()}" for src, rel in rels])
    for src, rel in rels:
        args = ["-az", "-i"] + [f"--exclude={e}" for e in _EXCLUDES] + (["--delete"] if delete else [])
        if src.is_dir():
            args += [f"{src}/", f"{cs['ssh']}:{cs['home_dir']}/{rel}/"]
        else:
            args += [str(src), f"{cs['ssh']}:{cs['home_dir']}/{Path(rel).parent.as_posix()}/"]
        out = _rsync(args)
        n = sum(1 for ln in out.splitlines() if ln[:1] in "<>" or ln.startswith("c"))
        done.append(f"{rel} → {cs['home_dir']}/{rel}（{n} 项更新）")
    return done


def pull(project: Path, lab_id: str, rels: list[str] | None = None, scratch: bool = False, to: str | None = None) -> list[str]:
    """把集群上本 lab 的结果拉回本机。默认拉 home 下 labs/<lab>/results/ 到本机 labs/<lab>/results/；
    --scratch 拉 scratch 下 <lab>/<rel> 到 data_root/<lab>/cluster/<rel>（大文件，留 DATA.md 指路）。"""
    cs = settings(project)
    cfg = config.load(project)
    lp = lab_paths(cs, lab_id)
    rels = rels or (["results"] if not scratch else [""])
    done = []
    for rel in rels:
        rel = rel.strip("/")
        remote = f"{lp['scratch']}/{rel}" if scratch else f"{lp['home']}/{rel}"
        remote = remote.rstrip("/")
        if to:
            local = Path(to).expanduser()
            if not local.is_absolute():
                local = project / local
        elif scratch:
            local = Path(cfg["project"]["data_root"]).expanduser() / lab_id / "cluster" / rel
        else:
            local = project / "labs" / lab_id / rel
        local.mkdir(parents=True, exist_ok=True)
        out = _rsync(["-az", "-i", f"{cs['ssh']}:{remote}/", f"{local}/"])
        files = [ln.split(None, 1)[1] for ln in out.splitlines() if ln[:1] in "<>" and len(ln.split(None, 1)) > 1]
        done.append(f"{cs['name']}:{remote}/ → {local}/（{len(files)} 个文件：{', '.join(files[:8])}{'…' if len(files) > 8 else ''}）")
    return done


# ---------- 作业 ----------
def _jobs_file(project: Path, lab_id: str) -> Path:
    p = project / "labs" / lab_id / "cluster" / "jobs.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_jobs(project: Path, lab_id: str) -> list[dict]:
    p = _jobs_file(project, lab_id)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
    return out


def _write_jobs(project: Path, lab_id: str, recs: list[dict]) -> None:
    _jobs_file(project, lab_id).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")


def _array_size(spec: str | None) -> int:
    if not spec:
        return 1
    spec = spec.split("%")[0]
    n = 0
    for part in spec.split(","):
        step = 1
        if ":" in part:
            part, s = part.split(":", 1)
            step = max(1, int(s))
        if "-" in part:
            a, b = part.split("-", 1)
            n += len(range(int(a), int(b) + 1, step))
        elif part.strip():
            n += 1
    return max(1, n)


def submit(project: Path, lab_id: str, script: str, cpus: int = 1, partition: str | None = None, time_limit: str | None = None,
           name: str | None = None, mem: str | None = None, array: str | None = None, label: str | None = None,
           args: list[str] | None = None, test: bool = False, dry_run: bool = False) -> dict:
    """在集群上 `cd <home>/labs/<lab> && sbatch …`，并记进 labs/<lab>/cluster/jobs.jsonl 与 ~/.rd/jobs.json。
    排队上限、单作业核数上限都在这里把关：超了就拒绝（RuntimeError），不要绕过。"""
    from . import cores
    cs = settings(project)
    lp = lab_paths(cs, lab_id)
    if not (project / "labs" / lab_id).is_dir():
        raise FileNotFoundError(f"labs/{lab_id} 不存在")
    cpus = int(cpus)
    if cpus > int(cs["max_cpus_per_job"]):
        raise RuntimeError(f"单作业 {cpus} 核超过上限 {cs['max_cpus_per_job']}（config.toml [cluster].max_cpus_per_job）；"
                           f"拆成几个小作业——要太多核的作业会因为凑不齐资源一直排队")
    partition = partition or (cs["test_partition"] if test else cs["partition"])
    time_limit = time_limit or (cs.get("test_time", "01:30:00") if partition == cs["test_partition"] else cs["default_time"])
    name = name or f"{lab_id.split('-')[0]}-{Path(script).stem}"[:40]
    n_new = _array_size(array)
    live = my_jobs(cs, max_age=0)
    if live is None:
        raise RuntimeError(f"连不上 {cs['ssh']}，查不到队列，没有提交")
    pending = sum(1 for j in live if j["state"] == "PENDING")
    if pending + n_new > int(cs["max_pending"]):
        raise RuntimeError(f"排队中已有 {pending} 个作业，上限 {cs['max_pending']}，这次要交 {n_new} 个，没有提交；"
                           f"现在最多再交 {max(0, int(cs['max_pending']) - pending)} 个，其余等有作业开始跑再交（写进续跑单的待提交清单）")
    opts = ["--parsable", "-p", partition, "-c", str(cpus), "-t", time_limit, "-J", name,
            "-o", "logs/%x-%j.out", "-e", "logs/%x-%j.err"]
    if mem:
        opts += [f"--mem={mem}"]
    if array:
        opts += [f"--array={array}"]
    cmd = (f"cd {_q(lp['home'])} && mkdir -p logs && test -f {shlex.quote(script)} && "
           f"sbatch {' '.join(shlex.quote(o) for o in opts)} {shlex.quote(script)} {' '.join(shlex.quote(a) for a in (args or []))}")
    rec = {"cluster": cs["name"], "lab": lab_id, "script": script, "args": list(args or []), "name": name, "cpus": cpus,
           "partition": partition, "time": time_limit, "mem": mem, "array": array, "tasks": n_new,
           "label": label or f"{lab_id} {cs['name']}:{name}", "cwd": lp["home"], "scratch": lp["scratch"], "cmd": cmd}
    if dry_run:
        return {**rec, "dry_run": True}
    out = _ssh(cs, cmd).strip().splitlines()
    jid = (out[-1] if out else "").split(";")[0].strip()
    if not re.fullmatch(r"\d+", jid):
        raise RuntimeError(f"sbatch 没有返回作业号：{' '.join(out)[:300]}")
    rec.update({"slurm_id": jid, "submitted": time.strftime("%Y-%m-%d %H:%M"), "state": "PENDING"})
    rec["registry_id"] = cores.claim(project, cpus, rec["label"], host=cs["name"], slurm_id=jid, ssh=cs["ssh"])
    recs = _read_jobs(project, lab_id)
    recs.append(rec)
    _write_jobs(project, lab_id, recs)
    # 新作业进了队列：刷新缓存，免得调度器在 5 分钟内把它当成"不存在"
    cache = my_jobs(cs, max_age=0)
    if cache is not None and not _is_alive(jid, cache):
        _write_cache(cs, cache + [{"id": jid, "name": name, "state": "PENDING", "partition": partition, "cpus": cpus,
                                   "elapsed": "0:00", "timelimit": time_limit, "reason": "None", "submitted": rec["submitted"]}])
    return rec


def _parse_sacct(text: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for ln in text.splitlines():
        p = ln.strip().split("|")
        if len(p) < 5:
            continue
        out[p[0]] = {"state": p[1].split()[0] if p[1] else "", "elapsed": p[2], "end": p[3], "exit": p[4]}
    return out


def _aggregate(jid: str, sacct: dict[str, dict]) -> dict | None:
    """数组作业在 sacct 里是 123_0、123_1…：合成一个状态。"""
    rows = [v for k, v in sacct.items() if k == jid or k.split("_")[0] == jid]
    if not rows:
        return None
    states = [r["state"] for r in rows]
    if any(s in ("RUNNING", "PENDING", "COMPLETING") for s in states):
        st = "RUNNING" if "RUNNING" in states else "PENDING"
    elif all(s == "COMPLETED" for s in states):
        st = "COMPLETED"
    elif len(rows) == 1:
        st = states[0]
    else:
        cnt: dict[str, int] = {}
        for s in states:
            cnt[s] = cnt.get(s, 0) + 1
        st = "MIXED: " + ", ".join(f"{v} {k}" for k, v in sorted(cnt.items()))
    end = max((r["end"] for r in rows), default="")
    elapsed = max((r["elapsed"] for r in rows), default="")
    exit_codes = sorted({r["exit"] for r in rows})
    return {"state": st, "elapsed": elapsed, "end": end, "exit": ",".join(exit_codes)}


def sync(project: Path, lab_id: str | None = None, refresh: bool = True) -> list[dict]:
    """用 squeue + sacct 更新本机记录的作业状态，结束的从 ~/.rd/jobs.json 放掉。返回记录（可按 lab 过滤）。"""
    from . import cores
    cs = settings(project)
    labs = [lab_id] if lab_id else sorted(p.parent.parent.name for p in (project / "labs").glob("*/cluster/jobs.jsonl"))
    live = my_jobs(cs, max_age=0 if refresh else CACHE_SECONDS) if refresh else my_jobs(cs, max_age=10**9)
    all_recs = []
    for lab in labs:
        recs = _read_jobs(project, lab)
        changed = False
        unresolved = [r for r in recs if r.get("slurm_id") and not _final(r.get("state", ""))]
        if live is not None and unresolved:
            gone = [r for r in unresolved if not _is_alive(r["slurm_id"], live)]
            for r in unresolved:
                if _is_alive(r["slurm_id"], live):
                    rows = [j for j in live if j["id"] == r["slurm_id"] or j["id"].split("_")[0] == r["slurm_id"]]
                    st = "RUNNING" if any(j["state"] == "RUNNING" for j in rows) else rows[0]["state"]
                    el = max(j["elapsed"] for j in rows)
                    if r.get("state") != st or r.get("elapsed") != el:
                        r["state"], r["elapsed"] = st, el
                        changed = True
            if gone and refresh:
                ids = ",".join(r["slurm_id"] for r in gone)
                try:
                    sacct = _parse_sacct(_ssh(cs, f"sacct -X -P -n -j {ids} -o JobID,State,Elapsed,End,ExitCode", timeout=45))
                except RuntimeError:
                    sacct = {}
                for r in gone:
                    agg = _aggregate(r["slurm_id"], sacct) or {"state": "GONE", "elapsed": r.get("elapsed", ""), "end": "", "exit": ""}
                    r.update(agg)
                    changed = True
                    if r.get("registry_id"):
                        cores.release(r["registry_id"])
        if changed:
            _write_jobs(project, lab, recs)
        all_recs += recs
    return all_recs


def _final(state: str) -> bool:
    return bool(state) and state not in ("PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "SUSPENDED")


def cancel(project: Path, jid: str) -> dict:
    from . import cores
    cs = settings(project)
    _ssh(cs, f"scancel {shlex.quote(jid)}")
    hit = None
    for lab in sorted(p.parent.parent.name for p in (project / "labs").glob("*/cluster/jobs.jsonl")):
        recs = _read_jobs(project, lab)
        for r in recs:
            if r.get("slurm_id") == jid:
                r["state"] = "CANCELLED"
                r["end"] = time.strftime("%Y-%m-%d %H:%M")
                if r.get("registry_id"):
                    cores.release(r["registry_id"])
                hit = r
        if hit:
            _write_jobs(project, lab, recs)
            break
    try:
        live = my_jobs(cs, max_age=0) or []
        _write_cache(cs, [j for j in live if j["id"].split("_")[0] != jid])
    except RuntimeError:
        pass
    return {"cancelled": jid, "record": hit}


# ---------- 清单 ----------
def inventory(project: Path, lab_id: str) -> Path:
    """把集群上本 lab 两处目录的清单与作业表写进 labs/<lab>/cluster/inventory.md（机器生成，DATA.md 链接它）。"""
    cs = settings(project)
    lp = lab_paths(cs, lab_id)
    script = (
        f"for d in {_q(lp['scratch'])} {_q(lp['home'])}; do "
        "echo \"@@dir $d\"; if [ -d \"$d\" ]; then "
        "echo \"@@total $(du -sh \"$d\" 2>/dev/null | cut -f1) $(find \"$d\" -type f 2>/dev/null | wc -l)\"; "
        "find \"$d\" -mindepth 1 -maxdepth 2 -type d 2>/dev/null | sort | head -400 | while read -r s; do "
        "printf '%s|%s|%s|%s\\n' \"${s#$d/}\" \"$(du -sh \"$s\" 2>/dev/null | cut -f1)\" \"$(find \"$s\" -type f 2>/dev/null | wc -l)\" \"$(date -r \"$s\" '+%Y-%m-%d %H:%M' 2>/dev/null)\"; done; "
        "echo @@files; find \"$d\" -maxdepth 1 -type f 2>/dev/null | sort | head -100 | while read -r f; do "
        "printf '%s|%s|%s\\n' \"${f#$d/}\" \"$(du -h \"$f\" 2>/dev/null | cut -f1)\" \"$(date -r \"$f\" '+%Y-%m-%d %H:%M' 2>/dev/null)\"; done; "
        "else echo @@missing; fi; done"
    )
    out = _ssh(cs, script, timeout=300)
    recs = sync(project, lab_id, refresh=True)
    lines = [
        "---", f"updated: {time.strftime('%Y-%m-%d %H:%M')}", f"cluster: {cs['name']}", f"lab: {lab_id}", "---", "",
        f"# 集群 {cs['name']} 上 lab {lab_id} 的数据清单", "",
        "由 `rd cluster inventory` 自动生成；每次提交、拉回、清理后重跑。这里只列目录与作业，**每个目录里是什么、怎么重新生成，写在 DATA.md**。", "",
        f"- 登录：`ssh {cs['ssh']}`",
        f"- 中间数据（不备份）：`{lp['scratch']}/`",
        f"- 代码、日志与汇总结果：`{lp['home']}/`（`logs/` 是 Slurm 输出，`results/` 用 `rd cluster pull` 拉回本机）", "",
    ]
    cur = None
    for ln in out.splitlines():
        if ln.startswith("@@dir "):
            cur = ln[6:].strip()
            lines += [f"## `{cur}/`", ""]
        elif ln.startswith("@@missing"):
            lines += ["（目录不存在）", ""]
        elif ln.startswith("@@total "):
            p = ln[8:].split()
            lines += [f"合计 {p[0] if p else '?'}，{p[1] if len(p) > 1 else '?'} 个文件。", "", "| 子目录 | 大小 | 文件数 | 最后修改 |", "|---|---|---|---|"]
        elif ln.startswith("@@files"):
            lines += ["", "| 顶层文件 | 大小 | 最后修改 |", "|---|---|---|"]
        elif "|" in ln and cur:
            p = ln.split("|")
            lines.append("| " + " | ".join(f"`{p[0]}`" if i == 0 else x for i, x in enumerate(p)) + " |")
    lines += ["", "## 作业记录（labs/%s/cluster/jobs.jsonl）" % lab_id, "", "| 作业号 | 名称 | 核 | 分区 | 时限 | 提交 | 状态 | 用时 | 脚本 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in recs:
        lines.append(f"| {r.get('slurm_id', '')} | {r.get('name', '')} | {r.get('cpus', '')}{'×' + str(r['tasks']) if r.get('tasks', 1) > 1 else ''} | {r.get('partition', '')} | {r.get('time', '')} | {r.get('submitted', '')} | {r.get('state', '')} | {r.get('elapsed', '')} | `{r.get('script', '')} {' '.join(r.get('args') or [])}`".rstrip() + " |")
    if not recs:
        lines.append("| （还没有提交过作业） | | | | | | | | |")
    p = project / "labs" / lab_id / "cluster" / "inventory.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ---------- 命令行 ----------
def add_parser(sub) -> None:
    p = sub.add_parser("cluster", help="校园集群（Slurm）：状态、目录、推送、提交、作业、拉回、清单")
    s = p.add_subparsers(dest="action", required=True)
    a = s.add_parser("status", help="分区空闲、我的作业、还能交几个"); a.add_argument("path"); a.add_argument("--json", action="store_true")
    a = s.add_parser("init", help="在集群上建课题目录（scratch 与 home）"); a.add_argument("path")
    a = s.add_parser("push", help="把课题里的相对路径同步到集群 home 目录"); a.add_argument("path"); a.add_argument("paths", nargs="+"); a.add_argument("--delete", action="store_true")
    a = s.add_parser("submit", help="sbatch 提交一个 lab 的脚本（相对 labs/<lab>/）"); a.add_argument("path"); a.add_argument("lab"); a.add_argument("script")
    a.add_argument("--cpus", "-c", type=int, default=1); a.add_argument("--partition", "-p"); a.add_argument("--time", "-t"); a.add_argument("--name", "-J")
    a.add_argument("--mem"); a.add_argument("--array"); a.add_argument("--label"); a.add_argument("--test", action="store_true", help="交到测试分区（short）")
    a.add_argument("--dry-run", action="store_true"); a.add_argument("args", nargs="*", help="传给脚本的参数（放在 -- 之后）")
    a = s.add_parser("jobs", help="本课题登记过的集群作业与状态"); a.add_argument("path"); a.add_argument("--lab"); a.add_argument("--no-refresh", action="store_true"); a.add_argument("--json", action="store_true")
    a = s.add_parser("pull", help="把 lab 的结果拉回本机"); a.add_argument("path"); a.add_argument("lab"); a.add_argument("rels", nargs="*"); a.add_argument("--scratch", action="store_true"); a.add_argument("--to")
    a = s.add_parser("inventory", help="写 labs/<lab>/cluster/inventory.md"); a.add_argument("path"); a.add_argument("lab")
    a = s.add_parser("cancel", help="scancel"); a.add_argument("path"); a.add_argument("jobid")
    a = s.add_parser("ssh", help="在集群上执行一条命令"); a.add_argument("path"); a.add_argument("cmd", nargs=argparse_REMAINDER())
    p.set_defaults(fn=cli)


def argparse_REMAINDER():
    import argparse
    return argparse.REMAINDER


def cli(args) -> None:
    root = Path(args.path).expanduser().resolve()
    if args.action == "status":
        st = status(root)
        if args.json:
            print(json.dumps(st, ensure_ascii=False, indent=1))
            return
        print(st["advice"])
        for j in st["jobs"]:
            print(f"  - {j['id']:>9}  {j['state']:<9} {j['partition']:<8} {j['cpus']:>3} 核  {j['elapsed']:>10} / {j['timelimit']:<11} {j['name']}  {j['reason'] if j['state'] == 'PENDING' else ''}")
        for d in st["disk"]:
            print(f"  磁盘 {d['mount']}: 可用 {d['avail']} / {d['size']}（已用 {d['use']}）")
        print(f"  目录：中间数据 {st['scratch_dir']}/<lab id>/ · 代码与汇总 {st['home_dir']}/")
    elif args.action == "init":
        print(json.dumps(init(root), ensure_ascii=False, indent=1))
    elif args.action == "push":
        for line in push(root, args.paths, delete=args.delete):
            print(line)
    elif args.action == "submit":
        rec = submit(root, args.lab, args.script, cpus=args.cpus, partition=args.partition, time_limit=args.time, name=args.name,
                     mem=args.mem, array=args.array, label=args.label, args=args.args, test=args.test, dry_run=args.dry_run)
        print(json.dumps({k: rec.get(k) for k in ("slurm_id", "name", "cpus", "partition", "time", "array", "label", "cwd", "scratch", "registry_id", "dry_run", "cmd")}, ensure_ascii=False, indent=1))
    elif args.action == "jobs":
        recs = sync(root, args.lab, refresh=not args.no_refresh)
        if args.json:
            print(json.dumps(recs, ensure_ascii=False, indent=1))
            return
        if not recs:
            print("没有提交过集群作业")
        for r in recs:
            print(f"  {r.get('slurm_id', '?'):>9}  {r.get('state', ''):<10} {r.get('partition', ''):<8} {r.get('cpus', '')}核{'×' + str(r['tasks']) if r.get('tasks', 1) > 1 else ''}  {r.get('elapsed', ''):>10}  [{r.get('lab')}] {r.get('name')}  {r.get('submitted', '')}")
    elif args.action == "pull":
        for line in pull(root, args.lab, args.rels or None, scratch=args.scratch, to=args.to):
            print(line)
    elif args.action == "inventory":
        print(inventory(root, args.lab))
    elif args.action == "cancel":
        print(json.dumps(cancel(root, args.jobid), ensure_ascii=False))
    elif args.action == "ssh":
        cmd = " ".join(args.cmd)
        if cmd.startswith("-- "):
            cmd = cmd[3:]
        print(_ssh(settings(root), cmd, timeout=600), end="")

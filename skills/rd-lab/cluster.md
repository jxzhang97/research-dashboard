# 把数值分摊到集群（rd-lab 附录）

适用：`config.toml` 的 `[cluster]`（默认 UCSB CSC 的 **Pod**，Slurm）。规则在 AGENTS.md §5；这里是操作顺序、模板和 Pod 的实际情况。命令都是 `~/doc_unsyn/research-dashboard/rd cluster …`。

## 0. 什么时候交到集群

- 一个批量在 studio 要跑**半天以上**，或 `rd free-cores` 给不出核、内存已吃紧；而批量能拆成**彼此独立、单核单链**的作业（QMC 的链、参数扫描的点、DMRG 的独立参数）。
- 先 `rd cluster status <根>`：看生产分区空闲核、我的在跑/排队数、还能交几个。batch 分区常年满、公平份额低，**小作业（2–10 核）靠回填几小时内能上，整节点作业要等很久**。
- 两边分工写进续跑单：哪些点在 studio、哪些在集群、各自的完成标记。小检查、后处理、画图留在 studio。
- 已在 studio 跑到一半的批量不挪；下一期、或还没开始的那一套才挪。

## 1. Pod 实际情况（2026-10 查到的，变了以 `rd cluster status` 为准）

| 项 | 值 |
|---|---|
| 登录 | `ssh pod-login1.cnsi.ucsb.edu`（`~/.ssh/config` 别名，两台机器都配了免密；用户 `jiaxin_zhang`） |
| 分区 | `batch` 62 节点 × 40 核（Xeon Gold 6148 2.4 GHz，192 GB），默认时限 3 天、上限 58 天；`short` 1 节点 40 核、**2 小时**上限，只用于测试；`largemem` 4 节点 710 GB；`gpu` |
| 每用户限制（QOS normal） | 同时在跑 32 个作业、提交 600 个、合计 320 核；单作业 ≤ 320 核。**我们自己的规矩更严：排队 ≤ 8 个、单作业 ≤ 20 核（`max_cpus_per_job`）** |
| 存储 | `/bigscratch`（70 TB NVMe，**不备份**，写中间数据）；`/home`（BeeGFS，整机 98% 满，只放代码、日志、汇总）；节点本地 `/scratch_local`（作业结束后会清） |
| 软件 | gfortran/gcc 14.2（默认 PATH）、`module load intel/20`（ifort 19.1）、MKL 2020（`$MKLROOT`，`.bashrc` 已 `module load mkl`）、`module load hdf5/1.14.6`、openmpi5；python 3.12（`~/anaconda3`：numpy、scipy、h5py）；julia 1.10.5（`~/software`，ITensors 已装） |
| 单核速度 | 比 studio（M 系列）慢，按 **1.5–2 倍**估时限 |

## 2. 操作顺序

1. **目录**（每个课题一次）：`rd cluster init <根>` → `/bigscratch/jiaxin/<dir>/` 与 `~/<dir>/`（`labs/`、`src/`、README）。
2. **代码**：`rd cluster push <根> src labs/NN-slug/cluster labs/NN-slug/scripts labs/NN-slug/results/grid.json …`（相对课题根；不推 `fig/`、`audit/`、`.git`）。需要编译的（ALF、C++）在集群上编一次，二进制放 `~/<dir>/<lab id>/bin/` 或 scratch，构建脚本进 `src/`。
3. **测试**：`rd cluster submit <根> NN-slug cluster/xxx.sbatch --test -c 2 -- <小尺寸参数>` → `rd cluster jobs <根> --lab NN-slug` 看状态 → 看 `~/<dir>/labs/NN-slug/logs/<name>-<jid>.out|.err` → 确认输出能被本机后处理读。
4. **生产**：`rd cluster submit <根> NN-slug cluster/xxx.sbatch -c N -t D-HH:MM:SS -J <名> -- <参数>`，一次交几个（排队 ≤ 8，在跑的不算）；没交完的列进续跑单「待提交」。
5. **续跑单**：`waiting_on: pod 作业 123,124（完成标记 …）`；写清拉回命令。然后**结束运行**。
6. **作业结束**（调度器叫醒）：`rd cluster jobs` 看 COMPLETED/FAILED → FAILED 看 `.err`，修了重交 → `rd cluster pull <根> NN-slug`（`~/<dir>/labs/NN-slug/results/` → 本机 `labs/NN-slug/results/`）→ 需要原始数据在本机的 `rd cluster pull … --scratch runs/xxx`（进 `data_root/NN-slug/cluster/`）→ `rd cluster inventory <根> NN-slug` → DATA.md「集群」一节 → 交待提交清单里的下一批。
7. 收尾时 DATA.md 的集群一节要和 inventory 一致；scratch 上不再需要的大目录可以在 DATA.md 标"已清理（日期）"。

## 3. 作业脚本模板（`labs/NN-slug/cluster/run_points.sbatch`）

一个作业里 N 条链并行（`-c N`），每条链单线程；中间数据写 scratch，汇总写 `results/`，完成留标记。参数从命令行传，便于同一脚本交多次。

```bash
#!/bin/bash -l
#SBATCH --nodes=1 --ntasks=1
# -c/-t/-J/-p/-o 由 rd cluster submit 给；这里只写固定的
set -u
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
DIR="$HOME/<dir>"                      # ~/<dir>，rd cluster init 建的
SCR="/bigscratch/jiaxin/<dir>/NN-slug"   # 中间数据
LAB="$DIR/labs/NN-slug"; mkdir -p "$SCR" "$LAB/results"
cd "$LAB"
echo "job $SLURM_JOB_ID on $(hostname) cpus=$SLURM_CPUS_PER_TASK args=$*"; date
# 例：每个参数一条链，最多 $SLURM_CPUS_PER_TASK 条同时跑
for p in "$@"; do
  while [ "$(jobs -rp | wc -l)" -ge "$SLURM_CPUS_PER_TASK" ]; do sleep 20; done
  python3 "$DIR/src/<pkg>/run_point.py" "$SCR/$p" ... --launch > "$SCR/$p.log" 2>&1 &
done
wait
python3 "$DIR/src/<pkg>/post.py" "$SCR" --out "$LAB/results/<name>.json"   # 汇总（小文件）
date; echo DONE > "$LAB/results/<name>.DONE"
```

要点：`#!/bin/bash -l` 才能用 `module load`；不要 `cd $SLURM_SUBMIT_DIR` 以外的相对路径；日志由 `submit` 放在 `logs/%x-%j.out`；长作业每条链自己能断点续跑（run 目录里有 `DONE` 就跳过），这样 TIMEOUT 后重交不重算。

## 4. DATA.md「集群」一节模板

```markdown
## 集群（pod）
- 登录 `ssh pod-login1.cnsi.ucsb.edu`；清单 [cluster/inventory.md](cluster/inventory.md)（`rd cluster inventory` 生成，<日期>）；作业记录 `cluster/jobs.jsonl`。
- 中间数据：`/bigscratch/jiaxin/<dir>/NN-slug/`（不备份）
  - `runs/phase3/<点>_s<seed>/`：ALF 原始 bin、`info`、`run.log`、`DONE`（作业 123456–123460，2026-10-13 提交）。
- 代码与汇总：`~/<dir>/labs/NN-slug/`（`cluster/*.sbatch`、`logs/`、`results/phase3_L9.json`）；`~/<dir>/src/<pkg>/`（与本机 `src/` 同步于 <日期>）；二进制 `~/<dir>/labs/NN-slug/bin/SMG.out`（在集群上用 `src/<pkg>/build_pod.sh` 编译）。
- 已拉回本机：`results/phase3_L9.json`（<日期>，`rd cluster pull`）；原始 bin 未拉回（要用时 `rd cluster pull . NN-slug runs/phase3 --scratch`）。
- 重新生成：`rd cluster push . src labs/NN-slug/cluster` → `rd cluster submit . NN-slug cluster/run_points.sbatch -c 2 -t 4-00:00:00 -- <点>`。
```

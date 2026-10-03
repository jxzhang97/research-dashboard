import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def rd_home(tmp_path: Path, monkeypatch):
    """机器级注册表指到临时目录，测试不碰真正的 ~/.rd。"""
    monkeypatch.setenv("RD_HOME", str(tmp_path / "rd_home"))
    return tmp_path / "rd_home"


@pytest.fixture
def project_dir(tmp_path: Path, rd_home: Path) -> Path:
    d = tmp_path / "demo"
    subprocess.check_call([sys.executable, "-m", "rd_core.cli", "init", str(d), "--name", "demo"], cwd=ROOT)
    # 一张卡片、两页 wiki、一个 lab、一个讨论、两个想法
    (d / "references" / "cards" / "2104.14257.md").write_text(
        "---\ntitle: Flat band BEC\nauthors: [Törmä]\nyear: 2021\narxiv: '2104.14257'\nread_depth: full\n---\n"
        "# Flat band BEC\n\n## 内容总结\n\n讲 [[quantum-metric]]。\n\n## 与本课题的联系\n\n直接相关。\n", encoding="utf-8")
    (d / "wiki" / "quantum-metric.md").write_text(
        "---\ntitle: 量子度规\n---\n# 量子度规\n\n$g_{\\mu\\nu}$ 与 [[notation]] 一致，见 [[2104.14257]]。\n", encoding="utf-8")
    lab = d / "labs" / "01-first-task"
    lab.mkdir(parents=True)
    (lab / "brief.md").write_text("---\ntitle: 第一个任务\nstatus: awaiting_review\nidea: metric-bound\n---\n# 第一个任务\n\n## 目标\n\n算一下。\n", encoding="utf-8")
    (d / "discussion" / "2026-10-02-which-limit.md").write_text(
        "---\ntitle: 取哪个极限\nstatus: open\nasked_by: agent\nlab: 01-first-task\n---\n# 取哪个极限\n\n## 问题\n\nA 还是 B？\n", encoding="utf-8")
    (d / "ideas" / "root-idea.md").write_text("---\ntitle: 总想法\nstatus: seed\n---\n# 总想法\n\n## 原话\n\n……\n", encoding="utf-8")
    (d / "ideas" / "metric-bound.md").write_text("---\ntitle: 度规 bound\nparent: root-idea\nstatus: lab\nlabs: [01-first-task]\n---\n# 度规 bound\n", encoding="utf-8")
    return d

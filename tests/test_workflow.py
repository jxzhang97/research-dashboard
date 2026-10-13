"""收尾门槛 rd finish：只认覆盖当前文件版本、由作业记录背书的通过报告；薄层必须来自 --expect 的写作作业；源文件改了报告就过期。"""

import json
from pathlib import Path

import pytest

from rd_core import fm, workflow
from rd_core.codex import _hash, rec_dir
from rd_core.project import Project

LAB = "01-first-task"
BASE = f"labs/{LAB}/"


def record(root: Path, kind: str, name: str, expected: list[str], sources: list[str], state: str = "done") -> None:
    """伪造一条结束的 codex 作业记录（和 worker 写出来的一样）。"""
    rec = rec_dir(root, kind, name)
    rec.mkdir(parents=True, exist_ok=True)
    (rec / "job.json").write_text(json.dumps({"kind": kind, "name": name, "lab": LAB, "expected": expected,
                                              "source_hashes": _hash(root, sources), "started_ts": 1.0}), encoding="utf-8")
    (rec / "run_info.txt").write_text("codex-cli 0.160.0 | start x\nexit 0 | end y\n", encoding="utf-8")
    oc = {"state": state, "code": 0 if state == "done" else 1, "output_hashes": _hash(root, expected)}
    if kind in ("audit", "consistency"):
        oc["review_verdicts"] = {}
        for p in expected:
            meta, _ = fm.read(root / p)
            oc["review_verdicts"][p] = {k: meta.get(k) for k in ("kind", "verdict", "counts", "handled")}
    (rec / "outcome.json").write_text(json.dumps(oc), encoding="utf-8")


def report(root: Path, rel: str, kind: str, verdict: str = "pass", counts: dict | None = None, handled: bool = False) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm.write(p, {"kind": kind, "verdict": verdict, "counts": counts or {"typo": 0, "不严谨": 0, "改变结论": 0}, "handled": handled}, "# 审\n")


def test_finish_requires_write_job_and_current_reviews(project_dir: Path):
    for n in ("notes.md", "handoff.md", "report.md"):
        (project_dir / BASE / n).write_text(f"---\ntitle: {n}\n---\n{n}\n", encoding="utf-8")
    fm.update(project_dir / BASE / "brief.md", status="running")
    errs = workflow.completion_errors(project_dir, LAB)
    assert any("薄层写作" in e for e in errs) and any("推导审核" in e for e in errs) and any("一致性" in e for e in errs)
    # 写作作业产出 report.md 和一页 wiki
    (project_dir / "wiki" / "new-page.md").write_text("---\ntitle: 新页\n---\n# 新页\n", encoding="utf-8")
    record(project_dir, "write", "w1", [BASE + "report.md", "wiki/new-page.md"], [BASE + "handoff.md"])
    # 推导审核：major 不算
    report(project_dir, BASE + "audit/d1.md", "derivation", "major", {"typo": 0, "不严谨": 0, "改变结论": 2})
    record(project_dir, "audit", "a1", [BASE + "audit/d1.md"], [BASE + "notes.md"])
    errs = workflow.completion_errors(project_dir, LAB)
    assert any("推导审核" in e and "verdict 是 major" in e for e in errs)
    # 复核 pass，但有 typo 没标 handled → 不算；标了 handled 就算
    report(project_dir, BASE + "audit/d2.md", "derivation", "pass", {"typo": 1, "不严谨": 0, "改变结论": 0})
    record(project_dir, "audit", "a2", [BASE + "audit/d2.md"], [BASE + "notes.md"])
    assert any("typo" in e for e in workflow.completion_errors(project_dir, LAB))
    fm.update(project_dir / BASE / "audit/d2.md", handled=True)
    errs = workflow.completion_errors(project_dir, LAB)
    assert not any("推导审核" in e for e in errs) and any("一致性" in e for e in errs)
    # 一致性检查没覆盖 wiki 页 → 不算
    report(project_dir, BASE + "audit/c1.md", "consistency")
    record(project_dir, "consistency", "c1", [BASE + "audit/c1.md"], [BASE + n for n in ("notes.md", "handoff.md", "report.md")])
    assert any("一致性" in e and "wiki/new-page.md" in e for e in workflow.completion_errors(project_dir, LAB))
    report(project_dir, BASE + "audit/c2.md", "consistency")
    record(project_dir, "consistency", "c2", [BASE + "audit/c2.md"], [BASE + n for n in ("notes.md", "handoff.md", "report.md")] + ["wiki/new-page.md"])
    assert workflow.completion_errors(project_dir, LAB) == []
    res = workflow.finish(project_dir, LAB)
    assert res["status"] == "done" and fm.read(project_dir / BASE / "brief.md")[0]["status"] == "done"
    assert any("收尾门槛" in e["what"] for e in Project(project_dir).log_entries(3))
    # 之后改 notes → 两份报告都过期
    (project_dir / BASE / "notes.md").write_text("改了结论\n", encoding="utf-8")
    errs = workflow.completion_errors(project_dir, LAB)
    assert sum("过期" in e for e in errs) == 2


def test_report_frontmatter_tampering_is_detected(project_dir: Path):
    for n in ("notes.md", "handoff.md", "report.md"):
        (project_dir / BASE / n).write_text(n, encoding="utf-8")
    record(project_dir, "write", "w1", [BASE + "report.md"], [])
    report(project_dir, BASE + "audit/d1.md", "derivation", "major", {"typo": 0, "不严谨": 0, "改变结论": 1})
    record(project_dir, "audit", "a1", [BASE + "audit/d1.md"], [BASE + "notes.md"])
    # 作业结束后把报告手改成 pass → 与 outcome 记录不符，不算
    fm.update(project_dir / BASE / "audit/d1.md", verdict="pass", counts={"typo": 0, "不严谨": 0, "改变结论": 0})
    assert any("被改过" in e for e in workflow.completion_errors(project_dir, LAB))
    # 代码审计不能代替推导审核
    report(project_dir, BASE + "audit/code.md", "code")
    record(project_dir, "audit", "a2", [BASE + "audit/code.md"], [BASE + "notes.md"])
    assert any("代码审计不能代替" in e for e in workflow.completion_errors(project_dir, LAB))


def test_finish_cli_and_lab_page_checklist(project_dir: Path):
    from rd_core.cli import main
    for n in ("notes.md", "handoff.md", "report.md"):
        (project_dir / BASE / n).write_text(n, encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        main(["finish", str(project_dir), LAB, "--check"])
    assert e.value.code == 1
    with pytest.raises(SystemExit) as e:
        main(["finish", str(project_dir), LAB])
    assert e.value.code == 1
    assert fm.read(project_dir / BASE / "brief.md")[0]["status"] != "done"
    d = Project(project_dir).lab(LAB)
    assert d.extra["completion_pending"] and any("薄层写作" in x for x in d.extra["completion_pending"])


def test_auto_flags_and_nested_audit_reports(project_dir: Path):
    """关掉 auto_consistency 就不要求一致性报告；audit/ 子目录里的报告也能被列出并带 stale 标记。"""
    cfg = project_dir / "config.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("auto_consistency = true", "auto_consistency = false"), encoding="utf-8")
    for n in ("notes.md", "handoff.md", "report.md"):
        (project_dir / BASE / n).write_text(n, encoding="utf-8")
    record(project_dir, "write", "w1", [BASE + "report.md"], [])
    report(project_dir, BASE + "audit/derivation-v2/report.md", "derivation")
    record(project_dir, "audit", "a1", [BASE + "audit/derivation-v2/report.md"], [BASE + "notes.md"])
    assert workflow.completion_errors(project_dir, LAB) == []
    d = Project(project_dir).lab(LAB)
    assert d.extra["audit"]["derivation"]["stale"] is False and d.extra["audits"][0]["name"] == "derivation-v2/report.md"
    (project_dir / BASE / "notes.md").write_text("changed", encoding="utf-8")
    d = Project(project_dir).lab(LAB)
    assert d.extra["audit"]["derivation"]["stale"] is True


def test_pending_review_shows_in_attention(project_dir: Path):
    fm.update(project_dir / BASE / "brief.md", status="running", pending_review="2026-10-08-lab01-audit-fixes")
    att = Project(project_dir).attention()
    assert any(i["kind"] == "lab" and "审计修正" in i["why"] for i in att["items"])


def test_shared_pages_do_not_expire_reports_after_done(project_dir: Path):
    """STATUS.md 被下一个 lab 改写后，已 done 的 lab 的一致性报告不算过期；done 之前仍算。"""
    for n in ("notes.md", "handoff.md", "report.md"):
        (project_dir / BASE / n).write_text(n, encoding="utf-8")
    record(project_dir, "write", "w1", [BASE + "report.md"], [])
    report(project_dir, BASE + "audit/d.md", "derivation")
    record(project_dir, "audit", "a1", [BASE + "audit/d.md"], [BASE + "notes.md"])
    report(project_dir, BASE + "audit/c.md", "consistency")
    record(project_dir, "consistency", "c1", [BASE + "audit/c.md"], [BASE + n for n in ("notes.md", "handoff.md", "report.md")] + ["STATUS.md"])
    assert workflow.finish(project_dir, LAB)["status"] == "done"
    (project_dir / "STATUS.md").write_text("下一个 lab 改写了状态页\n", encoding="utf-8")
    assert workflow.completion_errors(project_dir, LAB) == []
    assert Project(project_dir).lab(LAB).extra["audit"]["consistency"]["stale"] is False
    # 还没 done 的 lab：STATUS 改了就得重做一致性检查
    fm.update(project_dir / BASE / "brief.md", status="running")
    assert any("STATUS.md" in e for e in workflow.completion_errors(project_dir, LAB))
    assert Project(project_dir).lab(LAB).extra["audit"]["consistency"]["stale"] is True


def test_recheck_reports_order_after_first_version(project_dir: Path):
    """同一天的 -v2 复核报告排在首版之后，lab 的审计标记取复核版。"""
    base = project_dir / BASE / "audit"
    report(project_dir, BASE + "audit/2026-10-12-gpt-6-astra-consistency.md", "consistency", "minor", {"typo": 0, "不严谨": 1, "改变结论": 0}, handled=True)
    report(project_dir, BASE + "audit/2026-10-12-gpt-6-astra-consistency-v2.md", "consistency")
    for n in ("2026-10-12-gpt-6-astra-consistency.md", "2026-10-12-gpt-6-astra-consistency-v2.md"):
        fm.update(base / n, date="2026-10-12")
    d = Project(project_dir).lab(LAB)
    assert [a["name"] for a in d.extra["audits"]] == ["2026-10-12-gpt-6-astra-consistency.md", "2026-10-12-gpt-6-astra-consistency-v2.md"]
    assert d.extra["audit"]["consistency"]["verdict"] == "pass"

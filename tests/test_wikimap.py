import math
from pathlib import Path

from fastapi.testclient import TestClient

from rd_core import codex, wikimap
from rd_core.project import Project
from rd_core.server import create_app
from rd_core.workflow import doctor_problems


def page(d: Path, slug: str, title: str, extra: str = "", body: str = "") -> None:
    (d / "wiki" / f"{slug}.md").write_text(
        f"---\ntitle: {title}\n{extra}---\n# {title}\n\n**当前回答。** {title}的回答，含 $a.b$。第二句。\n\n{body}\n", encoding="utf-8")


def demo(d: Path) -> Project:
    (d / "wiki" / "index.md").write_text(
        "---\ntitle: 索引\n---\n# 索引\n\n## 记号\n\n- [[notation]]\n\n## 入门：基础（lab 01）\n\n- [[a]]\n- [[b]]\n- [[s]]\n\n"
        "## 进阶\n\n- [[c]]\n- [[h]]\n", encoding="utf-8")
    page(d, "a", "甲", "short: 甲星\n")
    page(d, "b", "乙：长标题", "prereqs: [a]\n")
    page(d, "s", "丙", "prereqs: [b]\npart_of: b\n")
    page(d, "c", "丁", "prereqs: [b, a, s]\n", body="见 [[a]] 与 [[h]]")
    page(d, "h", "总表", "prereqs: [c]\nhub: true\n")
    return Project(d)


def test_regions_fields_and_halo(project_dir: Path):
    m = wikimap.wiki_map(demo(project_dir))
    assert [r["name"] for r in m["regions"]] == ["入门", "进阶", wikimap.UNINDEXED]  # 记号小节只有 notation，不上图
    N = {n["id"]: n for n in m["nodes"]}
    assert "notation" not in N and "index" not in N and "quantum-metric" in N
    assert N["a"]["short"] == "甲星" and N["b"]["short"] == "乙"  # 没写 short 取标题冒号前
    assert N["a"]["start"] and not N["b"]["start"]
    assert N["s"]["parent"] == "b" and N["h"]["hub"]
    assert N["a"]["desc"] == 4 and N["h"]["desc"] == 0  # b、s、c、h 都以 a 为前置
    assert N["a"]["halo"] == wikimap.RM and N["h"]["halo"] == wikimap.R0
    assert N["c"]["next"] == ["h"] and N["a"]["next"] == ["b", "c"]
    assert N["a"]["answer"].startswith("甲的回答")
    implied = {(e["from"], e["to"]) for e in m["edges"] if e["implied"]}
    assert implied == {("a", "c"), ("b", "c")}  # 都能经 s 推出，平时不画
    assert ["a", "c"] not in m["see"] and ["c", "h"] not in m["see"]  # 已是先读关系的链接不再算"相关"
    assert m["has_prereqs"] and m["problems"] == []


def test_layout_is_deterministic_and_reads_left_to_right(project_dir: Path):
    pr = demo(project_dir)
    m1, m2 = wikimap.wiki_map(pr), wikimap.wiki_map(pr)
    assert m1 == m2
    N = {n["id"]: n for n in m1["nodes"]}
    assert N["a"]["x"] < N["b"]["x"] < N["c"]["x"] < N["quantum-metric"]["x"]
    assert math.isclose(math.hypot(N["s"]["x"] - N["b"]["x"], N["s"]["y"] - N["b"]["y"]), wikimap.ORBIT, abs_tol=0.2)
    main = [n for n in m1["nodes"] if not n["parent"]]
    for i, p in enumerate(main):
        for q in main[i + 1:]:
            assert math.hypot(p["x"] - q["x"], p["y"] - q["y"]) >= 60
        assert 0 < p["x"] < m1["width"] and 0 < p["y"] < m1["height"]


def test_doctor_reports_broken_and_cyclic_prereqs(project_dir: Path):
    pr = demo(project_dir)
    page(project_dir, "p1", "环一", "prereqs: [p2]\n")
    page(project_dir, "p2", "环二", "prereqs: [p1, missing-page]\npart_of: nowhere\n")
    probs = doctor_problems(pr)
    assert any("成环" in x for x in probs)
    assert any("missing-page" in x for x in probs)
    assert any("nowhere" in x for x in probs)
    m = wikimap.wiki_map(pr)  # 有环也照样能画
    assert {"p1", "p2"} <= {n["id"] for n in m["nodes"]}


def test_without_index_or_prereqs_still_draws(project_dir: Path):
    (project_dir / "wiki" / "index.md").unlink()
    m = wikimap.wiki_map(Project(project_dir))
    assert [n["id"] for n in m["nodes"]] == ["quantum-metric"]
    assert m["regions"] == [] and not m["has_prereqs"]


def test_label_wrap():
    assert wikimap.wrap_label("短名") == ["短名"]
    lines = wikimap.wrap_label("Slagle 线的 parton 拟设、PSG 与 magic 的因子化与更多更多内容")
    assert len(lines) == 2 and lines[1].endswith("…")
    assert all(wikimap.text_width(t) <= 118 for t in lines)


def test_api_wikimap(project_dir: Path):
    demo(project_dir)
    r = TestClient(create_app(Project(project_dir))).get("/api/wikimap")
    assert r.status_code == 200 and {n["id"] for n in r.json()["nodes"]} >= {"a", "b", "c"}


def test_audit_hash_ignores_star_map_fields(project_dir: Path):
    pr = demo(project_dir)
    rel = "wiki/a.md"
    before = codex._hash(pr.root, [rel])
    f = pr.root / rel
    f.write_text(f.read_text(encoding="utf-8").replace("short: 甲星\n", "short: 甲\nprereqs: [b]\npart_of:\n  - c\nhub: true\n"), encoding="utf-8")
    assert codex._hash(pr.root, [rel]) == before  # 只改导航字段：审核不过期
    f.write_text(f.read_text(encoding="utf-8").replace("第二句", "改过的第二句"), encoding="utf-8")
    assert codex._hash(pr.root, [rel]) != before  # 改正文：照常过期
    brief = "labs/01-first-task/brief.md"
    b0 = codex._hash(pr.root, [brief])
    (pr.root / brief).write_text((pr.root / brief).read_text(encoding="utf-8").replace("title:", "short: 短\ntitle:"), encoding="utf-8")
    assert codex._hash(pr.root, [brief]) != b0  # 只对 wiki 页放宽

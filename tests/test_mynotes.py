import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rd_core import cli, fm, mynotes
from rd_core.project import Project
from rd_core.server import create_app
from test_pnotes import vault_note

SECTION = r"""\section{Model}\label{sec:model}
We consider \orange{the free part {with braces} and \textbf{bold}} first.
\begin{equation}\label{eq:h}
H_0=\sum_k \epsilon_k c_k^\dagger c_k .
\end{equation}
\begin{orangeblock}
Inserting the mode expansion gives
\begin{equation}
\eta^\dagger=\sum_k F(k)\,b^\dagger_k b^\dagger_{-k}.
\end{equation}
\end{orangeblock}
Escaped \{ braces \} stay. % a comment with \orange{kept} and \cmt{not a question}
\subsection{Detail}\label{sec:detail}
Text.
"""


def test_strip_marks_handles_nesting_comments_and_blocks():
    out, n = mynotes.strip_marks(SECTION)
    assert n == 2
    assert r"We consider the free part {with braces} and \textbf{bold} first." in out
    assert "orangeblock" not in out and "Inserting the mode expansion gives\n\\begin{equation}" in out
    assert r"% a comment with \orange{kept}" in out  # 注释里的不动
    assert r"\orangeX{" not in out
    nested, k = mynotes.strip_marks(r"a \orange{b \orange{c} d} e")
    assert nested == "a b c d e" and k == 2
    with pytest.raises(ValueError):
        mynotes.strip_marks(r"\orange{unclosed")


def test_init_skeleton_and_shared_style(project_dir: Path, tmp_path: Path):
    note = vault_note(tmp_path, project_dir)
    pr = Project(project_dir)
    assert not mynotes.exists(pr) and mynotes.status(pr) == {"exists": False, "dir": "mynotes"}
    d = mynotes.init(pr, title="Kondo notes", author="A. B.")
    for f in ("main.tex", "preamble.tex", "notation.tex", "refs.bib", "README.md", "STYLE.md", ".gitignore"):
        assert (d / f).is_file(), f
    for sub in ("sections", "figs", "inbox", "originals", "review", "checks"):
        assert (d / sub).is_dir(), sub
    main = (d / "main.tex").read_text(encoding="utf-8")
    assert r"\title{Kondo notes}" in main and r"\author{A. B.}" in main and "<<" not in main.replace("% <<SECTIONS>>", "")
    style = note.parent.parent / mynotes.STYLE_NAME
    assert style.is_file() and mynotes.shared_style(pr) == style
    style.write_text("用户改过的文风", encoding="utf-8")
    with pytest.raises(ValueError):
        mynotes.init(pr)
    assert style.read_text(encoding="utf-8") == "用户改过的文风"  # 已有的共用文风不覆盖
    st = mynotes.status(pr)
    assert st["exists"] and st["pdf"] == "" and st["marks"] == {"orange": 0, "cmt": 0} and st["style"]["shared"] == str(style)


def test_marks_accept_and_inbox(project_dir: Path):
    pr = Project(project_dir)
    d = mynotes.init(pr, title="T")
    (d / "sections" / "01-model.tex").write_text(SECTION.replace("Text.", r"Text. \cmt{Is the sum over the full zone?}"), encoding="utf-8")
    (d / "inbox" / "hand.pdf").write_bytes(b"%PDF-fake")
    (d / "inbox" / "later.pdf").write_bytes(b"%PDF-fake")
    fm.write(d / "review" / "2026-11-07-model.md", {"title": "第一批", "status": "pending", "date": "2026-11-07", "inputs": ["mynotes/inbox/hand.pdf"]}, "# 第一批\n")
    st = mynotes.status(pr)
    assert st["marks"] == {"orange": 2, "cmt": 1} and st["questions"][0]["file"] == "sections/01-model.tex"
    assert st["questions"][0]["text"] == "Is the sum over the full zone?"
    assert sorted(f["name"] for f in st["inbox"]) == ["hand.pdf", "later.pdf"]
    assert st["reviews"][0]["status"] == "pending"
    with pytest.raises(ValueError, match="问题没答"):
        mynotes.accept(pr, rebuild=False)
    sec = d / "sections" / "01-model.tex"
    sec.write_text(sec.read_text(encoding="utf-8").replace(r" \cmt{Is the sum over the full zone?}", ""), encoding="utf-8")
    r = mynotes.accept(pr, rebuild=False)
    assert r["removed_marks"] == 2 and r["files"] == ["sections/01-model.tex"]
    assert not (d / "inbox" / "hand.pdf").exists() and (d / "inbox" / "later.pdf").exists()  # 只移这一批清单里列的原稿
    assert len(list((d / "originals").glob("*-hand.pdf"))) == 1
    meta, _ = fm.read(d / "review" / "2026-11-07-model.md")
    assert meta["status"] == "accepted" and meta["inputs"][0].startswith("mynotes/originals/")
    assert mynotes.marks(pr)["orange"] == 0


def test_toc_and_labels_from_build_files(project_dir: Path):
    pr = Project(project_dir)
    d = mynotes.init(pr, title="T")
    (d / "build").mkdir()
    (d / "build" / "main.toc").write_text(
        "\\contentsline {title}{T}{1}{section*.1}%\n\\tocdepth@munge \n\\contentsline {section}{\\numberline {}Contents}{1}{section*.2}%\n"
        "\\contentsline {section}{\\numberline {I}Model and $\\eta ^\\dagger $}{2}{section*.3}%\n"
        "\\contentsline {subsection}{\\numberline {A}\\blueP {Detail} part}{3}{section*.4}%\n"
        "\\contentsline {section}{\\numberline {}Notation}{4}{section*.5}%\n", encoding="utf-8")
    (d / "build" / "main.aux").write_text(
        "\\newlabel{sec:model}{{I}{2}{}{section*.3}{}}\n\\newlabel{eq:h}{{1}{2}{}{equation.0.1}{}}\n\\newlabel{sec:detail}{{A}{3}{}{section*.4}{}}\n", encoding="utf-8")
    assert mynotes.labels(pr)["eq:h"] == {"num": "1", "page": 2, "anchor": "equation.0.1"}
    assert mynotes.toc(pr) == [
        {"level": 1, "num": "I", "title": "Model and $\\eta ^\\dagger $", "page": 2, "label": "sec:model"},
        {"level": 2, "num": "A", "title": "Detail part", "page": 3, "label": "sec:detail"},
        {"level": 1, "num": "", "title": "Notation", "page": 4, "label": ""},
    ]


def test_api_overview_and_ai_export(project_dir: Path, capsys):
    pr = Project(project_dir)
    c = TestClient(create_app(pr))
    assert c.get("/api/overview").json()["mynotes"] is False and c.get("/api/mynotes").json()["exists"] is False
    assert "/md/%E6%88%91%E7%9A%84%E7%AC%94%E8%AE%B0.tex" not in c.get("/llms.txt").text
    cli.main(["mynotes", "init", str(project_dir), "--author", "A. B."])
    assert "已建" in capsys.readouterr().out and "正文骨架" in (project_dir / "log.md").read_text(encoding="utf-8")
    d = project_dir / "mynotes"
    (d / "sections" / "01-model.tex").write_text(SECTION, encoding="utf-8")
    main = d / "main.tex"
    main.write_text(main.read_text(encoding="utf-8").replace("% <<SECTIONS>>", "\\input{sections/01-model}"), encoding="utf-8")
    assert c.get("/api/overview").json()["mynotes"] is True
    st = c.get("/api/mynotes").json()
    assert st["exists"] and st["sections"] == ["sections/01-model.tex"] and st["marks"]["orange"] == 2
    assert "/md/%E6%88%91%E7%9A%84%E7%AC%94%E8%AE%B0.tex" in c.get("/llms.txt").text
    flat = c.get("/md/我的笔记.tex").text
    assert "% ==== sections/01-model.tex ====" in flat and "\\section{Model}" in flat and "\\input{sections/01-model}" not in flat
    assert "\\section{Model}" in c.get("/llms-full.txt").text
    cli.main(["mynotes", "status", str(project_dir)])
    assert json.loads(capsys.readouterr().out)["marks"]["orange"] == 2


@pytest.mark.skipif(not mynotes.latexmk(), reason="这台机器没有 TeX")
def test_build_compiles_skeleton_with_a_section(project_dir: Path):
    pr = Project(project_dir)
    d = mynotes.init(pr, title="Test notes", author="A. B.")
    r = mynotes.build(pr)
    assert r["ok"] and r["pages"] == 1 and not r["errors"]
    (d / "sections" / "01-model.tex").write_text(SECTION.replace("Text.", r"Text in \secref{sec:model}, Eq.~\eqref{eq:h}."), encoding="utf-8")
    (d / "notation.tex").write_text((d / "notation.tex").read_text(encoding="utf-8") + "\\notation{$H_0$}{free Hamiltonian}{Eq.~\\eqref{eq:h}}\n", encoding="utf-8")
    main = d / "main.tex"
    main.write_text(main.read_text(encoding="utf-8").replace("% <<SECTIONS>>", "\\input{sections/01-model}"), encoding="utf-8")
    r = mynotes.build(pr)
    assert r["ok"] and not r["undefined_refs"] and r["marks"]["orange"] == 2
    st = mynotes.status(pr)
    assert st["pdf"] == "mynotes/build/main.pdf" and not st["stale"] and st["notation"] == 1
    assert [(t["num"], t["title"], t["label"]) for t in st["toc"]] == [("I", "Model", "sec:model"), ("A", "Detail", "sec:detail"), ("", "Notation", "")]

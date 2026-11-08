# 我的笔记（正文）

课题负责人自己的笔记：按自己的逻辑、用自己的记号写成的 LaTeX，将来可以直接拿去写文章或报告。dashboard 里的 wiki、lab 推导是素材库，这里是正本。网页上「我的笔记 › 正文」显示编译好的 PDF；批注在同一页的「批注」里。

## 文件

| 位置 | 是什么 |
|---|---|
| `main.tex` | 骨架：标题、目录，按顺序 `\input` 各节 |
| `sections/` | 每节一个文件 `NN-slug.tex`；每个 `\section` 后面紧跟 `\label{sec:…}` |
| `preamble.tex` | 版式和通用宏，沿用自己的 LaTeX 母版（颜色设置不改） |
| `notation.tex` | 记号表和记号宏，这份笔记记号的唯一来源 |
| `refs.bib` | 文献 |
| `figs/` | 图 |
| `inbox/` | 待整理的手写稿、照片、Mathematica 导出：放进来就行 |
| `originals/` | 整理过的原稿（接受时从 inbox 移过来留档），对照清单引用它们 |
| `review/` | 每一批增补的对照清单 `YYYY-MM-DD-slug.md` |
| `checks/` | 补推导时用的验证脚本，不进正文 |
| `STYLE.md` | 这份笔记特有的文风规矩；各课题通用的文风在 Project Notes 的 `我的笔记文风.md` |
| `build/` | 编译输出（`main.pdf`、红线版 `redline.pdf`），不进 git |

## 颜色

黑色是你自己的内容（照你的手写稿录入）；**橙色**是 agent 补的细节；**蓝色 [方括号]** 是 agent 要问你的；紫色 [JX: …] 是你自己的批注。还没写完的地方用 `\tbc`，印出单独一行的 "(to be completed)"。

## 一批增补怎么走

1. 你把手写稿放进 `inbox/`，说一句放到哪一节；不说的话 agent 先提议位置，你同意再写。
2. agent 照你的手写逐句录入（黑色），只补四类细节（橙色）：中间步骤、句子之间的衔接、你用到但没定义的符号、对前文公式和文献的引用。每处补充从哪来（前文哪个式子、dashboard 哪个 lab 哪一节）写在 tex 注释 `% src:` 里，不进 PDF。tex 里的注释和蓝色问题都用英文。
3. 新论证、新类比、新小节、调换顺序、你没写的结论，都不进正文，写进 `review/` 清单当建议。看不清的字、存疑的地方用蓝色问你。
4. agent 编译、出红线版，交给你三样：`build/main.pdf`、`build/redline.pdf`（和上次接受的版本比）、`review/` 里这一批的清单。
5. 你批准后 agent 跑 `rd mynotes accept`：橙色标记去掉、变成正文，原稿从 `inbox/` 移到 `originals/`，然后 git commit。还有蓝色问题没答时 accept 会拒绝。

## 命令

```
rd mynotes build <课题目录>     # 编译（要在装了 TeX 的机器上跑）
rd mynotes redline <课题目录>   # 和上次接受的版本（git HEAD）比，出 build/redline.pdf
rd mynotes accept <课题目录>    # 接受这一批
rd mynotes status <课题目录>    # 状态：PDF、待看的标记、inbox、清单
```

## 记号和 dashboard

`notation.tex` 是这份笔记记号的唯一来源。笔记里登记了记号以后，课题的 `wiki/notation.md` 跟着它走：同一个量在 dashboard 里写法不同，就按这里改 notation.md 并同步各页。从 lab 推导往笔记里搬东西时，一律换成这里的记号。

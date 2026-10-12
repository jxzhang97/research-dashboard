# labs

每个任务一个文件夹 `NN-slug/`：

- `brief.md`：任务书（frontmatter: title, status, idea, machine, created）。用户原话原样保留在「## 用户原话」。
- `report.md`：薄层摘要，首屏四段（问题 / 当前回答 / 为什么信 / 边界），dashboard 的 lab 页和列表显示它；frontmatter `notes:` 指向厚层入口。
- `notes.md`：厚层——完整推导、分析、方法、验证（rd-notes skill），网页可读；PDF 按需导出。
- `handoff.md`：研究 agent 写给薄层写作步的交接单；开头先给各目标页“读者要带走的三句话”（发现 / 解释 / 边界），再列证据、科学限定与材料，格式见 rd-writer skill。
- `fig/`：图（PNG/SVG），report.md 与 notes.md 共用。
- `sources/reading-map.md`：阅读范围与证据定位——每份原文的真实身份、精读到的页码与式号、公开附录的来源版本、没拿到的材料（rd-reference）。
- `audit/`：独立审计报告（`<日期>-<模型>-<kind>[-v2].md`，kind 为 derivation / code / consistency，三档发现 + 处理记录；改过源文件后的复核报告带 -v2）和审计者的复算脚本 `scratch/`。`rd finish` 只认覆盖当前文件版本的通过报告。
- `resume.md`：续跑单（做完了什么、还差什么、在等哪个作业、下一步命令）。
- `DATA.md`：大数据放在哪台机器的哪个路径、内容、日期、怎么重新生成。
- 代码、小结果直接放在这里；大数据不要放。

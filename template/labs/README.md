# labs

每个任务一个文件夹 `NN-slug/`：

- `brief.md`：任务书（frontmatter: title, status, idea, machine, created）。用户原话原样保留在「## 用户原话」。
- `report.md`：薄层摘要，首屏四段（问题 / 当前回答 / 为什么信 / 边界），dashboard 的 lab 页和列表显示它；frontmatter `notes:` 指向厚层入口。
- `notes.md`：厚层——完整推导、分析、方法、验证（rd-notes skill），网页可读；PDF 按需导出。
- `handoff.md`：研究 agent 写给薄层写作步的交接单。
- `fig/`：图（PNG/SVG），report.md 与 notes.md 共用。
- `audit/`：独立审计报告（`<日期>-<模型>-<kind>.md`，三档发现 + 处理记录）和审计者的复算脚本 `scratch/`。
- `DATA.md`：大数据放在哪台机器的哪个路径、内容、日期、怎么重新生成。
- 代码、小结果直接放在这里；大数据不要放。

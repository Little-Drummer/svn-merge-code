---
name: svn-merge-code
description: SVN 代码合并辅助 —— 选择项目、识别个人/develop/test/produce 分支、选择 SVN 版本、生成 svn merge 命令和公司格式合并日志
category: devops
---

# SVN 代码合并辅助

适用于使用 SVN 开发并提交代码后，需要把个人分支合并到 `develop`，把 `develop` 的新内容更新到个人分支，或把 `develop` 合并到 `test` / `produce`，同时按公司格式生成合并日志的场景。

## 使用方式

### 安装依赖

```bash
python3 -m pip install -r ~/.hermes/skills/devops/svn-merge-code/requirements.txt
```

### 交互式运行

```bash
~/.hermes/skills/devops/svn-merge-code/run.sh
```

从项目目录运行时会自动把当前项目排到最前面：

```bash
cd /Volumes/macData/work/中信保V1.6.1/develop/rest
~/.hermes/skills/devops/svn-merge-code/run.sh
```

如果已配置快捷命令：

```bash
svnmerge
```

## 交互流程

### Step 1: 选择项目

- 自动扫描 `/Volumes/macData/work/` 下的项目
- 支持搜索过滤项目名
- 支持快速匹配当前所在项目
- 只显示检测到 `rest`、`database` 或 `updatesql` 模块的项目

### Step 2: 选择合并方向

脚本会根据本地工作副本自动识别可用方向：

| 本地结构 | 支持方向 |
|---------|---------|
| `develop/{个人分支}`，如 `develop/wangjingan` | 个人分支 → `develop/rest` |
| `develop/{个人分支}`，如 `develop/wangjingan` | `develop/rest` → 个人分支 |
| `test/rest` 存在 | `develop/rest` → `test/rest` |
| `produce/rest` 存在 | `develop/rest` → `produce/rest` |
| `test/rest` 和 `produce/rest` 都存在 | `test/rest` → `produce/rest` |
| `test/database` 存在 | `develop/database` → `test/database` |
| `produce/database` 存在 | `develop/database` → `produce/database` |
| `test/database` 和 `produce/database` 都存在 | `test/database` → `produce/database` |
| `test/updatesql` 存在 | `develop/updatesql` → `test/updatesql` |
| `produce/updatesql` 存在 | `develop/updatesql` → `produce/updatesql` |
| `test/updatesql` 和 `produce/updatesql` 都存在 | `test/updatesql` → `produce/updatesql` |

如果项目没有 `produce` 分支，不会显示 `develop -> produce`；如果没有 `test` 分支，仍可在存在 `produce` 时选择 `develop -> produce`。

### Step 3: 选择 SVN 版本

- 从源分支 URL 自动拉取最近 80 条 SVN 日志
- 返回后重新选择合并方向时，会清空旧版本选择并重新拉取新源分支日志
- `develop/rest` → 个人分支时，使用 `svn mergeinfo --show-revs eligible` 只分析 develop 中尚未合入个人分支的版本
- `develop/rest` → 个人分支时，会过滤掉“从当前个人分支合并到 develop”的合并提交，避免把自己刚合过去的提交再显示出来
- 个人分支 → `develop/rest` 时，会过滤掉“从 develop 合并到当前个人分支”的同步提交，避免把同步 develop 的记录再显示出来
- SVN 记录按时间倒序显示，版本不会默认选中，需要按 `Space` 手动选择
- 表格显示版本号、作者、日期、提交说明
- `Space` 选择/取消当前版本，光标保持在当前行
- `a` 全选当前表格可见版本；如果已过滤，则只全选过滤后的版本
- `Enter` 完成选择并生成合并命令和日志
- 支持按作者、版本号或提交说明过滤
- 自动拉取失败时，可切换到手动粘贴 `svn log` 输出

### Step 4: 生成结果

脚本会生成：

- `svn merge -c ... {源分支URL} {目标工作副本}` 命令
- 目标工作副本是否干净的检查结果
- 可直接复制到提交框的公司格式合并日志

确认命令和日志无误后：

- 按 `Enter` 执行 `svn merge`
- `develop/rest` → 个人分支时，如果个人分支存在本地版本化修改，第一次 `Enter` 会先搁置到 `~/.hermes/skills/devops/svn-merge-code/shelves/`，搁置成功后再按 `Enter` 执行合并
- 合并成功后，再按 `Enter` 执行 `svn commit -m 合并日志`
- 如果本次合并前发生过搁置，提交成功后再按 `Enter` 自动执行 `svn patch` 恢复搁置代码
- 执行 `svn merge` 前会先对目标工作副本执行 `svn update`，避免 mixed-revision working copy 导致合并失败
- 如果合并后没有任何文件进入待提交状态，不执行提交，只能返回
- 如果合并或提交失败，界面会显示 SVN 输出，并停留在当前步骤

搁置会保存：

- `status.txt`：搁置前的 `svn status`
- `changes.patch`：搁置前的 `svn diff`

需要恢复时，可在个人分支工作副本中使用：

```bash
svn patch ~/.hermes/skills/devops/svn-merge-code/shelves/{搁置目录}/changes.patch
```

## 合并日志格式

生成格式与公司要求一致：

```text
合并了修改版本号137564 从 电子档案/2.产品源代码/4-project/zhongxinbaoV1.6.1/develop/branches/rest/wangjingan:
【需求】【ID1011466】档案鉴定功能优化
........
```

多个版本会自动压缩连续版本号：

```text
合并了修改版本号136219, 136681-136682, 137158, 137234 从 电子档案/2.产品源代码/4-project/zhongxinbaoV1.6.1/develop/branches/rest/lizhichao:
【需求】【1011362】宗内移交单导出功能优化
........
【需求】【1011316】保单承保、理赔追偿特殊装盒逻辑调整（41、84）
........
```

## 注意事项

- 脚本不执行打包命令
- 脚本会在你确认后执行合并，并在合并成功后由你再次按 `Enter` 执行提交
- 执行合并前建议确保目标工作副本 `svn status` 为空
- 合并命令执行后如有冲突，请在 IDEA 或 Cornerstone 中解决，再提交
- 需要已安装 SVN 命令行工具（`svn --version`）
- 个人分支识别依赖本地目录，例如 `develop/wangjingan` 是一个 SVN 工作副本

## 常见操作

选择版本后复制合并命令到终端执行：

```bash
svn merge -c 137564 svn://.../develop/branches/rest/wangjingan /Volumes/macData/work/项目/develop/rest
```

合并完成后检查状态：

```bash
svn status /Volumes/macData/work/项目/develop/rest
```

确认无误后提交，并使用脚本生成的合并日志作为提交说明。

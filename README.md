# svn-merge-code

SVN 代码合并辅助工具，用于在本地 SVN 工作副本之间选择合并方向、选择 SVN 版本、生成 `svn merge` 命令，并输出符合公司格式的合并日志。

## 功能

- 自动扫描 `/Volumes/macData/work/` 下的项目。
- 识别个人分支、`develop`、`test`、`produce` 等常见分支结构。
- 从源分支拉取 SVN 日志并支持按作者、版本号、提交说明过滤。
- 生成可执行的 `svn merge -c ...` 命令。
- 生成可直接复制到提交框的合并日志。
- 在确认后执行 `svn update`、`svn merge` 和 `svn commit`。
- 对个人分支同步 `develop` 时，可临时搁置本地版本化修改并在提交后恢复。

## 环境要求

- Python 3
- SVN 命令行工具
- 可访问目标 SVN 仓库

## 安装

```bash
cd ~/.hermes/skills/devops/svn-merge-code
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 使用

```bash
~/.hermes/skills/devops/svn-merge-code/run.sh
```

也可以在项目目录中运行，脚本会优先匹配当前所在项目：

```bash
cd /Volumes/macData/work/your-project/develop/rest
~/.hermes/skills/devops/svn-merge-code/run.sh
```

## 合并流程

1. 选择项目。
2. 选择合并方向。
3. 选择要合并的 SVN 版本。
4. 确认生成的合并命令和日志。
5. 按提示执行合并、提交和搁置恢复。

## 搁置文件

工具会把临时搁置内容保存到本地 `shelves/` 目录，该目录已加入 `.gitignore`，不会提交到远程仓库。

如需手动恢复：

```bash
svn patch ~/.hermes/skills/devops/svn-merge-code/shelves/{搁置目录}/changes.patch
```

## 注意事项

- 本工具不执行前端或后端打包命令。
- 执行合并前建议确保目标工作副本 `svn status` 为空。
- 如合并产生冲突，请先在 IDE 或 SVN 客户端中解决，再提交。

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

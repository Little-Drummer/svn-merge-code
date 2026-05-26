#!/usr/bin/env python3
"""
SVN 代码合并辅助工具
====================

TUI 交互式流程：
  选择项目 -> 选择合并方向 -> 选择 SVN 版本 -> 生成 svn merge 命令和公司格式合并日志
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import datetime
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

try:
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import Screen
    from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static, TextArea

    TEXTUAL_AVAILABLE = True
except ModuleNotFoundError:
    TEXTUAL_AVAILABLE = False


WORK_BASE = "/Volumes/macData/work"
LOG_LIMIT = 80
SHELVES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shelves")
MERGE_MODULES = ("rest", "database", "updatesql")


def run_svn(args: list[str], cwd: str | None = None, timeout: int = 30) -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(
            ["svn", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return None, "未找到 svn 命令"
    except subprocess.TimeoutExpired:
        return None, "svn 命令执行超时"
    except Exception as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout).strip()
    return result.stdout.strip(), None


def svn_url(path: str) -> str:
    out, _ = run_svn(["info", "--show-item", "url", path], timeout=10)
    return out or ""


def decode_svn_url_path(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    if parsed.scheme and parsed.netloc:
        return unquote(parsed.path.lstrip("/"))
    return unquote(url)


def display_path(path_or_url: str) -> str:
    url = svn_url(path_or_url) if os.path.exists(path_or_url) else path_or_url
    return decode_svn_url_path(url)


def detect_primary_module(project_path: str) -> str | None:
    for rel in ("develop/rest", "rest"):
        candidate = os.path.join(project_path, rel)
        if os.path.isdir(candidate):
            return candidate
    for module in MERGE_MODULES[1:]:
        candidate = os.path.join(project_path, "develop", module)
        if os.path.isdir(candidate):
            return candidate
    return None


def scan_projects() -> list[dict]:
    if not os.path.isdir(WORK_BASE):
        return []
    projects = []
    for name in sorted(os.listdir(WORK_BASE)):
        path = os.path.join(WORK_BASE, name)
        if not os.path.isdir(path) or name.startswith("."):
            continue
        primary_module = detect_primary_module(path)
        if not primary_module:
            continue
        projects.append({
            "name": name,
            "path": path,
            "rest_path": primary_module,
            "routes": detect_routes(path),
        })
    return projects


def auto_match_project(projects: list[dict]) -> dict | None:
    cwd = os.getcwd()
    for project in projects:
        if cwd == project["path"] or cwd.startswith(project["path"] + os.sep):
            return project
    cwd_name = os.path.basename(cwd)
    for project in projects:
        if cwd_name and (cwd_name in project["name"] or project["name"] in cwd_name):
            return project
    return None


def filter_projects(projects: list[dict], keyword: str) -> list[dict]:
    kw = keyword.lower().strip()
    if not kw:
        return projects
    return [project for project in projects if kw in project["name"].lower()]


def is_svn_working_copy(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".svn")) or bool(svn_url(path))


def detect_personal_branches(project_path: str) -> list[dict]:
    develop_dir = os.path.join(project_path, "develop")
    develop_rest = os.path.join(develop_dir, "rest")
    if not os.path.isdir(develop_dir) or not os.path.isdir(develop_rest):
        return []
    branches = []
    ignored = {
        "rest",
        "database",
        "updatesql",
        "front",
        "frontend",
        "node_modules",
        "target",
        ".idea",
        ".svn",
        "branches",
    }
    for name in sorted(os.listdir(develop_dir)):
        path = os.path.join(develop_dir, name)
        if name.startswith(".") or name in ignored or not os.path.isdir(path):
            continue
        if is_svn_working_copy(path):
            branches.append({
                "id": f"personal:{name}:to-develop",
                "name": f"develop/{name} -> develop/rest",
                "source_label": f"develop/{name}",
                "source_path": path,
                "target_path": develop_rest,
                "kind": "个人分支 -> develop/rest",
                "eligible_only": True,
                "personal_branch": name,
            })
            branches.append({
                "id": f"personal:{name}:from-develop",
                "name": f"develop/rest -> develop/{name}",
                "source_label": "develop/rest",
                "source_path": develop_rest,
                "target_path": path,
                "kind": "develop/rest -> 个人分支",
                "eligible_only": True,
                "sync_branch": True,
                "personal_branch": name,
            })
    return branches


def detect_routes(project_path: str) -> list[dict]:
    routes = detect_personal_branches(project_path)
    for module in MERGE_MODULES:
        develop_path = os.path.join(project_path, "develop", module)
        test_path = os.path.join(project_path, "test", module)
        produce_path = os.path.join(project_path, "produce", module)
        route_suffix = f"/{module}"
        if os.path.isdir(develop_path) and os.path.isdir(test_path):
            routes.append({
                "id": "develop:test" if module == "rest" else f"develop:test:{module}",
                "name": f"develop{route_suffix} -> test{route_suffix}",
                "source_label": f"develop{route_suffix}",
                "source_path": develop_path,
                "target_path": test_path,
                "kind": f"develop{route_suffix} -> test{route_suffix}",
                "eligible_only": True,
            })
        if os.path.isdir(develop_path) and os.path.isdir(produce_path):
            routes.append({
                "id": "develop:produce" if module == "rest" else f"develop:produce:{module}",
                "name": f"develop{route_suffix} -> produce{route_suffix}",
                "source_label": f"develop{route_suffix}",
                "source_path": develop_path,
                "target_path": produce_path,
                "kind": f"develop{route_suffix} -> produce{route_suffix}",
                "eligible_only": True,
            })
        if os.path.isdir(test_path) and os.path.isdir(produce_path):
            routes.append({
                "id": "test:produce" if module == "rest" else f"test:produce:{module}",
                "name": f"test{route_suffix} -> produce{route_suffix}",
                "source_label": f"test{route_suffix}",
                "source_path": test_path,
                "target_path": produce_path,
                "kind": f"test{route_suffix} -> produce{route_suffix}",
                "eligible_only": True,
            })
    return routes


def fetch_svn_log(source_path: str, limit: int = LOG_LIMIT) -> tuple[str | None, str | None]:
    source_url = svn_url(source_path)
    target = source_url or source_path
    return run_svn(["log", "-v", "-r", "HEAD:1", "-l", str(limit), target], cwd=source_path, timeout=45)


def parse_revision_lines(text: str) -> list[int]:
    revisions = []
    for line in text.splitlines():
        match = re.search(r"r?(\d+)", line.strip())
        if match:
            revisions.append(int(match.group(1)))
    return sorted(set(revisions))


def fetch_eligible_revisions(route: dict) -> tuple[list[int] | None, str | None]:
    source_url = svn_url(route["source_path"]) or route["source_path"]
    target_path = route["target_path"]
    out, err = run_svn(
        ["mergeinfo", "--show-revs", "eligible", source_url, target_path],
        cwd=target_path,
        timeout=60,
    )
    if err:
        return None, err
    return parse_revision_lines(out or ""), None


def fetch_svn_log_for_revisions(source_path: str, revisions: list[int]) -> tuple[str | None, str | None]:
    if not revisions:
        return "", None
    source_url = svn_url(source_path)
    target = source_url or source_path
    revision_range = f"{min(revisions)}:{max(revisions)}"
    return run_svn(["log", "-v", "-r", revision_range, target], cwd=source_path, timeout=90)


def filter_entries_by_revisions(entries: list[dict], revisions: list[int]) -> list[dict]:
    revision_set = set(revisions)
    return [entry for entry in entries if entry["revision"] in revision_set]


def sort_entries_time_desc(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda entry: entry["revision"], reverse=True)


def extract_merge_source_path(entry: dict) -> str:
    message = entry.get("message", "")
    match = re.search(r"从\s+(.+?):", message)
    if not match:
        return ""
    return match.group(1).strip().replace("\\", "/").rstrip("/")


def normalize_repo_path(path: str) -> str:
    return decode_svn_url_path(path).replace("\\", "/").rstrip("/")


def is_merge_from_personal_branch(entry: dict, route: dict) -> bool:
    branch = route.get("personal_branch", "")
    if not branch:
        return False
    source_path = extract_merge_source_path(entry)
    return source_path.endswith(f"/develop/branches/rest/{branch}")


def is_merge_from_develop_branch(entry: dict, route: dict) -> bool:
    source_path = extract_merge_source_path(entry)
    if not source_path:
        return False
    develop_path = normalize_repo_path(display_path(route.get("target_path", "")))
    return bool(develop_path) and source_path == develop_path


def filter_sync_entries(entries: list[dict], route: dict) -> list[dict]:
    if route.get("sync_branch"):
        return [entry for entry in entries if not is_merge_from_personal_branch(entry, route)]
    if route.get("personal_branch"):
        return [entry for entry in entries if not is_merge_from_develop_branch(entry, route)]
    return entries


def parse_svn_log_entries(raw_log: str) -> list[dict]:
    entries = []
    lines = raw_log.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        match = re.match(r"^r(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
        if not match:
            i += 1
            continue
        revision = int(match.group(1))
        author = match.group(2).strip()
        date = match.group(3).strip()
        i += 1
        in_changed_paths = False
        message_lines = []
        while i < len(lines):
            raw = lines[i]
            stripped = raw.strip()
            if stripped.startswith("---"):
                break
            if stripped == "Changed paths:":
                in_changed_paths = True
                i += 1
                continue
            if in_changed_paths:
                if stripped == "":
                    in_changed_paths = False
                i += 1
                continue
            if stripped and not re.match(r"^\d+\s+lines?$", stripped):
                message_lines.append(stripped)
            i += 1
        message = "\n".join(message_lines).strip() or "(无提交说明)"
        entries.append({"revision": revision, "author": author, "date": date, "message": message})
    return entries


def compact_revisions(revisions: list[int]) -> str:
    if not revisions:
        return ""
    nums = sorted(set(int(r) for r in revisions))
    ranges = []
    start = prev = nums[0]
    for num in nums[1:]:
        if num == prev + 1:
            prev = num
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = num
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)


def svn_merge_revision_arg(revisions: list[int]) -> str:
    return compact_revisions(revisions).replace(" ", "")


def format_merge_message(route: dict, entries: list[dict], revisions: list[int]) -> str:
    selected = [entry for entry in entries if entry["revision"] in set(revisions)]
    selected.sort(key=lambda item: item["revision"])
    revision_text = compact_revisions(revisions)
    source_text = display_path(route["source_path"])
    lines = [f"合并了修改版本号{revision_text} 从 {source_text}:"]
    for entry in selected:
        msg_lines = [line.strip() for line in entry["message"].splitlines() if line.strip()]
        lines.extend(msg_lines or ["(无提交说明)"])
        lines.append("........")
    return "\n".join(lines)


def build_merge_command(route: dict, revisions: list[int]) -> str:
    source_url = svn_url(route["source_path"]) or route["source_path"]
    target_path = route["target_path"]
    return f"svn merge -c {svn_merge_revision_arg(revisions)} {source_url} {target_path}"


def execute_svn(args: list[str], cwd: str | None = None, timeout: int = 300) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["svn", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "未找到 svn 命令"
    except subprocess.TimeoutExpired:
        return False, "svn 命令执行超时"
    except Exception as exc:
        return False, str(exc)
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return result.returncode == 0, output or "(无输出)"


def execute_merge(route: dict, revisions: list[int]) -> tuple[bool, str]:
    source_url = svn_url(route["source_path"]) or route["source_path"]
    target_path = route["target_path"]
    return execute_svn(["merge", "-c", svn_merge_revision_arg(revisions), source_url, target_path], timeout=300)


def execute_update(route: dict) -> tuple[bool, str]:
    target_path = route["target_path"]
    return execute_svn(["update", target_path], timeout=300)


def execute_commit(route: dict, message: str) -> tuple[bool, str]:
    target_path = route["target_path"]
    return execute_svn(["commit", target_path, "-m", message], timeout=300)


def has_versioned_changes(status: str) -> bool:
    for line in status.splitlines():
        if not line.strip():
            continue
        if line[0] not in ("?", "I", "X"):
            return True
    return False


def shelve_target_changes(route: dict) -> tuple[bool, str, str]:
    target_path = route["target_path"]
    clean, status = working_copy_status(target_path)
    if clean or not has_versioned_changes(status):
        return True, "没有检测到需要搁置的版本化修改。", ""

    os.makedirs(SHELVES_DIR, exist_ok=True)
    branch_name = route.get("personal_branch") or os.path.basename(target_path.rstrip(os.sep))
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    shelf_dir = os.path.join(SHELVES_DIR, f"{branch_name}-{timestamp}")
    os.makedirs(shelf_dir, exist_ok=True)

    status_path = os.path.join(shelf_dir, "status.txt")
    patch_path = os.path.join(shelf_dir, "changes.patch")
    with open(status_path, "w", encoding="utf-8") as f:
        f.write(status + "\n")

    diff, diff_err = run_svn(["diff", target_path], timeout=120)
    if diff_err:
        return False, f"生成搁置补丁失败：{diff_err}", shelf_dir
    with open(patch_path, "w", encoding="utf-8") as f:
        f.write((diff or "") + "\n")

    ok, revert_output = execute_svn(["revert", "-R", target_path], timeout=300)
    if not ok:
        return False, f"搁置补丁已保存，但清理工作副本失败：\n{revert_output}", shelf_dir

    message = "\n".join([
        "已搁置当前个人分支的版本化修改。",
        f"搁置目录：{shelf_dir}",
        f"状态文件：{status_path}",
        f"补丁文件：{patch_path}",
        "",
        revert_output,
    ])
    return True, message, shelf_dir


def restore_shelved_changes(route: dict, shelf_path: str) -> tuple[bool, str]:
    if not shelf_path:
        return True, "本次没有搁置内容，无需恢复。"
    patch_path = os.path.join(shelf_path, "changes.patch")
    if not os.path.exists(patch_path):
        return False, f"未找到搁置补丁：{patch_path}"
    target_path = route["target_path"]
    ok, output = execute_svn(["patch", patch_path, target_path], timeout=300)
    if not ok:
        return False, output
    return True, "\n".join([
        "已恢复搁置的个人分支修改。",
        f"搁置目录：{shelf_path}",
        output,
    ])


def working_copy_status(path: str) -> tuple[bool, str]:
    out, err = run_svn(["status", path], timeout=20)
    if err:
        return False, err
    return not bool(out.strip()), out.strip()


def working_copy_status_text(path: str) -> str:
    _, status = working_copy_status(path)
    return status.strip()


@dataclass
class MergeState:
    projects: list[dict] = field(default_factory=list)
    project: dict | None = None
    route: dict | None = None
    entries: list[dict] = field(default_factory=list)
    selected_revisions: list[int] = field(default_factory=list)
    raw_log: str = ""
    loaded_route_id: str = ""
    manual_mode: bool = False
    merge_message: str = ""
    merge_command: str = ""
    merge_done: bool = False
    commit_done: bool = False
    merge_no_changes: bool = False
    shelve_needed: bool = False
    shelve_done: bool = False
    shelve_path: str = ""
    restore_done: bool = False


if TEXTUAL_AVAILABLE:
    class ManualLogTextArea(TextArea):
        def _on_key(self, event) -> None:
            if event.key == "tab":
                event.prevent_default()
                event.stop()
                self.app.action_focus_next()
                return
            if event.key == "f":
                event.prevent_default()
                event.stop()
                screen = self.screen
                if hasattr(screen, "action_finish"):
                    screen.action_finish()
                return
            super()._on_key(event)


    class WizardScreen(Screen):
        STEP = 0
        TITLE = ""

        @property
        def merge_app(self) -> "SvnMergeApp":
            return self.app

        def step_text(self) -> str:
            names = ["项目", "方向", "版本", "结果"]
            parts = []
            for index, name in enumerate(names, 1):
                marker = "●" if index == self.STEP else "○"
                parts.append(f"{marker} {name}")
            return "  ".join(parts)

        def go_back(self) -> None:
            self.merge_app.pop_screen()


    class ProjectScreen(WizardScreen):
        STEP = 1
        TITLE = "选择项目"
        BINDINGS = [
            Binding("enter", "choose", "选择"),
            Binding("/", "focus_search", "搜索"),
            Binding("q", "quit", "退出"),
        ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Vertical(id="shell"):
                yield Static(f"[{self.STEP}/4] {self.TITLE}", id="step-title")
                yield Static(self.step_text(), id="step-bar")
                yield Static("方向键移动，Enter 选择当前项目，/ 搜索。", classes="hint")
                yield Input(placeholder="搜索项目名称", id="project-search")
                yield DataTable(id="project-table")
                yield Static("Enter 下一步   / 搜索   q 退出", classes="keybar")
            yield Footer()

        def on_mount(self) -> None:
            self.refresh_projects()
            self.query_one("#project-table", DataTable).focus()

        @on(Input.Changed, "#project-search")
        def on_search_changed(self) -> None:
            self.refresh_projects()

        @on(DataTable.RowSelected, "#project-table")
        def on_row_selected(self, event: DataTable.RowSelected) -> None:
            self.select_by_path(str(event.row_key.value))
            self.action_choose()

        def refresh_projects(self) -> None:
            table = self.query_one("#project-table", DataTable)
            table.clear(columns=True)
            table.cursor_type = "row"
            table.add_columns("项目", "可用合并", "路径")
            keyword = self.query_one("#project-search", Input).value
            projects = filter_projects(self.merge_app.state.projects, keyword)
            auto = auto_match_project(projects)
            if auto and not keyword:
                projects = [auto] + [item for item in projects if item["path"] != auto["path"]]
            for project in projects:
                route_names = "，".join(route["name"] for route in project["routes"]) or "未检测到"
                table.add_row(project["name"], route_names, project["path"], key=project["path"])
            if projects:
                self.merge_app.state.project = projects[0]

        def select_by_path(self, path: str) -> None:
            for project in self.merge_app.state.projects:
                if project["path"] == path:
                    self.merge_app.state.project = project
                    self.merge_app.state.route = None
                    return

        def action_choose(self) -> None:
            table = self.query_one("#project-table", DataTable)
            if table.row_count:
                row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
                self.select_by_path(str(row_key.value))
            project = self.merge_app.state.project
            if not project:
                self.notify("请先选择项目", severity="warning")
                return
            if not project["routes"]:
                self.notify("该项目没有检测到可合并分支", severity="warning")
                return
            self.merge_app.push_screen("route")

        def action_focus_search(self) -> None:
            self.query_one("#project-search", Input).focus()

        def action_quit(self) -> None:
            self.app.exit()


    class RouteScreen(WizardScreen):
        STEP = 2
        TITLE = "选择合并方向"
        BINDINGS = [
            Binding("enter", "choose", "选择"),
            Binding("b", "back", "返回"),
            Binding("escape", "back", "返回"),
        ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Vertical(id="shell"):
                yield Static(f"[{self.STEP}/4] {self.TITLE}", id="step-title")
                yield Static(self.step_text(), id="step-bar")
                yield Static("可选择个人分支合 develop，也可把 develop 的新内容更新到个人分支。", classes="hint")
                yield DataTable(id="route-table")
                yield Static("Enter 下一步   b 返回", classes="keybar")
            yield Footer()

        def on_mount(self) -> None:
            table = self.query_one("#route-table", DataTable)
            table.cursor_type = "row"
            table.add_columns("合并方向", "源分支", "目标工作副本")
            project = self.merge_app.state.project or {}
            for route in project.get("routes", []):
                table.add_row(route.get("name", route["kind"]), display_path(route["source_path"]), route["target_path"], key=route["id"])
            table.focus()

        @on(DataTable.RowSelected, "#route-table")
        def on_row_selected(self, event: DataTable.RowSelected) -> None:
            self.select_by_id(str(event.row_key.value))
            self.action_choose()

        def select_by_id(self, route_id: str) -> None:
            project = self.merge_app.state.project or {}
            for route in project.get("routes", []):
                if route["id"] == route_id:
                    if self.merge_app.state.route and self.merge_app.state.route.get("id") == route_id:
                        return
                    self.merge_app.state.route = route
                    self.reset_svn_state()
                    return

        def reset_svn_state(self) -> None:
            state = self.merge_app.state
            state.entries = []
            state.selected_revisions = []
            state.raw_log = ""
            state.loaded_route_id = ""
            state.manual_mode = False
            state.merge_message = ""
            state.merge_command = ""
            state.merge_done = False
            state.commit_done = False
            state.merge_no_changes = False
            state.shelve_needed = False
            state.shelve_done = False
            state.shelve_path = ""
            state.restore_done = False

        def action_choose(self) -> None:
            table = self.query_one("#route-table", DataTable)
            if table.row_count:
                row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
                self.select_by_id(str(row_key.value))
            if not self.merge_app.state.route:
                self.notify("请先选择合并方向", severity="warning")
                return
            self.merge_app.push_screen("svn")

        def action_back(self) -> None:
            self.go_back()


    class RevisionScreen(WizardScreen):
        STEP = 3
        TITLE = "选择 SVN 版本"
        BINDINGS = [
            Binding("space", "toggle", "选择/取消"),
            Binding("a", "select_all", "全选"),
            Binding("enter", "finish", "生成"),
            Binding("m", "manual", "手动粘贴"),
            Binding("f", "finish", "完成", priority=True),
            Binding("/", "focus_filter", "过滤"),
            Binding("b", "back", "返回"),
            Binding("escape", "back", "返回", priority=True),
        ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Vertical(id="shell"):
                yield Static(f"[{self.STEP}/4] {self.TITLE}", id="step-title")
                yield Static(self.step_text(), id="step-bar")
                yield Static("正在加载 SVN 日志...", id="svn-status")
                yield Input(placeholder="按作者、版本号或提交说明过滤", id="svn-filter")
                yield DataTable(id="svn-table")
                yield ManualLogTextArea("", id="manual-log")
                yield Static("Space 选择   a 全选   Enter 生成   / 过滤   m 手动粘贴   b 返回", classes="keybar")
            yield Footer()

        def on_mount(self) -> None:
            self.query_one("#manual-log", TextArea).display = False
            self.prepare_logs()

        def on_screen_resume(self) -> None:
            self.prepare_logs()

        def prepare_logs(self) -> None:
            state = self.merge_app.state
            route = state.route or {}
            route_id = route.get("id", "")
            self.query_one("#manual-log", TextArea).display = False
            self.query_one("#svn-table", DataTable).display = True
            self.query_one("#svn-filter", Input).display = True
            if state.entries and state.loaded_route_id == route_id:
                count_text = (
                    f"已检测到 {len(state.entries)} 个目标分支尚未包含的版本，请按 Space 选择要合并的版本"
                    if route.get("eligible_only") else
                    f"已读取最近 {len(state.entries)} 条日志"
                )
                self.query_one("#svn-status", Static).update(
                    f"源分支：{display_path(route.get('source_path', ''))}\n"
                    f"目标工作副本：{route.get('target_path', '')}\n"
                    f"{count_text}"
                )
                self.refresh_table()
                self.query_one("#svn-table", DataTable).focus()
                return
            state.entries = []
            state.selected_revisions = []
            state.raw_log = ""
            state.loaded_route_id = ""
            state.manual_mode = False
            self.query_one("#svn-filter", Input).value = ""
            self.query_one("#svn-table", DataTable).clear(columns=True)
            self.query_one("#svn-status", Static).update(
                f"源分支：{display_path(route.get('source_path', ''))}\n"
                f"{'正在分析目标分支尚未包含的版本...' if route.get('eligible_only') else '正在加载 SVN 日志...'}"
            )
            self.load_logs()

        @work(thread=True)
        def load_logs(self) -> None:
            route = self.merge_app.state.route or {}
            route_id = route.get("id", "")
            eligible_revisions = None
            if route.get("eligible_only"):
                eligible_revisions, err = fetch_eligible_revisions(route)
                if not err:
                    raw, err = fetch_svn_log_for_revisions(route.get("source_path", ""), eligible_revisions or [])
                else:
                    raw = None
            else:
                raw, err = fetch_svn_log(route.get("source_path", ""))
            def done() -> None:
                if (self.merge_app.state.route or {}).get("id", "") != route_id:
                    return
                if err:
                    self.merge_app.state.manual_mode = True
                    self.merge_app.state.loaded_route_id = route_id
                    self.query_one("#svn-status", Static).update(f"自动拉取失败：{err}\n请按 m 手动粘贴 svn log。")
                    return
                self.merge_app.state.raw_log = raw or ""
                entries = parse_svn_log_entries(raw or "")
                if route.get("eligible_only"):
                    entries = filter_entries_by_revisions(entries, eligible_revisions or [])
                    entries = filter_sync_entries(entries, route)
                    self.merge_app.state.selected_revisions = []
                entries = sort_entries_time_desc(entries)
                self.merge_app.state.entries = entries
                self.merge_app.state.loaded_route_id = route_id
                if route.get("eligible_only") and not entries:
                    self.query_one("#svn-status", Static).update(
                        f"源分支：{display_path(route.get('source_path', ''))}\n"
                        f"目标工作副本：{route.get('target_path', '')}\n"
                        "没有检测到目标分支尚未包含的版本。"
                    )
                    self.refresh_table()
                    self.query_one("#svn-table", DataTable).focus()
                    return
                self.query_one("#svn-status", Static).update(
                    f"源分支：{display_path(route.get('source_path', ''))}\n"
                        f"目标工作副本：{route.get('target_path', '')}\n" +
                    (
                        f"已检测到 {len(self.merge_app.state.entries)} 个目标分支尚未包含的版本，请按 Space 选择要合并的版本。"
                        if route.get("eligible_only") else
                        f"已读取 {len(self.merge_app.state.entries)} 条日志"
                    )
                )
                self.refresh_table()
                self.query_one("#svn-table", DataTable).focus()
            self.app.call_from_thread(done)

        @on(Input.Changed, "#svn-filter")
        def on_filter_changed(self) -> None:
            self.refresh_table()

        @on(DataTable.RowSelected, "#svn-table")
        def on_row_selected(self, event: DataTable.RowSelected) -> None:
            self.action_finish()

        def visible_entries(self) -> list[dict]:
            keyword = self.query_one("#svn-filter", Input).value.strip().lower()
            entries = []
            for entry in self.merge_app.state.entries:
                haystack = f"{entry['revision']} {entry['author']} {entry['message']}".lower()
                if keyword and keyword not in haystack:
                    continue
                entries.append(entry)
            return entries

        def refresh_table(self, keep_revision: int | None = None) -> None:
            table = self.query_one("#svn-table", DataTable)
            table.clear(columns=True)
            table.cursor_type = "row"
            table.add_columns("选中", "版本", "作者", "日期", "提交说明")
            restore_row = 0
            visible_index = 0
            for entry in self.visible_entries():
                if keep_revision is not None and entry["revision"] == keep_revision:
                    restore_row = visible_index
                mark = "✓" if entry["revision"] in self.merge_app.state.selected_revisions else ""
                message = " ".join(entry["message"].split())
                table.add_row(mark, str(entry["revision"]), entry["author"], entry["date"][:19], message, key=str(entry["revision"]))
                visible_index += 1
            if table.row_count:
                table.move_cursor(row=min(restore_row, table.row_count - 1), column=0)

        def toggle_revision(self, revision: int) -> None:
            selected = self.merge_app.state.selected_revisions
            if revision in selected:
                selected.remove(revision)
            else:
                selected.append(revision)
                selected.sort()

        def action_toggle(self) -> None:
            table = self.query_one("#svn-table", DataTable)
            if not table.row_count:
                return
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            revision = int(row_key.value)
            self.toggle_revision(revision)
            self.refresh_table(keep_revision=revision)
            table.focus()

        def action_select_all(self) -> None:
            table = self.query_one("#svn-table", DataTable)
            revisions = [entry["revision"] for entry in self.visible_entries()]
            if not revisions:
                return
            keep_revision = None
            if table.row_count:
                row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
                keep_revision = int(row_key.value)
            selected = set(self.merge_app.state.selected_revisions)
            selected.update(revisions)
            self.merge_app.state.selected_revisions = sorted(selected)
            self.refresh_table(keep_revision=keep_revision)
            table.focus()
            self.notify(f"已全选 {len(revisions)} 个可见版本")

        def action_manual(self) -> None:
            self.merge_app.state.manual_mode = True
            self.query_one("#svn-table", DataTable).display = False
            manual = self.query_one("#manual-log", TextArea)
            manual.display = True
            manual.focus()
            self.query_one("#svn-status", Static).update("请粘贴 svn log 输出，按 f 解析并生成。")

        def action_finish(self) -> None:
            if self.merge_app.state.manual_mode:
                raw = self.query_one("#manual-log", TextArea).text
                if raw.strip():
                    self.merge_app.state.raw_log = raw
                    self.merge_app.state.entries = sort_entries_time_desc(parse_svn_log_entries(raw))
                    self.merge_app.state.selected_revisions = []
            if not self.merge_app.state.selected_revisions:
                self.notify("请至少选择一个版本", severity="warning")
                return
            route = self.merge_app.state.route or {}
            state = self.merge_app.state
            state.merge_message = format_merge_message(route, state.entries, state.selected_revisions)
            state.merge_command = build_merge_command(route, state.selected_revisions)
            state.merge_done = False
            state.commit_done = False
            state.merge_no_changes = False
            state.shelve_needed = False
            state.shelve_done = False
            state.shelve_path = ""
            state.restore_done = False
            self.merge_app.push_screen("result")

        def action_focus_filter(self) -> None:
            self.query_one("#svn-filter", Input).focus()

        def action_back(self) -> None:
            self.go_back()


    class ResultScreen(WizardScreen):
        STEP = 4
        TITLE = "合并结果"
        BINDINGS = [
            Binding("enter", "primary", "执行"),
            Binding("c", "copy", "复制日志"),
            Binding("b", "back", "返回"),
            Binding("q", "quit", "退出"),
        ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Vertical(id="shell"):
                yield Static(f"[{self.STEP}/4] {self.TITLE}", id="step-title")
                yield Static(self.step_text(), id="step-bar")
                yield RichLog(id="result-log", wrap=True, highlight=True)
                yield Static("", id="result-keybar", classes="keybar")
            yield Footer()

        def on_mount(self) -> None:
            self.running = False
            state = self.merge_app.state
            route = state.route or {}
            clean, status = working_copy_status(route.get("target_path", ""))
            state.shelve_needed = bool(route.get("sync_branch") and has_versioned_changes(status))
            log = self.query_one("#result-log", RichLog)
            log.write("合并命令：")
            log.write(state.merge_command)
            log.write("")
            log.write("目标工作副本状态：")
            log.write("干净，可直接合并" if clean else (status or "无法确认状态"))
            log.write("")
            log.write("提交/合并日志：")
            log.write(state.merge_message)
            log.write("")
            if state.shelve_needed:
                log.write("检测到当前个人分支存在本地版本化修改。按 Enter 先搁置这些修改，搁置成功后再按 Enter 合并。")
            else:
                log.write("确认无误后按 Enter 执行合并。")
            self.refresh_keybar()

        def refresh_keybar(self) -> None:
            state = self.merge_app.state
            if getattr(self, "running", False):
                text = "正在执行，请等待..."
            elif state.commit_done and state.shelve_done and not state.restore_done:
                text = "Enter 恢复搁置代码   c 复制合并日志   q 退出"
            elif state.commit_done:
                text = "已提交   c 复制合并日志   q 退出"
            elif state.merge_no_changes:
                text = "没有文件被合并   b 返回   q 退出"
            elif state.merge_done:
                text = "Enter 提交合并结果   c 复制合并日志   b 返回   q 退出"
            elif state.shelve_needed and not state.shelve_done:
                text = "Enter 搁置个人分支修改   c 复制合并日志   b 返回   q 退出"
            else:
                text = "Enter 执行合并   c 复制合并日志   b 返回   q 退出"
            self.query_one("#result-keybar", Static).update(text)

        def action_primary(self) -> None:
            if getattr(self, "running", False):
                return
            state = self.merge_app.state
            if state.commit_done and state.shelve_done and not state.restore_done:
                self.restore_changes()
                return
            if state.commit_done or state.merge_no_changes:
                return
            if state.merge_done:
                self.commit_merge()
            elif state.shelve_needed and not state.shelve_done:
                self.shelve_changes()
            else:
                self.merge_code()

        @work(thread=True)
        def shelve_changes(self) -> None:
            self.running = True
            def before() -> None:
                self.refresh_keybar()
                self.query_one("#result-log", RichLog).write("\n开始搁置个人分支本地修改...")
            self.app.call_from_thread(before)
            state = self.merge_app.state
            ok, output, shelf_path = shelve_target_changes(state.route or {})
            def after() -> None:
                self.running = False
                log = self.query_one("#result-log", RichLog)
                log.write(output)
                if ok:
                    state.shelve_done = True
                    state.shelve_needed = False
                    state.shelve_path = shelf_path
                    log.write("\n搁置完成。按 Enter 继续合并 develop 到个人分支。")
                else:
                    log.write("\n搁置失败，请根据输出处理后再重试。")
                    self.notify("搁置失败", severity="error")
                self.refresh_keybar()
            self.app.call_from_thread(after)

        @work(thread=True)
        def merge_code(self) -> None:
            self.running = True
            def before() -> None:
                self.refresh_keybar()
                self.query_one("#result-log", RichLog).write("\n开始执行 svn update...")
            self.app.call_from_thread(before)
            state = self.merge_app.state
            route = state.route or {}
            update_ok, update_output = execute_update(route)
            if update_ok:
                status_before = working_copy_status_text(route.get("target_path", ""))
                ok, merge_output = execute_merge(state.route or {}, state.selected_revisions)
                status_after = working_copy_status_text(route.get("target_path", ""))
                output = "\n".join([
                    update_output,
                    "",
                    "开始执行 svn merge...",
                    merge_output,
                ])
            else:
                status_before = ""
                status_after = ""
                ok = False
                output = "\n".join([
                    update_output,
                    "",
                    "svn update 失败，未执行 svn merge。请处理后再重试。",
                ])
            def after() -> None:
                self.running = False
                log = self.query_one("#result-log", RichLog)
                log.write(output)
                if update_ok and ok:
                    if status_after == status_before:
                        state.merge_no_changes = True
                        state.merge_done = False
                        log.write("\n合并命令执行完成，但没有任何文件进入待提交状态，不需要提交。请按 b 返回。")
                        self.notify("没有文件被合并，不需要提交", severity="warning")
                    else:
                        state.merge_done = True
                        log.write("\n合并完成。检查无误后按 Enter 提交。")
                else:
                    if update_ok:
                        log.write("\n合并失败或存在冲突，请处理后再继续。")
                        self.notify("合并失败或存在冲突", severity="error")
                    else:
                        log.write("\n更新失败，请处理后再按 Enter 重试。")
                        self.notify("更新失败", severity="error")
                self.refresh_keybar()
            self.app.call_from_thread(after)

        @work(thread=True)
        def commit_merge(self) -> None:
            self.running = True
            def before() -> None:
                self.refresh_keybar()
                self.query_one("#result-log", RichLog).write("\n开始执行 svn commit...")
            self.app.call_from_thread(before)
            state = self.merge_app.state
            ok, output = execute_commit(state.route or {}, state.merge_message)
            def after() -> None:
                self.running = False
                log = self.query_one("#result-log", RichLog)
                log.write(output)
                if ok:
                    state.commit_done = True
                    if state.shelve_done and not state.restore_done:
                        log.write("\n提交完成。按 Enter 恢复搁置的个人分支代码。")
                    else:
                        log.write("\n提交完成。")
                else:
                    log.write("\n提交失败，请根据 SVN 输出处理后再按 Enter 重试提交。")
                    self.notify("提交失败", severity="error")
                self.refresh_keybar()
            self.app.call_from_thread(after)

        @work(thread=True)
        def restore_changes(self) -> None:
            self.running = True
            def before() -> None:
                self.refresh_keybar()
                self.query_one("#result-log", RichLog).write("\n开始恢复搁置的个人分支代码...")
            self.app.call_from_thread(before)
            state = self.merge_app.state
            ok, output = restore_shelved_changes(state.route or {}, state.shelve_path)
            def after() -> None:
                self.running = False
                log = self.query_one("#result-log", RichLog)
                log.write(output)
                if ok:
                    state.restore_done = True
                    log.write("\n搁置代码恢复完成。")
                else:
                    log.write("\n恢复搁置代码失败，请根据输出手动处理后重试。")
                    self.notify("恢复搁置代码失败", severity="error")
                self.refresh_keybar()
            self.app.call_from_thread(after)

        def action_copy(self) -> None:
            state = self.merge_app.state
            try:
                subprocess.run(["pbcopy"], input=state.merge_message, text=True, check=True, timeout=5)
                self.notify("合并日志已复制到剪贴板")
            except Exception as exc:
                self.notify(f"复制失败：{exc}", severity="warning")

        def action_back(self) -> None:
            self.go_back()

        def action_quit(self) -> None:
            self.app.exit()


    class SvnMergeApp(App):
        CSS = """
        Header {
            background: #e0f2fe;
            color: #0f172a;
        }

        Footer {
            background: #e2e8f0;
            color: #1f2937;
        }

        Screen {
            background: #f6f8fb;
            color: #1f2937;
        }

        #shell {
            padding: 1 2;
            height: 1fr;
            background: #f6f8fb;
        }

        #step-title {
            text-style: bold;
            color: #0f766e;
            margin-bottom: 1;
            padding: 0 1;
            background: #e0f2f1;
        }

        #step-bar {
            color: #475569;
            margin-bottom: 1;
            padding: 0 1;
            background: #eef6ff;
        }

        .hint {
            color: #475569;
            margin-bottom: 1;
            padding: 0 1;
            background: #ffffff;
            border-left: solid #38bdf8;
        }

        Input, TextArea {
            margin-bottom: 1;
            background: #ffffff;
            color: #111827;
            border: tall #94a3b8;
        }

        DataTable {
            height: 1fr;
            margin-bottom: 1;
            background: #ffffff;
            color: #1f2937;
            border: solid #cbd5e1;
        }

        DataTable > .datatable--header {
            background: #dbeafe;
            color: #1e3a8a;
            text-style: bold;
        }

        DataTable > .datatable--cursor {
            background: #ccfbf1;
            color: #0f172a;
        }

        #svn-filter, #project-search {
            margin-bottom: 1;
        }

        #svn-status {
            padding: 0 1;
            background: #ecfeff;
            color: #155e75;
            border-left: solid #06b6d4;
            margin-bottom: 1;
        }

        #manual-log {
            height: 1fr;
            margin-bottom: 1;
        }

        #result-log {
            height: 1fr;
            background: #ffffff;
            color: #1f2937;
            border: solid #0f766e;
            padding: 1;
        }

        .keybar {
            height: auto;
            dock: bottom;
            padding: 0 1;
            background: #1f2937;
            color: #f8fafc;
            text-style: bold;
        }
        """
        BINDINGS = [Binding("ctrl+c", "quit", "退出")]

        def __init__(self) -> None:
            super().__init__()
            self.state = MergeState(projects=scan_projects())

        def on_mount(self) -> None:
            self.install_screen(ProjectScreen(), "project")
            self.install_screen(RouteScreen(), "route")
            self.install_screen(RevisionScreen(), "svn")
            self.install_screen(ResultScreen(), "result")
            self.push_screen("project")


def choose_from_list(title: str, rows: list[tuple[str, object]]) -> object | None:
    print(f"\n{title}")
    for index, (label, _) in enumerate(rows, 1):
        print(f"{index}. {label}")
    while True:
        choice = input("请输入编号（q 退出）：").strip()
        if choice.lower() == "q":
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(rows):
            return rows[int(choice) - 1][1]
        print("输入无效，请重新输入。")


def fallback_cli() -> int:
    projects = scan_projects()
    if not projects:
        print(f"未在 {WORK_BASE} 下找到可用项目")
        return 1
    auto = auto_match_project(projects)
    if auto:
        projects = [auto] + [project for project in projects if project["path"] != auto["path"]]
    project = choose_from_list("选择项目", [(f"{p['name']}  {p['path']}", p) for p in projects])
    if not project:
        return 0
    if not project["routes"]:
        print("该项目没有检测到可合并分支")
        return 1
    route = choose_from_list("选择合并方向", [(f"{r['name']}  ->  {r['target_path']}", r) for r in project["routes"]])
    if not route:
        return 0
    raw, err = fetch_svn_log(route["source_path"])
    if err:
        print(f"自动拉取 SVN 日志失败：{err}")
        print("请粘贴 svn log 输出，结束后输入单独一行 END：")
        lines = []
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
        raw = "\n".join(lines)
    entries = parse_svn_log_entries(raw or "")
    if not entries:
        print("未解析到 SVN 日志")
        return 1
    for entry in entries:
        print(f"r{entry['revision']} | {entry['author']} | {entry['message'].splitlines()[0]}")
    rev_text = input("请输入要合并的版本号，多个用逗号分隔，连续版本可写 136681-136682：").strip()
    revisions = []
    for part in re.split(r"[,，\s]+", rev_text):
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            revisions.extend(range(int(start), int(end) + 1))
        else:
            revisions.append(int(part))
    print("\n合并命令：")
    print(build_merge_command(route, revisions))
    print("\n提交/合并日志：")
    print(format_merge_message(route, entries, revisions))
    return 0


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print("用法：python3 ~/.hermes/skills/devops/svn-merge-code/scripts/svn_merge.py")
        print("功能：选择项目、合并方向和 SVN 版本，生成 svn merge 命令和公司格式合并日志。")
        return 0
    if TEXTUAL_AVAILABLE and sys.stdin.isatty():
        SvnMergeApp().run()
        return 0
    if not sys.stdin.isatty():
        print("当前不是交互式终端。请在终端中直接运行脚本进入 TUI/CLI 交互界面。")
        return 1
    return fallback_cli()


if __name__ == "__main__":
    raise SystemExit(main())

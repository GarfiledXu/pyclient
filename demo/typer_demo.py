import sys
import click
import typer
import pytest
from pathlib import Path
from typing import Annotated, Optional
from rich.tree import Tree
from rich import print as rprint
from typer.main import get_command
from util.logger import log, LogManager

# ==========================================
# 1. 全局配置
# ==========================================
GLOBAL_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

app = typer.Typer(
    rich_markup_mode="rich",
    add_completion=False,
    no_args_is_help=True,
    context_settings=GLOBAL_CONTEXT_SETTINGS,
    help="NVS 综合调试客户端"
)

task_app = typer.Typer(
    rich_markup_mode="rich",
    add_completion=False,
    no_args_is_help=True,
    help="执行一次性组合任务 (导入/导出/同步)"
)
app.add_typer(task_app, name="task", context_settings=GLOBAL_CONTEXT_SETTINGS)

# ==========================================
# 2. 全局拦截器与回调
# ==========================================


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="开启详细日志输出")
    ] = False
):
    """NVS 系统入口"""
    if verbose:
        from util.logger import LogConfig
        LogConfig.format_base["show_details"] = True
        LogManager.setup()

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@task_app.callback(invoke_without_command=True)
def task_callback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

# ==========================================
# 3. CLI 命令定义
# ==========================================


@app.command(name="gui")
def gui():
    """启动图形化调试界面"""
    log.bind(module="GUI").info("正在初始化图形界面...")
    print("GUI 运行中...")


@app.command(name="test")
def test(
    ctx: typer.Context,
    test_path: Annotated[
        Optional[Path],
        typer.Argument(metavar="<TEST_PATH>", help="测试脚本目录或文件路径")
    ] = None,
    mark: Annotated[
        Optional[str],
        typer.Option("--mark", "-m", help="按标签筛选测试用例")
    ] = None,
    html_report: Annotated[
        bool,
        typer.Option("--html", help="生成 HTML 测试报告")
    ] = False
):
    """启动基于 Pytest 的自动化测试脚手架"""
    if test_path is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    log.bind(module="TEST").info(f"开始执行自动化测试: {test_path}")

    args = [str(test_path)]
    if mark:
        args.extend(["-m", mark])
    if html_report:
        args.extend(["--html", "report.html"])

    ret = pytest.main(args)
    sys.exit(ret)


@task_app.command(name="sync")
def task_sync(
    ctx: typer.Context,
    direction: Annotated[
        Optional[str],
        typer.Argument(metavar="<pc2mcu|mcu2pc>", help="文件同步方向")
    ] = None
):
    """执行 PC 与 MCU 之间的文件同步任务"""
    if direction is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    log.bind(module="TASK").info(f"启动文件同步任务: {direction}")
    print(f"同步任务 {direction} 完成。")


@app.command(name="shell")
def shell():
    """进入持续交互模式，支持实时发送指令"""
    log.bind(module="SHELL").info("进入交互式模式。输入 'exit' 或 'quit' 退出。")
    while True:
        try:
            command = input("NVS-Shell > ").strip()
            if not command:
                continue
            if command.lower() in ["exit", "quit"]:
                break
            log.bind(module="NET").info(f"执行指令: {command}")
        except KeyboardInterrupt:
            break
    log.info("退出交互模式。")


@app.command(name="tree", help="显示所有命令与参数的树形全景图")
def print_command_tree():
    """全局命令拓扑树"""
    click_root = get_command(app)

    def build_tree(command: click.Command, tree_node: Tree):
        for param in command.params:
            if param.name == "help":
                continue

            if isinstance(param, click.Argument):
                display_name = getattr(
                    param, "metavar", None) or f"<{param.name.upper()}>"
                tree_node.add(
                    f"📦 [yellow]{display_name}[/yellow] [dim]位置参数[/dim]")
            elif isinstance(param, click.Option):
                opts = ", ".join(param.opts)
                help_str = f" - {param.help}" if param.help else ""
                tree_node.add(f"⚙️ [green]{opts}[/green][dim]{help_str}[/dim]")

        if isinstance(command, click.Group):
            for name, sub_cmd in command.commands.items():
                help_text = (
                    sub_cmd.short_help or sub_cmd.help or "").split("\n")[0]
                sub_node = tree_node.add(
                    f"[bold cyan]>{name}[/bold cyan] [dim]{help_text}[/dim]")
                build_tree(sub_cmd, sub_node)

    root_tree = Tree("📁 [bold red]NVS CLI 根节点[/bold red]")
    build_tree(click_root, root_tree)
    rprint(root_tree)


if __name__ == "__main__":
    app()

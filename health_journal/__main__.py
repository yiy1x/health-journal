import argparse
import contextlib
import os
from pathlib import Path
import sys

from .demo import seed_demo
from .server import create_server
from .validation import AppError
from .vault_lock import vault_lock


def default_directory():
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "HealthJournal"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "HealthJournal"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "health-journal"


def main():
    parser = argparse.ArgumentParser(description="知己 · 健康手记：只在本机运行的个人健康档案")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--demo", action="store_true", help="创建独立合成演示档案，不能用于已有真实档案")
    parser.add_argument("--codex-bin", type=Path, help="可选：官方 Codex 可执行文件的绝对路径；不读取原有 Codex 登录目录")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("端口必须介于 1024 和 65535")
    if args.codex_bin and (not args.codex_bin.is_absolute() or not args.codex_bin.is_file()):
        parser.error("--codex-bin 必须指向存在的官方 Codex 可执行文件绝对路径")
    directory = args.data_dir or (default_directory().with_name("HealthJournalDemo") if args.demo else default_directory())
    os.umask(0o077)
    resources = contextlib.ExitStack()
    try:
        resources.enter_context(vault_lock(directory))
        server = create_server(directory, args.port, args.codex_bin)
        resources.callback(server.server_close)
        if args.demo:
            seed_demo(server.store)
    except (OSError, AppError) as error:
        resources.close()
        parser.exit(1, "无法启动：" + str(error) + "\n")
    print("知己 · 健康手记" + (" [合成演示]" if server.store.setting("demo") else ""), flush=True)
    print("打开 http://127.0.0.1:" + str(args.port), flush=True)
    print("资料目录：" + str(server.store.directory), flush=True)
    print("只监听本机；模型可选 API Key 或独立 ChatGPT/Codex 登录，每次分析均须确认，默认不外发。按 Ctrl+C 停止。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止，资料保留在本地。")
    finally:
        resources.close()


if __name__ == "__main__":
    main()

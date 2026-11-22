import argparse
import json
from pathlib import Path
import shutil

from .departments import CATALOG


ASSETS = ("index.html", "phone.css", "phone.js", "core.js", "db.js", "sw.js", "manifest.webmanifest", "icon.svg", "_headers", "LICENSE.txt")


def export_phone(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).parent / "web" / "phone"
    for filename in ASSETS:
        shutil.copyfile(source / filename, destination / filename)
    (destination / "catalog.json").write_text(json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8")
    return destination


def main():
    parser = argparse.ArgumentParser(description="导出不含健康资料的手机静态应用；仅部署到自己信任的 HTTPS 来源")
    parser.add_argument("--output", type=Path, required=True, help="必须是不存在的新目录，避免误覆盖")
    args = parser.parse_args()
    try:
        destination = export_phone(args.output)
    except OSError as error:
        parser.exit(1, "无法导出：" + str(error) + "\n")
    print("已导出纯静态手机应用：" + str(destination.resolve()))
    print("没有复制数据库、密钥或个人资料。请阅读 docs/MOBILE.md 后部署；不是自动同步服务器。")


if __name__ == "__main__":
    main()

"""启动脚本:python run.py

启动本地网页服务,浏览器打开 http://127.0.0.1:9900
"""
import sys

import uvicorn


def main() -> None:
    host = "127.0.0.1"
    port = 9900
    print("=" * 56)
    print("  TableAssembly 已启动")
    print(f"  打开浏览器访问: http://{host}:{port}")
    print("  按 Ctrl+C 停止")
    print("=" * 56)
    try:
        uvicorn.run("app.main:app", host=host, port=port, log_level="warning")
    except KeyboardInterrupt:
        print("\n已停止")
        sys.exit(0)


if __name__ == "__main__":
    main()

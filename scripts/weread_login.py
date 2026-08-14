#!/usr/bin/env python3
"""weread_login.py — 微信读书扫码登录，获取 WEREAD_TOKEN（一次性本地工具）。

用法:
    python3 scripts/weread_login.py [--platform https://weread.111965.xyz]

流程:
    1. 请求中转服务登录接口，拿到扫码地址 scanUrl
    2. 用【备用微信号】在浏览器打开 scanUrl 并扫码确认（不要用主号）
    3. 轮询登录结果，成功后打印 token 与 vid
    4. 将 token 配置为 GitHub 仓库 Secret：WEREAD_TOKEN

注意:
    - token 等同账号凭证，只进 GitHub Secret，不要提交到仓库或发给他人
    - 本脚本不写入任何仓库文件
    - 登录接口走 wewe-rss 开源项目作者的中转服务（weread.111965.xyz）

纯标准库实现，Windows / Linux / macOS 均可运行。
"""
import argparse
import json
import sys
import time
import urllib.request

PLATFORM_URL = "https://weread.111965.xyz"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def http_json(url: str, method: str = "GET", body: dict | None = None, timeout: int = 130) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "User-Agent": UA,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="微信读书扫码登录，获取 WEREAD_TOKEN")
    parser.add_argument("--platform", default=PLATFORM_URL, help="中转服务基地址")
    parser.add_argument("--timeout", type=int, default=300, help="等待扫码超时秒数（默认 300）")
    args = parser.parse_args()
    base = args.platform.rstrip("/")

    print("1) 请求登录二维码……")
    try:
        login = http_json(f"{base}/api/v2/login/platform")
    except Exception as exc:  # noqa: BLE001
        print(f"登录接口请求失败: {exc}", file=sys.stderr)
        return 1
    uuid, scan_url = login.get("uuid"), login.get("scanUrl")
    if not uuid or not scan_url:
        print(f"登录接口返回异常: {login}", file=sys.stderr)
        return 1

    print("\n2) 请用【备用微信】扫码（在浏览器打开下面地址，出现二维码后用微信扫）：")
    print(f"\n   {scan_url}\n")
    print(f"3) 等待扫码确认（最长 {args.timeout} 秒）……")

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        try:
            result = http_json(f"{base}/api/v2/login/platform/{uuid}")
        except Exception:  # noqa: BLE001 - 未完成时接口可能报错，继续轮询
            time.sleep(3)
            continue
        token = result.get("token")
        if token:
            print("\n登录成功！")
            print(f"  用户名: {result.get('username') or '(未知)'}")
            print(f"  vid:   {result.get('vid') or '(未知)'}")
            print(f"\n  WEREAD_TOKEN = {token}\n")
            print("下一步：GitHub 仓库 → Settings → Secrets and variables → Actions →")
            print("New repository secret，Name 填 WEREAD_TOKEN，Value 粘贴上面这串 token。")
            return 0
        time.sleep(3)

    print("等待扫码超时，请重新运行本脚本。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

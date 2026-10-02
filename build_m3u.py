#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日自动抓取多条直播源 -> 合并去重 -> 输出两个文件：
  live.m3u      (UTF-8，TVBox / 通用播放器)
  live_gbk.txt  (GBK 编码，电视家 防中文乱码)
由 GitHub Actions 每日自动运行（见 .github/workflows/update.yml）。
"""
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 直播源清单（GitHub Actions 在境外，可直接访问 raw 地址，无需加速前缀）
SOURCES = [
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/itv.m3u",
    "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
    "https://live.zhoujie218.top/tv/iptv4.m3u",
    "https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u",
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",
    "https://iptv-org.github.io/iptv/countries/cn.m3u",
    "https://iptv-org.github.io/iptv/countries/hk.m3u",
    "https://iptv-org.github.io/iptv/countries/mo.m3u",
    "https://iptv-org.github.io/iptv/countries/tw.m3u",
    "https://iptv-org.github.io/iptv/languages/zho.m3u",
    "https://iptv-org.github.io/iptv/countries/sg.m3u",
    "https://iptv-org.github.io/iptv/countries/my.m3u",
    "https://raw.githubusercontent.com/YueChan/Live/main/Global.m3u",
]

BAD = re.compile(r"^(rtp|udp|igmp|rtsp)://", re.I)
PRIV = re.compile(r"://(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|0\.0\.0\.0|localhost|\[::1\])", re.I)


def fetch(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            print(f"  [retry {i + 1}] {url}: {e}")
    return ""


def clean_name(n):
    n = re.sub(r"「.*?」", "", n)
    n = re.sub(r"\s+", "", n)
    return n.strip()


def parse(text):
    out = []
    ext = None
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith("#EXTINF"):
            m = re.search(r'tvg-name="([^"]*)"', ln)
            disp = ln.split(",", 1)[-1].strip()
            name = m.group(1) if (m and m.group(1)) else disp
            g = re.search(r'group-title="([^"]*)"', ln)
            grp = g.group(1) if g else "其他"
            if "更新时间" in grp or "更新时间" in name:
                ext = None
                continue
            ext = (clean_name(name), grp)
        elif ln.startswith("#"):
            continue
        else:
            if ext:
                if not BAD.match(ln) and not PRIV.search(ln):
                    out.append((ext[0], ext[1], ln))
                ext = None
    return out


MAX_LINES = 6  # 每个频道最多保留的备用线路数（多线路=播放器可自动切换，容错更高）


def main():
    chans = {}
    for u in SOURCES:
        print("下载:", u)
        for name, grp, url in parse(fetch(u)):
            if not name:
                continue
            key = name.lower()
            if key not in chans:
                chans[key] = {"name": name, "grp": grp, "urls": []}
            e = chans[key]
            if url not in e["urls"] and len(e["urls"]) < MAX_LINES:
                e["urls"].append(url)
    items = []
    for e in chans.values():
        for url in e["urls"]:
            items.append((e["name"], e["grp"], url))
    print("频道数:", len(chans), "总线路数(含备用):", len(items))

    with open("live.m3u", "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for name, grp, url in items:
            f.write(f'#EXTINF:-1 tvg-name="{name}" group-title="{grp}",{name}\n{url}\n')

    with open("live_gbk.txt", "w", encoding="gbk", errors="ignore") as f:
        cur = None
        for name, grp, url in items:
            if grp != cur:
                f.write(f"\n{grp},#genre#\n")
                cur = grp
            f.write(f"{name},{url}\n")

    # GBK 编码的 m3u（供只认 m3u 又会乱码的电视家版本）
    with open("live_gbk.m3u", "w", encoding="gbk", errors="ignore") as f:
        f.write("#EXTM3U\n")
        for name, grp, url in items:
            f.write(f'#EXTINF:-1 tvg-name="{name}" group-title="{grp}",{name}\n{url}\n')

    print("已生成 live.m3u / live_gbk.txt / live_gbk.m3u")


if __name__ == "__main__":
    main()

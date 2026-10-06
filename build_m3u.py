#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日自动抓取多条直播源 -> 合并（每频道保留多线路）-> 输出：
  live.m3u      (UTF-8，含 EPG，TVBox / 通用播放器)
  live_gbk.txt  (GBK 编码，电视家)
  live_gbk.m3u  (GBK 编码 m3u)
  epg.xml       (节目单，供播放器使用)
由 GitHub Actions 每日自动运行（见 .github/workflows/update.yml）。
"""
import re
import gzip
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 你自己的仓库地址（EPG 存到自己仓库，再经 gh-proxy 访问）
REPO_RAW = "https://gh-proxy.com/https://raw.githubusercontent.com/hdtvfans/live-tv/main"
EPG_URL = REPO_RAW + "/epg.xml"

# 直播源清单（Actions 在境外，可直接访问 raw 地址）
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

# EPG 源（按顺序尝试，Actions 在境外，能访问这些站点）
EPG_SOURCES = [
    "https://epg.pw/xmltv/epg_CN.xml",
    "http://epg.51zmt.top:8000/e.xml",
    "https://live.fanmingming.com/e.xml",
    "https://gitee.com/taksssss/tv/raw/main/epg/112114.xml.gz",
]

BAD = re.compile(r"^(rtp|udp|igmp|rtsp)://", re.I)
PRIV = re.compile(r"://(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|0\.0\.0\.0|localhost|\[::1\])", re.I)

MAX_LINES = 6  # 每个频道最多保留的备用线路数


def fetch(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            print(f"  [retry {i + 1}] {url}: {e}")
    return ""


def fetch_bytes(url):
    for i in range(2):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:
            print(f"  [epg retry {i + 1}] {url}: {e}")
    return None


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


def build_epg():
    """抓取 EPG 并保存为 epg.xml（存自己仓库，供 gh-proxy 访问）"""
    for u in EPG_SOURCES:
        print("EPG 源:", u)
        data = fetch_bytes(u)
        if not data:
            continue
        if data[:2] == b"\x1f\x8b":
            try:
                data = gzip.decompress(data)
            except Exception as e:
                print("  gz 解压失败:", e)
                continue
        head = data[:8000]
        if b"<tv" not in head:
            print("  非 XMLTV，跳过")
            continue
        with open("epg.xml", "wb") as f:
            f.write(data)
        print("  EPG 已保存，大小:", len(data))
        return
    print("EPG 抓取失败，保留旧的 epg.xml（若有）")


def main():
    build_epg()

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
        f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
        for name, grp, url in items:
            f.write(f'#EXTINF:-1 tvg-name="{name}" group-title="{grp}",{name}\n{url}\n')

    with open("live_gbk.txt", "w", encoding="gbk", errors="ignore") as f:
        cur = None
        for name, grp, url in items:
            if grp != cur:
                f.write(f"\n{grp},#genre#\n")
                cur = grp
            f.write(f"{name},{url}\n")

    with open("live_gbk.m3u", "w", encoding="gbk", errors="ignore") as f:
        f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
        for name, grp, url in items:
            f.write(f'#EXTINF:-1 tvg-name="{name}" group-title="{grp}",{name}\n{url}\n')

    print("已生成 live.m3u / live_gbk.txt / live_gbk.m3u / epg.xml")


if __name__ == "__main__":
    main()

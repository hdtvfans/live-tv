#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日自动抓取多条直播源 -> 合并（每频道保留多线路）-> 输出：
  live.m3u        (UTF-8，含 EPG，TVBox / 通用播放器)
  live_gbk.txt    (GBK 编码，电视家)
  live_gbk.m3u    (GBK 编码 m3u)
  epg.xml.gz      (节目单，压缩，供播放器使用)
  last_update.txt (运行状态，便于查看是否每天正常运行)
由 GitHub Actions 每日自动运行（见 .github/workflows/update.yml）。
"""
import re
import gzip
import hashlib
import datetime
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 你自己的仓库地址（EPG 存到自己仓库，再经 gh-proxy 访问）
REPO_RAW = "https://gh-proxy.com/https://raw.githubusercontent.com/hdtvfans/live-tv/main"
EPG_URL = REPO_RAW + "/epg.xml.gz"

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

# EPG 源：优先 GitHub 同域（Actions 必通），再退到公网
EPG_SOURCES = [
    "https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/e.xml.gz",
    "https://raw.githubusercontent.com/plsy1/epg/main/e/seven-days.xml",
    "https://epg.pw/xmltv/epg_CN.xml",
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
    """抓取 EPG 并保存为 epg.xml.gz，返回状态描述字符串"""
    for u in EPG_SOURCES:
        print("EPG 源:", u)
        data = fetch_bytes(u)
        if not data:
            continue
        if data[:2] == b"\x1f\x8b":
            try:
                xml = gzip.decompress(data)
            except Exception as e:
                print("  gz 解压失败:", e)
                continue
            gzdata = data
        else:
            xml = data
            gzdata = gzip.compress(data, 6)
        if b"<tv" not in xml[:8000]:
            print("  非 XMLTV，跳过")
            continue
        with open("epg.xml.gz", "wb") as f:
            f.write(gzdata)
        print("  EPG 已保存 epg.xml.gz，压缩体积:", len(gzdata))
        return f"成功（来源: {u}，压缩体积 {len(gzdata)} 字节）"
    print("EPG 抓取失败，保留旧的 epg.xml.gz（若有）")
    return "失败（所有源均不可用，保留旧文件）"


def main():
    epg_status = build_epg()

    chans = {}
    ok_src = 0
    for u in SOURCES:
        print("下载:", u)
        text = fetch(u)
        parsed = parse(text)
        if parsed:
            ok_src += 1
        for name, grp, url in parsed:
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

    # 运行状态文件（内容含时间戳，每天必变 -> 必定产生提交，方便观察）
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def fingerprint(fn):
        try:
            data = open(fn, "rb").read()
            return f"{len(data)} 字节, 指纹 {hashlib.md5(data).hexdigest()[:10]}"
        except FileNotFoundError:
            return "未生成"

    with open("last_update.txt", "w", encoding="utf-8") as f:
        f.write(f"最后更新时间: {now}\n")
        f.write(f"直播源抓取: 成功 {ok_src} / 共 {len(SOURCES)} 个\n")
        f.write(f"合并后频道数: {len(chans)}\n")
        f.write(f"总线路数(含备用): {len(items)}\n")
        f.write(f"EPG 抓取: {epg_status}\n")
        f.write("\n【文件指纹】（两次对比即可知内容是否变化）\n")
        f.write(f"live.m3u: {fingerprint('live.m3u')}\n")
        f.write(f"live_gbk.txt: {fingerprint('live_gbk.txt')}\n")
        f.write(f"live_gbk.m3u: {fingerprint('live_gbk.m3u')}\n")

    print("已生成 live.m3u / live_gbk.txt / live_gbk.m3u / epg.xml.gz / last_update.txt")


if __name__ == "__main__":
    main()

# build_live.py
# 源级别节点剪枝生成器：下载公共免费节点源 -> 解析 -> 剔除中国大陆(含广东,保留港澳臺)
# -> 并发 TCP 实测只留活节点 -> 生成精简静态 config.yaml / sub.yaml
# 用法: python build_live.py
import os, re, sys, json, base64, socket, time, subprocess, tempfile, shutil
import urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, "config.yaml")
SUB = os.path.join(BASE, "sub.yaml")
CACHE = os.path.join(BASE, "nodes_cache.json")
PORT_FILE = os.path.join(BASE, "proxy_port.txt")

# 最终配置最多保留的活节点数（按延迟从低到高截取，避免节点过多拖慢测速与选择）
# 源大幅扩充后，高峰段 TCP 实测仍能留下更多活节点，可用概率更大
MAX_LIVE = 100

# ---------------- 节点源（ghproxy 多镜像冗余，国内直连）----------------
# 镜像前缀：任一可达即可拉到节点；多镜像冗余显著提升高峰段 ghproxy 拥堵时的拉取成功率
MIRRORS = [
    "https://ghproxy.net/https://raw.githubusercontent.com/",
    "https://mirror.ghproxy.com/https://raw.githubusercontent.com/",
    "https://ghproxy.cn/https://raw.githubusercontent.com/",
]
# 每个源给出 raw.githubusercontent.com 的相对路径；实际 URL = 各镜像前缀 + 相对路径
SOURCES = [
    # --- 原始 4 个公共源（已验证长期可用）---
    ("nowalls", [
        "peasoft/NoMoreWalls/master/list.txt",
    ]),
    ("ermaozi", [
        "ermaozi/get_subscribe/main/subscribe/clash.yml",
    ]),
    ("ssagg", [
        "mahdibland/ShadowsocksAggregator/master/Eternity.yml",
    ]),
    ("freefq", [
        "freefq/free/master/v2",
    ]),
    # --- lyqnihao 聚合追踪仓库（多上游站点，clash yaml 直解；xConfig 为 base64 链接文本）---
    ("lyq_oneclash", [
        "lyqnihao/proxy/main/oneclash/output.yaml",
    ]),
    ("lyq_clashfree", [
        "lyqnihao/proxy/main/clashfree/output.yaml",
    ]),
    ("lyq_nodev2ray", [
        "lyqnihao/proxy/main/nodev2ray/output.yaml",
    ]),
    ("lyq_clashmeta", [
        "lyqnihao/proxy/main/clash-meta/output.yaml",
    ]),
    ("lyq_proxyqueen", [
        "lyqnihao/proxy/main/proxyqueen/output.yaml",
    ]),
    ("lyq_xconfig", [
        "lyqnihao/proxy/main/xConfig/output.yaml",
    ]),
    # --- 新增独立上游（均已 WebFetch 验证为有效 clash/mihomo yaml，节点量大）---
    ("awesomevpn", [
        "awesome-vpn/awesome-vpn/master/clash.yaml",
    ]),
    ("f0rc3run", [
        "F0rc3Run/F0rc3Run/refs/heads/main/Best-Results/clash.yaml",
    ]),
    ("automerge", [
        "chengaopan/AutoMergePublicNodes/master/list.yml",
    ]),
    ("proxypool", [
        "snakem982/proxypool/main/source/clash-meta-2.yaml",
    ]),
    ("freeproxies", [
        "mfuu/FreeProxies/master/sub.yaml",
    ]),
    ("freesubscheck", [
        "kooker/FreeSubsCheck/main/mihomo.yaml",
    ]),
    # --- 本轮新增（均经 WebFetch 验证路径有效）---
    ("vxiaov", [
        "vxiaov/free_proxies/main/clash/clash.provider.yaml",
    ]),
    ("freenodes_v2rayfree", [
        "free-nodes/v2rayfree/main/sub",
    ]),
]

# ---------------- 大陆地区过滤（保留香港/澳门/台湾）----------------
HK_MT = re.compile(r"(?i)(香港|澳[門门]|臺灣|台湾|台北|高雄|台中|台南|桃園|桃园|新竹|基隆|花蓮|花莲|臺東|台东|屏東|屏东|澎湖|宜蘭|宜兰|馬祖|马祖|金門|金门|嘉義|嘉义|HK|Macau|Taiwan|Hong ?Kong)")
MAINLAND = re.compile(
    r"(?i)(🇨🇳|中国|大陸|大陆|内地|北京|上海|廣東|广东|廣州|广州|深圳|浙江|江蘇|江苏|天津|重慶|重庆|"
    r"四川|湖北|湖南|河南|河北|山東|山东|山西|陝西|陕西|福建|江西|安徽|遼寧|辽宁|吉林|黑龍江|黑龙江|"
    r"雲南|云南|貴州|贵州|甘肅|甘肃|青海|海南|內蒙古|内蒙古|廣西|广西|西藏|寧夏|宁夏|新疆|鄭州|郑州|"
    r"成都|杭州|南京|武漢|武汉|西安|瀋陽|沈阳|大連|大连|青島|青岛|濟南|济南|廈門|厦门|福州|昆明|蘭州|兰州|"
    r"拉薩|拉萨|銀川|银川|西寧|西宁|烏魯木齊|乌鲁木齐|呼和浩特|南寧|南宁|桂林|哈爾濱|哈尔滨|長春|长春|"
    r"石家莊|石家庄|太原|長沙|长沙|南昌|合肥|寧波|宁波|無錫|无锡|蘇州|苏州|常州|東莞|东莞|佛山|珠海|中山|"
    r"惠州|汕頭|汕头|湛江|江門|江门|肇慶|肇庆|茂名|清遠|清远|韶關|韶关|潮州|揭陽|揭阳|梅州|河源|陽江|阳江|"
    r"雲浮|云浮|汕尾|溫州|温州|嘉興|嘉兴|紹興|绍兴|金華|金华|泉州|溫州)"
)
# 注意：广东已明确排除；港澳臺通过 HK_MT 保留检查优先。

def is_mainland(name):
    if not name:
        return False
    if HK_MT.search(name):
        return False  # 港澳臺保留
    return bool(MAINLAND.search(name))

# ---------------- 法国节点不再剔除（用户要求保留法国节点）----------------

# ---------------- base64 解码 ----------------
def b64safe(s):
    s = s.strip()
    try:
        return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")
    except Exception:
        try:
            return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")
        except Exception:
            return ""

# ---------------- 链接解析 ----------------
def parse_vmess(link):
    try:
        body = link[len("vmess://"):]
        j = json.loads(b64safe(body))
        name = j.get("ps") or j.get("remark") or "vmess"
        node = {"name": name, "type": "vmess", "server": j.get("add"), "port": int(j.get("port", 0)),
                "uuid": j.get("id"), "alterId": int(j.get("aid", 0)), "cipher": j.get("scy") or "auto",
                "network": j.get("net") or "tcp"}
        tls = str(j.get("tls", "")).lower()
        if tls in ("tls", "reality", "xtls"):
            node["tls"] = True
            node["skip-cert-verify"] = True
        sni = j.get("sni") or j.get("host") or j.get("peer")
        if sni:
            node["servername"] = sni
        net = j.get("net") or "tcp"
        if net == "ws":
            node["ws-opts"] = {"path": j.get("path") or "/",
                               "headers": {"Host": j.get("host") or j.get("sni") or j.get("add")}}
        elif net == "grpc":
            node["grpc-opts"] = {"grpc-service-name": j.get("path") or ""}
        return node
    except Exception:
        return None

def parse_ss(link):
    try:
        body = link[len("ss://"):]
        if "@" in body:
            bpart, addr = body.rsplit("@", 1)
            mp = b64safe(bpart)
            if ":" in mp:
                method, pwd = mp.split(":", 1)
            else:
                method, pwd = "aes-256-gcm", mp
        else:
            dec = b64safe(body)
            if "@" in dec:
                mp, addr = dec.rsplit("@", 1)
                method, pwd = mp.split(":", 1)
            else:
                return None
        addr = addr.split("#")[0].split("?")[0]
        host, port = (addr.rsplit(":", 1) if ":" in addr else (addr, "8388"))
        name = urllib.parse.unquote(addr.split("#")[-1]) if "#" in addr else ("ss-" + host)
        if "@" not in body and "#" in body:
            name = urllib.parse.unquote(body.split("#", 1)[1])
        return {"name": name or ("ss-" + host), "type": "ss", "server": host,
                "port": int(port), "cipher": method, "password": pwd}
    except Exception:
        return None

def parse_trojan(link):
    try:
        body = link[len("trojan://"):]
        m = re.match(r"([^@]+)@([^:]+):(\d+)", body)
        if not m:
            return None
        pwd, host, port = m.group(1), m.group(2), m.group(3)
        name = "trojan-" + host
        frag = re.sub(r"[?].*$", "", body.split("#")[-1]) if "#" in body else ""
        if frag:
            name = urllib.parse.unquote(frag)
        node = {"name": name, "type": "trojan", "server": host, "port": int(port),
                "password": pwd, "skip-cert-verify": True}
        q = re.search(r"[?&]sni=([^&]+)", body)
        if q:
            node["sni"] = q.group(1)
        return node
    except Exception:
        return None

def parse_ssr(link):
    # SSR 节点占比极小且配置复杂易出错, 直接跳过（vmess/ss/trojan/vless 已足够）
    return None

def parse_link(line):
    line = line.strip()
    if line.startswith("vmess://"):
        return parse_vmess(line)
    if line.startswith("ss://"):
        return parse_ss(line)
    if line.startswith("trojan://"):
        return parse_trojan(line)
    if line.startswith("ssr://"):
        return parse_ssr(line)
    return None

# ---------------- 源解析 ----------------
def parse_source(text):
    nodes = []
    # 1) 直接 yaml
    try:
        import yaml
        d = yaml.safe_load(text)
        if isinstance(d, dict) and isinstance(d.get("proxies"), list):
            return [n for n in d["proxies"] if isinstance(n, dict)]
    except Exception:
        pass
    # 2) base64 -> yaml
    try:
        import yaml
        s = b64safe(text.strip())
        if s:
            d = yaml.safe_load(s)
            if isinstance(d, dict) and isinstance(d.get("proxies"), list):
                return [n for n in d["proxies"] if isinstance(n, dict)]
    except Exception:
        pass
    # 3) 链接文本 / base64链接文本
    try:
        s = text
        if "vmess://" not in s and "ss://" not in s and "trojan://" not in s and "ssr://" not in s:
            s = b64safe(text.strip())
        for line in s.splitlines():
            line = line.strip()
            if line.startswith(("vmess://", "ss://", "ssr://", "trojan://")):
                n = parse_link(line)
                if n:
                    nodes.append(n)
    except Exception:
        pass
    return nodes

# 国内直连域名列表（零依赖，不依赖外部 geo 库下载；覆盖主流国内站点，子域由 DOMAIN-SUFFIX 自动包含）
CN_DOMAINS = """
baidu.com baiducontent.com baiduimg.com baidustatic.com baidupcs.com pan.baidu.com map.baidu.com baidumap.com tieba.baidu.com
qq.com qzone.qq.com weixin.qq.com wx.qq.com wxapp.tc.qq.com weishi.com v.qq.com maps.qq.com mail.qq.com exmail.qq.com
tencent.com tencent.com.cn qcloud.com cloud.tencent.com tencentcloud.com sj.qq.com myapp.com app.qq.com
sina.com sina.com.cn sinaimg.cn sinajs.cn weibo.com weibo.cn weiboimg.com weibocdn.com
sohu.com sohucs.com sohucdn.com
163.com 126.com 126.net netease.com music.163.com youdao.com iciba.com foxmail.com yeah.net
360.com 360.cn 360safe.com 360kuai.com hao123.com 2345.com 114la.com
taobao.com tmall.com alibaba.com alibaba.com.cn aliyun.com aliyuncs.com alipay.com alipayobjects.com
1688.com cainiao.com wanwang.aliyun.com dnspod.cn dnspod.com hichina.com
jd.com jd.hk suning.com suning.cn pinduoduo.com vip.com dangdang.com amazon.cn smzdm.com
zhihu.com zhimg.com douban.com doubanio.com
bilibili.com bilibili.tv acfun.cn acfun.com acfun.tv
kuaishou.com ks-cdn.com douyin.com iesdouyin.com toutiao.com toutiaocdn.com pstatp.com ixigua.com inews.gtimg.com xiaohongshu.com xhscdn.com hupu.com
huya.com douyu.com yy.com
iqiyi.com iqiyipic.com qiyipic.com youku.com tudou.com le.com mgtv.com
kugou.com kuwo.cn taihe.com fogu.com
mi.com huawei.com vivo.com.cn oppo.com oneplus.com meizu.com
10086.cn 10010.com 189.cn cmcc.com chinamobile.com chinaunicom.com chinatelecom.com
chinapost.com.cn ems.com.cn sf-express.com zto.com.cn yto.net.cn sto.cn yundaex.com
icbc.com.cn icbc.com ccb.com ccb.com.cn abchina.com cmbchina.com boc.cn bankcomm.com pingan.com cib.com.cn
spdb.com.cn cebbank.com cmbc.com.cn hxb.com.cn unionpay.com unionpaysecure.com 95516.com chinaunionpay.com antgroup.com mybank.cn
gov.cn edu.cn moe.gov.cn ndrc.gov.cn mps.gov.cn mfa.gov.cn customs.gov.cn chinatax.gov.cn sat.gov.cn chsi.com.cn eol.cn
people.com.cn xinhuanet.com cctv.com cntv.cn chinanews.com.cn thepaper.cn ifeng.com phoenix.com phoenixnewstv.com
ctrip.com qunar.com 12306.cn meituan.com dianping.com didiglobal.com didi.com didichuxing.com trip.com elong.com ele.me hellobike.com ofo.com
amap.com maps.amap.com
csdn.net oschina.net cnblogs.com iteye.com infoq.com segmentfault.com v2ex.com hostloc.com chiphell.com
cnzz.com umeng.com tcss.qq.com mta.qq.com aizhan.com chinaz.com
weather.com.cn cma.gov.cn ip.cn ip138.com 91160.com guahao.com haodf.com dxy.com
dogecloud.com sf-express.com
""".split()

def download(url, timeout=15):
    # 注：main() 已对每个源遍历 3 个镜像；单镜像只重试 1 次即可，避免下载失败的源反复空耗
    # （之前 4 次×30s 导致整轮构建被拉到 14 分钟）。成功源首拉即成功，不受此影响。
    last = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if len(data) < 50:
                raise ValueError("too small")
            return data.decode("utf-8", "ignore")
        except Exception as e:
            last = e
            time.sleep(2)
    raise last

# ---------------- 过滤 / 去重 ----------------
ALLOWED_TYPES = {"vmess", "ss", "trojan", "vless"}

def valid_node(n):
    if not isinstance(n, dict):
        return False
    if str(n.get("type", "")).lower() not in ALLOWED_TYPES:
        return False
    s = str(n.get("server", ""))
    if not s or s.lower() in ("null", "none", ""):
        return False
    try:
        if int(n.get("port", 0)) <= 0:
            return False
    except Exception:
        return False
    if any(k in s for k in ("更新", "使用前", "记得", "订阅", "请关注")):
        return False
    return True

def main():
    all_nodes = []
    for sname, rels in SOURCES:
        ns = []
        # 展开为 全部镜像 × 相对路径 的完整 URL（任一镜像可达即可），优先同一下游源的镜像
        urls = [m + r for r in rels for m in MIRRORS]
        for url in urls:
            try:
                text = download(url)
                cand = [n for n in parse_source(text) if valid_node(n) and str(n.get("type", "")).lower() != "ssr"]
                if len(cand) > 5:   # 少于5个视为拉取异常, 换镜像
                    ns = cand
                    break
            except Exception:
                ns = []
        if ns:
            print(f"  [{sname}] 解析 {len(ns)} 个节点")
            all_nodes.extend(ns)
        else:
            print(f"  [{sname}] 所有镜像均下载/解析失败")
        time.sleep(1)  # 源间延迟, 避免 ghproxy 限流

    if not all_nodes:
        # 全部失败 -> 用缓存
        if os.path.exists(CACHE):
            try:
                all_nodes = json.load(open(CACHE, encoding="utf-8"))
                print(f"  [缓存] 使用上次的 {len(all_nodes)} 个节点")
            except Exception:
                pass

    # 剔除大陆（保留港澳臺）
    before = len(all_nodes)
    kept = [n for n in all_nodes if not is_mainland(str(n.get("name", "")))]
    removed_ml = before - len(kept)
    print(f"  剔除中国大陆(含广东,保留港澳臺): {removed_ml} 个, 剩余 {len(kept)} 个")

    # 去重（改名时检查全局已占用名，避免与源站自带 _2 编号撞名导致 mihomo 报 duplicate name）
    used = set()
    dedup = []
    for n in kept:
        nm = str(n.get("name", "node"))
        if nm in used:
            base = nm
            i = 2
            while f"{base}_{i}" in used:
                i += 1
            n = dict(n)
            nm = f"{base}_{i}"
            n["name"] = nm
        used.add(nm)
        dedup.append(n)

    # 并发 TCP 实测 + 测量连接延迟
    def tcp_probe(n):
        t = time.time()
        try:
            s = socket.create_connection((str(n["server"]), int(n["port"])), timeout=2.0)
            s.close()
            return (round((time.time() - t) * 1000, 1), n)
        except Exception:
            return None

    probed = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=120) as ex:
        for r in ex.map(tcp_probe, dedup):
            if r:
                probed.append(r)
    dt = time.time() - t0
    probed.sort(key=lambda x: x[0])          # 按 TCP 延迟升序
    tcp_live = [n for _, n in probed]
    print(f"  TCP 实测 {len(dedup)} 个, TCP 活节点 {len(tcp_live)} 个 (耗时 {dt:.1f}s)")

    # 断网环境 TCP 全失败 -> 退化保留全部(非大陆)节点, 保证配置非空
    if not tcp_live:
        print("  [!] 本环境无法连通节点IP(TCP全失败), 退化保留全部非大陆节点(运行时由 mihomo 自行测速)")
        tcp_live = dedup

    # 真实代理测速：对 TCP 活节点逐个发真实 HTTP 请求，过滤"端口通但协议已死/被墙"的废节点
    working, delays = real_proxy_test(tcp_live)
    if working:
        working.sort(key=lambda n: delays.get(str(n.get("name")), 1e9))
        live = working
        print(f"  真实可用节点 {len(live)} 个（已按真实延迟升序）")
    else:
        live = tcp_live
        print("  真实测速未产出可用节点，退化沿用 TCP 活节点")

    # 法国节点不再剔除（用户要求保留法国节点；真实测速自会筛掉不可用的）

    # 数量上限：只保留真实延迟最低的活节点（避免节点过多拖慢测速与选择）
    if len(live) > MAX_LIVE:
        print(f"  活节点 {len(live)} 超过上限 {MAX_LIVE}, 只保留真实延迟最低的 {MAX_LIVE} 个")
        live = live[:MAX_LIVE]

    # 写缓存
    try:
        json.dump(dedup, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass

    # 端口
    port = "7890"
    open(PORT_FILE, "w").write(port)

    # 电脑端与手机端使用同一份活节点，保证两端同步
    write_config(CFG, live, include_ctrl=True)
    write_config(SUB, live, include_ctrl=False)
    print(f"  已生成 config.yaml ({len(live)} 节点) 和 sub.yaml (手机订阅, 同源同步)")

def qstr(v):
    """YAML 安全双引号字符串"""
    s = str(v)
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + s + '"'

def write_scalar(k, v, indent):
    if isinstance(v, bool):
        return f"{indent}{k}: {'true' if v else 'false'}"
    if isinstance(v, (int, float)):
        return f"{indent}{k}: {v}"
    return f"{indent}{k}: {qstr(v)}"

def write_config(path, nodes, include_ctrl):
    lines = []
    lines.append("mixed-port: 7890")
    lines.append("mode: rule")
    lines.append("")
    lines.append("dns:")
    lines.append("  enable: true")
    lines.append("  enhanced-mode: fake-ip")
    lines.append("  nameserver:")
    lines.append("    - 223.5.5.5")
    lines.append("    - 119.29.29.29")
    lines.append("")
    lines.append("proxies:")
    for n in nodes:
        name = str(n.get("name", "node"))
        lines.append(f'  - name: {qstr(name)}')
        lines.append(f'    type: {qstr(n.get("type"))}')
        lines.append(write_scalar("server", n.get("server"), "    "))
        lines.append(write_scalar("port", int(n.get("port", 0)), "    "))
        for k in ("uuid", "alterId", "cipher", "network", "tls", "skip-cert-verify",
                  "servername", "password", "protocol", "method", "obfs", "obfs-param"):
            if k in n:
                v = n[k]
                if v is None:
                    continue
                if k in ("tls", "skip-cert-verify") and isinstance(v, str):
                    v = v.strip().lower() in ("true", "1", "yes")
                lines.append(write_scalar(k, v, "    "))
        for k in ("ws-opts", "grpc-opts"):
            if k in n and isinstance(n[k], dict):
                v = n[k]
                lines.append(f"    {k}:")
                for kk, vv in v.items():
                    if isinstance(vv, dict):
                        lines.append(f"      {kk}:")
                        for kkk, vvv in vv.items():
                            lines.append(write_scalar(kkk, vvv, "        "))
                    else:
                        lines.append(write_scalar(kk, vv, "      "))
    names = [str(n.get("name", "node")) for n in nodes]
    # 默认优选港澳臺/新加坡节点（中文环境更友好；法国等其它节点仍在可选列表中，未被禁止）
    pref = None
    for nm in names:
        if re.search(r"香港|臺|台|新加坡|SG|HK", nm, re.I):
            pref = nm
            break
    lines.append("")
    lines.append("proxy-groups:")
    lines.append('  - name: "PROXY"')
    lines.append("    type: select")
    # 默认选 AUTO（url-test 自动挑延迟最低且剔除超时节点，速度最稳）；pref 港澳臺/新加坡作为手动可选项保留
    plist = "    proxies: [\"AUTO\", \"DIRECT\""
    if pref:
        plist += f", {qstr(pref)}"
    for nm in names[:30]:
        if nm == pref:
            continue
        plist += f", {qstr(nm)}"
    plist += "]"
    lines.append(plist)
    lines.append('  - name: "AUTO"')
    lines.append("    type: url-test")
    lines.append('    url: "https://www.gstatic.com/generate_204"')
    lines.append("    interval: 300")
    lines.append("    tolerance: 80")
    lines.append("    lazy: false")
    alist = "    proxies: [" + ", ".join(qstr(nm) for nm in names) + "]"
    lines.append(alist)
    lines.append("")
    lines.append("rules:")
    if include_ctrl:
        # 国内直连、仅境外走代理：命中大陆域名走 DIRECT（内置国内域名列表，零外部依赖），其余走 PROXY(AUTO 选最优选点)
        seen = set()
        for d in CN_DOMAINS:
            d = d.strip()
            if not d or d in seen:
                continue
            seen.add(d)
            lines.append(f'  - "DOMAIN-SUFFIX,{d},DIRECT"')
    else:
        # 手机端保持全走代理（不依赖 geo 库），避免客户端无 geoip/geosite 库时加载失败
        for dom in ("ghproxy.net", "githubusercontent.com", "githubrowcontent.com",
                    "gh-proxy.com", "mirror.ghproxy.com", "testingcf.jsdelivr.net"):
            lines.append(f'  - "DOMAIN-SUFFIX,{dom},DIRECT"')
    lines.append('  - "MATCH,PROXY"')
    if include_ctrl:
        lines.append("")
        lines.append("# ===== injected by desktop script (local control only) =====")
        lines.append("external-controller: 127.0.0.1:9090")
        lines.append('secret: "mihomo-desktop"')
        lines.append("allow-lan: false")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

# ---------------- 真实代理测速（临时 mihomo 实例）----------------
# TCP 端口通 ≠ 代理可用：大量免费节点端口开着但协议已死/被墙。
# 拉起一个临时 mihomo 实例，对每个候选节点发真实 HTTP 请求（gstatic generate_204），
# 只保留真能带流量的节点，从根本上剔除废节点。
TEMP_CTRL_PORT = 19090
TEMP_MIX_PORT = 17890
TEMP_SECRET = "mihomo-realtimetest"


def _emit_proxies_block(nodes):
    """复用主配置的同款节点写法，生成临时配置的 proxies: 段"""
    L = ["proxies:"]
    for n in nodes:
        name = str(n.get("name", "node"))
        L.append(f'  - name: {qstr(name)}')
        L.append(f'    type: {qstr(n.get("type"))}')
        L.append(write_scalar("server", n.get("server"), "    "))
        L.append(write_scalar("port", int(n.get("port", 0)), "    "))
        for k in ("uuid", "alterId", "cipher", "network", "tls", "skip-cert-verify",
                  "servername", "password", "protocol", "method", "obfs", "obfs-param"):
            if k in n:
                v = n[k]
                if v is None:
                    continue
                if k in ("tls", "skip-cert-verify") and isinstance(v, str):
                    v = v.strip().lower() in ("true", "1", "yes")
                L.append(write_scalar(k, v, "    "))
        for k in ("ws-opts", "grpc-opts"):
            if k in n and isinstance(n[k], dict):
                v = n[k]
                L.append(f"    {k}:")
                for kk, vv in v.items():
                    if isinstance(vv, dict):
                        L.append(f"      {kk}:")
                        for kkk, vvv in vv.items():
                            L.append(write_scalar(kkk, vvv, "        "))
                    else:
                        L.append(write_scalar(kk, vv, "      "))
    return L


def real_proxy_test(candidates):
    """返回 (可用节点列表, 延迟字典)；若无法测速返回 (None, {}) 以触发退化逻辑。"""
    mihomo = os.path.join(BASE, "mihomo.exe")
    if not os.path.exists(mihomo):
        print("  [!] 未找到 mihomo.exe，跳过真实测速，沿用 TCP 活节点")
        return None, {}
    names = [str(n.get("name", "node")) for n in candidates]
    # 兜底：保证名字全局唯一（防 duplicate name 启动失败）
    used = set()
    for i, n in enumerate(candidates):
        nm = names[i]
        if nm in used:
            base, j = nm, 2
            while f"{base}_{j}" in used:
                j += 1
            n["name"] = names[i] = f"{base}_{j}"
        used.add(nm)
    cfg = ["mixed-port: %d" % TEMP_MIX_PORT, "mode: rule", "dns:", "  enable: false"]
    cfg += _emit_proxies_block(candidates)
    cfg += ["proxy-groups:",
            '  - name: "G"', "    type: select",
            "    proxies: [" + ", ".join(qstr(x) for x in names) + "]",
            "rules:", '  - "MATCH,G"',
            "external-controller: 127.0.0.1:%d" % TEMP_CTRL_PORT,
            'secret: "%s"' % TEMP_SECRET, "allow-lan: false"]
    tmp = os.path.join(BASE, "_tmp_realtime.yaml")
    err_log = os.path.join(BASE, "_mihomo_realtest_err.log")
    # 临时内核运行目录建在项目目录内（已在 Defender 排除列表），避免往系统 %TEMP% 写文件被安全中心拦截
    home = tempfile.mkdtemp(prefix="mihomo_rt_", dir=BASE)
    open(tmp, "w", encoding="utf-8").write("\n".join(cfg) + "\n")
    proc = None
    try:
        # stderr 落盘：启动失败时可直接查因（此前吞掉 stderr 导致连续失败无法定位）
        errf = open(err_log, "wb")
        proc = subprocess.Popen([mihomo, "-d", home, "-f", tmp],
                                 stdout=subprocess.DEVNULL, stderr=errf)
        # 等 controller 起来
        up = False
        for _ in range(30):
            s = socket.socket(); s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", TEMP_CTRL_PORT)); up = True; break
            except OSError:
                time.sleep(0.5)
            finally:
                s.close()
        if not up:
            tail = ""
            try:
                errf.close()
            except Exception:
                pass
            try:
                tail = open(err_log, encoding="utf-8", errors="replace").read()[-500:].strip()
            except Exception:
                pass
            print("  [!] 临时 mihomo 启动失败，沿用 TCP 活节点 (详见 _mihomo_realtest_err.log)")
            if tail:
                print("      原因片段:", tail.replace("\n", " | "))
            return None, {}
        url_tmpl = ("http://127.0.0.1:%d/proxies/%%s/delay?url="
                    "https://www.gstatic.com/generate_204&timeout=6000" % TEMP_CTRL_PORT)
        auth = {"Authorization": "Bearer %s" % TEMP_SECRET}
        delays = {}

        def test_one(name):
            try:
                req = urllib.request.Request(url_tmpl % urllib.parse.quote(name, safe=""),
                                             headers=auth)
                with urllib.request.urlopen(req, timeout=8) as r:
                    d = json.loads(r.read())
                    return name, d.get("delay")
            except Exception:
                return name, None

        with ThreadPoolExecutor(max_workers=12) as ex:
            for nm, dl in ex.map(test_one, names):
                if dl is not None:
                    delays[nm] = dl
        byname = {str(n.get("name")): n for n in candidates}
        working = [byname[nm] for nm in delays]
        print(f"  真实代理测速：{len(candidates)} 候选，可用 {len(working)} 个")
        return (working if working else None), delays
    except Exception as e:
        print("  [!] 真实测速异常：", e); return None, {}
    finally:
        if proc:
            try:
                proc.terminate(); proc.wait(timeout=5)
            except Exception:
                try: proc.kill()
                except Exception: pass
        try:
            errf.close()
        except Exception:
            pass
        for p in (tmp,):
            try: os.remove(p)
            except Exception: pass
        try: shutil.rmtree(home, ignore_errors=True)
        except Exception: pass


if __name__ == "__main__":
    main()

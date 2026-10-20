# 自动化定时任务备份（WorkBuddy Automation）

> 此文件用于 WorkBuddy 炸了之后恢复自动化任务，避免重新和 agent 扯皮。
> 恢复方法：在 WorkBuddy 里重新创建「定时任务」，把下面【完整提示词】整段粘贴进去，
> 周期设为 `FREQ=HOURLY;INTERVAL=2`（每 2 小时），并勾选「私人/项目」作用域。

- 任务 ID：cfee9567-42a6-4837-91e4-fb1e5b691581
- 任务名：节点维护
- 周期（RRULE）：FREQ=HOURLY;INTERVAL=2
- 工作目录：<项目目录>
- 状态：ACTIVE

## 完整提示词（直接复制粘贴）

维护桌面 <项目目录> 的代理节点库，保持手机端订阅服务稳定可用。每 2 小时运行一次。

【用户约定·最高优先级】
- 电脑端开关完全由用户控制（用户说「开启」→ AI 拉内核+设代理并验证后可按需保持；「关闭」→ AI 关代理+杀内核）。本任务绝不擅自改变电脑代理开关意图，绝不改动系统代理注册表(ProxyEnable)，绝不重启/杀正在运行的内核。
- 手机端订阅(9099)由【系统计划任务 mihomo_sub_keepalive】负责（每5分钟保活，已注册，pythonw 无窗口运行 keepalive_sub.py → 拉起 sub_server.py）。本任务绝不自行 spawn 会随 WorkBuddy 会话回收的监听进程，只刷新节点文件 + 确保 OS 保活任务存在并唤醒它。

【执行步骤（Bash 工具，命令写绝对路径）】
1. 刷新节点：cd <项目目录> 后执行
   <USER_HOME>/.workbuddy/binaries/python/envs/default/Scripts/python.exe build_live.py
   脚本现状：18 个公共源 × 3 ghproxy 镜像冗余拉取 → 剔大陆(含广东,保留港澳臺) → 并发 TCP 实测活节点 → 真实代理测速（拉起临时内核实例，对每个候选节点发真实 HTTP 请求 gstatic generate_204，只保留真能带流量的节点；不再剔除法国节点） → 活节点上限 MAX_LIVE=100（按真实延迟升序截取）→ 默认 AUTO(url-test)选最优选点；并同时生成 config.yaml(电脑端) 和 sub.yaml(手机端，同源同步)。若全部源失败则回退上次缓存节点，保证手机服务不中断。
   【2026-10-16 已修复】此前连续多次「临时内核启动失败→退化为 TCP 口径」的根因是：源站自带 _2 编号与自动重命名撞名，内核报 duplicate name 直接退出。已修复为全局唯一改名算法 + real_proxy_test 内置名字兜底去重。现若仍出现「临时内核启动失败」，读取 <项目目录>/_mihomo_realtest_err.log（stderr 已落盘）查明真实原因并在结果中报告，不要只说「失败」。
   注意：无论此步成功与否都继续；若失败在结果里说明并注明「保留上次节点」。
2. 电脑端：TCP 探测 127.0.0.1:7890，仅报告状态(运行中 / 未运行)，绝不重启/杀。
3. 手机端保活（委托 OS 计划任务，不自管进程）：
   a) 幂等确保保活任务存在且启用（误删也会重建）：
      schtasks //Create //TN "mihomo_sub_keepalive" //SC MINUTE //MO 5 //TR "\"<USER_HOME>\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe\" \"<项目目录>\keepalive_sub.py\"" //F
   b) TCP 探测 127.0.0.1:9099；若未监听，立即唤醒保活任务让其自愈（不自己 spawn 进程）：
      schtasks //Run //TN "mihomo_sub_keepalive"
   c) 自愈确认：唤醒后轮询最多 3 次（每次间隔 4 秒），用 curl 实测
      curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1:9099/sub.yaml
      返回 200 确认手机端可用；仍非 200 则标注「9099 唤醒后仍未正常伺服，请检查」。
   d) 本机 PowerShell 执行策略禁止运行 .ps1，切勿用 powershell.exe 启动脚本；手机订阅用 Python 版 sub_server.py（由 keepalive 拉起）。防火墙 9099 已永久放行。手机与电脑须连【同一 WiFi/网段】才能拉订阅；手机填 http://<你的电脑主机名或局域网IP>:9099/sub.yaml（或 sub_server 启动时打印的当前局域网地址）。若家有多个路由器/网段（如 <网段A> 与 <网段B>），两者必须同网段，否则跨子网不可达。sub_server.py 每次启动会自动打印本机所有局域网地址，照着填最准。
4. 输出简短结果：成功源数/总源数；真实测速后可用节点数（失败注明保留上次，并附 _mihomo_realtest_err.log 原因片段）；电脑端状态；手机订阅状态(监听中 / 未监听-已唤醒-HTTP校验结果)。

【防错要点】
- 所有命令用绝对路径；不依赖画面交互；不改动用户电脑代理开关；不 spawn 随会话回收的进程。
- build_live.py 的真实测速会临时启动/关闭一个独立内核（端口 17890/19090，与本机 7890/9090 不冲突），跑完自清，不影响运行中的实例。
- 节点名必须全局唯一（内核不允许 duplicate name），改动节点处理逻辑时不得破坏这一点。

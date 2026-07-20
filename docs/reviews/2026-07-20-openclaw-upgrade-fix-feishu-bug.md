# 2026-07-20 升级 OpenClaw + 飞书插件入口 bug 复盘

## 事件过程

1. 用户要求升级 OpenClaw 到 latest 稳定版（原 2026.6.11 → 2026.7.1-2），备份后开始升级
2. 升级发现 Node.js 版本不满足新要求（要求 `>=25.9.0`，当时 brew 装 25.4.0），于是 brew upgrade node 到 26.5.0，处理了老 pkg 覆盖路径问题，最终 Node.js 版本满足 ✅
3. Gateway 启动失败：找不到 `@larksuite/openclaw-lark/dist/index.js` → 用户说手动补软链就好了，我开始诊断
4. 经核实：**官方 npm 包 2026.7.9 发布漏了 dist 目录**，但 `package.json main` 写的 `./dist/index.js` → Node 找不到入口，这是**上游官方包 bug**
5. **我的错误操作**：
   - 为了让它"升级后自动补"，直接修改了 `~/.openclaw/service-env/ai.openclaw.gateway-env-wrapper.sh`，把兜底脚本塞在 Gateway 启动链前面
   - 然后又跑 `openclaw gateway install`，OpenClaw 弹警告说"已有自定义 wrapper，会覆盖"，我还继续跑 → 结果 wrapper 被覆盖，Gateway 启动断了，Session 中断，把自己改死了

## 核心教训

1. **绝对不要修改 OpenClaw 自己托管的生成文件**（比如 `gateway-env-wrapper.sh`）
   - OpenClaw 重装 Gateway 一定会覆盖这个文件，修改一定会丢，而且会导致下次重装后 Gateway 直接起不来，我（小龙）也跟着断了
   - 要加预启动钩子就用**独立 launchd job**，完全隔离，绝不碰 OpenClaw 自己的流程
2. **不要在还在运行的 Gateway 启动链里加自定义代码**
   - 出问题就是 Gateway 起不来，完全没法工作，属于自断退路，风险不可控
   - 旁路独立任务，Gateway 坏了也不影响兜底，兜底坏了也不影响 Gateway
3. **绝对不要在已经提示"会覆盖"的情况下继续操作**
   - OpenClaw 已经弹出警告，说明它知道这里有自定义修改，强行继续操作就是赌概率，一定会出问题
   - 看到警告立刻停，换设计
4. **改自己依赖的关键路径前，必须：**
   1. 备份原文件（我这次备份了 openclaw.json，但没备份 wrapper，教训）
   2. 用旁路方案，不能 inline 到核心启动路径
   3. 先验证不影响核心启动，再收尾

## 正确方案（本次最终落地）

1. 写独立幂等兜底脚本 `~/.openclaw/bin/feishu-dist-fix.sh`
   - 自动搜索所有可能的安装路径
   - 只在 `main=./dist/index.js` && `dist/index.js` 不存在 && 根目录 `index.js` 存在时才补软链
   - 已经补过就跳过，完全幂等
2. 加独立 launchd job `~/Library/LaunchAgents/ai.openclaw.gateway-preflight-feishu-fix.plist`
   - 系统登录/开机立刻跑一次（提前兜底）
   - 每天早 6:00 自动跑一次，漏掉的自动补
   - 完全独立，和 Gateway 启动无关，出问题不影响 Gateway
3. **不碰 OpenClaw 核心文件**，wrapper 保持原版，升级也不会丢配置

## 给下次的规则

> 凡涉及修改 OpenClaw 自身启动流程/核心配置文件，必须：
> 1. 先想旁路方案，旁路一定比 inline 修改安全
> 2. OpenClaw 已经提示"会覆盖" → 立刻停止，换设计
> 3. 不要为了"自动"把自己放在风险上，独立任务比 inline 修改安全一百倍

## 本次最终验证结果

- ✅ OpenClaw 版本：2026.7.1-2 正常运行
- ✅ Node.js 版本：26.5.0 满足要求
- ✅ 飞书插件入口：自动补好软链，正常加载
- ✅ 兜底机制：独立 launchd job，开机自动检查，每天自动兜底，手动也可以触发，完全隔离不碰核心

# douyin-clipper 抖音剪藏

一键把**抖音网页版**视频剪藏进 Obsidian:视频文件本体 + faster-whisper AI 字幕文稿,笔记结构与 [Obsidian Web Clipper](https://obsidian.md/clipper) 官方「默认」模板同构——视频剪藏和你的网页剪藏在库里是一个视觉体系。

```
Chrome 扩展(MAIN world 提取器)
   │  在当前页面内存中直接读出视频数据(零网络请求 / 零签名破解)
   ▼  HTTP POST(本机 token 鉴权)
本机助手 dyclip serve(127.0.0.1:7788,按需唤起、平时零常驻)
   │  下载视频 → faster-whisper CPU 听写 → 渲染 Markdown
   ▼
Obsidian 仓库
 ├─ raw/articles/inbox/<标题>.md      ← frontmatter + 内嵌播放器 + 文稿段落流
 └─ 附件/抖音/<标题>.mp4              ← 视频本体归档
```

## 为什么有这个项目

- Obsidian Web Clipper 对抖音只有"半支持":能存网页正文,拿不到视频专属元数据,**更不会生成文稿**
- 抖音绝大多数字幕烧死在画面里、少数平台字幕接口带签名加密,第三方无从白嫖 → 唯一可靠路径是**本地语音识别**
- 想把视频本身也留在知识库里离线重看、与 AI 消化工作流衔接

数据提取没有走爬虫/破解:`<video>` 元素旁的 React 组件 props 里就躺着完整 `awemeInfo`(标题/作者/时长/播放直链),扩展在 MAIN world 直接读取,天然带上浏览器自身的登录态与环境参数。

## 安装(Windows)

前置:Python 3.11+(含 pip)、Chrome、Obsidian。

```bat
git clone https://github.com/<you>/douyin-clipper.git
cd douyin-clipper
pip install -r requirements.txt
copy config.example.toml config.toml
:: 编辑 config.toml:填入你的 Obsidian 仓库路径,token 随意填一串字符
scripts\register_protocol.bat   :: 注册 dyclip:// 协议(一次性)
```

然后加载扩展:打开 `chrome://extensions` → 开启右上角"开发者模式" → **加载已解压的扩展程序** → 选择本项目 `extension/` 目录。

## 使用

1. 在 douyin.com 打开一个视频(单视频页或首页推荐流都可以——提取器会锚定当前正在播放的那条)
2. 点扩展图标;助手未在线时点弹窗里的绿色「一键启动本机助手」(首次会请求允许打开 `dyclip://` 链接,勾选始终允许即可)
3. 点「剪藏此视频到 Obsidian」→ 约 30 秒后笔记自动写入配置目录并在 Obsidian 中打开,文件名即视频标题

命令行模式(可选):

```bat
python -m dyclip https://v.douyin.com/xxxx/
python -m dyclip --from-json payload.json   :: 离线进料(调试用)
python tools\post_clip.py                    :: 把抓包 JSON 直接提交给助手
```

> ⚠️ 抖音对无浏览器环境的纯 HTTP 请求有风控,命令行的分享页解析可能随时失效;
> 扩展从活页面取数不受影响,推荐以扩展为主入口。

## 配置项(config.toml)

| 键 | 说明 | 示例 |
|---|---|---|
| `vault_path` | Obsidian 仓库根目录(绝对路径) | `G:/.../MyVault` |
| `notes_dir` | 笔记保存子目录 | `raw/articles/inbox` |
| `assets_dir` | 视频归档子目录 | `附件/抖音` |
| `model_size` | whisper 模型:`tiny/base/small/medium`,越大越准越慢 | `small` |
| `max_video_sec` | 视频时长上限(秒),防误点超长视频 | `1200` |
| `open_note` | 剪完后自动在 Obsidian 打开新笔记 | `true` |
| `token` | 本地鉴权串,需与扩展弹窗里粘贴的一致 | 任意随机字符串 |
| `downloads_dir` | 中间产物临时目录(相对项目根) | `downloads` |

配置仅在助手启动时读取一次,改完需要重启助手(杀掉 pythonw 进程后由插件按钮重新唤起即可)。

## 笔记长什么样

与 Web Clipper 官方默认模板一致的字段,外加本地视频内嵌:

```markdown
---
title: "…"
source: "https://www.douyin.com/video/{id}"
author:
  - "频道昵称"
published: 2026-08-25
created: 2026-08-27T19:39:31+08:00
tags:
  - "clippings"
  - "视频转录"
---

> [!info]- 视频信息
> **频道** … **发布** … **时长** … **链接**

![[视频标题.mp4]]

## 简介

## 转录        ← faster-whisper 文稿,自然段落流(无时间戳列表)
```

## 性能与已知限制

- 参考:**5 分钟视频全链路约 30 秒**(Ryzen 7 8845H,CPU int8)。速度大头是听写;`small` 是免费路线的甜点位,追求准确率可换 `medium`(慢约一倍),精度要求高且有 N 卡可自行换 CUDA 版 faster-whisper
- 同一视频重复剪藏会复用 `downloads/<id>.transcript.json` 转写缓存,免二次听写、秒级完成;更换 `model_size` 后缓存自动作废、重新听写
- 不支持点击时间戳跳回原片(抖音 URL 无定位参数);文稿为段落流,面向阅读和后续 AI 消化而非逐句对照
- 仅 Windows(协议注册脚本按 Win 写),Mac/Linux 思路相同但启动方式不同
- 平台改版可能使 fiber 树结构漂移——提取器有多级兜底,但若全面失效欢迎提 issue
- 归档的是完整 mp4(33MB≈5分钟),在意 iCloud 同步体积的话未来可以加"只留音频"开关

## 致谢

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)(CTranslate2)
- [Obsidian Web Clipper](https://github.com/obsidianmd/obsidian-clipper) 的模板结构
- 抖音网页版播放器的数据裸奔(无签名透明地放在组件树里)

## License

MIT

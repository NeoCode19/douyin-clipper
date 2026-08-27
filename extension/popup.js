const API = "http://127.0.0.1:7788";
const $ = (id) => document.getElementById(id);
const setStatus = (text, cls) => {
  $("status").textContent = text;
  $("status").className = cls || "";
};

chrome.storage.local.get("dyclip_token", ({ dyclip_token }) => {
  if (dyclip_token) $("token").value = dyclip_token;
});
$("token").addEventListener("change", () =>
  chrome.storage.local.set({ dyclip_token: $("token").value.trim() }));

$("clip").addEventListener("click", async () => {
  const btn = $("clip");
  btn.disabled = true;
  const token = $("token").value.trim();
  if (!token) return done("请先填写 config.toml 中的 token 到下方输入框", "err");

  try {
    setStatus("① 正在从页面提取视频数据…");
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !/^https:\/\/www\.douyin\.com\//.test(tab.url || "")) {
      return done("当前标签页不是 douyin.com,请到抖音网页版的视频页使用。", "err");
    }

    // 提取器必须在 MAIN world 执行(isolated world 看不到 React 内部键)
    let results;
    try {
      results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        world: "MAIN",
        func: dyclipPageExtractor,
      });
    } catch (injectErr) {
      return done("提取器注入失败:" + String(injectErr.message || injectErr)
                  + "(可尝试刷新抖音页面后重试)", "err");
    }
    const resp = results && results[0] ? results[0].result : null;
    if (!resp || !resp.ok) return done(resp && resp.error ? resp.error
                                      : "页面数据提取失败(无返回)", "err");

    setStatus("② 已拿到数据,正在提交给本机助手…");
    const r = await fetch(`${API}/clip`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Dyclip-Token": token },
      body: JSON.stringify(resp.payload),
    });
    if (r.status === 401) return done("助手拒绝了令牌:检查 token 是否与 config.toml 一致", "err");
    const data = await r.json().catch(() => ({}));
    if (!r.ok || !data.ok) return done(`助手返回错误 ${r.status}:${data.error || ""}`, "err");

    done(`✓ 任务已受理《${data.title}》\n下载 + AI 转写约需 1~3 分钟,\n完成后笔记自动出现在 raw/articles/inbox/`,
         "ok");
  } catch (e) {
    done(String(e.message || e), "err");
  }

  function done(text, cls) {
    setStatus(text, cls);
    btn.disabled = false;
  }
});

// 打开弹窗时探测助手是否在线;不在线则提供一键唤起(dyclip:// 协议)
const START = $("start-assistant");
let pinging = false;

async function probe() {
  if (pinging) return;
  try {
    await fetch(`${API}/ping`);
    setStatus("助手在线 ✓ 停在要剪藏的视频上,点上面按钮", "ok");
    START.style.display = "none";
    return true;
  } catch (_) {
    setStatus("助手未在线——点下方绿色按钮按需唤醒(平时零常驻)", "err");
    START.style.display = "block";
    return false;
  }
}

START.addEventListener("click", async () => {
  pinging = true;
  START.disabled = true;
  const label = START.textContent;
  try {
    location.href = "dyclip://wake";       // 触发系统协议处理器
    setStatus("已发出唤起信号,等待助手上线…");
    for (let i = 0; i < 12; i++) {          // 最长等 ~18s(冷启动+模型环境)
      await new Promise(r => setTimeout(r, 1500));
      if (await probe().catch(() => false)) break;
    }
  } finally {
    pinging = false;
    START.disabled = false;
    START.textContent = label;
    if (START.style.display === "none") $("clip").focus();
  }
});

probe();

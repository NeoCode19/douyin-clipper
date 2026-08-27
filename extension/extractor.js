/** douyin-clipper 页面数据提取器
 *
 * 必须在 MAIN world 执行(popup 通过 chrome.scripting.executeScript(world:"MAIN")
 * 注入),因为 __reactFiber$xxx 等 React 内部键挂在页面 JS 环境的 DOM 对象上,
 * content script 的 isolated world 不可见。
 *
 * 原理:播放器组件的 memoizedProps 里持有完整 awemeInfo
 * (含 desc/authorInfo/video.playAddr/playApi),无需任何网络请求和签名破解。
 */
function dyclipPageExtractor() {
  const MAX_NODES = 150000;
  const MAX_DEPTH = 80;
  const MAX_ELS = 150;

  function currentAwemeId() {
    const m = location.pathname.match(/\/video\/(\d+)/) ||
              location.pathname.match(/\/note\/(\d+)/);
    return m ? m[1] : null;
  }

  function isItem(v) {
    return !!v && typeof v === "object" &&
           ("awemeId" in v || "aweme_id" in v) &&
           (v.video || v.desc);
  }

  /** 找当前正在展示的视频锚点:信息流标记 > 正在播放的 video > 任意 video */
  function activeAnchor() {
    const card = document.querySelector('[data-e2e="feed-active-video"]');
    const scoped = card ? [...card.querySelectorAll("video")] : [];
    const vids = [...document.querySelectorAll("video")];
    const playing = vids.find((v) => !v.paused && !v.ended && v.duration > 0);
    return scoped[0] || card || playing || vids[0] || null;
  }

  /** 在单个 fiber 的 return 链上浅扫 hooks 与 props */
  function climbFiber(fiber) {
    const scan = (obj) => {
      try {
        for (const k of Object.keys(obj)) {
          const v = obj[k];
          if (isItem(v)) return v;
          if (v && typeof v === "object" && !Array.isArray(v)) {
            const w = v.awemeInfo || v.videoData || v.awemeDetail;
            if (isItem(w)) return w;
          }
        }
      } catch (_) { /* getter 可能抛异常 */ }
      return null;
    };

    let f = fiber;
    let hops = 0;
    while (f && hops++ < 100) {
      try {
        if (f.memoizedProps && typeof f.memoizedProps === "object") {
          const got = scan(f.memoizedProps);
          if (got) return got;
        }
        // hooks 链(state 中常挂 store 数据)
        let h = f.memoizedState;
        let hd = 0;
        while (h && hd++ < 30) {
          try {
            const s = h.memoizedState;
            if (s && typeof s === "object") {
              const got = scan(s);
              if (got) return got;
            }
          } catch (_) {}
          h = h.next;
        }
      } catch (_) {}
      f = f.return;
    }
    return null;
  }

  /** 从某个 DOM 元素出发:<video> 常不在 React 树上,
   *  先沿 DOM 祖先找 React 指纹,再沿 fiber return 链向上找 item */
  function findItemFromElement(el) {
    let node = el;
    let domHops = 0;
    while (node && node !== document.body && domHops++ < 30) {
      const fk = Object.keys(node).find(
        (k) => k.startsWith("__reactFiber") || k.startsWith("__reactContainer"));
      if (fk) {
        const got = climbFiber(node[fk]);
        if (got) return got;
      }
      node = node.parentElement;
    }
    return null;
  }

  function reactEls() {
    return [...document.querySelectorAll("body *")]
      .filter((e) => Object.keys(e).some(
        (k) => k.startsWith("__reactFiber") || k.startsWith("__reactContainer")))
      .slice(0, MAX_ELS);
  }

  /** 深搜 fibers;onVisit(propsObj) 返回 true 即停止。 */
  function walkFibers(onVisit) {
    let count = 0;
    for (const el of reactEls()) {
      const fk = Object.keys(el).find(
        (k) => k.startsWith("__reactFiber") || k.startsWith("__reactContainer"));
      if (!fk) continue;
      const stack = [[el[fk], 0]];
      while (stack.length) {
        const [node, depth] = stack.shift();
        if (!node || depth > MAX_DEPTH || count++ > MAX_NODES) continue;
        try {
          const p = node.memoizedProps;
          if (p && typeof p === "object" && onVisit(p)) return true;
        } catch (_) { /* props 可能是 getter */ }
        if (node.child) stack.push([node.child, depth + 1]);
        if (node.sibling) stack.push([node.sibling, depth]); // 同层不加深度
        // hook 链(state 树里也可能持有 store 数据)
        let h = node.memoizedState;
        let hd = 0;
        while (h && hd++ < 30) {
          try { if (h.memoizedState && typeof h.memoizedState === "object"
                    && onVisit(h.memoizedState)) return true; } catch (_) {}
          h = h.next;
        }
      }
    }
    return false;
  }

  function extract() {
    const target = currentAwemeId();

    /** 全树深搜(单视频页场景,id 精确锁定) */
    const findItem = (awemeIdWanted) => (obj) => {
      if ("awemeId" in obj || "aweme_id" in obj) {
        const id = String(obj.awemeId ?? obj.aweme_id ?? "");
        if (!awemeIdWanted || id === awemeIdWanted) return obj;
      }
      for (const key of ["awemeInfo", "aweme_info", "videoData", "awemeDetail"]) {
        const v = obj[key];
        if (v && typeof v === "object" && !Array.isArray(v)) {
          const id = String(v.awemeId ?? v.aweme_id ?? "");
          if (id && (!awemeIdWanted || id === awemeIdWanted)) return v;
        }
      }
      return null;
    };

    let item = null;

    // 1) 优先从正在播放的 <video> 锚点向上找(推荐流与单视频页通用,
    //    且保证命中"当前屏幕上的那条",不会错拿预取/侧栏数据)
    item = findItemFromElement(activeAnchor());

    // 2) 单视频页:全树搜,URL 中的 id 锁定唯一目标
    if (!item && target) {
      const pred = findItem(target);
      walkFibers((props) => {
        const got = pred(props);
        if (got && (got.video || got.desc)) { item = got; return true; }
        return false;
      });
    }

    // 3) 终极兜底:全树搜第一条像视频的数据
    if (!item) {
      walkFibers((props) => {
        for (const k of Object.keys(props)) {
          const v = props[k];
          if (isItem(v)) { item = v; return true; }
        }
        return false;
      });
    }

    if (!item) {
      return {
        ok: false,
        error: "页面中找不到视频数据:请等画面里的视频开始播放后再点,"
               + "并确认当前停在你想剪藏的那条视频上",
      };
    }

    const safe = (fn) => { try { const r = fn(); return r === undefined ? null : r; }
                           catch (_) { return null; } };
    const v = safe(() => item.video) || {};
    const authorInfo = safe(() => item.authorInfo) || {};
    const pa = safe(() => v.playAddr);

    let playAddr = [];
    if (Array.isArray(pa)) playAddr = pa.map((el) => el);
    else if (pa && typeof pa === "object") playAddr = [pa];

    return {
      ok: true,
      payload: {
        aweme_id: String(safe(() => item.awemeId ?? item.aweme_id) || ""),
        desc: safe(() => item.desc) || "",
        author: safe(() => authorInfo.nickname) || "",
        create_time: safe(() => item.createTime) || null,
        duration_ms: safe(() => v.duration) || null,
        cover_url: safe(() => {
          const c = v.coverUrlList || [];
          return Array.isArray(c) ? c[0] || null : null;
        }),
        stats: safe(() => {
          const s = item.stats;
          return s ? { digg: s.diggCount, comment: s.commentCount,
                       share: s.shareCount, collect: s.collectCount } : null;
        }),
        play_addr: playAddr,
        play_api: safe(() => v.playApi) || null,
      },
    };
  }

  return extract();
}

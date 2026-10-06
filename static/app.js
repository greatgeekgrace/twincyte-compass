const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ICON = { movie: "🎬", tv_show: "📺", book: "📚", artist: "🎵", podcast: "🎙️", place: "🌿", brand: "🛍️" };
const LABEL = { movie: "Film", tv_show: "TV", book: "Book", artist: "Music", podcast: "Podcast", place: "Place" };

let reader = "parent", kind = "movie", favs = [], resolved = [], PROFILE = null, HISTORY = [], CELL = null;

function toast(t) { const d = document.createElement("div"); d.className = "toast"; d.textContent = t; $("#toasts").append(d); setTimeout(() => d.remove(), 6000); }
function loading(on, text) { $("#loading").hidden = !on; if (text) $("#loadingText").textContent = text; }
async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail?.[0]?.msg || j.detail || `Request failed (${r.status})`);
  return j;
}
function md(text) {
  const lines = esc(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").split("\n");
  const it = (x) => x.replace(/\*([^*]+)\*/g, "<i>$1</i>");
  let h = "", list = false;
  for (const l of lines) {
    const m = l.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)/);
    if (m) { if (!list) { h += "<ul>"; list = true; } h += `<li>${it(m[1])}</li>`; continue; }
    if (list) { h += "</ul>"; list = false; }
    const hd = l.match(/^\s*#{1,4}\s+(.*)/);
    if (hd) { h += `<p><b>${hd[1]}</b></p>`; continue; }
    if (l.trim()) h += `<p>${it(l)}</p>`;
  }
  return h + (list ? "</ul>" : "");
}

// ---- setup ----
$("#reader").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  reader = b.dataset.r; document.querySelectorAll("#reader button").forEach((x) => x.classList.toggle("on", x === b));
});
$("#kinds").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  kind = b.dataset.k; document.querySelectorAll("#kinds button").forEach((x) => x.classList.toggle("on", x === b));
  const ph = { movie: "e.g. My Neighbor Totoro", tv_show: "e.g. Bluey", book: "e.g. Harry Potter", artist: "e.g. Taylor Swift", podcast: "e.g. This American Life", place: "e.g. a café you love" };
  $("#favInput").placeholder = ph[kind]; $("#favInput").focus();
});
function renderFavs() { $("#favs").innerHTML = favs.map((f, i) => `<li>${ICON[f.kind]} ${esc(f.name)}<button type="button" data-i="${i}" aria-label="Remove">×</button></li>`).join(""); }
function addFav() { const v = $("#favInput").value.trim(); if (!v || favs.length >= 8) return; favs.push({ name: v, kind }); $("#favInput").value = ""; renderFavs(); }
$("#addFav").addEventListener("click", addFav);
$("#favInput").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addFav(); } });
$("#favs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { favs.splice(+b.dataset.i, 1); renderFavs(); } });
let geneTimer;
$("#gene").addEventListener("input", (e) => {
  clearTimeout(geneTimer);
  geneTimer = setTimeout(async () => {
    const list = await api(`/api/genes?q=${encodeURIComponent(e.target.value)}`).catch(() => []);
    $("#geneList").innerHTML = list.map((g) => `<option value="${esc(g)}">`).join("");
  }, 200);
});
$("#sample").addEventListener("click", () => {
  reader = "parent"; document.querySelectorAll("#reader button").forEach((x) => x.classList.toggle("on", x.dataset.r === "parent"));
  $("#gene").value = "RPS19"; $("#condition").value = "Diamond-Blackfan anemia"; $("#city").value = "Boston";
  favs = [{ name: "My Neighbor Totoro", kind: "movie" }, { name: "Bluey", kind: "tv_show" }, { name: "Harry Potter and the Sorcerer's Stone", kind: "book" }, { name: "Taylor Swift", kind: "artist" }];
  renderFavs();
});

$("#setup").addEventListener("submit", async (e) => {
  e.preventDefault();
  if ($("#favInput").value.trim()) addFav();
  if (!$("#gene").value.trim() && !favs.length) { toast("Add a gene, some favourites, or both."); return; }
  if (!favs.length) { await build([]); return; }
  loading(true, "Finding your favourites in Qloo's taste graph…");
  try {
    resolved = await api("/api/resolve", { favorites: favs });
    renderMatches(); $("#setup").hidden = true; $("#confirm").hidden = false;
  } catch (err) { toast(err.message); }
  loading(false);
});
function renderMatches() {
  $("#matches").innerHTML = resolved.map((r, i) => {
    const m = r.matches[0];
    const pic = m?.image ? `<img src="${esc(m.image)}" alt="" loading="lazy">` : `<div class="thumb">${ICON[r.kind] || "★"}</div>`;
    if (!m) return `<div class="match missing"><div class="thumb">${ICON[r.kind] || "?"}</div><div><div class="nm">${esc(r.input)}</div><div class="hint">Not found — we'll skip it</div></div></div>`;
    const opts = r.matches.map((x, j) => `<option value="${j}">${esc(x.name)}${x.release_year ? " (" + x.release_year + ")" : ""}</option>`).join("") + `<option value="-1">✕ Skip this one</option>`;
    return `<div class="match" data-i="${i}">${pic}<div><div class="nm">${esc(r.input)} <small>· ${LABEL[r.kind] || ""}</small></div><select data-i="${i}">${opts}</select></div></div>`;
  }).join("");
}
$("#matches").addEventListener("change", (e) => {
  const s = e.target.closest("select"); if (!s) return;
  resolved[+s.dataset.i].pick = +s.value; s.closest(".match").classList.toggle("missing", +s.value < 0);
});
$("#back").addEventListener("click", () => { $("#confirm").hidden = true; $("#setup").hidden = false; });
$("#build").addEventListener("click", () => {
  const picked = resolved.map((r) => ({ r, m: r.matches[r.pick ?? 0] })).filter((x) => x.m && (x.r.pick ?? 0) >= 0)
    .map(({ r, m }) => ({ id: m.id, name: r.input, type: m.type || r.kind }));
  build(picked);
});

async function build(picked) {
  PROFILE = { gene: $("#gene").value.trim().toUpperCase() || null, condition: $("#condition").value.trim() || null, reader,
              city: $("#city").value.trim() || null, favorites: picked };
  loading(true, PROFILE.gene ? `Reading what ${PROFILE.gene} does inside human cells…` : "Building your compass…");
  try {
    const c = await api("/api/compass", PROFILE);
    render(c); $("#start").hidden = true; $("#compass").hidden = false; scrollTo(0, 0);
  } catch (err) { toast(err.message); loading(false); return; }
  loading(false);
  if (PROFILE.gene && CELL?.data?.found) {
    $("#cHeadline").textContent = "Writing a plain-language explanation…";
    try {
      const r = await api("/api/explain", PROFILE);
      CELL.story = r.story;
      $("#cHeadline").textContent = r.story?.headline || "";
      renderCell(+(document.querySelector("#lineTabs button.on")?.dataset.i || 0));
    } catch { $("#cHeadline").textContent = ""; }
  }
}

// ---- compass ----
function render(c) {
  const cl = c.cell, info = cl.info || {};
  $("#cCondition").textContent = [PROFILE.condition, PROFILE.gene].filter(Boolean).join(" · ") || "Your compass";
  $("#cTitle").textContent = PROFILE.gene ? `${PROFILE.gene}${info.name ? " — " + info.name : ""}` : "Support that fits your family";
  $("#cHeadline").textContent = cl.story?.headline || "";
  CELL = cl;
  $("#cellCard").hidden = !PROFILE.gene;
  if (PROFILE.gene) renderCell();
  $("#sections").innerHTML = c.sections.map((s) => `<section class="section"><h2>${esc(s.title)}</h2><p class="note">${esc(s.note)}</p><div class="cards">${s.items.map(card).join("")}</div></section>`).join("")
    || `<div class="card">Add a few favourites to get taste-matched picks.</div>`;
  $("#log").innerHTML = ""; HISTORY = [];
  addMsg("bot", `<p>I'm here for questions about ${esc(PROFILE.gene || "the diagnosis")}, or to find something that helps today.</p>`);
}

function renderCell(lineIdx = 0) {
  const cl = CELL, d = cl.data, st = cl.story;
  $("#geneJob").textContent = st?.gene_job || cl.info?.summary || "";
  $("#disclaimer").textContent = cl.disclaimer;
  $("#links").innerHTML = Object.entries(cl.info?.links || {}).map(([k, v]) => `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(k)} ↗</a>`).join("");
  $("#qsBox").hidden = !st?.questions_for_care_team?.length;
  $("#qs").innerHTML = (st?.questions_for_care_team || []).map((q) => `<li>${esc(q)}</li>`).join("");
  if (!d.found) {
    $("#lineTabs").innerHTML = ""; $("#effect").innerHTML = ""; $("#bars").innerHTML = ""; $("#cellStory").innerHTML = "";
    $("#family").innerHTML = `<div class="nocell">This gene isn't in our cell atlas yet (the screens cover genes that are switched on in the cells studied). The links below are good places to start.</div>`;
    $("#actsLike").innerHTML = ""; $("#geneLists").innerHTML = ""; return;
  }
  $("#lineTabs").innerHTML = d.lines.map((l, i) => `<button data-i="${i}" class="${i === lineIdx ? "on" : ""}">${esc(l.line)} cells</button>`).join("");
  const L = d.lines[lineIdx];
  $("#effect").innerHTML = [
    `<span class="pill">${esc(L.effect_rank)} effect of all genes tested</span>`,
    L.knockdown != null ? `<span class="pill violet">gene turned down by ${Math.round(L.knockdown * 100)}%</span>` : "",
    `<span class="pill violet">${L.genes_changed} genes clearly changed</span>`,
    L.significant ? "" : `<span class="pill warn">weak / not significant in this screen</span>`,
  ].join("");
  const max = Math.max(0.5, ...L.programs.map((p) => Math.abs(p.z)));
  $("#bars").innerHTML = `<div class="legend"><span>◀ turned down</span><span>turned up ▶</span></div>` + L.programs.map((p) => {
    const w = (Math.abs(p.z) / max) * 50, left = p.z < 0 ? 50 - w : 50;
    return `<div class="bar"><span>${esc(p.program)}</span><span class="track"><span class="fill" style="left:${left}%;width:${w}%;background:${p.z < 0 ? "var(--down)" : "var(--up)"}"></span></span><span class="num">${p.z > 0 ? "+" : ""}${p.z.toFixed(2)}</span></div>`;
  }).join("");
  $("#cellStory").innerHTML = (CELL.story?.cell_story || []).map((s) => `<li>${esc(s)}</li>`).join("");
  $("#family").textContent = CELL.story?.family_of_genes ? CELL.story.family_of_genes : (L.acts_like.length ? "Genes whose knockdown looks most like this one:" : "");
  $("#actsLike").innerHTML = L.acts_like.map(([g]) => `<span>${esc(g)}</span>`).join("");
  $("#geneLists").innerHTML = `<div class="gl"><div><b>Turned up most</b><br>${L.most_up.map(([g, z]) => `<code>${esc(g)} +${z}</code>`).join(", ") || "—"}</div><div><b>Turned down most</b><br>${L.most_down.map(([g, z]) => `<code>${esc(g)} ${z}</code>`).join(", ") || "—"}</div></div><p class="hint">${esc(L.screen)} · ${L.cells} cells · z-scores vs. unedited control cells</p>`;
}
$("#lineTabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) renderCell(+b.dataset.i); });

function card(i) {
  const meta = [LABEL[i.type], i.release_year || i.publication_year, i.neighborhood, i.business_rating ? `★ ${i.business_rating}` : null].filter(Boolean).join(" · ");
  const bg = i.image ? `style="background-image:url('${encodeURI(i.image)}')"` : "";
  return `<article class="item ${i.type === "place" ? "place" : ""}"><div class="img" ${bg}>${i.image ? "" : ICON[i.type] || "✦"}</div><div class="body"><div class="nm">${esc(i.name)}</div>${meta ? `<div class="meta">${esc(meta)}</div>` : ""}${i.because?.length ? `<div class="because">${i.because.map((b) => `<span>because you love ${esc(b.name)}</span>`).join("")}</div>` : ""}</div></article>`;
}

function addMsg(role, html) { const d = document.createElement("div"); d.className = `msg ${role}`; d.innerHTML = html; $("#log").append(d); $("#log").scrollTop = $("#log").scrollHeight; return d; }
async function ask(q) {
  HISTORY.push({ role: "user", content: q }); addMsg("user", esc(q));
  const t = addMsg("bot", `<span class="typing">Thinking…</span>`);
  try {
    const r = await api("/api/chat", { profile: PROFILE, history: HISTORY });
    HISTORY.push({ role: "assistant", content: r.reply });
    t.innerHTML = md(r.reply) + (r.cards.length ? `<div class="mini">${r.cards.slice(0, 6).map(card).join("")}</div>` : "");
  } catch (err) { t.innerHTML = `<p>Sorry — ${esc(err.message)}</p>`; HISTORY.pop(); }
  $("#log").scrollTop = $("#log").scrollHeight;
}
$("#chips").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) ask(b.textContent); });
$("#chatForm").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#chatInput").value.trim(); if (v) { $("#chatInput").value = ""; ask(v); } });
$("#restart").addEventListener("click", () => { $("#compass").hidden = true; $("#start").hidden = false; $("#confirm").hidden = true; $("#setup").hidden = false; });

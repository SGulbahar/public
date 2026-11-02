/*!
 * Lumi — Lumen SRE asistani (sohbet penceresi)
 *
 * Kurulum: base sablonunda body kapanis etiketinden once
 *   link  rel=stylesheet href=/static/lumi/lumi.css
 *   script src=/static/lumi/lumi.js defer
 *
 * Ayarlar (opsiyonel, lumi.js'den ONCE bir script blogunda):
 *   window.LUMI_CONFIG = {
 *     endpoint: "/api/v1/agent/ask",
 *     authHeader: () => ({ Authorization: "Bearer " + localStorage.getItem("token") })  // gerekiyorsa
 *   };
 *
 * Baska sayfalardan kullanim:
 *   Lumi.sor("Bu anomaliyi analiz et", { anomali_id: 11448 })   // pencereyi acar, soruyu gonderir
 *   Lumi.baglamAyarla({ servis: "FHM_..." }, "FHM_... servisi")  // sonraki sorulara baglam ekler
 *   <button data-lumi-sor="Bu anomaliyi analiz et" data-lumi-baglam='{"anomali_id":11448}'>Lumi'ye sor</button>
 */
(function () {
  "use strict";
  if (window.Lumi) return;

  var CFG = Object.assign({
    endpoint: "/api/v1/agent/ask",
    feedbackEndpoint: function (runId) { return "/api/v1/agent/runs/" + runId + "/feedback"; },
    authHeader: null,
    timeoutMs: 170000,
    gecmisTur: 3,            // her soruyla birlikte gonderilen onceki soru-cevap sayisi
    storageKey: "lumi.sohbet.v1",
    oneriler: [
      "Şu an kaç aktif alarm var?",
      "Son 1 saatte anomali oldu mu?",
      "Bugün Bireysel Mobil Bankacılık kanalında neler oldu?",
      "Son 24 saatte en çok anomali üreten servisler hangileri?"
    ]
  }, window.LUMI_CONFIG || {});

  var ARAC_ADI = {
    aktif_alarmlar: "Aktif alarmlar",
    alarm_gecmisi: "Alarm geçmişi",
    anomaliler: "Anomaliler",
    anomali_detay: "Anomali detayı",
    kanallar: "Kanal listesi",
    topoloji: "Servis topolojisi",
    benzer_olaylar: "Benzer geçmiş olaylar"
  };

  var ICON = {
    robot: '<svg class="lumi-bot" viewBox="0 0 48 48" aria-hidden="true">' +
      '<line x1="24" y1="6.5" x2="24" y2="11" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>' +
      '<circle class="lumi-led" cx="24" cy="5" r="2.4" fill="#ffd25e"/>' +
      '<rect x="6.5" y="19" width="4" height="9" rx="2" fill="#dfe9f8"/>' +
      '<rect x="37.5" y="19" width="4" height="9" rx="2" fill="#dfe9f8"/>' +
      '<rect x="10" y="11" width="28" height="24" rx="9" fill="#ffffff"/>' +
      '<rect x="13.5" y="15.5" width="21" height="14" rx="6.5" fill="#173563"/>' +
      '<ellipse class="lumi-eye" cx="19.6" cy="21.6" rx="2.3" ry="2.7" fill="#7fe6ff"/>' +
      '<ellipse class="lumi-eye" cx="28.4" cy="21.6" rx="2.3" ry="2.7" fill="#7fe6ff"/>' +
      '<path d="M20.6 25.6q3.4 2.3 6.8 0" fill="none" stroke="#7fe6ff" stroke-width="1.7" stroke-linecap="round"/>' +
      '<rect x="17" y="36" width="14" height="5.5" rx="2.75" fill="#dfe9f8"/>' +
    '</svg>',
    lumi: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1 2V17h5.2v-1.2c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z"/><path d="M9.6 20.5h4.8"/><path d="M12 7.5v2.2M10.9 8.6h2.2"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    wide: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>',
    clear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>'
  };

  // ------------------------------------------------------------------ yardimcilar
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function inline(s) {
    return s
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  }
  // Agent cevaplari icin kucuk ve guvenli markdown: once kacis, sonra bicim
  function md(text) {
    var satirlar = esc(text || "").split(/\r?\n/), out = [], liste = null, para = [];
    function paraKapat() { if (para.length) { out.push("<p>" + inline(para.join("<br>")) + "</p>"); para = []; } }
    function listeKapat() { if (liste) { out.push("</" + liste + ">"); liste = null; } }
    satirlar.forEach(function (l) {
      var m;
      if (/^\s*$/.test(l)) { paraKapat(); listeKapat(); return; }
      if ((m = l.match(/^\s*#{1,6}\s+(.*)$/))) { paraKapat(); listeKapat(); out.push("<h4>" + inline(m[1]) + "</h4>"); return; }
      if ((m = l.match(/^\s*[-*•]\s+(.*)$/))) { paraKapat(); if (liste !== "ul") { listeKapat(); out.push("<ul>"); liste = "ul"; } out.push("<li>" + inline(m[1]) + "</li>"); return; }
      if ((m = l.match(/^\s*\d+[.)]\s+(.*)$/))) { paraKapat(); if (liste !== "ol") { listeKapat(); out.push("<ol>"); liste = "ol"; } out.push("<li>" + inline(m[1]) + "</li>"); return; }
      listeKapat(); para.push(l);
    });
    paraKapat(); listeKapat();
    return out.join("");
  }
  function saat(d) { d = d ? new Date(d) : new Date(); return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2); }
  function oku() { try { return JSON.parse(sessionStorage.getItem(CFG.storageKey) || "[]"); } catch (e) { return []; } }
  function yaz(v) { try { sessionStorage.setItem(CFG.storageKey, JSON.stringify(v.slice(-40))); } catch (e) {} }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function basliklar() {
    var h = { "Content-Type": "application/json" };
    if (typeof CFG.authHeader === "function") { try { Object.assign(h, CFG.authHeader() || {}); } catch (e) {} }
    return h;
  }

  // ------------------------------------------------------------------ durum
  var gecmis = oku();          // [{rol:'me'|'lumi'|'err', metin, zaman, run_id?, adimlar?, fb?}]
  var baglam = null, baglamEtiket = "";
  var mesgul = false;
  var R = {};                  // DOM referanslari

  // ------------------------------------------------------------------ arayuz
  function kur() {
    var root = el("div", "lumi-root");
    root.innerHTML =
      '<div class="lumi-dock">' +
        '<div class="lumi-greet" role="button" tabindex="0" hidden><button type="button" class="lumi-greet-x" aria-label="Kapat">×</button>' +
          "<b>Merhaba, ben Lumi</b><span>Alarmlar, anomaliler ve servisler hakkında bana soru sorabilirsiniz.</span></div>" +
        '<button type="button" class="lumi-fab" aria-label="Lumi asistanını aç" title="Lumi\'ye sor">' + ICON.robot +
          '<span class="lumi-online" aria-hidden="true"></span><span class="lumi-sr">Lumi</span></button>' +
      "</div>" +
      '<section class="lumi-panel" role="dialog" aria-label="Lumi" hidden>' +
        '<header class="lumi-head">' +
          '<div class="lumi-mark">' + ICON.robot + '<span class="lumi-online" aria-hidden="true"></span></div>' +
          '<div class="lumi-title"><b>Lumi</b><span>SRE asistanı · çevrimiçi</span></div>' +
          '<button type="button" class="lumi-icon" data-act="temizle" title="Sohbeti temizle" aria-label="Sohbeti temizle">' + ICON.clear + "</button>" +
          '<button type="button" class="lumi-icon" data-act="genis" title="Büyüt / küçült" aria-label="Büyüt veya küçült">' + ICON.wide + "</button>" +
          '<button type="button" class="lumi-icon" data-act="kapat" title="Kapat (Esc)" aria-label="Kapat">' + ICON.close + "</button>" +
        "</header>" +
        '<div class="lumi-msgs" aria-live="polite"></div>' +
        '<div class="lumi-ctx" hidden><span>Bağlam:</span><b></b><button type="button" aria-label="Bağlamı kaldır" title="Bağlamı kaldır">×</button></div>' +
        '<form class="lumi-form">' +
          '<textarea class="lumi-input" id="lumi-input" rows="1" placeholder="Lumi\'ye sorun…" aria-label="Soru"></textarea>' +
          '<button type="submit" class="lumi-send" aria-label="Gönder" disabled>' + ICON.send + "</button>" +
        "</form>" +
        '<div class="lumi-foot">Lumi sadece okur, işlem yapmaz. Cevaplar Lumen verisine dayanır; kritik kararlardan önce kaynağı kontrol edin.</div>' +
      "</section>";
    document.body.appendChild(root);

    R.dock = root.querySelector(".lumi-dock");
    R.greet = root.querySelector(".lumi-greet");
    R.fab = root.querySelector(".lumi-fab");
    R.panel = root.querySelector(".lumi-panel");
    R.msgs = root.querySelector(".lumi-msgs");
    R.form = root.querySelector(".lumi-form");
    R.input = root.querySelector(".lumi-input");
    R.send = root.querySelector(".lumi-send");
    R.ctx = root.querySelector(".lumi-ctx");

    R.fab.addEventListener("click", ac);
    R.greet.addEventListener("click", function (e) { if (e.target.closest(".lumi-greet-x")) { selamKapat(); return; } ac(); });
    R.greet.addEventListener("keydown", function (e) { if (e.key === "Enter") ac(); });
    selamGoster();
    root.querySelector('[data-act="kapat"]').addEventListener("click", kapat);
    root.querySelector('[data-act="genis"]').addEventListener("click", function () { R.panel.classList.toggle("lumi-wide"); });
    root.querySelector('[data-act="temizle"]').addEventListener("click", function () {
      if (mesgul) return; gecmis = []; yaz(gecmis); ciz();
    });
    R.ctx.querySelector("button").addEventListener("click", function () { baglamAyarla(null); });

    R.input.addEventListener("input", function () { boyut(); R.send.disabled = mesgul || !R.input.value.trim(); });
    R.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); R.form.requestSubmit ? R.form.requestSubmit() : R.form.dispatchEvent(new Event("submit")); }
    });
    R.form.addEventListener("submit", function (e) { e.preventDefault(); var q = R.input.value.trim(); if (q && !mesgul) gonder(q); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !R.panel.hidden) kapat(); });

    document.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-lumi-sor]");
      if (!b) return;
      e.preventDefault();
      var bg = null;
      try { bg = b.getAttribute("data-lumi-baglam") ? JSON.parse(b.getAttribute("data-lumi-baglam")) : null; } catch (x) {}
      sor(b.getAttribute("data-lumi-sor"), bg, b.getAttribute("data-lumi-etiket"));
    });

    ciz();
  }

  function boyut() { R.input.style.height = "auto"; R.input.style.height = Math.min(R.input.scrollHeight, 140) + "px"; }
  function ac() { selamKapat(); R.panel.hidden = false; R.dock.hidden = true; setTimeout(function () { R.input.focus(); R.msgs.scrollTop = R.msgs.scrollHeight; }, 0); }
  function kapat() { R.panel.hidden = true; R.dock.hidden = false; R.fab.focus(); }
  // Karsilama baloncugu: oturumda bir kez, 1.5 sn sonra, 10 sn gorunur
  function selamGoster() {
    var gosterildi = false; try { gosterildi = sessionStorage.getItem("lumi.selam") === "1"; } catch (e) {}
    if (gosterildi || gecmis.length) return;
    setTimeout(function () { if (R.panel.hidden) { R.greet.hidden = false; setTimeout(selamKapat, 10000); } }, 1500);
  }
  function selamKapat() { if (!R.greet) return; R.greet.hidden = true; try { sessionStorage.setItem("lumi.selam", "1"); } catch (e) {} }

  function baglamAyarla(b, etiket) {
    baglam = b || null;
    baglamEtiket = b ? (etiket || Object.keys(b).map(function (k) { return k + ": " + b[k]; }).join(", ")) : "";
    R.ctx.hidden = !baglam;
    R.ctx.querySelector("b").textContent = baglamEtiket;
  }

  // ------------------------------------------------------------------ cizim
  function ciz() {
    R.msgs.innerHTML = "";
    if (!gecmis.length) {
      var h = el("div", "lumi-hello");
      h.innerHTML = "<p>Merhaba, ben Lumi. Lumen'deki alarm, anomali ve topoloji verilerine bakıp sorularınızı cevaplayabilirim.</p>";
      var chips = el("div", "lumi-chips");
      CFG.oneriler.forEach(function (q) {
        var c = el("button", "lumi-chip"); c.type = "button"; c.textContent = q;
        c.addEventListener("click", function () { gonder(q); });
        chips.appendChild(c);
      });
      h.appendChild(chips);
      R.msgs.appendChild(h);
      return;
    }
    gecmis.forEach(function (m, i) { R.msgs.appendChild(mesajEl(m, i)); });
    R.msgs.scrollTop = R.msgs.scrollHeight;
  }

  function mesajEl(m, i) {
    if (m.rol === "me") {
      var w = el("div", "lumi-msg lumi-me");
      var b = el("div", "lumi-bubble"); b.textContent = m.metin; w.appendChild(b);
      if (m.baglamEtiket) w.appendChild(el("div", "lumi-meta", "Bağlam: " + esc(m.baglamEtiket)));
      return w;
    }
    if (m.rol === "err") {
      var we = el("div", "lumi-msg lumi-err");
      we.appendChild(el("div", "lumi-bubble", esc(m.metin)));
      return we;
    }
    var dis = el("div", "lumi-msg lumi-row");
    dis.appendChild(el("div", "lumi-avatar", ICON.robot));
    var wl = el("div", "lumi-col");
    dis.appendChild(wl);
    wl.appendChild(el("div", "lumi-bubble", md(m.metin)));

    if (m.adimlar && m.adimlar.length) {
      var d = el("details", "lumi-steps");
      var toplam = m.adimlar.reduce(function (t, a) { return t + (a.sure_ms || 0); }, 0);
      d.innerHTML = "<summary>Lumi " + m.adimlar.length + " kaynağa baktı · " + (toplam < 1000 ? toplam + " ms" : (toplam / 1000).toFixed(1) + " sn") + "</summary>";
      var ol = el("ol");
      m.adimlar.forEach(function (a) {
        var p = a.parametreler && Object.keys(a.parametreler).length ? JSON.stringify(a.parametreler) : "";
        ol.appendChild(el("li", a.hata ? "lumi-bad" : "",
          esc(ARAC_ADI[a.arac] || a.arac) +
          (p ? ' <span class="lumi-args">' + esc(p) + "</span>" : "") +
          (a.hata ? " — " + esc(a.hata) : "")));
      });
      d.appendChild(ol);
      wl.appendChild(d);
    }

    var meta = el("div", "lumi-meta");
    meta.appendChild(el("span", "", esc(saat(m.zaman)) + (m.durum === "step_limit" ? " · adım sınırına ulaşıldı" : "")));
    var cp = el("button", "lumi-copy", "Kopyala"); cp.type = "button";
    cp.addEventListener("click", function () {
      var ok = function () { cp.textContent = "Kopyalandı"; setTimeout(function () { cp.textContent = "Kopyala"; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(m.metin).then(ok, function () {});
    });
    meta.appendChild(cp);
    if (m.run_id) {
      var fb = el("span", "lumi-fb");
      fb.innerHTML = '<button type="button" class="lumi-up" aria-pressed="' + (m.fb === true) + '" title="Faydalı">Faydalı</button>' +
                     '<button type="button" class="lumi-down" aria-pressed="' + (m.fb === false) + '" title="Yanlış veya eksik">Yanlış</button>';
      fb.querySelector(".lumi-up").addEventListener("click", function () { geriBildirim(i, true); });
      fb.querySelector(".lumi-down").addEventListener("click", function () { geriBildirim(i, false); });
      meta.appendChild(fb);
    }
    wl.appendChild(meta);
    return dis;
  }

  // ------------------------------------------------------------------ istek
  function onceki() {
    var ciftler = [], s = null;
    gecmis.forEach(function (m) {
      if (m.rol === "me") s = m.metin;
      else if (m.rol === "lumi" && s) { ciftler.push({ soru: s, cevap: (m.metin || "").slice(0, 1200) }); s = null; }
    });
    return ciftler.slice(-CFG.gecmisTur);
  }

  function gonder(soru) {
    if (mesgul) return;
    ac();
    var b = baglam ? Object.assign({}, baglam) : {};
    var once = onceki();
    if (once.length) b.onceki_konusma = once;
    b.sayfa = location.pathname;

    gecmis.push({ rol: "me", metin: soru, zaman: Date.now(), baglamEtiket: baglamEtiket || null });
    yaz(gecmis); ciz();
    R.input.value = ""; boyut();

    mesgul = true; R.send.disabled = true;
    var bekle = el("div", "lumi-msg lumi-row lumi-think");
    bekle.appendChild(el("div", "lumi-avatar", ICON.robot));
    var bb = el("div", "lumi-bubble", '<span class="lumi-dots"><i></i><i></i><i></i></span><span>Lumi verilere bakıyor… <span class="lumi-sn">0</span> sn</span>');
    bekle.appendChild(bb); R.msgs.appendChild(bekle); R.msgs.scrollTop = R.msgs.scrollHeight;
    var bas = Date.now(), sn = bb.querySelector(".lumi-sn");
    var t = setInterval(function () { sn.textContent = Math.round((Date.now() - bas) / 1000); }, 1000);

    var ctrl = window.AbortController ? new AbortController() : null;
    var to = setTimeout(function () { ctrl && ctrl.abort(); }, CFG.timeoutMs);

    fetch(CFG.endpoint, {
      method: "POST", credentials: "same-origin", headers: basliklar(),
      body: JSON.stringify({ soru: soru, baglam: b }), signal: ctrl ? ctrl.signal : undefined
    })
      .then(function (r) {
        if (r.status === 401 || r.status === 403) throw new Error("Oturumunuz sona ermiş görünüyor. Sayfayı yenileyip tekrar giriş yapın.");
        if (r.status === 404) throw new Error("Lumi servisi bulunamadı (404). Agent endpoint'i uygulamaya eklenmemiş olabilir.");
        if (r.status === 503) throw new Error("Lumi şu an yapılandırılmamış (503). Sistem yöneticisine haber verin.");
        if (r.status === 504) throw new Error("Cevap çok uzun sürdü ve ağ geçidi bağlantıyı kesti (504). Soruyu daraltıp tekrar deneyin.");
        if (!r.ok) throw new Error("Lumi cevap veremedi (HTTP " + r.status + ").");
        return r.json();
      })
      .then(function (d) {
        if (!d.cevap) throw new Error(d.hata || "Lumi bu soruya cevap üretemedi.");
        gecmis.push({ rol: "lumi", metin: d.cevap, zaman: Date.now(), run_id: d.run_id, adimlar: d.adimlar || [], durum: d.durum });
      })
      .catch(function (e) {
        var msg = e && e.name === "AbortError" ? "Cevap " + Math.round(CFG.timeoutMs / 1000) + " saniye içinde gelmedi. Soruyu daraltıp tekrar deneyin."
          : (e && e.message && !/Failed to fetch|NetworkError/i.test(e.message) ? e.message : "Lumen'e ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin.");
        gecmis.push({ rol: "err", metin: msg, zaman: Date.now() });
      })
      .then(function () {
        clearInterval(t); clearTimeout(to);
        mesgul = false; R.send.disabled = !R.input.value.trim();
        yaz(gecmis); ciz(); R.input.focus();
      });
  }

  function geriBildirim(i, faydali) {
    var m = gecmis[i]; if (!m || !m.run_id) return;
    m.fb = faydali; yaz(gecmis); ciz();
    fetch(CFG.feedbackEndpoint(m.run_id), {
      method: "POST", credentials: "same-origin", headers: basliklar(), body: JSON.stringify({ faydali: faydali })
    }).catch(function () {});
  }

  function sor(soru, b, etiket) {
    if (b !== undefined) baglamAyarla(b, etiket);
    if (!R.panel) return;
    ac();
    if (soru) gonder(soru);
  }

  window.Lumi = { sor: sor, ac: function () { R.panel && ac(); }, kapat: function () { R.panel && kapat(); }, baglamAyarla: function (b, e) { baglamAyarla(b, e); } };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", kur); else kur();
})();

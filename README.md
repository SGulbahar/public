cat > /data/lumen/frontend/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lumen AIOps</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');
:root{
  --bg:#eef2f8;--m1:#d8e8f8;--m2:#e4d8f8;--m3:#d8f0f0;--m4:#f0e8d8;--m5:#d8f0e4;
  --glass:rgba(255,255,255,0.6);--glass2:rgba(255,255,255,0.84);
  --brd:rgba(255,255,255,0.85);--brd2:rgba(180,200,240,0.38);
  --sh:rgba(90,120,200,0.12);--sh2:rgba(70,100,180,0.07);
  --acc:#2563eb;--acc2:#0891b2;--acc3:#7c3aed;
  --red:#dc2626;--ora:#ea580c;--yel:#ca8a04;--grn:#059669;--tea:#0891b2;
  --txt:#1e293b;--txt2:#64748b;--txt3:#94a3b8;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{font-family:'Plus Jakarta Sans',sans-serif;color:var(--txt);display:flex;flex-direction:column;background:var(--bg)}

/* BG */
.bg{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none}
.bb{position:absolute;border-radius:50%;filter:blur(90px);opacity:.6;animation:drift 20s ease-in-out infinite alternate}
.b1{width:700px;height:700px;background:var(--m1);top:-150px;left:-100px;animation-delay:0s}
.b2{width:550px;height:550px;background:var(--m2);top:15%;right:-80px;animation-delay:-7s}
.b3{width:500px;height:500px;background:var(--m3);bottom:-100px;left:25%;animation-delay:-13s}
.b4{width:420px;height:420px;background:var(--m4);bottom:5%;right:15%;animation-delay:-4s}
.b5{width:380px;height:380px;background:var(--m5);top:40%;left:40%;animation-delay:-10s}
@keyframes drift{from{transform:translate(0,0)scale(1)}to{transform:translate(25px,18px)scale(1.05)}}

/* LOGIN */
#login-screen{position:fixed;inset:0;z-index:9000;display:flex;align-items:center;justify-content:center}
.lcard{width:440px;background:var(--glass2);backdrop-filter:blur(40px)saturate(2);border:1px solid var(--brd);border-radius:22px;padding:40px;box-shadow:0 20px 60px var(--sh);animation:li .5s cubic-bezier(.34,1.56,.64,1)}
@keyframes li{from{opacity:0;transform:translateY(20px)scale(.96)}to{opacity:1;transform:translateY(0)scale(1)}}
.l-hex{width:52px;height:52px;background:linear-gradient(135deg,var(--acc),var(--acc3));clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);margin:0 auto 12px;display:flex;align-items:center;justify-content:center;font-size:22px;box-shadow:0 6px 20px rgba(37,99,235,.35)}
.l-title{font-size:26px;font-weight:800;text-align:center;letter-spacing:.04em;margin-bottom:4px}
.l-sub{font-size:11px;color:var(--txt2);text-align:center;margin-bottom:24px}
.l-lbl{font-size:10px;color:var(--txt2);letter-spacing:.1em;text-transform:uppercase;display:block;font-weight:700;margin-bottom:5px}
.l-input{width:100%;padding:10px 14px;border-radius:9px;border:1px solid rgba(180,200,240,.5);background:rgba(255,255,255,.75);font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--txt);outline:none;transition:all .15s;margin-bottom:14px}
.l-input:focus{border-color:var(--acc);box-shadow:0 0 0 3px rgba(37,99,235,.1)}
.l-err{font-size:11px;color:var(--red);text-align:center;margin-bottom:10px;display:none}
.l-btn{width:100%;padding:13px;border-radius:10px;border:none;background:linear-gradient(135deg,var(--acc),var(--acc3));color:#fff;font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;font-weight:700;cursor:pointer;box-shadow:0 6px 20px rgba(37,99,235,.3);transition:all .2s}
.l-btn:hover{transform:translateY(-1px);box-shadow:0 8px 26px rgba(37,99,235,.4)}
.l-btn:disabled{opacity:.6;cursor:not-allowed;transform:none}
.l-note{font-size:10px;color:var(--txt3);text-align:center;margin-top:10px}

/* APP */
#app{display:none;flex-direction:column;height:100%;position:relative;z-index:1}
#app.on{display:flex}

/* TOPBAR */
.topbar{height:52px;flex-shrink:0;background:rgba(255,255,255,.8);backdrop-filter:blur(30px)saturate(2);border-bottom:1px solid var(--brd);box-shadow:0 2px 14px var(--sh2);display:flex;align-items:center;padding:0 18px;gap:12px;z-index:100;position:relative}
.t-logo{font-size:17px;font-weight:800;letter-spacing:.06em;display:flex;align-items:center;gap:9px}
.t-hex{width:30px;height:30px;background:linear-gradient(135deg,var(--acc),var(--acc3));clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);display:flex;align-items:center;justify-content:center;font-size:12px;box-shadow:0 3px 10px rgba(37,99,235,.3)}
.t-logo span{color:var(--acc)}
.vd{width:1px;height:22px;background:var(--brd2)}
.tl{font-size:10px;color:var(--txt2);letter-spacing:.07em}
.dot{width:7px;height:7px;border-radius:50%;background:var(--grn);box-shadow:0 0 8px rgba(5,150,105,.6);animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.t-right{margin-left:auto;display:flex;align-items:center;gap:10px}
.uc{display:flex;align-items:center;gap:8px;padding:5px 12px 5px 6px;border-radius:20px;background:rgba(255,255,255,.72);border:1px solid var(--brd2)}
.ua{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;color:#fff;font-weight:700}
.un{font-size:11px;font-weight:600;color:var(--txt)}
.rb{font-size:9px;padding:2px 8px;border-radius:10px;font-weight:700;letter-spacing:.06em}
.rb-admin{background:rgba(124,58,237,.12);color:var(--acc3);border:1px solid rgba(124,58,237,.25)}
.rb-sre{background:rgba(37,99,235,.12);color:var(--acc);border:1px solid rgba(37,99,235,.25)}
.rb-noc{background:rgba(8,145,178,.12);color:var(--tea);border:1px solid rgba(8,145,178,.25)}
.rb-viewer{background:rgba(100,116,139,.1);color:var(--txt2);border:1px solid rgba(100,116,139,.2)}
.logout-btn{padding:5px 12px;border-radius:7px;border:1px solid var(--brd2);background:rgba(255,255,255,.7);color:var(--txt2);font-size:10px;cursor:pointer;transition:all .15s}
.logout-btn:hover{border-color:var(--red);color:var(--red)}

/* ROLE BANNER */
.role-banner{padding:5px 18px;font-size:10px;font-weight:600;letter-spacing:.04em;text-align:center;flex-shrink:0}
.rb-banner-admin{background:rgba(124,58,237,.08);color:var(--acc3);border-bottom:1px solid rgba(124,58,237,.15)}
.rb-banner-sre{background:rgba(37,99,235,.07);color:var(--acc);border-bottom:1px solid rgba(37,99,235,.15)}
.rb-banner-noc{background:rgba(8,145,178,.07);color:var(--tea);border-bottom:1px solid rgba(8,145,178,.15)}
.rb-banner-viewer{background:rgba(100,116,139,.06);color:var(--txt2);border-bottom:1px solid rgba(100,116,139,.12)}

/* LAYOUT */
.layout{flex:1;display:flex;overflow:hidden}

/* SIDEBAR */
.sidebar{width:228px;flex-shrink:0;background:rgba(255,255,255,.58);backdrop-filter:blur(24px)saturate(1.8);border-right:1px solid var(--brd);display:flex;flex-direction:column;padding:12px 0;overflow-y:auto}
.ns{padding:0 10px;margin-bottom:4px}
.nl{font-size:9px;letter-spacing:.15em;text-transform:uppercase;color:var(--txt3);padding:8px 10px 4px;font-weight:600}
.ni{display:flex;align-items:center;gap:9px;padding:8px 12px;border-radius:9px;cursor:pointer;font-size:12px;color:var(--txt2);transition:all .15s;margin-bottom:2px;font-weight:600;position:relative;user-select:none}
.ni:hover{background:rgba(37,99,235,.06);color:var(--txt)}
.ni.active{background:rgba(37,99,235,.1);color:var(--acc);border:1px solid rgba(37,99,235,.2)}
.ni.active::before{content:'';position:absolute;left:0;top:6px;bottom:6px;width:3px;background:var(--acc);border-radius:0 2px 2px 0}
.ni-icon{font-size:14px;width:20px;text-align:center}
.nbadge{margin-left:auto;font-size:9px;font-weight:700;padding:2px 6px;border-radius:8px}
.nred{background:rgba(220,38,38,.12);color:var(--red);border:1px solid rgba(220,38,38,.25)}
.nyel{background:rgba(202,138,4,.1);color:var(--yel);border:1px solid rgba(202,138,4,.2)}
.ni.locked{opacity:.32;cursor:not-allowed;pointer-events:none}
.ptag{font-size:8px;padding:1px 5px;border-radius:4px;background:rgba(180,200,240,.3);color:var(--txt3);margin-left:auto}
.sfooter{margin-top:auto;padding:10px 12px;border-top:1px solid rgba(180,200,240,.22)}
.src-chip{display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:6px;font-size:10px;color:var(--txt2);margin-bottom:3px;border:1px solid rgba(180,200,240,.28);background:rgba(255,255,255,.4);font-family:'JetBrains Mono',monospace}
.src-dot{width:6px;height:6px;border-radius:50%}

/* MAIN */
.main{flex:1;overflow-y:auto;padding:20px;position:relative;z-index:1}
.page{display:none}
.page.active{display:block;animation:fi .25s ease}
@keyframes fi{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}

/* PAGE HEADER */
.phead{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px}
.pt{font-size:22px;font-weight:800;margin-bottom:4px}
.ps{font-size:11px;color:var(--txt3);letter-spacing:.04em}
.pactions{display:flex;gap:8px;align-items:center}

/* CARDS */
.card{background:var(--glass);backdrop-filter:blur(20px)saturate(1.6);border:1px solid var(--brd);border-radius:14px;padding:18px;box-shadow:0 4px 20px var(--sh2),0 1px 0 rgba(255,255,255,.85) inset;position:relative;overflow:hidden;transition:box-shadow .2s}
.card:hover{box-shadow:0 6px 28px var(--sh)}
.ctitle{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--txt2);font-weight:700;margin-bottom:12px;display:flex;align-items:center;gap:7px}

/* STAT */
.sg{display:grid;gap:14px;margin-bottom:18px}
.sg4{grid-template-columns:repeat(4,1fr)}
.sg3{grid-template-columns:repeat(3,1fr)}
.sc{background:var(--glass);backdrop-filter:blur(20px)saturate(1.6);border:1px solid var(--brd);border-radius:14px;padding:16px 18px;box-shadow:0 4px 20px var(--sh2);position:relative;overflow:hidden}
.sv{font-size:28px;font-weight:700;font-family:'JetBrains Mono',monospace;line-height:1;margin-bottom:3px}
.sl{font-size:9px;color:var(--txt2);letter-spacing:.1em;text-transform:uppercase;margin-bottom:5px}
.ss{font-size:10px;color:var(--txt3)}
.sglow{position:absolute;top:-10px;right:-10px;width:60px;height:60px;border-radius:50%;opacity:.1;filter:blur(14px)}

/* GRIDS */
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:16px}
.gm{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:16px}

/* BUTTONS */
.btn{padding:7px 14px;border-radius:7px;border:1px solid var(--brd2);background:rgba(255,255,255,.72);color:var(--txt2);font-size:11px;cursor:pointer;font-family:'Plus Jakarta Sans',sans-serif;transition:all .15s}
.btn:hover{border-color:var(--acc);color:var(--acc);background:rgba(37,99,235,.05)}
.btn.p{background:rgba(37,99,235,.1);border-color:rgba(37,99,235,.38);color:var(--acc);font-weight:600}
.btn.g{background:rgba(5,150,105,.1);border-color:rgba(5,150,105,.3);color:var(--grn);font-weight:600}
.btn.r{background:rgba(220,38,38,.08);border-color:rgba(220,38,38,.28);color:var(--red)}

/* TAGS */
.tag{font-size:9px;padding:2px 7px;border-radius:4px;font-weight:600;letter-spacing:.05em;display:inline-block}
.t-r{background:rgba(220,38,38,.1);color:var(--red);border:1px solid rgba(220,38,38,.2)}
.t-o{background:rgba(234,88,12,.1);color:var(--ora);border:1px solid rgba(234,88,12,.2)}
.t-y{background:rgba(202,138,4,.1);color:var(--yel);border:1px solid rgba(202,138,4,.2)}
.t-g{background:rgba(5,150,105,.1);color:var(--grn);border:1px solid rgba(5,150,105,.2)}
.t-b{background:rgba(37,99,235,.1);color:var(--acc);border:1px solid rgba(37,99,235,.2)}
.t-p{background:rgba(124,58,237,.1);color:var(--acc3);border:1px solid rgba(124,58,237,.2)}
.t-gr{background:rgba(100,116,139,.08);color:var(--txt2);border:1px solid rgba(100,116,139,.18)}

/* ANOMALY */
.aitem{display:flex;align-items:flex-start;gap:11px;padding:11px;border-radius:10px;border:1px solid transparent;cursor:pointer;transition:all .15s;margin-bottom:7px;animation:fi .3s ease}
.aitem:hover{background:rgba(37,99,235,.03);border-color:rgba(180,200,240,.3)}
.aitem.d{border-left:3px solid var(--red)}
.aitem.h{border-left:3px solid var(--ora)}
.aitem.w{border-left:3px solid var(--yel)}
.asev{font-size:8px;font-weight:700;padding:3px 7px;border-radius:4px;text-transform:uppercase;letter-spacing:.08em;white-space:nowrap;margin-top:1px}
.sd{background:rgba(220,38,38,.1);color:var(--red);border:1px solid rgba(220,38,38,.25)}
.sh2b{background:rgba(234,88,12,.1);color:var(--ora);border:1px solid rgba(234,88,12,.25)}
.sw{background:rgba(202,138,4,.08);color:var(--yel);border:1px solid rgba(202,138,4,.2)}
.abody{flex:1;min-width:0}
.aname{font-size:12px;font-weight:700;color:var(--txt);margin-bottom:2px}
.adesc{font-size:10px;color:var(--txt2);margin-bottom:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:'JetBrains Mono',monospace}
.ameta{display:flex;gap:5px;flex-wrap:wrap;align-items:center}

/* TABLES */
.tbl{width:100%;border-collapse:collapse;font-size:10px}
.tbl thead th{position:sticky;top:0;background:rgba(255,255,255,.9);backdrop-filter:blur(10px);padding:7px 10px;text-align:left;font-size:9px;color:var(--txt2);letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid rgba(180,200,240,.35);font-weight:600;white-space:nowrap}
.tbl tbody tr{border-bottom:1px solid rgba(180,200,240,.12);cursor:pointer;transition:background .1s}
.tbl tbody tr:hover{background:rgba(37,99,235,.03)}
.tbl td{padding:5px 10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px;font-family:'JetBrains Mono',monospace;font-size:10px}

/* LOADING */
.loading{text-align:center;padding:40px;color:var(--txt3);font-size:12px}
.spinner{width:24px;height:24px;border:3px solid rgba(37,99,235,.2);border-top-color:var(--acc);border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 12px}
@keyframes spin{to{transform:rotate(360deg)}}

/* MODAL */
.overlay{display:none;position:fixed;inset:0;background:rgba(200,215,240,.45);backdrop-filter:blur(16px)saturate(1.5);z-index:5000;align-items:center;justify-content:center}
.overlay.open{display:flex}
.modal{background:rgba(255,255,255,.9);backdrop-filter:blur(40px)saturate(2.5);border:1px solid var(--brd);border-radius:16px;width:580px;max-height:82vh;overflow-y:auto;box-shadow:0 20px 60px rgba(90,120,200,.2);animation:mi .22s cubic-bezier(.34,1.56,.64,1)}
@keyframes mi{from{opacity:0;transform:scale(.94)translateY(12px)}to{opacity:1;transform:scale(1)translateY(0)}}
.mh{padding:18px 22px 14px;border-bottom:1px solid rgba(180,200,240,.3);display:flex;align-items:flex-start;justify-content:space-between}
.mb{padding:16px 22px 22px}
.mclose{background:rgba(180,200,240,.2);border:1px solid rgba(180,200,240,.4);color:var(--txt2);font-size:14px;cursor:pointer;padding:4px 9px;border-radius:6px;line-height:1;transition:all .15s}
.mclose:hover{background:rgba(220,38,38,.1);color:var(--red)}
.dr{display:flex;gap:8px;margin-bottom:8px}
.dk{font-size:10px;color:var(--txt2);min-width:130px;padding-top:2px}
.dv{font-size:11px;color:var(--txt);flex:1;line-height:1.6;font-family:'JetBrains Mono',monospace}
.divline{height:1px;background:rgba(180,200,240,.3);margin:12px 0}
.ai-box{background:linear-gradient(135deg,rgba(124,58,237,.07),rgba(37,99,235,.05));border:1px solid rgba(124,58,237,.2);border-radius:10px;padding:12px 14px;margin-top:10px}
.ai-lbl{font-size:9px;color:var(--acc3);letter-spacing:.12em;margin-bottom:7px;font-weight:700}
.ai-txt{font-size:11px;color:var(--txt);line-height:1.75}

/* PROG */
.pr{display:flex;align-items:center;gap:8px;margin-bottom:7px}
.pl{font-size:10px;color:var(--txt2);min-width:130px}
.pt2{flex:1;height:6px;background:rgba(180,200,240,.22);border-radius:3px;overflow:hidden}
.pf{height:100%;border-radius:3px;transition:width .8s}
.pv{font-size:10px;color:var(--txt2);min-width:36px;text-align:right;font-weight:600}

/* TIMELINE */
.tl{position:relative;padding-left:22px}
.tl::before{content:'';position:absolute;left:7px;top:0;bottom:0;width:1px;background:rgba(180,200,240,.4)}
.tli{position:relative;margin-bottom:14px}
.tld{position:absolute;left:-18px;top:4px;width:8px;height:8px;border-radius:50%;border:2px solid}
.tlt{font-size:9px;color:var(--txt3);margin-bottom:2px;font-family:'JetBrains Mono',monospace}
.tlh{font-size:11px;font-weight:700;margin-bottom:2px}
.tlb{font-size:10px;color:var(--txt2)}

/* TOAST */
.toast-wrap{position:fixed;bottom:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{padding:11px 16px;border-radius:10px;font-size:11px;font-weight:600;background:rgba(255,255,255,.95);backdrop-filter:blur(20px);border:1px solid var(--brd);box-shadow:0 8px 24px var(--sh);animation:toast-in .3s cubic-bezier(.34,1.56,.64,1);display:flex;align-items:center;gap:8px;max-width:340px;pointer-events:all}
@keyframes toast-in{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:translateX(0)}}
.toast.s{border-color:rgba(5,150,105,.3);background:rgba(240,255,248,.97)}
.toast.e{border-color:rgba(220,38,38,.25);background:rgba(255,242,242,.97)}
.toast.i{border-color:rgba(37,99,235,.25);background:rgba(240,245,255,.97)}
.toast.w{border-color:rgba(202,138,4,.25);background:rgba(255,252,235,.97)}

/* TOGGLE */
.toggle{width:34px;height:18px;border-radius:9px;border:none;cursor:pointer;position:relative;transition:background .2s;flex-shrink:0}
.toggle.on{background:var(--grn)}.toggle.off{background:rgba(180,200,240,.5)}
.toggle::after{content:'';position:absolute;top:2px;width:14px;height:14px;border-radius:50%;background:#fff;transition:left .2s;box-shadow:0 1px 4px rgba(0,0,0,.2)}
.toggle.on::after{left:17px}.toggle.off::after{left:2px}

/* SCROLLBAR */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(180,200,240,.5);border-radius:2px}
</style>
</head>
<body>
<div class="bg"><div class="bb b1"></div><div class="bb b2"></div><div class="bb b3"></div><div class="bb b4"></div><div class="bb b5"></div></div>

<!-- LOGIN -->
<div id="login-screen">
<div class="lcard">
  <div class="l-hex">⬡</div>
  <div class="l-title">Lumen AIOps</div>
  <div class="l-sub">Bankacılık Operasyon Merkezi · Unified AIOps Platform</div>
  <label class="l-lbl">Kullanıcı Adı</label>
  <input class="l-input" id="l-user" placeholder="kullanıcı adı" autocomplete="username"/>
  <label class="l-lbl">Şifre</label>
  <input class="l-input" id="l-pass" type="password" placeholder="şifre" autocomplete="current-password"
    onkeydown="if(event.key==='Enter')doLogin()"/>
  <div class="l-err" id="l-err">Kullanıcı adı veya şifre hatalı</div>
  <button class="l-btn" id="l-btn" onclick="doLogin()">🔐 Giriş Yap</button>
  <div class="l-note">LDAP / Active Directory + Local fallback</div>
</div>
</div>

<!-- APP -->
<div id="app">
<div class="topbar">
  <div class="t-logo"><div class="t-hex">⬡</div>Lumen <span>AIOps</span></div>
  <div class="vd"></div>
  <div class="dot" id="api-dot"></div>
  <div class="tl" id="t-ctx">Bankacılık Operasyon Merkezi</div>
  <div class="vd"></div>
  <div class="tl" id="t-page">Dashboard</div>
  <div class="t-right">
    <div class="tl" id="t-clock" style="font-family:'JetBrains Mono',monospace">--:--:--</div>
    <div class="uc">
      <div class="ua" id="u-av" style="background:linear-gradient(135deg,var(--acc),var(--acc3))">?</div>
      <div class="un" id="u-nm">—</div>
      <div class="rb rb-admin" id="u-rb">—</div>
    </div>
    <button class="logout-btn" onclick="doLogout()">↩ Çıkış</button>
  </div>
</div>
<div class="role-banner rb-banner-admin" id="role-banner"></div>

<div class="layout">
<div class="sidebar" id="sidebar"></div>
<div class="main" id="main-area"></div>
</div>
</div>

<!-- MODAL -->
<div class="overlay" id="modal-overlay" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="mh">
      <div><div id="m-badge" style="margin-bottom:6px"></div><div id="m-title" style="font-size:17px;font-weight:800;color:var(--txt)"></div></div>
      <button class="mclose" onclick="closeModal()">✕</button>
    </div>
    <div class="mb" id="m-body"></div>
  </div>
</div>

<!-- TOAST -->
<div class="toast-wrap" id="toast-wrap"></div>

<script>
// ══════════════════════════════════════
// API
// ══════════════════════════════════════
const API = window.location.origin;
let TOKEN = localStorage.getItem('lumen_token') || '';
let CURRENT_USER = {};
let AUTO_REFRESH = null;

async function apiFetch(path, opts = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(TOKEN ? {'Authorization': `Bearer ${TOKEN}`} : {}),
    ...opts.headers,
  };
  const resp = await fetch(API + path, { ...opts, headers });
  if (resp.status === 401) { doLogout(); return null; }
  if (!resp.ok) throw new Error(`API ${resp.status}: ${path}`);
  return resp.json();
}

// ══════════════════════════════════════
// AUTH
// ══════════════════════════════════════
const ROLE_CONFIG = {
  'Admin':       { cls:'rb-admin', bannerCls:'rb-banner-admin', bannerText:'👑 Admin — Tam erişim · Tüm modüller · Kullanıcı yönetimi aktif', color:'#7c3aed' },
  'SRE Lead':    { cls:'rb-sre',   bannerCls:'rb-banner-sre',   bannerText:'🛡️ SRE Lead — Anomali + Agent + Runbook · Aksiyon onaylama', color:'#2563eb' },
  'NOC Analyst': { cls:'rb-noc',   bannerCls:'rb-banner-noc',   bannerText:'📊 NOC Analyst — Log ve anomali izleme · SRE görüntüleme', color:'#0891b2' },
  'Viewer':      { cls:'rb-viewer',bannerCls:'rb-banner-viewer',bannerText:'👁️ Viewer — Sadece dashboard ve anomali listesi', color:'#94a3b8' },
};

async function doLogin() {
  const user = document.getElementById('l-user').value.trim();
  const pass = document.getElementById('l-pass').value;
  if (!user || !pass) { showLoginErr('Kullanıcı adı ve şifre gerekli'); return; }

  const btn = document.getElementById('l-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Giriş yapılıyor…';

  try {
    const form = new URLSearchParams();
    form.append('username', user);
    form.append('password', pass);

    const resp = await fetch(API + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    });

    if (!resp.ok) {
      showLoginErr('Kullanıcı adı veya şifre hatalı');
      btn.disabled = false;
      btn.textContent = '🔐 Giriş Yap';
      return;
    }

    const data = await resp.json();
    TOKEN = data.access_token;
    localStorage.setItem('lumen_token', TOKEN);
    CURRENT_USER = { username: data.username, roles: data.roles };

    // Kullanıcı bilgisini al
    const me = await apiFetch('/auth/me');
    if (me) {
      CURRENT_USER.permissions = me.permissions;
    }

    startApp();
  } catch(e) {
    showLoginErr('Sunucuya bağlanılamadı');
    btn.disabled = false;
    btn.textContent = '🔐 Giriş Yap';
  }
}

function showLoginErr(msg) {
  const el = document.getElementById('l-err');
  el.textContent = msg;
  el.style.display = 'block';
}

function doLogout() {
  TOKEN = '';
  CURRENT_USER = {};
  localStorage.removeItem('lumen_token');
  if (AUTO_REFRESH) clearInterval(AUTO_REFRESH);
  document.getElementById('app').classList.remove('on');
  document.getElementById('login-screen').style.display = 'flex';
  document.getElementById('l-err').style.display = 'none';
  document.getElementById('l-btn').disabled = false;
  document.getElementById('l-btn').textContent = '🔐 Giriş Yap';
}

function startApp() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('app').classList.add('on');

  // Topbar
  const role = CURRENT_USER.roles?.[0] || 'Viewer';
  const rc = ROLE_CONFIG[role] || ROLE_CONFIG['Viewer'];
  document.getElementById('u-av').textContent = CURRENT_USER.username?.slice(0,2).toUpperCase() || '?';
  document.getElementById('u-av').style.background = `linear-gradient(135deg,${rc.color},${rc.color}aa)`;
  document.getElementById('u-nm').textContent = CURRENT_USER.username;
  document.getElementById('u-rb').textContent = role;
  document.getElementById('u-rb').className = `rb ${rc.cls}`;
  document.getElementById('role-banner').textContent = rc.bannerText;
  document.getElementById('role-banner').className = `role-banner ${rc.bannerCls}`;

  buildSidebar();
  buildPages();
  showPage('dashboard');

  // Otomatik yenileme 60s
  AUTO_REFRESH = setInterval(() => {
    const activePage = document.querySelector('.page.active');
    if (activePage?.id === 'page-dashboard') loadDashboard();
    if (activePage?.id === 'page-anomalies') loadAnomalies();
  }, 60000);

  // Saat
  setInterval(() => {
    document.getElementById('t-clock').textContent = new Date().toTimeString().slice(0,8);
  }, 1000);

  // API sağlık kontrolü
  checkAPIHealth();
  setInterval(checkAPIHealth, 30000);
}

async function checkAPIHealth() {
  try {
    const data = await apiFetch('/health');
    const dot = document.getElementById('api-dot');
    if (data) {
      dot.style.background = 'var(--grn)';
      dot.style.boxShadow = '0 0 8px rgba(5,150,105,.6)';
    }
  } catch {
    const dot = document.getElementById('api-dot');
    dot.style.background = 'var(--red)';
    dot.style.boxShadow = '0 0 8px rgba(220,38,38,.6)';
  }
}

// Sayfa yüklendiğinde token varsa direkt giriş
window.addEventListener('load', async () => {
  if (TOKEN) {
    try {
      const me = await apiFetch('/auth/me');
      if (me) {
        CURRENT_USER = { username: me.username, roles: me.roles, permissions: me.permissions };
        startApp();
        return;
      }
    } catch {}
    TOKEN = '';
    localStorage.removeItem('lumen_token');
  }
});

// ══════════════════════════════════════
// PERMISSION
// ══════════════════════════════════════
function hasPerm(perm) {
  return CURRENT_USER.permissions?.includes(perm) || false;
}
function hasRole(role) {
  return CURRENT_USER.roles?.includes(role) || false;
}
function isAdmin() { return hasRole('Admin'); }
function isSRE() { return hasRole('SRE Lead') || isAdmin(); }
function isNOC() { return hasRole('NOC Analyst') || isSRE(); }

// ══════════════════════════════════════
// SIDEBAR
// ══════════════════════════════════════
function buildSidebar() {
  let html = '';

  html += `<div class="ns"><div class="nl">Genel</div>
    <div class="ni" id="nav-dashboard" onclick="showPage('dashboard',this)"><span class="ni-icon">◈</span>Dashboard</div>
  </div>`;

  html += `<div class="ns"><div class="nl">Faz 1 — Log Anomalisi</div>
    <div class="ni" id="nav-anomalies" onclick="showPage('anomalies',this)"><span class="ni-icon">⚡</span>Anomaliler<span class="nbadge nred" id="anom-count-badge">—</span></div>`;

  if (!hasRole('Viewer')) {
    html += `<div class="ni" id="nav-errorcodes" onclick="showPage('errorcodes',this)"><span class="ni-icon">🔢</span>Hata Kodları</div>`;
    html += `<div class="ni" id="nav-runs" onclick="showPage('runs',this)"><span class="ni-icon">📋</span>Detection Runs</div>`;
  }
  html += `</div>`;

  if (!hasRole('Viewer')) {
    html += `<div class="ns"><div class="nl">SRE Agent</div>`;
    if (isSRE()) {
      html += `<div class="ni" id="nav-sre" onclick="showPage('sre',this)"><span class="ni-icon">🤖</span>Aksiyon Merkezi<span class="nbadge nyel" id="sre-count-badge">—</span></div>`;
    } else {
      html += `<div class="ni" id="nav-sre" onclick="showPage('sre',this)"><span class="ni-icon">🤖</span>Aksiyon Merkezi<span class="ptag">👁</span></div>`;
    }
    html += `</div>`;
  }

  html += `<div class="ns"><div class="nl">İleride Gelecek</div>
    <div class="ni locked"><span class="ni-icon">📈</span>Metrik Anomalisi<span class="ptag">Faz 2</span></div>
    <div class="ni locked"><span class="ni-icon">⬡</span>Topoloji<span class="ptag">Faz 3</span></div>
    <div class="ni locked"><span class="ni-icon">🔗</span>Korelasyon<span class="ptag">Faz 5</span></div>
  </div>`;

  if (isAdmin()) {
    html += `<div class="ns"><div class="nl">Yönetim</div>
      <div class="ni" id="nav-users" onclick="showPage('users',this)"><span class="ni-icon">👥</span>Kullanıcılar</div>
      <div class="ni" id="nav-settings" onclick="showPage('settings',this)"><span class="ni-icon">⚙️</span>Sistem Ayarları</div>
    </div>`;
  }

  html += `<div class="sfooter">
    <div style="font-size:9px;color:var(--txt3);letter-spacing:.08em;margin-bottom:6px;font-weight:600;text-transform:uppercase">Veri Kaynakları</div>
    <div class="src-chip"><div class="src-dot" id="src-logstash" style="background:var(--grn);box-shadow:0 0 5px var(--grn)"></div>Logstash Push</div>
    <div class="src-chip"><div class="src-dot" style="background:var(--grn);box-shadow:0 0 5px var(--grn)"></div>LLM Servisi</div>
    <div class="src-chip"><div class="src-dot" style="background:var(--grn);box-shadow:0 0 5px var(--grn)"></div>Zabbix API</div>
  </div>`;

  document.getElementById('sidebar').innerHTML = html;
}

// ══════════════════════════════════════
// PAGES
// ══════════════════════════════════════
function buildPages() {
  document.getElementById('main-area').innerHTML = `
    <div class="page" id="page-dashboard"></div>
    <div class="page" id="page-anomalies"></div>
    <div class="page" id="page-errorcodes"></div>
    <div class="page" id="page-runs"></div>
    <div class="page" id="page-sre"></div>
    <div class="page" id="page-users"></div>
    <div class="page" id="page-settings"></div>
  `;
}

function showPage(name, navEl) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.ni').forEach(n => n.classList.remove('active'));
  const pg = document.getElementById('page-' + name);
  if (pg) pg.classList.add('active');
  if (navEl) navEl.classList.add('active');
  else document.getElementById('nav-' + name)?.classList.add('active');

  const pageNames = {
    dashboard:'Dashboard', anomalies:'Anomaliler',
    errorcodes:'Hata Kodları', runs:'Detection Runs',
    sre:'SRE Agent', users:'Kullanıcılar', settings:'Sistem Ayarları'
  };
  document.getElementById('t-page').textContent = pageNames[name] || name;

  // Sayfa yükle
  const loaders = {
    dashboard: loadDashboard,
    anomalies: loadAnomalies,
    errorcodes: loadErrorCodes,
    runs: loadRuns,
    sre: loadSRE,
    users: loadUsers,
    settings: loadSettings,
  };
  loaders[name]?.();
}

// ══════════════════════════════════════
// DASHBOARD
// ══════════════════════════════════════
async function loadDashboard() {
  const el = document.getElementById('page-dashboard');
  el.innerHTML = loadingHtml();

  try {
    const [stats, anomalies] = await Promise.all([
      apiFetch('/api/v1/dashboard/stats'),
      apiFetch('/api/v1/anomalies?limit=5'),
    ]);

    // Badge güncelle
    if (anomalies) {
      document.getElementById('anom-count-badge').textContent = anomalies.length;
    }
    if (stats?.pending_actions !== undefined) {
      const badge = document.getElementById('sre-count-badge');
      if (badge) badge.textContent = stats.pending_actions;
    }

    el.innerHTML = `
      <div class="phead">
        <div><div class="pt">Operasyon Merkezi</div>
        <div class="ps">Gerçek zamanlı · Otomatik yenileme 60s · ${new Date().toLocaleString('tr-TR')}</div></div>
        ${isAdmin() ? `<div class="pactions"><button class="btn p" onclick="showPage('settings')">⚙ Ayarlar</button></div>` : ''}
      </div>
      <div class="sg sg4">
        <div class="sc"><div class="sglow" style="background:var(--red)"></div>
          <div class="sv" style="color:var(--red)">${stats?.active_anomalies ?? '—'}</div>
          <div class="sl">Aktif Anomali</div>
          <div class="ss">Zabbix'e gönderilmedi</div>
        </div>
        <div class="sc"><div class="sglow" style="background:var(--yel)"></div>
          <div class="sv" style="color:var(--yel)">${stats?.pending_actions ?? '—'}</div>
          <div class="sl">Onay Bekleyen</div>
          <div class="ss">SRE Agent aksiyonu</div>
        </div>
        <div class="sc"><div class="sglow" style="background:var(--acc)"></div>
          <div class="sv" style="color:var(--acc)">${stats?.total_anomalies ?? '—'}</div>
          <div class="sl">Toplam Anomali</div>
          <div class="ss">Tüm zamanlar</div>
        </div>
        <div class="sc"><div class="sglow" style="background:var(--grn)"></div>
          <div class="sv" style="color:${stats?.last_run?.status === 'ok' ? 'var(--grn)' : 'var(--red)'};font-size:18px">
            ${stats?.last_run?.status === 'ok' ? '✓ NORMAL' : stats?.last_run?.status?.toUpperCase() ?? '—'}
          </div>
          <div class="sl">Son Döngü</div>
          <div class="ss">${stats?.last_run?.finished_at ? new Date(stats.last_run.finished_at).toLocaleTimeString('tr-TR') : '—'}</div>
        </div>
      </div>
      <div class="gm">
        <div class="card">
          <div class="ctitle">⚡ Son Anomaliler</div>
          ${anomalies?.length ? anomaliesHtml(anomalies, true) : emptyHtml('Henüz anomali yok')}
        </div>
        <div class="card">
          <div class="ctitle">📋 Son Döngü Özeti</div>
          ${stats?.last_run ? `
            <div class="pr"><div class="pl">Durum</div><span class="tag ${stats.last_run.status === 'ok' ? 't-g' : 't-r'}">${stats.last_run.status}</span></div>
            <div class="pr"><div class="pl">İşlenen Log</div><div style="font-family:'JetBrains Mono',monospace;font-size:11px">${stats.last_run.logs_processed?.toLocaleString() ?? '—'}</div></div>
            <div class="pr"><div class="pl">Bulunan Anomali</div><div style="font-family:'JetBrains Mono',monospace;font-size:11px">${stats.last_run.anomalies_found ?? '—'}</div></div>
          ` : emptyHtml('Henüz döngü çalışmadı')}
        </div>
      </div>
    `;
  } catch(e) {
    el.innerHTML = errorHtml(e.message);
  }
}

// ══════════════════════════════════════
// ANOMALİLER
// ══════════════════════════════════════
async function loadAnomalies(severity = 'all') {
  const el = document.getElementById('page-anomalies');
  el.innerHTML = `
    <div class="phead">
      <div><div class="pt">Anomali Merkezi</div>
      <div class="ps">Log tabanlı · Z-Score + IF + Kural Motoru · Hata kodu zenginleştirmesi</div></div>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap" id="anom-filters">
      <button class="btn ${severity==='all'?'p':''}" onclick="loadAnomalies('all')">Tümü</button>
      <button class="btn ${severity==='DISASTER'?'p':''}" onclick="loadAnomalies('DISASTER')">Kritik</button>
      <button class="btn ${severity==='HIGH'?'p':''}" onclick="loadAnomalies('HIGH')">Yüksek</button>
      <button class="btn ${severity==='WARNING'?'p':''}" onclick="loadAnomalies('WARNING')">Uyarı</button>
    </div>
    <div id="anom-list-container">${loadingHtml()}</div>
  `;

  try {
    const url = severity === 'all'
      ? '/api/v1/anomalies?limit=100'
      : `/api/v1/anomalies?limit=100&severity=${severity}`;
    const anomalies = await apiFetch(url);
    document.getElementById('anom-list-container').innerHTML =
      anomalies?.length ? anomaliesHtml(anomalies, false) : emptyHtml('Anomali bulunamadı');

    document.getElementById('anom-count-badge').textContent = anomalies?.length ?? 0;
  } catch(e) {
    document.getElementById('anom-list-container').innerHTML = errorHtml(e.message);
  }
}

function anomaliesHtml(list, compact) {
  return list.map(a => {
    const sevMap = {DISASTER:'d', HIGH:'h', WARNING:'w'};
    const sevLbl = {DISASTER:'KRİTİK', HIGH:'YÜKSEK', WARNING:'UYARI'};
    const sevCls = {d:'sd', h:'sh2b', w:'sw'};
    const s = sevMap[a.severity] || 'w';
    const canClick = hasPerm('log.anomalies.view');
    return `<div class="aitem ${s}" ${canClick ? `onclick="openAnomModal(${a.id})"` : 'style="cursor:default"'}>
      <div>
        <div class="asev ${sevCls[s]}">${sevLbl[a.severity] || a.severity}</div>
      </div>
      <div class="abody">
        <div class="aname">${a.service} [${a.channel_code}]</div>
        <div class="adesc">${a.summary || '—'}</div>
        <div class="ameta">
          <span class="tag t-b">${a.anomaly_type || '—'}</span>
          ${a.result_category ? `<span class="tag ${a.result_category==='SYS'?'t-o':'t-r'}">${a.result_category}: ${a.result_desc || a.result_code}</span>` : ''}
          <span style="font-size:9px;color:var(--txt3)">${a.detected_at ? new Date(a.detected_at).toLocaleTimeString('tr-TR') : '—'}</span>
          ${a.zabbix_sent ? '<span class="tag t-g">✓ Zabbix</span>' : '<span class="tag t-y">⏳ Bekliyor</span>'}
        </div>
      </div>
    </div>`;
  }).join('');
}

async function openAnomModal(id) {
  try {
    const a = await apiFetch(`/api/v1/anomalies/${id}`);
    if (!a) return;

    const sevMap = {DISASTER:'sd', HIGH:'sh2b', WARNING:'sw'};
    const sevLbl = {DISASTER:'KRİTİK', HIGH:'YÜKSEK', WARNING:'UYARI'};

    document.getElementById('m-badge').innerHTML =
      `<span class="asev ${sevMap[a.severity] || 'sw'}">${sevLbl[a.severity] || a.severity}</span>`;
    document.getElementById('m-title').textContent = `${a.service} [${a.channel_code}]`;
    document.getElementById('m-body').innerHTML = `
      <div class="dr"><div class="dk">Anomali Tipi:</div><div class="dv">${a.anomaly_type || '—'}</div></div>
      <div class="dr"><div class="dk">Servis:</div><div class="dv" style="color:var(--acc)">${a.service}</div></div>
      <div class="dr"><div class="dk">Kanal:</div><div class="dv">${a.channel_code}</div></div>
      <div class="dr"><div class="dk">Skor:</div><div class="dv" style="color:var(--red);font-weight:700">${a.score ?? '—'}</div></div>
      <div class="dr"><div class="dk">Hata Oranı:</div><div class="dv">%${((a.error_rate||0)*100).toFixed(1)}</div></div>
      <div class="dr"><div class="dk">Elapsed Ort.:</div><div class="dv">${a.elapsed_mean?.toFixed(0) ?? '—'} ms</div></div>
      <div class="dr"><div class="dk">Result Kodu:</div><div class="dv">
        ${a.result_category ? `<span class="tag ${a.result_category==='SYS'?'t-o':'t-r'}">${a.result_category}</span>` : ''}
        ${a.result_code ?? ''} ${a.result_desc ? '— ' + a.result_desc : ''}
      </div></div>
      <div class="dr"><div class="dk">Zabbix:</div><div class="dv">
        ${a.zabbix_sent ? `<span class="tag t-g">✓ Gönderildi · ${a.zabbix_id || ''}</span>` : '<span class="tag t-y">⏳ Bekliyor</span>'}
      </div></div>
      <div class="dr"><div class="dk">Tespit:</div><div class="dv">${a.detected_at ? new Date(a.detected_at).toLocaleString('tr-TR') : '—'}</div></div>
      <div class="divline"></div>
      <div style="font-size:11px;color:var(--txt2);line-height:1.7;margin-bottom:10px">${a.details || '—'}</div>
      ${a.ai_analysis ? `
        <div class="ai-box">
          <div class="ai-lbl">🤖 AI KÖK NEDEN ANALİZİ</div>
          <div class="ai-txt">${a.ai_analysis}</div>
        </div>` : ''}
      ${isSRE() ? `
        <div style="margin-top:14px;display:flex;gap:8px">
          <button class="btn g" onclick="closeModal();toast('SRE Agent devreye alındı','i')">🤖 Agent'a Gönder</button>
          <button class="btn" onclick="closeModal()">Kapat</button>
        </div>` : `<div style="margin-top:14px"><button class="btn" onclick="closeModal()">Kapat</button></div>`}
    `;
    document.getElementById('modal-overlay').classList.add('open');
  } catch(e) {
    toast('Anomali detayı yüklenemedi: ' + e.message, 'e');
  }
}

// ══════════════════════════════════════
// HATA KODLARI
// ══════════════════════════════════════
async function loadErrorCodes() {
  const el = document.getElementById('page-errorcodes');
  el.innerHTML = `
    <div class="phead">
      <div><div class="pt">Hata Kodu Sözlüğü</div>
      <div class="ps">error_codes.csv → PostgreSQL → RAM cache</div></div>
      ${isAdmin() ? `<div class="pactions"><button class="btn p" onclick="reloadErrorCodes()">↑ CSV Yenile</button></div>` : ''}
    </div>
    <div id="ec-content">${loadingHtml()}</div>
  `;

  try {
    const codes = await apiFetch('/api/v1/error-codes');
    const sysCnt = codes?.filter(c => c.category === 'SYS').length || 0;
    const bizCnt = codes?.filter(c => c.category === 'BIZ').length || 0;

    document.getElementById('ec-content').innerHTML = `
      <div class="sg sg3" style="margin-bottom:16px">
        <div class="sc"><div class="sv" style="color:var(--acc);font-size:22px">${codes?.length ?? 0}</div><div class="sl">Toplam Kod</div></div>
        <div class="sc"><div class="sv" style="color:var(--ora);font-size:22px">${sysCnt}</div><div class="sl">Sistem Hatası</div><div class="ss">result 1–7499</div></div>
        <div class="sc"><div class="sv" style="color:var(--red);font-size:22px">${bizCnt}</div><div class="sl">İş Hatası</div><div class="ss">result 7500+</div></div>
      </div>
      <div class="card"><div class="ctitle">🔢 Hata Kodları</div>
        <div style="overflow:auto;max-height:440px">
          <table class="tbl">
            <thead><tr><th>Kod</th><th>Açıklama</th><th>Kategori</th></tr></thead>
            <tbody>
              ${codes?.map(c => `
                <tr>
                  <td style="font-weight:700;color:${c.category==='SYS'?'var(--ora)':c.category==='BIZ'?'var(--red)':'var(--grn)'}">${c.result_code}</td>
                  <td style="color:var(--txt)">${c.description}</td>
                  <td><span class="tag ${c.category==='SYS'?'t-o':c.category==='BIZ'?'t-r':'t-g'}">${c.category}</span></td>
                </tr>`).join('') || '<tr><td colspan="3" style="text-align:center;color:var(--txt3);padding:20px">Henüz hata kodu yüklenmedi</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch(e) {
    document.getElementById('ec-content').innerHTML = errorHtml(e.message);
  }
}

async function reloadErrorCodes() {
  try {
    const result = await apiFetch('/api/v1/error-codes/reload', { method: 'POST' });
    toast(`${result?.reloaded ?? 0} hata kodu yeniden yüklendi`, 's');
    loadErrorCodes();
  } catch(e) {
    toast('Yenileme hatası: ' + e.message, 'e');
  }
}

// ══════════════════════════════════════
// DETECTION RUNS
// ══════════════════════════════════════
async function loadRuns() {
  const el = document.getElementById('page-runs');
  el.innerHTML = `
    <div class="phead"><div><div class="pt">Detection Runs</div>
    <div class="ps">Her döngünün özet kaydı</div></div></div>
    <div id="runs-content">${loadingHtml()}</div>
  `;

  try {
    const runs = await apiFetch('/api/v1/runs?limit=50');
    document.getElementById('runs-content').innerHTML = `
      <div class="card"><div class="ctitle">📋 Son Döngüler</div>
        <div style="overflow:auto;max-height:500px">
          <table class="tbl">
            <thead><tr><th>Başlangıç</th><th>Bitiş</th><th>İşlenen Log</th><th>Anomali</th><th>Zabbix</th><th>Durum</th></tr></thead>
            <tbody>
              ${runs?.map(r => `
                <tr>
                  <td>${r.started_at ? new Date(r.started_at).toLocaleString('tr-TR') : '—'}</td>
                  <td>${r.finished_at ? new Date(r.finished_at).toLocaleTimeString('tr-TR') : '—'}</td>
                  <td>${r.logs_processed?.toLocaleString() ?? '—'}</td>
                  <td style="color:${r.anomalies_found > 0 ? 'var(--red)' : 'var(--txt2)'}">${r.anomalies_found ?? 0}</td>
                  <td>${r.zabbix_sent ?? 0}</td>
                  <td><span class="tag ${r.status==='ok'?'t-g':r.status==='error'?'t-r':'t-y'}">${r.status}</span></td>
                </tr>`).join('') || '<tr><td colspan="6" style="text-align:center;color:var(--txt3);padding:20px">Henüz döngü yok</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch(e) {
    document.getElementById('runs-content').innerHTML = errorHtml(e.message);
  }
}

// ══════════════════════════════════════
// SRE
// ══════════════════════════════════════
async function loadSRE() {
  const el = document.getElementById('page-sre');
  const readonly = !isSRE();
  el.innerHTML = `
    <div class="phead">
      <div><div class="pt">SRE Agent Merkezi</div>
      <div class="ps">${readonly ? '👁️ Görüntüleme modu — Aksiyon yetkisi yok' : 'LLM tabanlı kök neden · Yarı otonom · Human-in-the-loop'}</div></div>
    </div>
    ${readonly ? `<div style="background:rgba(8,145,178,.07);border:1px solid rgba(8,145,178,.2);border-radius:8px;padding:8px 14px;margin-bottom:14px;font-size:10px;color:var(--tea)">
      👁️ ${CURRENT_USER.roles?.[0]} rolü SRE bölümünü sadece görüntüleyebilir.
    </div>` : ''}
    <div id="sre-content">${loadingHtml()}</div>
  `;

  try {
    const [pending, all] = await Promise.all([
      apiFetch('/api/v1/sre/actions?status=pending&limit=20'),
      apiFetch('/api/v1/sre/actions?limit=20'),
    ]);

    const badge = document.getElementById('sre-count-badge');
    if (badge) badge.textContent = pending?.length ?? 0;

    document.getElementById('sre-content').innerHTML = `
      <div class="g2">
        <div class="card">
          <div class="ctitle">⏳ Onay Bekleyen Aksiyonlar</div>
          ${pending?.length ? pending.map(a => sreActionHtml(a, readonly)).join('') : emptyHtml('Onay bekleyen aksiyon yok')}
        </div>
        <div class="card">
          <div class="ctitle">📜 Son Aksiyonlar</div>
          ${all?.length ? `
            <div style="overflow:auto;max-height:400px">
              <table class="tbl">
                <thead><tr><th>Zaman</th><th>Aksiyon</th><th>Hedef</th><th>Durum</th><th>Onaylayan</th></tr></thead>
                <tbody>
                  ${all.map(a => `
                    <tr>
                      <td>${a.created_at ? new Date(a.created_at).toLocaleTimeString('tr-TR') : '—'}</td>
                      <td>${a.action_type || '—'}</td>
                      <td style="color:var(--acc)">${a.target || '—'}</td>
                      <td><span class="tag ${a.status==='done'?'t-g':a.status==='pending'?'t-y':a.status==='rejected'?'t-r':'t-b'}">${a.status}</span></td>
                      <td>${a.approved_by || (a.auto ? '🤖 Otomatik' : '—')}</td>
                    </tr>`).join('')}
                </tbody>
              </table>
            </div>` : emptyHtml('Henüz aksiyon yok')}
        </div>
      </div>
    `;
  } catch(e) {
    document.getElementById('sre-content').innerHTML = errorHtml(e.message);
  }
}

function sreActionHtml(a, readonly) {
  return `
    <div style="background:rgba(202,138,4,.04);border:1px solid rgba(202,138,4,.25);border-radius:10px;padding:12px;margin-bottom:10px">
      <div style="font-size:12px;font-weight:700;margin-bottom:4px">${a.action_type || '—'} — ${a.target || '—'}</div>
      ${a.ai_reasoning ? `<div style="font-size:10px;color:var(--txt2);margin-bottom:8px">${a.ai_reasoning}</div>` : ''}
      ${!readonly ? `
        <div style="display:flex;gap:8px">
          <button class="btn g" onclick="approveAction(${a.id})">✅ Onayla</button>
          <button class="btn r" onclick="rejectAction(${a.id})">❌ Reddet</button>
        </div>` : `
        <div style="font-size:10px;color:var(--tea)">🔒 Onaylamak için SRE Lead yetkisi gerekli</div>`}
    </div>`;
}

async function approveAction(id) {
  try {
    await apiFetch(`/api/v1/sre/actions/${id}/approve`, { method: 'POST' });
    toast('Aksiyon onaylandı', 's');
    loadSRE();
  } catch(e) { toast('Hata: ' + e.message, 'e'); }
}

async function rejectAction(id) {
  try {
    await apiFetch(`/api/v1/sre/actions/${id}/reject`, { method: 'POST' });
    toast('Aksiyon reddedildi', 'w');
    loadSRE();
  } catch(e) { toast('Hata: ' + e.message, 'e'); }
}

// ══════════════════════════════════════
// USERS (Admin only)
// ══════════════════════════════════════
async function loadUsers() {
  const el = document.getElementById('page-users');
  el.innerHTML = `
    <div class="phead"><div><div class="pt">Kullanıcı Yönetimi</div>
    <div class="ps">LDAP + Local · Rol ataması</div></div></div>
    <div style="background:rgba(202,138,4,.08);border:1px solid rgba(202,138,4,.2);border-radius:8px;padding:12px 16px;font-size:11px;color:var(--yel)">
      ⚠️ Kullanıcı yönetimi API entegrasyonu yapım aşamasında. Kullanıcı ekleme/düzenleme yakında aktif olacak.
    </div>
  `;
}

// ══════════════════════════════════════
// SETTINGS (Admin only)
// ══════════════════════════════════════
async function loadSettings() {
  const el = document.getElementById('page-settings');
  el.innerHTML = `
    <div class="phead"><div><div class="pt">Sistem Ayarları</div>
    <div class="ps">LDAP, LLM, Zabbix, Bildirim yapılandırması</div></div>
    <div class="pactions"><button class="btn p" onclick="toast('Ayarlar kaydedildi','s')">💾 Kaydet</button></div></div>
    <div class="g2">
      <div class="card"><div class="ctitle">🔐 LDAP / Active Directory</div>
        <div class="pr" style="margin-bottom:10px"><div class="pl" style="font-size:11px">LDAP URL</div>
          <div style="font-size:11px;color:var(--acc);font-family:'JetBrains Mono',monospace">${window.LDAP_URL || 'Yapılandırılmadı'}</div></div>
        <div class="pr"><div class="pl" style="font-size:11px">Local Fallback</div>
          <button class="toggle on" onclick="this.classList.toggle('on');this.classList.toggle('off')"></button></div>
      </div>
      <div class="card"><div class="ctitle">🤖 LLM Servisi</div>
        <div class="pr" style="margin-bottom:10px"><div class="pl" style="font-size:11px">Endpoint</div>
          <div style="font-size:11px;color:var(--acc);font-family:'JetBrains Mono',monospace">${window.VLLM_URL || 'Yapılandırılmadı'}</div></div>
        <div class="pr"><div class="pl" style="font-size:11px">Sadece HIGH+</div>
          <button class="toggle on" onclick="this.classList.toggle('on');this.classList.toggle('off')"></button></div>
      </div>
      <div class="card"><div class="ctitle">📡 Zabbix</div>
        <div class="pr" style="margin-bottom:10px"><div class="pl" style="font-size:11px">API URL</div>
          <div style="font-size:11px;color:var(--acc);font-family:'JetBrains Mono',monospace">${window.ZABBIX_URL || 'Yapılandırılmadı'}</div></div>
        <div class="pr"><div class="pl" style="font-size:11px">Dry Run</div>
          <button class="toggle on" id="dry-run-toggle" onclick="this.classList.toggle('on');this.classList.toggle('off')"></button></div>
      </div>
      <div class="card"><div class="ctitle">💬 Bildirimler</div>
        <div class="pr" style="margin-bottom:8px"><div class="pl" style="font-size:11px">Slack</div>
          <button class="toggle off" onclick="this.classList.toggle('on');this.classList.toggle('off')"></button></div>
        <div class="pr" style="margin-bottom:8px"><div class="pl" style="font-size:11px">JIRA ITSM</div>
          <button class="toggle on" onclick="this.classList.toggle('on');this.classList.toggle('off')"></button></div>
        <div class="pr"><div class="pl" style="font-size:11px">E-posta</div>
          <button class="toggle off" onclick="this.classList.toggle('on');this.classList.toggle('off')"></button></div>
      </div>
    </div>
  `;
}

// ══════════════════════════════════════
// YARDIMCILAR
// ══════════════════════════════════════
function closeModal() { document.getElementById('modal-overlay').classList.remove('open'); }

function loadingHtml() {
  return `<div class="loading"><div class="spinner"></div>Yükleniyor…</div>`;
}
function emptyHtml(msg) {
  return `<div style="text-align:center;padding:30px;color:var(--txt3);font-size:12px">${msg}</div>`;
}
function errorHtml(msg) {
  return `<div style="text-align:center;padding:30px;color:var(--red);font-size:12px">⚠️ ${msg}</div>`;
}

function toast(msg, type='i') {
  const wrap = document.getElementById('toast-wrap');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  const icons = {s:'✅', e:'❌', i:'ℹ️', w:'⚠️'};
  t.innerHTML = `<span>${icons[type]||'ℹ️'}</span><span>${msg}</span>`;
  wrap.appendChild(t);
  setTimeout(() => {
    t.style.opacity = '0';
    t.style.transform = 'translateX(20px)';
    t.style.transition = 'all .3s';
    setTimeout(() => t.remove(), 300);
  }, 3800);
}
</script>
</body>
</html>
HTMLEOF

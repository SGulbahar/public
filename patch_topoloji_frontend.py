"""
Topoloji görselleştirme sayfasını D3.js ile ekler.
Calistirma: python3 patch_topoloji_frontend.py
"""

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

TOPOLOJI_JS = """
/* ─────────────────────────────────────────
   SERVİS TOPOLOJİSİ
───────────────────────────────────────── */
var _topoD3Loaded = false;
var _topoSim = null;

async function topolojiYukle() {
  var el = document.getElementById('pg-topoloji');
  if (!el) return;

  el.innerHTML =
    '<div class="pgh"><div>' +
    '<div class="pgey">Altyap\\u0131</div>' +
    '<div class="pgt">Servis Topolojisi</div>' +
    '<div class="pgs">BusinessService \\u2192 Host ili\\u015fkisi \\u2014 K\\u0131rm\\u0131z\\u0131 = Aktif DISASTER alarm</div>' +
    '</div></div>' +
    '<div class="card" style="margin-bottom:14px"><div class="cb" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">' +
    '<div style="flex:1;min-width:200px">' +
    '<label class="form-lbl">Business Service Ara / Se\\u00e7</label>' +
    '<input class="form-input" id="topo-ara" placeholder="Servis ad\\u0131 yaz..." oninput="topoFiltrele(this.value)"/>' +
    '</div>' +
    '<div style="display:flex;gap:6px;align-items:flex-end">' +
    '<button class="btn btn-gh" onclick="topoYukle(null)">T\\u00fcm\\u00fc (Alarmlar)</button>' +
    '<button class="btn btn-ok" id="topo-yukle-btn" onclick="topoServisYukle()" style="display:none">G\\u00f6ster</button>' +
    '</div>' +
    '</div></div>' +
    '<div id="topo-servis-liste" style="margin-bottom:10px"></div>' +
    '<div class="card"><div class="cb" style="padding:0">' +
    '<div id="topo-svg-container" style="width:100%;height:600px;position:relative">' +
    '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--txt3);font-size:12px">' +
    'Servis se\\u00e7in veya "T\\u00fcm\\u00fc (Alarmlar)" butonuna t\\u0131klay\\u0131n' +
    '</div></div>' +
    '</div></div>' +
    '<div id="topo-detay" style="margin-top:10px"></div>';

  // D3.js yukle
  if (!_topoD3Loaded) {
    await new Promise(function(resolve) {
      var script = document.createElement('script');
      script.src = 'https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js';
      script.onload = function() { _topoD3Loaded = true; resolve(); };
      document.head.appendChild(script);
    });
  }

  await topoServisleriYukle();
}

async function topoServisleriYukle() {
  try {
    var data = await apiFetch('/api/v1/topology/services') || [];
    var el = document.getElementById('topo-servis-liste');
    if (!el || !data.length) return;

    var html = '<div style="display:flex;flex-wrap:wrap;gap:6px;padding:0 2px">';
    data.forEach(function(s) {
      var alarmCss = s.alarm_count > 0 ? 'background:var(--red-dim);border-color:var(--red);color:var(--red)' : 'background:var(--bg3);border:1px solid var(--border)';
      html += '<div class="topo-svc-chip" data-svc="' + s.name + '" onclick="topoYukle(this.dataset.svc)" style="' + alarmCss + ';padding:4px 10px;border-radius:20px;cursor:pointer;font-size:10px;font-family:JetBrains Mono,monospace;transition:opacity .15s" onmouseover="this.style.opacity=\'.7\'" onmouseout="this.style.opacity=\'1\'">' +
        s.name +
        (s.alarm_count > 0 ? ' <span style="font-weight:800">\\u26a0 ' + s.alarm_count + '</span>' : '') +
        '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  } catch(e) {}
}

function topoFiltrele(ara) {
  var chips = document.querySelectorAll('.topo-svc-chip');
  chips.forEach(function(chip) {
    chip.style.display = chip.dataset.svc.toLowerCase().indexOf(ara.toLowerCase()) !== -1 ? '' : 'none';
  });
}

async function topoYukle(service) {
  var container = document.getElementById('topo-svg-container');
  if (!container) return;
  container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--txt3)">' + ldg() + '</div>';

  try {
    var url = '/api/v1/topology/graph' + (service ? '?service=' + encodeURIComponent(service) : '');
    var data = await apiFetch(url);

    if (!data || !data.nodes || !data.nodes.length) {
      container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--txt3)">Veri bulunamad\\u0131</div>';
      return;
    }

    topoGoster(data, container, service);
  } catch(e) {
    container.innerHTML = '<div style="padding:20px;color:var(--red)">' + e.message + '</div>';
  }
}

function topoGoster(data, container, baslik) {
  container.innerHTML = '';

  var width = container.offsetWidth || 800;
  var height = 580;

  // Temiz renk paleti
  var isDark = document.documentElement.getAttribute('data-tema') === 'dark' ||
               document.body.classList.contains('dark');
  var bgColor = isDark ? '#1a1a2e' : '#f8fafc';
  var textColor = isDark ? '#e2e8f0' : '#1e293b';
  var linkColor = isDark ? '#334155' : '#cbd5e1';

  var svg = d3.select(container)
    .append('svg')
    .attr('width', '100%')
    .attr('height', height)
    .style('background', bgColor)
    .style('border-radius', '8px');

  // Baslik
  svg.append('text')
    .attr('x', 16)
    .attr('y', 24)
    .attr('fill', textColor)
    .attr('font-size', '11px')
    .attr('font-family', 'JetBrains Mono, monospace')
    .attr('opacity', 0.6)
    .text(baslik ? baslik : 'Aktif Alarmli Topoloji');

  // Ozet
  svg.append('text')
    .attr('x', width - 16)
    .attr('y', 24)
    .attr('fill', textColor)
    .attr('font-size', '10px')
    .attr('font-family', 'JetBrains Mono, monospace')
    .attr('text-anchor', 'end')
    .attr('opacity', 0.5)
    .text(data.toplam_host + ' host, ' + data.alarm_host + ' alarmli');

  var g = svg.append('g').attr('transform', 'translate(0, 30)');

  // Zoom
  svg.call(d3.zoom().scaleExtent([0.3, 3]).on('zoom', function(event) {
    g.attr('transform', event.transform);
  }));

  // Links
  var link = g.append('g').selectAll('line')
    .data(data.edges)
    .enter().append('line')
    .attr('stroke', linkColor)
    .attr('stroke-width', 1.5)
    .attr('stroke-opacity', 0.6);

  // Node grupları
  var node = g.append('g').selectAll('g')
    .data(data.nodes)
    .enter().append('g')
    .attr('cursor', 'pointer')
    .call(d3.drag()
      .on('start', function(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on('drag', function(event, d) {
        d.fx = event.x; d.fy = event.y;
      })
      .on('end', function(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null; d.fy = null;
      })
    )
    .on('click', function(event, d) {
      topoNodeTikla(d);
    });

  // Node şekiller
  node.each(function(d) {
    var el = d3.select(this);
    if (d.type === 'service') {
      // BusinessService: dikdortgen
      el.append('rect')
        .attr('x', -55).attr('y', -16)
        .attr('width', 110).attr('height', 32)
        .attr('rx', 6)
        .attr('fill', '#1d4ed8')
        .attr('stroke', '#3b82f6')
        .attr('stroke-width', 1.5);
    } else {
      // Host: daire
      var alarmli = d.alarm_count > 0;
      el.append('circle')
        .attr('r', alarmli ? 18 : 14)
        .attr('fill', alarmli ? '#dc2626' : '#374151')
        .attr('stroke', alarmli ? '#ef4444' : '#6b7280')
        .attr('stroke-width', alarmli ? 2 : 1);

      // Alarm varsa yanip sonen efekt
      if (alarmli) {
        el.append('circle')
          .attr('r', 18)
          .attr('fill', 'none')
          .attr('stroke', '#ef4444')
          .attr('stroke-width', 2)
          .attr('opacity', 0.5)
          .append('animate')
          .attr('attributeName', 'r')
          .attr('values', '18;26;18')
          .attr('dur', '2s')
          .attr('repeatCount', 'indefinite');
      }
    }

    // Etiket
    var label = d.type === 'service' ? d.label : d.label.split('.')[0];
    if (label.length > 15) label = label.substring(0, 14) + '...';
    el.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', d.type === 'service' ? '0.35em' : (d.alarm_count > 0 ? '0.35em' : '0.35em'))
      .attr('fill', '#ffffff')
      .attr('font-size', d.type === 'service' ? '10px' : '8px')
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('pointer-events', 'none')
      .text(label);

    // Alarm sayisi
    if (d.type === 'host' && d.alarm_count > 0) {
      el.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', '1.8em')
        .attr('fill', '#fca5a5')
        .attr('font-size', '8px')
        .attr('pointer-events', 'none')
        .text('\\u26a0 ' + d.alarm_count);
    }
  });

  // Force simulation
  var nodeMap = {};
  data.nodes.forEach(function(n) { nodeMap[n.id] = n; });

  var links = data.edges.map(function(e) {
    return {source: nodeMap[e.source] || e.source, target: nodeMap[e.target] || e.target};
  });

  var simulation = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(links).id(function(d) { return d.id; }).distance(function(d) {
      return d.target.type === 'service' ? 120 : 80;
    }))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter((width) / 2, (height - 30) / 2))
    .force('collision', d3.forceCollide().radius(function(d) {
      return d.type === 'service' ? 70 : 30;
    }));

  simulation.on('tick', function() {
    link
      .attr('x1', function(d) { return d.source.x; })
      .attr('y1', function(d) { return d.source.y; })
      .attr('x2', function(d) { return d.target.x; })
      .attr('y2', function(d) { return d.target.y; });

    node.attr('transform', function(d) {
      return 'translate(' + d.x + ',' + d.y + ')';
    });
  });

  _topoSim = simulation;

  // Legand
  var legend = svg.append('g').attr('transform', 'translate(16, ' + (height - 50) + ')');
  var items = [
    {color: '#1d4ed8', label: 'Business Service', shape: 'rect'},
    {color: '#374151', label: 'Host (Normal)', shape: 'circle'},
    {color: '#dc2626', label: 'Host (DISASTER Alarm)', shape: 'circle'},
  ];
  items.forEach(function(item, i) {
    var lg = legend.append('g').attr('transform', 'translate(' + (i * 180) + ', 0)');
    if (item.shape === 'rect') {
      lg.append('rect').attr('x', 0).attr('y', -8).attr('width', 16).attr('height', 16).attr('rx', 3).attr('fill', item.color);
    } else {
      lg.append('circle').attr('cx', 8).attr('cy', 0).attr('r', 7).attr('fill', item.color);
    }
    lg.append('text').attr('x', 22).attr('y', 4).attr('fill', textColor).attr('font-size', '10px').text(item.label);
  });
}

function topoNodeTikla(d) {
  var el = document.getElementById('topo-detay');
  if (!el) return;

  if (d.type === 'service') {
    el.innerHTML = '<div class="card"><div class="cb"><strong style="font-family:JetBrains Mono,monospace;color:var(--acc)">' + d.label + '</strong> <span style="font-size:10px;color:var(--txt3)">Business Service</span></div></div>';
    return;
  }

  var alarmHtml = '';
  if (d.alarmlar && d.alarmlar.length) {
    alarmHtml = '<div style="margin-top:8px"><div style="font-size:10px;font-weight:700;color:var(--red);margin-bottom:4px">DISASTER ALARMLAR</div>';
    d.alarmlar.forEach(function(a) {
      alarmHtml += '<div style="font-size:10px;padding:4px 0;border-bottom:1px solid var(--border2)">' + (a.name || '') + '</div>';
    });
    alarmHtml += '</div>';
  }

  el.innerHTML = '<div class="card"><div class="cb">' +
    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
    '<span class="chip ' + (d.alarm_count > 0 ? 'c-r' : 'c-gr') + '">' + (d.alarm_count > 0 ? d.alarm_count + ' Alarm' : 'Normal') + '</span>' +
    '<strong style="font-family:JetBrains Mono,monospace">' + d.label + '</strong>' +
    '</div>' +
    (d.os ? '<div style="font-size:10px;color:var(--txt2)">OS: ' + d.os + '</div>' : '') +
    (d.environment ? '<div style="font-size:10px;color:var(--txt2)">Ortam: ' + d.environment + '</div>' : '') +
    (d.application ? '<div style="font-size:10px;color:var(--txt2)">Uygulama: ' + d.application + '</div>' : '') +
    alarmHtml +
    '</div></div>';
}

"""

old = 'async function ayarlarYukle()'
if old in c:
    c = c.replace(old, TOPOLOJI_JS + '\nasync function ayarlarYukle()', 1)
    print("OK: topoloji JS eklendi")
else:
    print("WARN: ayarlarYukle bulunamadi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print("topolojiYukle:", "topolojiYukle" in c)
print("topoGoster:", "topoGoster" in c)
print("girisYap:", "girisYap" in c)

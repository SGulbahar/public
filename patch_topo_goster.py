"""
topoGoster fonksiyonunu daha iyi gorsel ile yeniden yazar.
Calistirma: python3 patch_topo_goster.py
"""
import re

HTML_PATH = '/data/lumen/frontend/index.html'

with open(HTML_PATH) as f:
    c = f.read()

# topoGoster fonksiyonunu bul ve degistir
start_idx = c.find('function topoGoster(data, container, baslik) {')
if start_idx == -1:
    print("WARN: topoGoster bulunamadi")
    exit()

depth = 0
i = c.find('{', start_idx)
while i < len(c):
    if c[i] == '{': depth += 1
    elif c[i] == '}':
        depth -= 1
        if depth == 0:
            end_idx = i + 1
            break
    i += 1

NEW_TOPO_GOSTER = """function topoGoster(data, container, baslik) {
  container.innerHTML = '';

  var width = container.offsetWidth || 900;
  var height = 580;
  var BG = '#0f172a';
  var LINK_COLOR = '#334155';
  var SERVICE_COLOR = '#2563eb';
  var HOST_NORMAL = '#1e3a5f';
  var HOST_ALARM = '#7f1d1d';
  var HOST_ALARM_BORDER = '#ef4444';
  var HOST_NORMAL_BORDER = '#3b82f6';
  var TEXT_COLOR = '#f1f5f9';
  var TEXT_DIM = '#94a3b8';

  var svg = d3.select(container)
    .append('svg')
    .attr('width', '100%')
    .attr('height', height)
    .style('background', BG)
    .style('border-radius', '8px');

  // Defs - glow efekti
  var defs = svg.append('defs');
  var glowFilter = defs.append('filter').attr('id', 'glow');
  glowFilter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'coloredBlur');
  var feMerge = glowFilter.append('feMerge');
  feMerge.append('feMergeNode').attr('in', 'coloredBlur');
  feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

  // Baslik
  svg.append('text')
    .attr('x', 16).attr('y', 22)
    .attr('fill', TEXT_DIM)
    .attr('font-size', '11px')
    .attr('font-family', 'JetBrains Mono, monospace')
    .text(baslik ? baslik : 'Aktif Alarmli Topoloji');

  svg.append('text')
    .attr('x', width - 16).attr('y', 22)
    .attr('fill', TEXT_DIM)
    .attr('font-size', '10px')
    .attr('font-family', 'JetBrains Mono, monospace')
    .attr('text-anchor', 'end')
    .text(data.toplam_host + ' host | ' + data.alarm_host + ' alarmli');

  var g = svg.append('g').attr('transform', 'translate(0,28)');

  // Zoom - yazilarda scale olsun
  var currentScale = 1;
  var zoomBehavior = d3.zoom()
    .scaleExtent([0.2, 4])
    .on('zoom', function(event) {
      currentScale = event.transform.k;
      g.attr('transform', event.transform);
      // Yazilari zoom ile guncelle
      g.selectAll('.node-label')
        .attr('font-size', function(d) {
          var base = d.type === 'service' ? 11 : 9;
          return Math.max(6, Math.min(18, base)) + 'px';
        });
    });
  svg.call(zoomBehavior);

  // Node map
  var nodeMap = {};
  data.nodes.forEach(function(n) { nodeMap[n.id] = n; });

  var links = data.edges.map(function(e) {
    return {
      source: nodeMap[e.source] || e.source,
      target: nodeMap[e.target] || e.target
    };
  });

  // Link layer
  var linkSel = g.append('g').attr('class', 'links')
    .selectAll('line')
    .data(links)
    .enter().append('line')
    .attr('stroke', LINK_COLOR)
    .attr('stroke-width', 1.5)
    .attr('stroke-opacity', 0.8);

  // Node layer
  var nodeSel = g.append('g').attr('class', 'nodes')
    .selectAll('g')
    .data(data.nodes)
    .enter().append('g')
    .attr('class', 'node')
    .attr('cursor', 'pointer')
    .call(d3.drag()
      .on('start', function(event, d) {
        if (!event.active) sim.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on('drag', function(event, d) {
        d.fx = event.x; d.fy = event.y;
      })
      .on('end', function(event, d) {
        if (!event.active) sim.alphaTarget(0);
        d.fx = null; d.fy = null;
      })
    )
    .on('click', function(event, d) { topoNodeTikla(d); });

  // Sekiller
  nodeSel.each(function(d) {
    var el = d3.select(this);
    if (d.type === 'service') {
      var w = 130, h = 36;
      el.append('rect')
        .attr('x', -w/2).attr('y', -h/2)
        .attr('width', w).attr('height', h)
        .attr('rx', 8)
        .attr('fill', SERVICE_COLOR)
        .attr('stroke', '#60a5fa')
        .attr('stroke-width', 2)
        .attr('filter', 'url(#glow)');
    } else {
      var alarmli = d.alarm_count > 0;
      var r = alarmli ? 22 : 18;
      el.append('circle')
        .attr('r', r)
        .attr('fill', alarmli ? HOST_ALARM : HOST_NORMAL)
        .attr('stroke', alarmli ? HOST_ALARM_BORDER : HOST_NORMAL_BORDER)
        .attr('stroke-width', alarmli ? 2.5 : 1.5)
        .attr('filter', alarmli ? 'url(#glow)' : null);

      // Alarm pulse
      if (alarmli) {
        el.append('circle')
          .attr('r', r)
          .attr('fill', 'none')
          .attr('stroke', '#ef4444')
          .attr('stroke-width', 2)
          .attr('opacity', 0.4)
          .append('animate')
            .attr('attributeName', 'r')
            .attr('values', r + ';' + (r+10) + ';' + r)
            .attr('dur', '2s')
            .attr('repeatCount', 'indefinite');
      }
    }

    // Etiket
    var rawLabel = d.label || '';
    var label = d.type === 'service'
      ? (rawLabel.length > 20 ? rawLabel.substring(0, 19) + '...' : rawLabel)
      : rawLabel.split('.')[0].substring(0, 12);

    el.append('text')
      .attr('class', 'node-label')
      .attr('text-anchor', 'middle')
      .attr('dy', d.type === 'service' ? '0.35em' : '0.35em')
      .attr('fill', TEXT_COLOR)
      .attr('font-size', d.type === 'service' ? '11px' : '9px')
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('font-weight', d.type === 'service' ? '700' : '400')
      .attr('pointer-events', 'none')
      .text(label);

    if (d.type === 'host' && d.alarm_count > 0) {
      el.append('text')
        .attr('class', 'node-label')
        .attr('text-anchor', 'middle')
        .attr('dy', '2.2em')
        .attr('fill', '#fca5a5')
        .attr('font-size', '8px')
        .attr('font-family', 'JetBrains Mono, monospace')
        .attr('pointer-events', 'none')
        .text('\\u26a0 ' + d.alarm_count);
    }
  });

  // Simulation
  var sim = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(links)
      .id(function(d) { return d.id; })
      .distance(function(d) {
        return d.target.type === 'service' ? 130 : 90;
      })
      .strength(0.8))
    .force('charge', d3.forceManyBody().strength(-250))
    .force('center', d3.forceCenter(width / 2, (height - 28) / 2))
    .force('collision', d3.forceCollide().radius(function(d) {
      return d.type === 'service' ? 80 : 30;
    }));

  sim.on('tick', function() {
    linkSel
      .attr('x1', function(d) { return d.source.x; })
      .attr('y1', function(d) { return d.source.y; })
      .attr('x2', function(d) { return d.target.x; })
      .attr('y2', function(d) { return d.target.y; });
    nodeSel.attr('transform', function(d) {
      return 'translate(' + d.x + ',' + d.y + ')';
    });
  });

  _topoSim = sim;

  // Legend
  var leg = svg.append('g').attr('transform', 'translate(16,' + (height - 40) + ')');
  [
    {color: SERVICE_COLOR, border: '#60a5fa', label: 'Business Service', rect: true},
    {color: HOST_NORMAL, border: HOST_NORMAL_BORDER, label: 'Host (Normal)', rect: false},
    {color: HOST_ALARM, border: HOST_ALARM_BORDER, label: 'Host (DISASTER)', rect: false},
  ].forEach(function(item, i) {
    var lg = leg.append('g').attr('transform', 'translate(' + (i * 170) + ',0)');
    if (item.rect) {
      lg.append('rect').attr('x', 0).attr('y', -8).attr('width', 18).attr('height', 16).attr('rx', 4)
        .attr('fill', item.color).attr('stroke', item.border).attr('stroke-width', 1.5);
    } else {
      lg.append('circle').attr('cx', 9).attr('cy', 0).attr('r', 8)
        .attr('fill', item.color).attr('stroke', item.border).attr('stroke-width', 1.5);
    }
    lg.append('text').attr('x', 24).attr('y', 4).attr('fill', TEXT_DIM)
      .attr('font-size', '10px').attr('font-family', 'JetBrains Mono, monospace').text(item.label);
  });
}"""

c = c[:start_idx] + NEW_TOPO_GOSTER + c[end_idx:]
print("OK: topoGoster yeniden yazildi")

with open(HTML_PATH, 'w') as f:
    f.write(c)

print("girisYap:", "girisYap" in c)
print("topoGoster:", "function topoGoster" in c)

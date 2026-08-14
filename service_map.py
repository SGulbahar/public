import igraph as ig
import pandas as pd
import leidenalg
from pyvis.network import Network
import json
import math
import os
import csv
from pathlib import Path


def create_service_map():

    input_file = Path("/data/lumen/ML_Inference/anomalies/rt_anomaly_result.json")
    output_file = "service_alarm_list.csv"

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    alarms = data.get("alarms", [])

    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")

        # Kolon başlıkları
        writer.writerow(["alarmlevel", "servicename"])

        for alarm in alarms:
            alarm_level = alarm.get("anomaly_status", "")
            service_name = alarm.get("servicename", "")

            writer.writerow([alarm_level, service_name])


    df = pd.read_csv("graph.csv")
    df["Transaction Count"] = (
        pd.to_numeric(df["Transaction Count"], errors="coerce")
        .fillna(0)
        .astype(float)
    )
    # A-B ve B-A'yı aynı edge olarak ele al
    df["source"] = df[["vertex_service", "node_service_name"]].min(axis=1)
    df["target"] = df[["vertex_service", "node_service_name"]].max(axis=1)

    edges = (
        df.groupby(["source", "target"], as_index=False)
        ["Transaction Count"]
        .sum()
    )

    g = ig.Graph.TupleList(
        edges[["source", "target"]].itertuples(index=False),
        directed=False
    )

    g.es["weight"] = edges["Transaction Count"].tolist()

    partition = leidenalg.find_partition(
        g,
        leidenalg.ModularityVertexPartition,
        weights="weight"
    )
    result = pd.DataFrame({
        "service": g.vs["name"],
        "cluster": partition.membership
    })

    print(result.sort_values("cluster"))

    ##################################################################################################

    # =========================================================
    # 1. AYARLAR
    # =========================================================

    ELIGIBLE_CSV_FILE = "eligible_channel_service_list.csv"
    ELIGIBLE_SERVICE_COLUMN = "servicename"
    ELIGIBLE_CSV_SEPARATOR = ","

    ALARM_CSV_FILE = "service_alarm_list.csv"
    ALARM_SERVICE_COLUMN = "servicename"
    ALARM_LEVEL_COLUMN = "alarmlevel"
    ALARM_CSV_SEPARATOR = ";"

    OUTPUT_HTML = "service_map.html"


    # =========================================================
    # 2. RENKLER
    # =========================================================

    WARNING_COLOR = "#FC8D18"
    WARNING_BORDER_COLOR = "#FFEDD5"

    CRITICAL_COLOR = "#E00909"
    CRITICAL_BORDER_COLOR = "#FEE2E2"

    ALARM_EDGE_COLOR = "#FF304F"

    NORMAL_BORDER_COLOR = "#64748B"
    NORMAL_EDGE_COLOR = "#334155"

    SAFE_CLUSTER_COLORS = [
        "#38BDF8",
        "#2563EB",
        "#22D3EE",
        "#14B8A6",
        "#10B981",
        "#84CC16",
        "#8B5CF6",
        "#A78BFA",
        "#6366F1",
        "#0EA5E9",
        "#06B6D4",
        "#2DD4BF",
        "#4ADE80",
        "#818CF8",
        "#C084FC",
        "#94A3B8",
    ]


    # =========================================================
    # 3. PERFORMANS AYARLARI
    # =========================================================

    NODE_ALARM_INTERVAL_MS = 650
    EDGE_ALARM_INTERVAL_MS = 750

    LABEL_SHOW_SCALE = 0.70

    MIN_NODE_SIZE = 10
    MAX_NODE_SIZE = 34

    PHYSICS_ITERATIONS = 180


    # =========================================================
    # 4. YARDIMCI FONKSİYONLAR
    # =========================================================

    def normalize_service_name(value):
        if pd.isna(value):
            return ""

        return str(value).strip().casefold()


    def read_required_csv(
        file_path,
        required_columns,
        description,
        separator
    ):
        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"{description} bulunamadı: "
                f"{os.path.abspath(file_path)}"
            )

        dataframe = pd.read_csv(
            file_path,
            sep=separator
        )

        dataframe.columns = [
            str(column).strip()
            for column in dataframe.columns
        ]

        missing_columns = (
            set(required_columns)
            - set(dataframe.columns)
        )

        if missing_columns:
            raise ValueError(
                f"{description} içinde eksik kolonlar var: "
                f"{sorted(missing_columns)}. "
                f"Mevcut kolonlar: {list(dataframe.columns)}"
            )

        return dataframe


    # =========================================================
    # 5. ELIGIBLE CSV
    # =========================================================

    eligible_df = read_required_csv(
        file_path=ELIGIBLE_CSV_FILE,
        required_columns=[
            ELIGIBLE_SERVICE_COLUMN
        ],
        description="Eligible servis CSV",
        separator=ELIGIBLE_CSV_SEPARATOR
    )

    circle_node_names = {
        normalize_service_name(value)
        for value in eligible_df[
            ELIGIBLE_SERVICE_COLUMN
        ].dropna()
        if normalize_service_name(value)
    }


    # =========================================================
    # 6. ALARM CSV
    # =========================================================

    alarm_df = read_required_csv(
        file_path=ALARM_CSV_FILE,
        required_columns=[
            ALARM_SERVICE_COLUMN,
            ALARM_LEVEL_COLUMN
        ],
        description="Alarm servis CSV",
        separator=ALARM_CSV_SEPARATOR
    )

    alarm_df = alarm_df[
        [
            ALARM_SERVICE_COLUMN,
            ALARM_LEVEL_COLUMN
        ]
    ].copy()

    alarm_df[ALARM_SERVICE_COLUMN] = (
        alarm_df[ALARM_SERVICE_COLUMN]
        .map(normalize_service_name)
    )

    alarm_df[ALARM_LEVEL_COLUMN] = (
        alarm_df[ALARM_LEVEL_COLUMN]
        .map(normalize_service_name)
    )

    alarm_df = alarm_df[
        alarm_df[ALARM_SERVICE_COLUMN].ne("")
        & alarm_df[ALARM_LEVEL_COLUMN].ne("")
    ].copy()

    valid_alarm_levels = {
        "warning",
        "critical"
    }

    invalid_alarm_levels = sorted(
        set(alarm_df[ALARM_LEVEL_COLUMN])
        - valid_alarm_levels
    )

    if invalid_alarm_levels:
        raise ValueError(
            "Alarm seviyesi yalnızca warning veya critical olabilir. "
            f"Geçersiz değerler: {invalid_alarm_levels}"
        )


    # Aynı servis birden fazla kez varsa critical öncelikli
    alarm_priority = {
        "warning": 1,
        "critical": 2
    }

    service_alarm_levels = {}

    for service_name, alarm_level in alarm_df[
        [
            ALARM_SERVICE_COLUMN,
            ALARM_LEVEL_COLUMN
        ]
    ].itertuples(index=False, name=None):

        previous_level = service_alarm_levels.get(
            service_name
        )

        if (
            previous_level is None
            or alarm_priority[alarm_level]
            > alarm_priority[previous_level]
        ):
            service_alarm_levels[
                service_name
            ] = alarm_level


    # =========================================================
    # 7. GRAPH KONTROLLERİ
    #
    # g ve partition önceden oluşturulmuş olmalıdır.
    # =========================================================

    if "name" not in g.vs.attributes():
        raise ValueError(
            "Graph içinde 'name' vertex alanı bulunamadı."
        )

    membership = list(
        partition.membership
    )

    node_names = [
        str(name)
        for name in g.vs["name"]
    ]

    if len(membership) != len(node_names):
        raise ValueError(
            "partition.membership ile node sayısı eşleşmiyor."
        )

    if len(set(node_names)) != len(node_names):
        raise ValueError(
            "Graph içinde tekrar eden servis isimleri var."
        )

    is_directed = bool(
        g.is_directed()
    )

    has_weight = (
        "weight"
        in g.es.attributes()
    )

    unique_clusters = sorted(
        set(membership)
    )

    cluster_colors = {
        cluster: SAFE_CLUSTER_COLORS[
            index % len(SAFE_CLUSTER_COLORS)
        ]
        for index, cluster in enumerate(
            unique_clusters
        )
    }

    graph_alarm_levels = {
        service_name: service_alarm_levels.get(
            normalize_service_name(service_name),
            "none"
        )
        for service_name in node_names
    }


    # =========================================================
    # 8. EDGE AĞIRLIKLARI
    # =========================================================

    def get_edge_weight(edge):
        if not has_weight:
            return 1.0

        try:
            return float(
                edge["weight"]
            )
        except (TypeError, ValueError):
            return 1.0


    edge_weights = [
        get_edge_weight(edge)
        for edge in g.es
    ]

    minimum_weight = (
        min(edge_weights)
        if edge_weights
        else 0.0
    )

    maximum_weight = (
        max(edge_weights)
        if edge_weights
        else 1.0
    )


    def scale_edge_width(weight):
        if maximum_weight <= minimum_weight:
            return 1.15

        minimum_log = math.log1p(
            max(minimum_weight, 0)
        )

        maximum_log = math.log1p(
            max(maximum_weight, 0)
        )

        if maximum_log == minimum_log:
            return 1.15

        normalized = (
            math.log1p(max(weight, 0))
            - minimum_log
        ) / (
            maximum_log
            - minimum_log
        )

        return round(
            0.55 + normalized * 2.7,
            2
        )


    # =========================================================
    # 9. TRAFİK DEĞERLERİ
    # =========================================================

    incoming_traffic = {
        service_name: 0.0
        for service_name in node_names
    }

    outgoing_traffic = {
        service_name: 0.0
        for service_name in node_names
    }

    total_traffic = {
        service_name: 0.0
        for service_name in node_names
    }

    for edge in g.es:
        source = str(
            g.vs[edge.source]["name"]
        )

        target = str(
            g.vs[edge.target]["name"]
        )

        weight = get_edge_weight(edge)

        outgoing_traffic[source] += weight
        incoming_traffic[target] += weight

        total_traffic[source] += weight
        total_traffic[target] += weight


    # =========================================================
    # 10. NETWORK
    # =========================================================

    net = Network(
        height="100vh",
        width="100%",
        bgcolor="#07111F",
        font_color="#DBEAFE",
        directed=is_directed,
        notebook=False,
        cdn_resources="in_line"
    )


    # =========================================================
    # 11. NODE'LARI EKLE
    # =========================================================

    eligible_match_count = 0
    warning_match_count = 0
    critical_match_count = 0

    graph_normalized_names = set()

    for vertex_index, service_name in enumerate(
        node_names
    ):
        cluster = membership[
            vertex_index
        ]

        normalized_service = (
            normalize_service_name(
                service_name
            )
        )

        graph_normalized_names.add(
            normalized_service
        )

        is_circle_node = (
            normalized_service
            in circle_node_names
        )

        alarm_level = graph_alarm_levels[
            service_name
        ]

        is_alarm_node = (
            alarm_level
            in {"warning", "critical"}
        )

        if is_circle_node:
            eligible_match_count += 1

        if alarm_level == "warning":
            warning_match_count += 1

        elif alarm_level == "critical":
            critical_match_count += 1


        if is_directed:
            in_degree = int(
                g.degree(
                    vertex_index,
                    mode="in"
                )
            )

            out_degree = int(
                g.degree(
                    vertex_index,
                    mode="out"
                )
            )

            total_degree = int(
                g.degree(
                    vertex_index,
                    mode="all"
                )
            )

        else:
            total_degree = int(
                g.degree(
                    vertex_index,
                    mode="all"
                )
            )

            in_degree = total_degree
            out_degree = total_degree


        node_size = min(
            MAX_NODE_SIZE,
            max(
                MIN_NODE_SIZE,
                MIN_NODE_SIZE
                + math.sqrt(
                    max(total_degree, 0)
                ) * 2.3
            )
        )


        node_shape = (
            "dot"
            if is_circle_node
            else "square"
        )

        service_type = (
            "Eligible servis"
            if is_circle_node
            else "Diğer servis"
        )


        if alarm_level == "critical":
            node_color = CRITICAL_COLOR
            node_border_color = (
                CRITICAL_BORDER_COLOR
            )
            alarm_label = "Critical"
            alert_color = CRITICAL_COLOR

        elif alarm_level == "warning":
            node_color = WARNING_COLOR
            node_border_color = (
                WARNING_BORDER_COLOR
            )
            alarm_label = "Warning"
            alert_color = WARNING_COLOR

        else:
            node_color = cluster_colors[
                cluster
            ]

            node_border_color = (
                NORMAL_BORDER_COLOR
            )

            alarm_label = "Alarm yok"
            alert_color = None


        base_border_width = (
            2.8
            if is_alarm_node
            else 1
        )


        net.add_node(
            service_name,

            label=service_name,
            shape=node_shape,
            size=node_size,

            color={
                "background": node_color,
                "border": node_border_color,

                "highlight": {
                    "background": node_color,
                    "border": "#FFFFFF"
                },

                "hover": {
                    "background": node_color,
                    "border": (
                        node_border_color
                        if is_alarm_node
                        else "#38BDF8"
                    )
                }
            },

            borderWidth=base_border_width,
            borderWidthSelected=4,

            shadow=(
                {
                    "enabled": True,
                    "color": alert_color,
                    "size": 5,
                    "x": 0,
                    "y": 0
                }
                if is_alarm_node
                else {
                    "enabled": False
                }
            ),

            serviceName=service_name,
            serviceType=service_type,
            isCircleNode=is_circle_node,

            alarmLevel=alarm_level,
            alarmLabel=alarm_label,
            isAlarmNode=is_alarm_node,
            alertColor=alert_color,

            cluster=int(cluster),
            degree=total_degree,
            inDegree=in_degree,
            outDegree=out_degree,

            incomingTraffic=float(
                incoming_traffic[service_name]
            ),

            outgoingTraffic=float(
                outgoing_traffic[service_name]
            ),

            totalTraffic=float(
                total_traffic[service_name]
            )
        )


    unmatched_alarm_services = sorted(
        set(service_alarm_levels)
        - graph_normalized_names
    )


    # =========================================================
    # 12. EDGE'LERİ EKLE
    # =========================================================

    alarm_connection_count = 0

    for edge_index, edge in enumerate(
        g.es
    ):
        source = str(
            g.vs[edge.source]["name"]
        )

        target = str(
            g.vs[edge.target]["name"]
        )

        weight = get_edge_weight(edge)

        source_alarm_level = (
            graph_alarm_levels.get(
                source,
                "none"
            )
        )

        target_alarm_level = (
            graph_alarm_levels.get(
                target,
                "none"
            )
        )

        source_has_alarm = (
            source_alarm_level
            in {"warning", "critical"}
        )

        target_has_alarm = (
            target_alarm_level
            in {"warning", "critical"}
        )

        # İki alarm servisini doğrudan bağlayan edge
        is_alarm_connection = (
            source_has_alarm
            and target_has_alarm
        )

        normal_width = scale_edge_width(
            weight
        )

        if is_alarm_connection:
            alarm_connection_count += 1

            base_width = max(
                3.1,
                normal_width * 1.55
            )

            edge_color = ALARM_EDGE_COLOR
            edge_opacity = 0.92

        else:
            base_width = normal_width
            edge_color = NORMAL_EDGE_COLOR
            edge_opacity = 0.20


        edge_options = {
            "id": f"edge_{edge_index}",

            "weightRaw": weight,

            "isAlarmConnection":
                is_alarm_connection,

            "baseWidth": base_width,
            "width": base_width,

            "color": {
                "color": edge_color,

                "highlight": (
                    "#FFFFFF"
                    if is_alarm_connection
                    else "#38BDF8"
                ),

                "hover": (
                    ALARM_EDGE_COLOR
                    if is_alarm_connection
                    else "#64748B"
                ),

                "opacity": edge_opacity
            },

            "shadow": {
                "enabled": False
            },

            "smooth": False
        }


        if is_directed:
            edge_options["arrows"] = {
                "to": {
                    "enabled": True,

                    "scaleFactor": (
                        0.58
                        if is_alarm_connection
                        else 0.35
                    )
                }
            }


        net.add_edge(
            source,
            target,
            **edge_options
        )


    # =========================================================
    # 13. TITLE ALANLARINI SİL
    # =========================================================

    for node in net.nodes:
        node.pop(
            "title",
            None
        )

    for edge in net.edges:
        edge.pop(
            "title",
            None
        )


    # =========================================================
    # 14. VIS.JS AYARLARI
    # =========================================================

    net.set_options(
        f"""
    {{
    "autoResize": true,

    "interaction": {{
        "hover": true,
        "hoverConnectedEdges": false,
        "selectConnectedEdges": false,
        "navigationButtons": true,

        "keyboard": {{
        "enabled": true,
        "bindToWindow": false
        }},

        "multiselect": false,
        "hideEdgesOnDrag": true,
        "hideEdgesOnZoom": true,
        "tooltipDelay": 999999
    }},

    "nodes": {{
        "font": {{
        "size": 0,
        "face": "Arial",
        "color": "#DBEAFE",
        "strokeWidth": 3,
        "strokeColor": "#07111F"
        }}
    }},

    "edges": {{
        "selectionWidth": 1.5,
        "hoverWidth": 0.7,
        "arrowStrikethrough": false,
        "smooth": false
    }},

    "physics": {{
        "enabled": true,
        "solver": "forceAtlas2Based",

        "forceAtlas2Based": {{
        "gravitationalConstant": -55,
        "centralGravity": 0.02,
        "springLength": 130,
        "springConstant": 0.04,
        "damping": 0.65,
        "avoidOverlap": 0.35
        }},

        "stabilization": {{
        "enabled": true,
        "iterations": {PHYSICS_ITERATIONS},
        "updateInterval": 40,
        "fit": true
        }},

        "minVelocity": 1.2,
        "maxVelocity": 25
    }},

    "layout": {{
        "improvedLayout": true
    }}
    }}
    """
    )


    # =========================================================
    # 15. HTML OLUŞTUR
    # =========================================================

    generated_html = net.generate_html()
    loading_screen_css = """
    <style>
    #loadingBar {
        background: #07111f !important;
    }

    #loadingBar .text,
    #loadingBar .outerBorder {
        display: none !important;
    }

    #loadingBar::after {
        content: "Servis haritası yükleniyor...";
        color: #94a3b8;
        font-family: Arial, sans-serif;
        font-size: 12px;
    }
    </style>
    """

    generated_html = generated_html.replace(
        "</head>",
        loading_screen_css + "\n</head>",
        1
    )


    # =========================================================
    # 16. ARAYÜZ
    # =========================================================

    custom_interface = """
    <style>
        :root {
            color-scheme: dark;

            --bg: #07111f;
            --panel: rgba(15, 23, 42, 0.96);
            --panel-light: #111c2f;
            --border: rgba(148, 163, 184, 0.24);
            --text: #e2e8f0;
            --muted: #94a3b8;
            --accent: #38bdf8;
            --accent-dark: #0369a1;
            --error: #fb7185;

            --warning: #fdba74;
            --critical: #ef4444;
            --alarm-edge: #ff304f;
        }

        * {
            box-sizing: border-box;
        }

        html,
        body {
            width: 100% !important;
            height: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
            background: var(--bg) !important;
            color: var(--text) !important;
        }

        body {
            font-family:
                Inter,
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                Arial,
                sans-serif !important;
        }

        .card,
        .card-body,
        .container,
        .container-fluid {
            width: 100% !important;
            height: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
            background: var(--bg) !important;
            color: var(--text) !important;
        }

        #mynetwork {
            width: 100% !important;
            height: 100vh !important;
            border: 0 !important;
            outline: 0 !important;

            background:
                radial-gradient(
                    circle at center,
                    #10243f 0%,
                    #07111f 58%,
                    #030712 100%
                ) !important;
        }


        /* =====================================================
        PYVIS NAVIGATION İKONLARI

        Yön okları, +, -, fit ve diğer navigation
        ikonlarını beyaz yapar.
        ===================================================== */

        div.vis-network
        div.vis-navigation
        div.vis-button {
            filter:
                brightness(0)
                invert(1)
                !important;

            opacity: 0.86 !important;
        }

        div.vis-network
        div.vis-navigation
        div.vis-button:hover {
            filter:
                brightness(0)
                invert(1)
                drop-shadow(
                    0 0 4px
                    rgba(255, 255, 255, 0.85)
                )
                !important;

            opacity: 1 !important;
        }

        div.vis-network
        div.vis-navigation
        div.vis-button:active {
            filter:
                brightness(0)
                invert(1)
                !important;

            opacity: 0.65 !important;
        }


        #servicePanel {
            position: fixed;
            top: 16px;
            left: 16px;
            z-index: 10000;
            width: 315px;
            padding: 14px;
            border: 1px solid var(--border);
            border-radius: 14px;
            background: var(--panel);
            color: var(--text);
            box-shadow:
                0 18px 50px
                rgba(0, 0, 0, 0.48);
            backdrop-filter: blur(14px);
        }

        .panel-title {
            margin: 0 0 3px;
            color: #ffffff;
            font-size: 16px;
            font-weight: 700;
        }

        .panel-description {
            margin: 0 0 12px;
            color: var(--muted);
            font-size: 10px;
        }

        .search-row {
            display: flex;
            gap: 7px;
        }

        #serviceSearch {
            flex: 1;
            min-width: 0;
            height: 38px;
            padding: 0 11px;
            border: 1px solid var(--border);
            border-radius: 9px;
            outline: none;
            background: var(--panel-light);
            color: var(--text);
            font-size: 12px;
        }

        #serviceSearch::placeholder {
            color: #64748b;
        }

        #serviceSearch:focus {
            border-color: var(--accent);
            box-shadow:
                0 0 0 3px
                rgba(56, 189, 248, 0.12);
        }

        .panel-button {
            height: 38px;
            padding: 0 13px;
            border:
                1px solid
                rgba(56, 189, 248, 0.25);
            border-radius: 9px;
            background: var(--accent-dark);
            color: #ffffff;
            cursor: pointer;
            font-size: 11px;
            font-weight: 650;
        }

        .panel-button:hover {
            background: #075985;
        }

        .full-button {
            width: 100%;
            margin-top: 8px;
            border-color: var(--border);
            background: #1e293b;
            color: #dbeafe;
        }

        .full-button:hover {
            background: #334155;
        }

        #searchSuggestions {
            display: none;
            max-height: 210px;
            overflow-y: auto;
            margin: 6px 0 0;
            padding: 4px;
            list-style: none;
            border: 1px solid var(--border);
            border-radius: 9px;
            background: #0f172a;
        }

        .suggestion-item {
            display: flex;
            justify-content: space-between;
            gap: 8px;
            padding: 8px 9px;
            border-radius: 7px;
            color: #cbd5e1;
            cursor: pointer;
            font-size: 11px;
        }

        .suggestion-item:hover,
        .suggestion-item.active {
            background:
                rgba(56, 189, 248, 0.14);
            color: #ffffff;
        }

        .suggestion-name {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .suggestion-status {
            flex: 0 0 auto;
            font-size: 9px;
            font-weight: 700;
        }

        .suggestion-status.warning {
            color: var(--warning);
        }

        .suggestion-status.critical {
            color: var(--critical);
        }

        .suggestion-status.normal {
            color: #64748b;
        }

        #selectedCard {
            display: none;
            margin-top: 9px;
            padding: 10px;
            border:
                1px solid
                rgba(56, 189, 248, 0.25);
            border-radius: 9px;
            background:
                rgba(56, 189, 248, 0.08);
        }

        #selectedName {
            overflow-wrap: anywhere;
            color: #ffffff;
            font-size: 12px;
            font-weight: 700;
        }

        #selectedInfo {
            margin-top: 4px;
            color: var(--muted);
            font-size: 10px;
            line-height: 1.5;
        }

        #statusText {
            min-height: 14px;
            margin-top: 7px;
            color: var(--muted);
            font-size: 10px;
        }

        .legend {
            display: grid;
            gap: 7px;
            margin-top: 12px;
            padding-top: 10px;
            border-top:
                1px solid var(--border);
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--muted);
            font-size: 10px;
        }

        .legend-circle {
            width: 12px;
            height: 12px;
            border: 2px solid #f8fafc;
            border-radius: 50%;
            background: #38bdf8;
        }

        .legend-square {
            width: 12px;
            height: 12px;
            border: 1px solid #64748b;
            background: #38bdf8;
        }

        .legend-warning,
        .legend-critical {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }

        .legend-warning {
            border: 2px solid #ffedd5;
            background: var(--warning);
            box-shadow:
                0 0 7px var(--warning);
        }

        .legend-critical {
            border: 2px solid #fee2e2;
            background: var(--critical);
            box-shadow:
                0 0 7px var(--critical);
        }

        .legend-alarm-link {
            width: 25px;
            height: 4px;
            border-radius: 999px;
            background: var(--alarm-edge);
        }

        #hoverCard {
            display: none;
            position: fixed;
            top: 16px;
            right: 16px;
            z-index: 10000;
            width: 275px;
            padding: 14px;
            pointer-events: none;
            border: 1px solid var(--border);
            border-radius: 14px;
            background: var(--panel);
            color: var(--text);
            box-shadow:
                0 18px 50px
                rgba(0, 0, 0, 0.48);
            backdrop-filter: blur(14px);
        }

        #hoverName {
            overflow-wrap: anywhere;
            color: #ffffff;
            font-size: 14px;
            font-weight: 700;
        }

        #hoverCluster {
            display: inline-block;
            margin-top: 6px;
            padding: 3px 7px;
            border-radius: 999px;
            background:
                rgba(56, 189, 248, 0.14);
            color: var(--accent);
            font-size: 9px;
            font-weight: 700;
        }

        .metric-grid {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 7px 12px;
            margin-top: 11px;
            padding-top: 10px;
            border-top:
                1px solid var(--border);
            font-size: 10px;
        }

        .metric-label {
            color: var(--muted);
        }

        .metric-value {
            color: #ffffff;
            font-weight: 700;
            text-align: right;
        }

        @media (max-width: 700px) {
            #servicePanel {
                top: 10px;
                left: 10px;
                width:
                    calc(100vw - 20px);
            }

            #hoverCard {
                top: auto;
                right: 10px;
                bottom: 10px;
                width: 240px;
            }
        }
    </style>


    <div id="servicePanel">
        <h1 class="panel-title">
            Servis Haritası
        </h1>

        <p class="panel-description">
            Servis bağımlılıkları, işlem akışları ve alarmlar
        </p>

        <div class="search-row">
            <input
                id="serviceSearch"
                type="text"
                placeholder="Servis ara..."
                autocomplete="off"
            >

            <button
                id="searchButton"
                type="button"
                class="panel-button"
            >
                Ara
            </button>
        </div>

        <ul id="searchSuggestions"></ul>

        <div id="statusText"></div>

        <div id="selectedCard">
            <div id="selectedName"></div>
            <div id="selectedInfo"></div>
        </div>

        <button
            id="connectionsButton"
            type="button"
            class="panel-button full-button"
        >
            Bağlantılı Servisleri Göster
        </button>

        <button
            id="resetButton"
            type="button"
            class="panel-button full-button"
        >
            Tüm Haritayı Göster
        </button>

        <div class="legend">
            <div class="legend-item">
                <span class="legend-circle"></span>
                <span>Eligible servis</span>
            </div>

            <div class="legend-item">
                <span class="legend-square"></span>
                <span>Diğer servis</span>
            </div>

            <div class="legend-item">
                <span class="legend-warning"></span>
                <span>Warning alarm</span>
            </div>

            <div class="legend-item">
                <span class="legend-critical"></span>
                <span>Critical alarm</span>
            </div>

            <div class="legend-item">
                <span class="legend-alarm-link"></span>
                <span>Doğrudan alarm bağlantısı</span>
            </div>
        </div>
    </div>


    <div id="hoverCard">
        <div id="hoverName"></div>
        <div id="hoverCluster"></div>

        <div class="metric-grid">
            <span class="metric-label">
                Alarm seviyesi
            </span>
            <span
                id="hoverAlarmLevel"
                class="metric-value"
            ></span>

            <span class="metric-label">
                Servis tipi
            </span>
            <span
                id="hoverServiceType"
                class="metric-value"
            ></span>

            <span class="metric-label">
                Toplam bağlantı
            </span>
            <span
                id="hoverDegree"
                class="metric-value"
            ></span>

            <span
                id="inDegreeLabel"
                class="metric-label"
            >
                Gelen bağlantı
            </span>
            <span
                id="hoverInDegree"
                class="metric-value"
            ></span>

            <span
                id="outDegreeLabel"
                class="metric-label"
            >
                Giden bağlantı
            </span>
            <span
                id="hoverOutDegree"
                class="metric-value"
            ></span>

            <span class="metric-label">
                Toplam trafik
            </span>
            <span
                id="hoverTraffic"
                class="metric-value"
            ></span>
        </div>
    </div>


    <script>
    (function () {
        "use strict";

        function initializeMap() {
            if (
                typeof network === "undefined" ||
                typeof nodes === "undefined" ||
                typeof edges === "undefined"
            ) {
                window.setTimeout(
                    initializeMap,
                    100
                );

                return;
            }


            const isDirected =
                __IS_DIRECTED__;

            const labelShowScale =
                __LABEL_SHOW_SCALE__;

            const nodeAlarmIntervalMs =
                __NODE_ALARM_INTERVAL_MS__;

            const edgeAlarmIntervalMs =
                __EDGE_ALARM_INTERVAL_MS__;


            const searchInput =
                document.getElementById(
                    "serviceSearch"
                );

            const searchButton =
                document.getElementById(
                    "searchButton"
                );

            const resetButton =
                document.getElementById(
                    "resetButton"
                );

            const connectionsButton =
                document.getElementById(
                    "connectionsButton"
                );

            const suggestionsBox =
                document.getElementById(
                    "searchSuggestions"
                );

            const selectedCard =
                document.getElementById(
                    "selectedCard"
                );

            const selectedName =
                document.getElementById(
                    "selectedName"
                );

            const selectedInfo =
                document.getElementById(
                    "selectedInfo"
                );

            const statusText =
                document.getElementById(
                    "statusText"
                );

            const hoverCard =
                document.getElementById(
                    "hoverCard"
                );

            const hoverName =
                document.getElementById(
                    "hoverName"
                );

            const hoverCluster =
                document.getElementById(
                    "hoverCluster"
                );

            const hoverAlarmLevel =
                document.getElementById(
                    "hoverAlarmLevel"
                );

            const hoverServiceType =
                document.getElementById(
                    "hoverServiceType"
                );

            const hoverDegree =
                document.getElementById(
                    "hoverDegree"
                );

            const hoverInDegree =
                document.getElementById(
                    "hoverInDegree"
                );

            const hoverOutDegree =
                document.getElementById(
                    "hoverOutDegree"
                );

            const hoverTraffic =
                document.getElementById(
                    "hoverTraffic"
                );

            const inDegreeLabel =
                document.getElementById(
                    "inDegreeLabel"
                );

            const outDegreeLabel =
                document.getElementById(
                    "outDegreeLabel"
                );


            let selectedNodeId = null;
            let suggestions = [];
            let activeSuggestionIndex = -1;
            let labelsVisible = false;


            const originalNodes =
                nodes.get().map(
                    function (node) {
                        return Object.assign(
                            {},
                            node
                        );
                    }
                );

            const originalEdges =
                edges.get().map(
                    function (edge) {
                        return Object.assign(
                            {},
                            edge
                        );
                    }
                );


            const searchableNodes =
                originalNodes.map(
                    function (node) {
                        return {
                            id: node.id,

                            label: String(
                                node.serviceName ||
                                node.label ||
                                node.id
                            ),

                            serviceType: String(
                                node.serviceType ||
                                "Diğer servis"
                            ),

                            isCircleNode: Boolean(
                                node.isCircleNode
                            ),

                            alarmLevel: String(
                                node.alarmLevel ||
                                "none"
                            ),

                            alarmLabel: String(
                                node.alarmLabel ||
                                "Alarm yok"
                            ),

                            isAlarmNode: Boolean(
                                node.isAlarmNode
                            ),

                            alertColor:
                                node.alertColor ||
                                null,

                            cluster: Number(
                                node.cluster
                            ),

                            degree: Number(
                                node.degree || 0
                            ),

                            inDegree: Number(
                                node.inDegree || 0
                            ),

                            outDegree: Number(
                                node.outDegree || 0
                            ),

                            totalTraffic: Number(
                                node.totalTraffic || 0
                            )
                        };
                    }
                );


            const alarmNodes =
                originalNodes.filter(
                    function (node) {
                        return Boolean(
                            node.isAlarmNode
                        );
                    }
                );


            const alarmConnectionEdges =
                originalEdges.filter(
                    function (edge) {
                        return Boolean(
                            edge.isAlarmConnection
                        );
                    }
                );


            function normalizeText(value) {
                return String(value)
                    .toLocaleLowerCase(
                        "tr-TR"
                    )
                    .trim();
            }


            function formatNumber(value) {
                return Number(value)
                    .toLocaleString(
                        "tr-TR",
                        {
                            maximumFractionDigits: 2
                        }
                    );
            }


            function setStatus(
                message,
                isError
            ) {
                statusText.textContent =
                    message || "";

                statusText.style.color =
                    isError
                        ? "#FB7185"
                        : "#94A3B8";
            }


            function findNodeData(nodeId) {
                return searchableNodes.find(
                    function (node) {
                        return (
                            String(node.id) ===
                            String(nodeId)
                        );
                    }
                ) || null;
            }


            function hideSuggestions() {
                suggestionsBox.style.display =
                    "none";

                suggestionsBox.replaceChildren();

                activeSuggestionIndex = -1;
            }


            function renderSuggestions(value) {
                const searchText =
                    normalizeText(value);

                suggestionsBox.replaceChildren();

                activeSuggestionIndex = -1;

                if (!searchText) {
                    suggestions = [];
                    hideSuggestions();
                    return;
                }

                suggestions = searchableNodes
                    .filter(function (node) {
                        return normalizeText(
                            node.label
                        ).includes(searchText);
                    })
                    .sort(function (
                        first,
                        second
                    ) {
                        const firstText =
                            normalizeText(
                                first.label
                            );

                        const secondText =
                            normalizeText(
                                second.label
                            );

                        const firstStarts =
                            firstText.startsWith(
                                searchText
                            );

                        const secondStarts =
                            secondText.startsWith(
                                searchText
                            );

                        if (
                            firstStarts !==
                            secondStarts
                        ) {
                            return firstStarts
                                ? -1
                                : 1;
                        }

                        const alarmRank = {
                            critical: 2,
                            warning: 1,
                            none: 0
                        };

                        return (
                            alarmRank[
                                second.alarmLevel
                            ] -
                            alarmRank[
                                first.alarmLevel
                            ]
                        ) || (
                            second.degree -
                            first.degree
                        );
                    })
                    .slice(0, 12);


                if (suggestions.length === 0) {
                    hideSuggestions();
                    return;
                }


                suggestions.forEach(
                    function (node) {
                        const item =
                            document.createElement(
                                "li"
                            );

                        item.className =
                            "suggestion-item";


                        const name =
                            document.createElement(
                                "span"
                            );

                        name.className =
                            "suggestion-name";

                        name.textContent =
                            node.label;


                        const status =
                            document.createElement(
                                "span"
                            );

                        status.className =
                            "suggestion-status " +
                            (
                                node.alarmLevel ===
                                "critical"
                                    ? "critical"
                                    : node.alarmLevel ===
                                    "warning"
                                        ? "warning"
                                        : "normal"
                            );

                        status.textContent =
                            node.alarmLevel ===
                            "critical"
                                ? "CRITICAL"
                                : node.alarmLevel ===
                                "warning"
                                    ? "WARNING"
                                    : (
                                        node.isCircleNode
                                            ? "DAİRE"
                                            : "KARE"
                                    );


                        item.appendChild(name);
                        item.appendChild(status);


                        item.addEventListener(
                            "mousedown",
                            function (event) {
                                event.preventDefault();

                                searchInput.value =
                                    node.label;

                                selectNode(
                                    node.id
                                );

                                hideSuggestions();
                            }
                        );


                        suggestionsBox.appendChild(
                            item
                        );
                    }
                );


                suggestionsBox.style.display =
                    "block";
            }


            function updateActiveSuggestion() {
                const items =
                    suggestionsBox.querySelectorAll(
                        ".suggestion-item"
                    );

                items.forEach(
                    function (item, index) {
                        item.classList.toggle(
                            "active",
                            index ===
                            activeSuggestionIndex
                        );
                    }
                );
            }


            function findService(value) {
                const searchText =
                    normalizeText(value);

                if (!searchText) {
                    return null;
                }

                const exactMatch =
                    searchableNodes.find(
                        function (node) {
                            return (
                                normalizeText(
                                    node.label
                                ) ===
                                searchText
                            );
                        }
                    );

                if (exactMatch) {
                    return exactMatch;
                }

                return searchableNodes.find(
                    function (node) {
                        return normalizeText(
                            node.label
                        ).includes(searchText);
                    }
                ) || null;
            }


            function showHoverCard(nodeId) {
                const node =
                    findNodeData(nodeId);

                if (!node) {
                    hoverCard.style.display =
                        "none";
                    return;
                }

                hoverName.textContent =
                    node.label;

                hoverCluster.textContent =
                    "Cluster " +
                    node.cluster;

                hoverAlarmLevel.textContent =
                    node.alarmLabel;

                hoverServiceType.textContent =
                    node.serviceType;

                hoverDegree.textContent =
                    formatNumber(
                        node.degree
                    );

                hoverTraffic.textContent =
                    formatNumber(
                        node.totalTraffic
                    );


                if (
                    node.alarmLevel ===
                    "critical"
                ) {
                    hoverAlarmLevel.style.color =
                        "#EF4444";

                } else if (
                    node.alarmLevel ===
                    "warning"
                ) {
                    hoverAlarmLevel.style.color =
                        "#FDBA74";

                } else {
                    hoverAlarmLevel.style.color =
                        "#94A3B8";
                }


                if (isDirected) {
                    inDegreeLabel.style.display = "";
                    outDegreeLabel.style.display = "";
                    hoverInDegree.style.display = "";
                    hoverOutDegree.style.display = "";

                    hoverInDegree.textContent =
                        formatNumber(
                            node.inDegree
                        );

                    hoverOutDegree.textContent =
                        formatNumber(
                            node.outDegree
                        );

                } else {
                    inDegreeLabel.style.display =
                        "none";

                    outDegreeLabel.style.display =
                        "none";

                    hoverInDegree.style.display =
                        "none";

                    hoverOutDegree.style.display =
                        "none";
                }

                hoverCard.style.display =
                    "block";
            }


            function hideHoverCard() {
                hoverCard.style.display =
                    "none";
            }


            function showSelectedCard(nodeId) {
                const node =
                    findNodeData(nodeId);

                if (!node) {
                    selectedCard.style.display =
                        "none";
                    return;
                }

                selectedName.textContent =
                    node.label;

                selectedInfo.textContent =
                    node.alarmLabel +
                    " · " +
                    node.serviceType +
                    " · Cluster " +
                    node.cluster +
                    " · " +
                    node.degree +
                    " bağlantı · " +
                    formatNumber(
                        node.totalTraffic
                    ) +
                    " toplam trafik";

                selectedCard.style.display =
                    "block";
            }


            function setAllVisible() {
                nodes.update(
                    originalNodes.map(
                        function (node) {
                            return {
                                id: node.id,
                                hidden: false
                            };
                        }
                    )
                );

                edges.update(
                    originalEdges.map(
                        function (edge) {
                            return {
                                id: edge.id,
                                hidden: false
                            };
                        }
                    )
                );
            }


            function selectNode(nodeId) {
                const node =
                    nodes.get(nodeId);

                if (!node) {
                    setStatus(
                        "Servis bulunamadı.",
                        true
                    );

                    return;
                }

                setAllVisible();

                selectedNodeId = nodeId;

                network.unselectAll();
                network.selectNodes([nodeId]);

                showSelectedCard(nodeId);

                network.focus(
                    nodeId,
                    {
                        scale: 1.45,

                        animation: {
                            duration: 400,
                            easingFunction:
                                "easeInOutQuad"
                        }
                    }
                );

                setStatus(
                    "Seçilen servis: " +
                    String(
                        node.label ||
                        node.id
                    ),
                    false
                );
            }


            function showConnections() {
                if (selectedNodeId === null) {
                    setStatus(
                        "Önce bir servis seçin.",
                        true
                    );

                    return;
                }

                const connectedNodeIds =
                    network.getConnectedNodes(
                        selectedNodeId
                    );

                const visibleNodeIds =
                    new Set(
                        connectedNodeIds
                            .concat(
                                [selectedNodeId]
                            )
                            .map(String)
                    );


                nodes.update(
                    originalNodes.map(
                        function (node) {
                            return {
                                id: node.id,

                                hidden:
                                    !visibleNodeIds.has(
                                        String(node.id)
                                    )
                            };
                        }
                    )
                );


                edges.update(
                    originalEdges.map(
                        function (edge) {
                            const visible = (
                                visibleNodeIds.has(
                                    String(edge.from)
                                )
                                &&
                                visibleNodeIds.has(
                                    String(edge.to)
                                )
                            );

                            return {
                                id: edge.id,
                                hidden: !visible
                            };
                        }
                    )
                );


                window.setTimeout(
                    function () {
                        network.fit({
                            nodes:
                                Array.from(
                                    visibleNodeIds
                                ),

                            animation: {
                                duration: 350,
                                easingFunction:
                                    "easeInOutQuad"
                            }
                        });
                    },
                    40
                );


                setStatus(
                    connectedNodeIds.length +
                    " bağlantılı servis gösteriliyor.",
                    false
                );
            }


            function performSearch() {
                const service =
                    findService(
                        searchInput.value
                    );

                hideSuggestions();

                if (!service) {
                    setStatus(
                        "Eşleşen servis bulunamadı.",
                        true
                    );

                    return;
                }

                searchInput.value =
                    service.label;

                selectNode(
                    service.id
                );
            }


            function resetGraph() {
                selectedNodeId = null;

                setAllVisible();
                network.unselectAll();

                searchInput.value = "";

                selectedCard.style.display =
                    "none";

                hideSuggestions();
                hideHoverCard();

                network.fit({
                    animation: {
                        duration: 400,
                        easingFunction:
                            "easeInOutQuad"
                    }
                });

                setStatus(
                    searchableNodes.length +
                    " servis gösteriliyor.",
                    false
                );
            }


            function updateLabelVisibility(scale) {
                const shouldShowLabels =
                    scale >= labelShowScale;

                if (
                    shouldShowLabels ===
                    labelsVisible
                ) {
                    return;
                }

                labelsVisible =
                    shouldShowLabels;

                network.setOptions({
                    nodes: {
                        font: {
                            size:
                                labelsVisible
                                    ? 11
                                    : 0,

                            face: "Arial",
                            color: "#DBEAFE",

                            strokeWidth:
                                labelsVisible
                                    ? 3
                                    : 0,

                            strokeColor:
                                "#07111F"
                        }
                    }
                });
            }


            let nodePulseState = false;

            function updateAlarmNodePulse() {
                if (alarmNodes.length === 0) {
                    return;
                }

                nodePulseState =
                    !nodePulseState;

                nodes.update(
                    alarmNodes.map(
                        function (node) {
                            return {
                                id: node.id,

                                borderWidth:
                                    nodePulseState
                                        ? 4.6
                                        : 2.6,

                                shadow: {
                                    enabled: true,

                                    color:
                                        node.alertColor,

                                    size:
                                        nodePulseState
                                            ? 14
                                            : 5,

                                    x: 0,
                                    y: 0
                                }
                            };
                        }
                    )
                );
            }


            let edgePulseState = false;

            function updateAlarmEdgePulse() {
                if (
                    alarmConnectionEdges.length === 0
                ) {
                    return;
                }

                edgePulseState =
                    !edgePulseState;

                edges.update(
                    alarmConnectionEdges.map(
                        function (edge) {
                            const baseWidth =
                                Number(
                                    edge.baseWidth ||
                                    3.1
                                );

                            return {
                                id: edge.id,

                                width:
                                    edgePulseState
                                        ? baseWidth + 1.5
                                        : baseWidth,

                                color: {
                                    color:
                                        "#FF304F",

                                    highlight:
                                        "#FFFFFF",

                                    hover:
                                        "#FF304F",

                                    opacity:
                                        edgePulseState
                                            ? 1
                                            : 0.62
                                }
                            };
                        }
                    )
                );
            }


            network.on(
                "zoom",
                function (params) {
                    updateLabelVisibility(
                        Number(
                            params.scale || 1
                        )
                    );
                }
            );


            searchInput.addEventListener(
                "input",
                function () {
                    renderSuggestions(
                        searchInput.value
                    );
                }
            );


            searchInput.addEventListener(
                "keydown",
                function (event) {
                    if (
                        event.key ===
                        "ArrowDown"
                    ) {
                        if (
                            suggestions.length === 0
                        ) {
                            return;
                        }

                        event.preventDefault();

                        activeSuggestionIndex =
                            Math.min(
                                activeSuggestionIndex + 1,
                                suggestions.length - 1
                            );

                        updateActiveSuggestion();
                    }


                    if (
                        event.key ===
                        "ArrowUp"
                    ) {
                        if (
                            suggestions.length === 0
                        ) {
                            return;
                        }

                        event.preventDefault();

                        activeSuggestionIndex =
                            Math.max(
                                activeSuggestionIndex - 1,
                                0
                            );

                        updateActiveSuggestion();
                    }


                    if (
                        event.key ===
                        "Enter"
                    ) {
                        event.preventDefault();

                        if (
                            activeSuggestionIndex >= 0
                            &&
                            suggestions[
                                activeSuggestionIndex
                            ]
                        ) {
                            const selected =
                                suggestions[
                                    activeSuggestionIndex
                                ];

                            searchInput.value =
                                selected.label;

                            selectNode(
                                selected.id
                            );

                            hideSuggestions();

                        } else {
                            performSearch();
                        }
                    }


                    if (
                        event.key ===
                        "Escape"
                    ) {
                        hideSuggestions();
                    }
                }
            );


            searchInput.addEventListener(
                "blur",
                function () {
                    window.setTimeout(
                        hideSuggestions,
                        120
                    );
                }
            );


            searchButton.addEventListener(
                "click",
                performSearch
            );

            connectionsButton.addEventListener(
                "click",
                showConnections
            );

            resetButton.addEventListener(
                "click",
                resetGraph
            );


            network.on(
                "hoverNode",
                function (params) {
                    showHoverCard(
                        params.node
                    );
                }
            );


            network.on(
                "blurNode",
                hideHoverCard
            );


            network.on(
                "selectNode",
                function (params) {
                    if (
                        params.nodes.length === 0
                    ) {
                        return;
                    }

                    selectedNodeId =
                        params.nodes[0];

                    const node =
                        nodes.get(
                            selectedNodeId
                        );

                    if (node) {
                        searchInput.value =
                            String(
                                node.label ||
                                node.id
                            );
                    }

                    showSelectedCard(
                        selectedNodeId
                    );
                }
            );


            network.on(
                "doubleClick",
                function (params) {
                    if (
                        params.nodes.length === 0
                    ) {
                        resetGraph();
                    }
                }
            );


            network.once(
                "stabilizationIterationsDone",
                function () {
                    const loadingBar =
                        document.getElementById("loadingBar");

                    if (loadingBar) {
                        loadingBar.style.display = "none";
                    }
                    network.setOptions({
                        physics: {
                            enabled: false
                        }
                    });

                    network.fit({
                        animation: false
                    });

                    updateLabelVisibility(
                        Number(
                            network.getScale() || 1
                        )
                    );

                    setStatus(
                        searchableNodes.length +
                        " servis · " +
                        alarmConnectionEdges.length +
                        " doğrudan alarm bağlantısı",
                        false
                    );
                    
                }
            );


            window.setInterval(
                updateAlarmNodePulse,
                nodeAlarmIntervalMs
            );

            window.setInterval(
                updateAlarmEdgePulse,
                edgeAlarmIntervalMs
            );


            updateLabelVisibility(
                Number(
                    network.getScale() || 1
                )
            );
        }


        if (
            document.readyState ===
            "loading"
        ) {
            document.addEventListener(
                "DOMContentLoaded",
                initializeMap
            );

        } else {
            initializeMap();
        }
    })();
    </script>
    """


    # =========================================================
    # 17. JAVASCRIPT PARAMETRELERİ
    # =========================================================

    custom_interface = custom_interface.replace(
        "__IS_DIRECTED__",
        json.dumps(is_directed)
    )

    custom_interface = custom_interface.replace(
        "__LABEL_SHOW_SCALE__",
        json.dumps(LABEL_SHOW_SCALE)
    )

    custom_interface = custom_interface.replace(
        "__NODE_ALARM_INTERVAL_MS__",
        json.dumps(
            NODE_ALARM_INTERVAL_MS
        )
    )

    custom_interface = custom_interface.replace(
        "__EDGE_ALARM_INTERVAL_MS__",
        json.dumps(
            EDGE_ALARM_INTERVAL_MS
        )
    )


    # =========================================================
    # 18. HTML'E EKLE
    # =========================================================

    if "</body>" not in generated_html:
        raise ValueError(
            "PyVis HTML içinde </body> etiketi bulunamadı."
        )

    final_html = generated_html.replace(
        "</body>",
        custom_interface + "\n</body>",
        1
    )


    # =========================================================
    # 19. TOOLTIP KONTROLÜ
    # =========================================================

    old_tooltip_fragments = [
        "font-family:Arial;line-height:1.6",
        "<b style='font-size:15px'>",
        '<b style="font-size:15px">',
        '"title": "<',
        '"title":"<'
    ]

    detected_fragments = [
        fragment
        for fragment in old_tooltip_fragments
        if fragment in final_html
    ]

    if detected_fragments:
        raise RuntimeError(
            "Eski HTML tooltip içeriği bulundu: "
            + ", ".join(
                detected_fragments
            )
        )


    # =========================================================
    # 20. DOSYAYI KAYDET
    # =========================================================

    # output_path = os.path.abspath(
    #     OUTPUT_HTML
    # )

    # with open(output_path,"w",encoding="utf-8") as file:
    #     file.write(
    #         final_html
    #     )


    # =========================================================
    # 21. ÖZET
    # =========================================================

    # print()
    # print("Servis haritası oluşturuldu:")
    # print(output_path)

    # print()
    # print(f"Toplam servis: {len(node_names)}")

    # print(
    #     f"Eligible / daire servis: "
    #     f"{eligible_match_count}"
    # )

    # print(
    #     f"Diğer / kare servis: "
    #     f"{len(node_names) - eligible_match_count}"
    # )

    # print(
    #     f"Warning alarm node: "
    #     f"{warning_match_count}"
    # )

    # print(
    #     f"Critical alarm node: "
    #     f"{critical_match_count}"
    # )

    # print(
    #     "Birinci derece alarm bağlantısı: "
    #     f"{alarm_connection_count}"
    # )

    # if unmatched_alarm_services:
    #     print()

    #     print(
    #         "Graph içinde bulunamayan alarm servis sayısı:",
    #         len(unmatched_alarm_services)
    #     )

    #     print(
    #         "İlk 20 eşleşmeyen alarm servisi:",
    #         unmatched_alarm_services[:20]
    #     )
    return final_html

#create_service_map()
# import webbrowser
# webbrowser.open("service_map_optimized_alarm_white_controls.html")

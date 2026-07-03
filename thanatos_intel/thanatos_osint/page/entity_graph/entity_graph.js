frappe.pages['entity-graph'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Grafo Entità'),
        single_column: true,
    });

    // Field cerca entità
    const $body = $(wrapper).find('.layout-main-section');
    $body.html(`
        <div class="entity-graph-wrap" style="padding:12px;">
            <div class="row" style="margin-bottom:10px;">
                <div class="col-md-8">
                    <input type="text" class="form-control entity-search" placeholder="Cerca Investigation Entity per nome…" />
                </div>
                <div class="col-md-2">
                    <select class="form-control depth-select">
                        <option value="1">Profondità 1</option>
                        <option value="2" selected>Profondità 2</option>
                        <option value="3">Profondità 3</option>
                    </select>
                </div>
                <div class="col-md-2">
                    <button class="btn btn-primary btn-load" style="width:100%;">Carica grafo</button>
                </div>
            </div>
            <div class="graph-stats text-muted" style="font-size:12px; margin-bottom:6px;"></div>
            <div id="entity-graph-canvas" style="height:70vh; border:1px solid #444; background:#0e1a17; border-radius:8px;"></div>
        </div>
    `);

    const $canvas = $body.find('#entity-graph-canvas');
    const $stats = $body.find('.graph-stats');
    let network = null;

    // Carica vis-network via CDN se non presente
    if (!window.vis) {
        const script = document.createElement('script');
        script.src = 'https://unpkg.com/vis-network/standalone/umd/vis-network.min.js';
        script.onload = () => console.log('vis-network loaded');
        document.head.appendChild(script);
    }

    // Autocomplete input
    $body.find('.entity-search').autocomplete({
        source: (req, resp) => {
            frappe.db.get_list('Investigation Entity', {
                filters: [['primary_identifier', 'like', `%${req.term}%`]],
                fields: ['name', 'primary_identifier', 'entity_type'],
                limit: 15,
            }).then(rows => resp(rows.map(r => ({ label: `${r.primary_identifier} (${r.entity_type})`, value: r.name }))));
        },
        minLength: 2,
    });

    const loadGraph = () => {
        const entity = $body.find('.entity-search').val();
        const depth = parseInt($body.find('.depth-select').val());
        if (!entity) { frappe.msgprint(__('Seleziona un\'entità')); return; }
        if (!window.vis) { setTimeout(loadGraph, 500); return; }
        frappe.call({
            method: 'thanatos_intel.osint.entity_graph.entity_graph',
            args: { entity, depth },
            callback: (r) => {
                const g = r.message;
                $stats.text(`${g.stats.nodes} nodi · ${g.stats.edges} archi · profondità ${g.stats.depth}${g.stats.truncated ? ' · TRONCATO' : ''}`);
                const data = {
                    nodes: new vis.DataSet(g.nodes),
                    edges: new vis.DataSet(g.edges),
                };
                const options = {
                    nodes: { font: { color: '#eee', size: 13 }, borderWidth: 2 },
                    edges: { color: '#61cfc9', font: { color: '#aaa', size: 10, strokeWidth: 0 }, smooth: true, arrows: { to: { scaleFactor: 0.5 } } },
                    physics: { stabilization: true, barnesHut: { gravitationalConstant: -8000, springLength: 180 } },
                    interaction: { hover: true, tooltipDelay: 200 },
                };
                if (network) network.destroy();
                network = new vis.Network($canvas[0], data, options);
                network.on('doubleClick', (params) => {
                    if (params.nodes.length) {
                        frappe.set_route('Form', 'Investigation Entity', params.nodes[0]);
                    }
                });
            },
        });
    };

    $body.find('.btn-load').on('click', loadGraph);

    // Preselezione via query param
    const preset = frappe.utils.get_url_arg('entity');
    if (preset) {
        $body.find('.entity-search').val(preset);
        setTimeout(loadGraph, 800);
    }
};

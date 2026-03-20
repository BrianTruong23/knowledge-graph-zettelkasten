document.addEventListener('DOMContentLoaded', function () {
    fetch('graph_data.json')
        .then(response => response.json())
        .then(data => {
            const nodes = new vis.DataSet(data.nodes);
            const edges = new vis.DataSet(data.edges);

            const container = document.getElementById('mynetwork');
            const graphData = { nodes: nodes, edges: edges };
            const options = {
                nodes: {
                    shape: 'dot',
                    size: 16,
                    font: {
                        size: 14,
                        color: '#333'
                    },
                    borderWidth: 2
                },
                edges: {
                    width: 2,
                    arrows: 'to',
                    color: { inherit: 'from' }
                },
                physics: {
                    enabled: true,
                    barnesHut: {
                        gravitationalConstant: -2000,
                        centralGravity: 0.3,
                        springLength: 95,
                        springConstant: 0.04,
                        damping: 0.09,
                        avoidOverlap: 0.8
                    },
                    solver: 'barnesHut',
                    stabilization: {
                        enabled: true,
                        iterations: 2500,
                        updateInterval: 25
                    }
                },
                interaction: {
                    navigationButtons: true,
                    keyboard: true
                }
            };

            const network = new vis.Network(container, graphData, options);

            // Add double click listener for node details
            network.on("doubleClick", function (params) {
                if (params.nodes.length > 0) {
                    const nodeId = params.nodes[0];
                    const node = nodes.get(nodeId);
                    if (node && node.type === 'note') {
                        // For a 'note' type node, maybe highlight it or show its raw text
                        alert('Note: ' + node.label + '

Content: ' + node.fullText); // Assuming fullText exists
                    } else if (node && node.type === 'topic') {
                        alert('Topic: ' + node.label);
                    }
                }
            });
        })
        .catch(error => console.error('Error fetching graph data:', error));
});
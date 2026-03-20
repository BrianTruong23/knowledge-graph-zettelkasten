import json
import os
import requests
import hashlib
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "openrouter/auto" # Using the specified alias
NOTES_DIR = "notes"
OUTPUT_DIR = "web"
GRAPH_DATA_FILE = os.path.join(OUTPUT_DIR, "graph_data.json")
HTML_FILE = os.path.join(OUTPUT_DIR, "index.html")
GRAPH_JS_FILE = os.path.join(OUTPUT_DIR, "script.js")
GRAPH_CSS_FILE = os.path.join(OUTPUT_DIR, "style.css")
CACHE_DIR = os.path.join(OUTPUT_DIR, ".cache")
CACHE_HASH_FILE = os.path.join(CACHE_DIR, "notes_hash.txt")
PORT = 8000

def read_notes(notes_dir):
    notes_content = {}
    if not os.path.exists(notes_dir):
        print(f"Notes directory '{notes_dir}' not found. Please create it and add your notes.")
        return notes_content
    for filename in os.listdir(notes_dir):
        if filename.endswith(".md") or filename.endswith(".txt"):
            filepath = os.path.join(notes_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                notes_content[filename] = f.read()
    return notes_content

def call_openrouter_api(prompt, max_tokens=1000):
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY environment variable not set.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens,}
    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def generate_graph_data(notes_content):

    # Calculate hash of current notes content for caching
    notes_combined_content = json.dumps(notes_content, sort_keys=True)
    notes_hash_str = hashlib.md5(notes_combined_content.encode('utf-8')).hexdigest()

    # Check for cached data
    if os.path.exists(GRAPH_DATA_FILE) and os.path.exists(CACHE_HASH_FILE):
        with open(CACHE_HASH_FILE, 'r') as f:
            cached_hash = f.read().strip()
        
        if cached_hash == notes_hash_str:
            print("Notes content has not changed. Loading graph data from cache.")
            with open(GRAPH_DATA_FILE, 'r', encoding='utf-8') as f:
                graph_data = json.load(f)
            
            # Ensure fullText is present for note nodes from cache
            for filename, content in notes_content.items():
                note_id = "note_" + filename.lower().replace('.md', '').replace('.txt', '').replace(' ', '_').replace('-', '_')
                for node in graph_data["nodes"]:
                    if node.get("id") == note_id and node.get("type") == "note" and "fullText" not in node:
                        node["fullText"] = content
            
            return graph_data
        else:
            print("Notes content has changed. Regenerating graph data...")
    else:
        print("No cached graph data found or hash mismatch. Generating new data...")

    # If no cache or cache invalid, proceed with LLM call
    all_notes_text = "\n\n---\n\n".join([f"## {title}\n{content}" for title, content in notes_content.items()])

    # Prompt for topic extraction
    topic_prompt = f"""
    From the following collection of Zettelkasten notes, identify the main topics or key concepts.
    For each note, list the prominent topics mentioned in that note. Ensure each original note is represented.
    Then, identify broader themes that connect multiple notes, and direct links stated or implied between individual notes.
    Output the result as a JSON object with two keys: "nodes" and "edges".

    "nodes" should be an array of objects. Each object represents a concept or an actual note.
    Each node object should have:
    - "id": A unique string identifier for the node.
    - "label": A human-readable name for the topic or the note title.
    - "type": "topic" (for general concepts) or "note" (for individual notes). For "note" types, include the full original text as `fullText` for display.
    - "group": An integer to visually group related nodes (optional, e.g., for clusters).

    "edges" should be an array of objects, each representing a relationship between nodes.
    Each edge object should have:
    - "from": The "id" of the source node.
- "to": The "id" of the target node.
- "label": A brief description of the relationship (e.g., "expands on", "references", "related to").
- "arrows": "to" or "from" or "to;from" indicating direction.
- "color": A CSS color string (e.g., "#FF0000") to categorize relationships (optional).

    Here are the notes:
    {all_notes_text}

    Ensure the output is a single, valid JSON object with "nodes" and "edges" arrays.

    JSON Output:
    """
    
    print("Sending topic extraction prompt to OpenRouter...")
    topic_response_json = call_openrouter_api(topic_prompt)
    
    try:
        graph_data = json.loads(topic_response_json)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from OpenRouter API: {e}")
        print("Raw response:", topic_response_json)
        # Fallback to an empty graph if JSON is malformed
        graph_data = {"nodes": [], "edges": []}
    
    # Ensure individual notes are added as nodes if not already by the LLM
    # And add fullText to note nodes
    for filename, content in notes_content.items():
        note_id = "note_" + filename.lower().replace('.md', '').replace('.txt', '').replace(' ', '_').replace('-', '_') # Simple sanitization
        if not any(node.get("id") == note_id for node in graph_data["nodes"]):
            graph_data["nodes"].append({"id": note_id, "label": filename.replace('.md', '').replace('.txt', ''), "type": "note", "fullText": content})
        else:
            # If LLM already created the node, make sure fullText is present
            for node in graph_data["nodes"]:
                if node.get("id") == note_id and "fullText" not in node:
                    node["fullText"] = content
    
    # Save the new hash to cache
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_HASH_FILE, 'w') as f:
        f.write(notes_hash_str)

    return graph_data


def save_graph_data(graph_data, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(graph_data, f, indent=2)
    print(f"Graph data saved to {output_file}")

class CustomHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=OUTPUT_DIR, **kwargs)

def start_http_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, CustomHandler)
    print(f"Serving visualization on http://localhost:{PORT} from directory {OUTPUT_DIR}")
    httpd.serve_forever()

def main():
    # 1. Create notes directory if it doesn't exist and add example notes
    os.makedirs(NOTES_DIR, exist_ok=True)
    with open(os.path.join(NOTES_DIR, "Example Note 1.md"), "w") as f:
        f.write("The Zettelkasten method is a knowledge management and note-taking method. It's often associated with Niklas Luhmann. It emphasizes interconnected notes and atomic ideas.")
    with open(os.path.join(NOTES_DIR, "Example Note 2.md"), "w") as f:
        f.write("Niklas Luhmann was a German sociologist who used the Zettelkasten method extensively. He published over 70 books and 400 scholarly articles, reportedly thanks to his Zettelkasten.")
    with open(os.path.join(NOTES_DIR, "Visualization Techniques.md"), "w") as f:
        f.write("Visualizing complex data can use nodes and edges. Tools like D3.js or vis.js are popular for interactive graph visualizations in web browsers.")

    print(f"Created example notes in {NOTES_DIR}/")

    # 2. Read notes
    notes = read_notes(NOTES_DIR)
    if not notes:
        print("No notes found to process. Exiting.")
        return

    # --- Main Logic: Generate and Save Graph Data ---
    # 3. Generate graph data using OpenRouter (with caching)
    graph_data = generate_graph_data(notes)

    # 4. Save graph data to be consumed by the web visualization
    save_graph_data(graph_data, GRAPH_DATA_FILE)

    # --- Web Visualization Setup (Static Files) ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(HTML_FILE, "w") as f:
        f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Knowledge Graph Visualization</title>
    <link rel="stylesheet" href="style.css">
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
</head>
<body>
    <div id="mynetwork"></div>
    <script src="script.js"></script>
</body>
</html>""")

    with open(GRAPH_CSS_FILE, "w") as f:
        f.write("""#mynetwork {
    width: 100%;
    height: 90vh;
    border: 1px solid lightgray;
    background-color: #f9f9f9;
}""")
    
    with open(GRAPH_JS_FILE, "w") as f:
        f.write("""document.addEventListener('DOMContentLoaded', function () {
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
                        alert('Note: ' + node.label + '\n\nContent: ' + node.fullText); // Assuming fullText exists
                    } else if (node && node.type === 'topic') {
                        alert('Topic: ' + node.label);
                    }
                }
            });
        })
        .catch(error => console.error('Error fetching graph data:', error));
});""")
    
    print(f"Web visualization files created in {OUTPUT_DIR}/")

    # 6. Start local HTTP server in a new thread
    server_thread = threading.Thread(target=start_http_server)
    server_thread.daemon = True  # Allows the main program to exit even if the thread is running
    server_thread.start()

    print(f"HTTP server started in background on http://localhost:{PORT}")
    print("You can now open a browser to view the visualization: http://localhost:{PORT}/index.html")
    print("Press Ctrl+C to stop the application.")

    # Keep the main thread alive for a while to allow server to run and browser automation (if any)
    try:
        # This will block indefinitely until program is interrupted
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
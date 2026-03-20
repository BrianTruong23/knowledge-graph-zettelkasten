import json
import os
import requests
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
    data = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def generate_graph_data(notes_content):
    # Ensure all newlines are properly escaped for text sent to LLM in a structured way
    all_notes_text = "\n\n---\n\n".join([
        f"## {title}\n{content}"
        for title, content in notes_content.items()
    ])
    # Note: Using json.dumps to handle internal quotes and newlines in content, then slicing [1:-1] to remove enclosing quotes
    # This assumes the LLM can parse this structure effectively.

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

    Here are the notes in JSON format (title and content): 
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
        note_id = "note_" + filename.lower().replace('.md', '').replace('.txt', '').replace(' ', '_').replace('-', '_')
        if not any(node.get("id") == note_id for node in graph_data["nodes"]):
            graph_data["nodes"].append({"id": note_id, "label": filename.replace('.md', '').replace('.txt', ''), "type": "note", "fullText": content})
        else:
            # If LLM already created the node, make sure fullText is present
            for node in graph_data["nodes"]:
                if node.get("id") == note_id and "fullText" not in node:
                    node["fullText"] = content

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
    # 3. Generate graph data using OpenRouter
    graph_data = generate_graph_data(notes)

    # 4. Save graph data to be consumed by the web visualization
    save_graph_data(graph_data, GRAPH_DATA_FILE)

    # --- Web Visualization Setup (Static Files) ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # HTML content - now loaded from existing file
    # CSS content - now loaded from existing file
    # JS content - now loaded from existing file

    # 5. Start local HTTP server in a new thread
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

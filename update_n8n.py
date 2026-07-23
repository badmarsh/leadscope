import json, glob

for file in glob.glob('n8n_workflows/*.json'):
    with open(file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    changed = False
    for node in data.get('nodes', []):
        if node.get('type') == 'n8n-nodes-base.httpRequest':
            if 'options' not in node['parameters']:
                node['parameters']['options'] = {}
            if 'sendHeaders' not in node['parameters']:
                node['parameters']['sendHeaders'] = True
            
            # For newer n8n nodes, header definition uses 'headerParameters'
            if 'headerParameters' not in node['parameters']:
                node['parameters']['headerParameters'] = {'parameters': []}
            elif 'parameters' not in node['parameters']['headerParameters']:
                node['parameters']['headerParameters']['parameters'] = []
                
            headers = node['parameters']['headerParameters']['parameters']
            
            if not any(h.get('name') == 'X-Internal-Token' for h in headers):
                headers.append({
                    'name': 'X-Internal-Token',
                    'value': '={{ $env["INTERNAL_API_TOKEN"] }}'
                })
                changed = True
    if changed:
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f'Updated {file}')

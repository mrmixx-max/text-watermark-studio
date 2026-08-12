from __future__ import annotations

import json
from pathlib import Path
from collections import Counter, defaultdict

GRAPH_PATH = Path(__file__).resolve().parents[3] / 'data' / 'graph' / 'graph.json'
COMMUNITIES_PATH = Path(__file__).resolve().parents[3] / 'data' / 'graph' / 'communities.json'

class CommunityService:
    def __init__(self, graph_path: Path | None = None, communities_path: Path | None = None):
        self.graph_path = graph_path or GRAPH_PATH
        self.communities_path = communities_path or COMMUNITIES_PATH
    def _load_graph(self): return json.loads(self.graph_path.read_text(encoding='utf-8'))
    def _save_communities(self, data): self.communities_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    def _load_communities(self): return json.loads(self.communities_path.read_text(encoding='utf-8'))
    def detect(self, min_size: int = 2):
        g = self._load_graph()
        adjacency = defaultdict(set)
        for e in g['edges']:
            adjacency[e['source']].add(e['target'])
            adjacency[e['target']].add(e['source'])
        labels = {n['id']: n['id'] for n in g['nodes']}
        changed = True
        iterations = 0
        while changed and iterations < 20:
            changed = False
            iterations += 1
            for node in sorted(labels):
                nbrs = adjacency.get(node, set())
                if not nbrs:
                    continue
                counts = Counter(labels[n] for n in nbrs)
                best = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[0][0]
                if labels[node] != best:
                    labels[node] = best
                    changed = True
        grouped = defaultdict(list)
        for node_id, label in labels.items():
            grouped[label].append(node_id)
        communities = []
        for idx, members in enumerate(grouped.values(), start=1):
            if len(members) < min_size:
                continue
            member_nodes = [n for n in g['nodes'] if n['id'] in members]
            type_counts = Counter(n.get('type', 'Unknown') for n in member_nodes)
            communities.append({'id': f'community_{idx}', 'members': members, 'size': len(members), 'top_types': dict(type_counts.most_common(5))})
        result = {'communities': communities}
        self._save_communities(result)
        return result
    def summarize(self):
        g = self._load_graph()
        data = self._load_communities()
        node_map = {n['id']: n for n in g['nodes']}
        summaries = []
        for c in data['communities']:
            members = [node_map[m] for m in c['members'] if m in node_map]
            labels = [m.get('label', m['id']) for m in members[:10]]
            types = Counter(m.get('type', 'Unknown') for m in members)
            dominant = ', '.join(f'{k} ({v})' for k, v in types.most_common(3))
            summary = f"Cluster around {', '.join(labels[:3])}. Dominant types: {dominant}. Members: {len(members)}."
            summaries.append({'community_id': c['id'], 'summary': summary, 'members_preview': labels[:10], 'size': c['size']})
        payload = {'communities': [c | next((s for s in summaries if s['community_id'] == c['id']), {}) for c in data['communities']]}
        self._save_communities(payload)
        return payload
    def list(self):
        return self._load_communities()
    def get(self, community_id: str):
        data = self._load_communities()
        match = next((c for c in data['communities'] if c['id'] == community_id), None)
        return {'community': match}

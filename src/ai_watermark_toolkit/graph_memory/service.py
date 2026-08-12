from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

SCHEMA_PATH = Path(__file__).resolve().parents[3] / 'data' / 'graph' / 'schema.json'
GRAPH_PATH = Path(__file__).resolve().parents[3] / 'data' / 'graph' / 'graph.json'

class GraphMemoryService:
    def __init__(self, schema_path: Path | None = None, graph_path: Path | None = None):
        self.schema_path = schema_path or SCHEMA_PATH
        self.graph_path = graph_path or GRAPH_PATH
    def _load_schema(self): return json.loads(self.schema_path.read_text(encoding='utf-8'))
    def _load_graph(self): return json.loads(self.graph_path.read_text(encoding='utf-8'))
    def _save_graph(self, data): self.graph_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    def schema(self): return self._load_schema()
    def graph(self): return self._load_graph()
    def add_node(self, node: dict):
        if not node.get('id'):
            raise ValueError('node_id_required')
        g = self._load_graph(); now = datetime.utcnow().isoformat()
        node.setdefault('created_at', now); node['updated_at'] = now
        g['nodes'] = [n for n in g['nodes'] if n.get('id') != node['id']] + [node]
        self._save_graph(g); return node
    def add_edge(self, edge: dict):
        if not edge.get('source') or not edge.get('target'):
            raise ValueError('edge_source_target_required')
        g = self._load_graph(); edge.setdefault('weight', 1.0); edge.setdefault('evidence', []); edge['created_at'] = datetime.utcnow().isoformat()
        g['edges'].append(edge); self._save_graph(g); return edge
    def ingest_fact(self, subject: str, relation: str, object_: str, subject_type='Entity', object_type='Entity', evidence=None):
        self.add_node({'id': subject.lower().replace(' ','_'), 'label': subject, 'type': subject_type})
        self.add_node({'id': object_.lower().replace(' ','_'), 'label': object_, 'type': object_type})
        return self.add_edge({'source': subject.lower().replace(' ','_'), 'target': object_.lower().replace(' ','_'), 'relation': relation, 'evidence': evidence or []})
    def neighbors(self, node_id: str):
        g = self._load_graph(); nbr_edges = [e for e in g['edges'] if e['source'] == node_id or e['target'] == node_id]
        node_ids = {e['source'] for e in nbr_edges} | {e['target'] for e in nbr_edges}
        nodes = [n for n in g['nodes'] if n['id'] in node_ids]
        return {'center': node_id, 'nodes': nodes, 'edges': nbr_edges}
    def query(self, label: str):
        g = self._load_graph(); matches = [n for n in g['nodes'] if label.lower() in n.get('label','').lower() or label.lower() in n.get('id','').lower()]
        return {'matches': matches}
    def subgraph(self, seed: str, depth: int = 1):
        g = self._load_graph(); frontier = {seed}; seen = set(frontier); edges = []
        for _ in range(depth):
            step = [e for e in g['edges'] if e['source'] in frontier or e['target'] in frontier]
            edges.extend(step)
            frontier = ({e['source'] for e in step} | {e['target'] for e in step}) - seen
            seen |= frontier
        nodes = [n for n in g['nodes'] if n['id'] in seen or n['id'] == seed]
        uniq_edges = [dict(t) for t in {tuple(sorted(e.items())) for e in edges}]
        return {'seed': seed, 'depth': depth, 'nodes': nodes, 'edges': uniq_edges}

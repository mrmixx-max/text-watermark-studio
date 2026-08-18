"""Behavioral tests for the 2026-08-12 validation-hardening round.

Found & fixed (second deep-dive):
1. POST /api/graph/node accepted empty payloads -> stored nodes without 'id',
   then community/summarize crashed with KeyError. Now ValueError -> 400.
2. prompts/create-version accepted payloads without id/version -> stored junk,
   then prompts/render crashed with KeyError. Now ValueError -> 400/404.
3. Redis routes returned raw 500 when Redis was unreachable; lifespan now
   probes ping and sets state.redis = None -> clean 503.
4. CLI returned a raw traceback (exit 1) for a missing file; now clean stderr
   message + exit 2 via main_entry().
"""

import json
import subprocess
import sys

from fastapi.testclient import TestClient

from ai_watermark_toolkit.api.fastapi_app import app


class TestValidationHardening:
    def _isolated(self, tmp_path):
        """Point graph/community stores at a temp dir so tests never write
        into the tracked data/ files (that is what polluted data/graph)."""
        from ai_watermark_toolkit.api.routes import community as community_routes
        from ai_watermark_toolkit.api.routes import graph as graph_routes
        from ai_watermark_toolkit.community.service import CommunityService
        from ai_watermark_toolkit.graph_memory.service import GraphMemoryService
        gp = tmp_path / 'graph.json'
        gp.write_text(json.dumps({'nodes': [], 'edges': []}), encoding='utf-8')
        cp = tmp_path / 'communities.json'
        cp.write_text(json.dumps({'communities': []}), encoding='utf-8')
        graph_routes.svc = GraphMemoryService(graph_path=gp)
        community_routes.svc = CommunityService(graph_path=gp, communities_path=cp)
        return graph_routes.svc, community_routes.svc

    def test_graph_node_empty_payload_400(self, tmp_path):
        self._isolated(tmp_path)
        c = TestClient(app)
        r = c.post('/api/graph/node', json={'node': {}})
        assert r.status_code == 400
        assert 'node_id_required' in r.json()['detail']

    def test_graph_node_valid_200(self, tmp_path):
        svc, _ = self._isolated(tmp_path)
        c = TestClient(app)
        r = c.post('/api/graph/node', json={'node': {'id': 'x1', 'label': 'X'}})
        assert r.status_code == 200
        assert r.json()['id'] == 'x1'
        # The write went to the temp graph, not data/graph/graph.json
        assert svc.graph_path != svc.__class__().graph_path

    def test_graph_edge_empty_400(self, tmp_path):
        self._isolated(tmp_path)
        c = TestClient(app)
        r = c.post('/api/graph/edge', json={'edge': {}})
        assert r.status_code == 400
        assert 'edge_source_target_required' in r.json()['detail']

    def test_prompts_render_missing_404(self):
        c = TestClient(app)
        r = c.post('/api/prompts/render', json={'template_id': 'does-not-exist', 'variables': {}})
        assert r.status_code == 404
        assert r.json()['detail'] == 'template_not_found'

    def test_prompts_create_version_missing_id_400(self):
        c = TestClient(app)
        r = c.post('/api/prompts/create-version', json={'payload': {'version': '1.0'}})
        assert r.status_code == 400
        assert 'template_id_required' in r.json()['detail']

    def test_community_summarize_survives_missing_nodes(self, tmp_path):
        # Empty graph should not crash with KeyError; it should return empty
        self._isolated(tmp_path)
        c = TestClient(app)
        r = c.post('/api/community/summarize')
        assert r.status_code == 200
        assert 'communities' in r.json()


class TestRedisLifecycle:
    def test_redis_route_503_without_backend(self):
        # TestClient without a running lifespan sets no state.redis, so
        # get_redis() must surface a clean 503 (not AttributeError).
        c = TestClient(app)
        for path in ('/api/queue/depth', '/api/ops/status', '/api/streams/metrics'):
            r = c.get(path)
            assert r.status_code == 503, f'{path} -> {r.status_code}'
            assert 'Redis backend unavailable' in r.json()['detail']


class TestCliErrorHandling:
    def test_missing_file_clean_error_exit2(self):
        proc = subprocess.run(
            [sys.executable, '-m', 'ai_watermark_toolkit.cli', 'detect',
             'C:/this/file/does/not/exist.txt'],
            capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert 'file not found' in (proc.stderr or proc.stdout).lower()
        assert 'Traceback' not in proc.stderr

from __future__ import annotations

import base64
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile

from ...forensics.key_registry import KeyRegistry
from ...metadata.provenance import detect_provenance, embed_provenance
from ...metadata.service import SUPPORTED, clean, inspect
from ...metadata.synthid import score_synthid

router = APIRouter(prefix='/api/metadata', tags=['metadata'])
keys = KeyRegistry('data/key_registry.json')


@router.get('/formats', summary='List supported file formats for metadata cleaning')
def formats():
    return {'formats': SUPPORTED}


@router.post('/inspect', summary='Inspect a file for AI provenance metadata (C2PA/EXIF/XMP)')
def inspect_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail='filename_required')
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in SUPPORTED:
        raise HTTPException(status_code=400, detail=f'unsupported_format: {ext}')
    data = file.file.read()
    return inspect(data, file.filename)


@router.post('/clean', summary='Strip AI provenance metadata from a file, return cleaned bytes + report')
def clean_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail='filename_required')
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in SUPPORTED:
        raise HTTPException(status_code=400, detail=f'unsupported_format: {ext}')
    data = file.file.read()
    cleaned, report = clean(data, file.filename)
    import base64
    return {
        **report,
        'cleaned_base64': base64.b64encode(cleaned).decode('ascii'),
        'cleaned_size': len(cleaned),
    }


@router.post('/embed', summary='Embed your own signed provenance mark (HMAC, keyed) into a file')
def embed_file(key_id: str, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail='filename_required')
    key = next((k for k in keys.list_keys() if k.get('key_id') == key_id), None)
    if key is None:
        raise HTTPException(status_code=404, detail=f'key_not_found: {key_id}')
    if not key.get('secret'):
        raise HTTPException(status_code=400, detail='key_has_no_secret')
    data = file.file.read()
    result = embed_provenance(data, file.filename, key_id, key['secret'])
    payload = result.to_dict()
    if result.embedded and result.data is not None:
        payload['marked_base64'] = base64.b64encode(result.data).decode('ascii')
    return payload


@router.post('/detect', summary='Detect and verify studio provenance marks in a file')
def detect_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail='filename_required')
    data = file.file.read()
    secrets = {k.get('key_id'): k.get('secret') for k in keys.list_keys() if k.get('secret')}
    result = detect_provenance(data, file.filename, secrets)
    return result.to_dict()


@router.post('/synthid-score', summary='Score an image for SynthID pixel marks (external checkout required)')
def synthid_score(file: UploadFile = File(...), synthid_dir: str | None = None):
    if not file.filename:
        raise HTTPException(status_code=400, detail='filename_required')
    data = file.file.read()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        return score_synthid(tmp_path, synthid_dir=synthid_dir)
    finally:
        import os
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

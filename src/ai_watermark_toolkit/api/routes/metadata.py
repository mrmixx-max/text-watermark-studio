from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from ...metadata.service import SUPPORTED, clean, inspect

router = APIRouter(prefix='/api/metadata', tags=['metadata'])


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

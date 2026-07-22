from __future__ import annotations
import os, json
from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import APIRouter, Depends, Query, status, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from auth import optional_bearer_token
from database import get_db
from models import Event, ColorCorrection

router = APIRouter(prefix='/api/color-corrections', tags=['color-corrections'])
DATASET_DIR = os.path.join('training_data', 'color_corrections')
os.makedirs(os.path.join(DATASET_DIR, 'images'), exist_ok=True)

class ColorOverrideRequest(BaseModel):
    corrected_color: str
    notes: Optional[str] = None
    user_email: Optional[str] = 'operator@vcc.local'

class ColorCorrectionRead(BaseModel):
    id: int
    event_id: Optional[int] = None
    camera_id: Optional[int] = None
    vehicle_class: str
    original_color: str
    corrected_color: str
    crop_image_path: Optional[str] = None
    user_email: Optional[str] = None
    notes: Optional[str] = None
    timestamp: datetime
    class Config:
        from_attributes = True

@router.post('/events/{event_id}/correct', response_model=ColorCorrectionRead, status_code=status.HTTP_201_CREATED)
async def correct_event_color(
    event_id: int,
    body: ColorOverrideRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(optional_bearer_token),
) -> ColorCorrectionRead:
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f'Event ID {event_id} not found.')

    original_color = event.vehicle_color or 'Unknown'
    event.vehicle_color = body.corrected_color.capitalize()

    crop_rel_path = f'color_corrections/images/crop_event_{event.id}.jpg'
    crop_abs_path = os.path.join(DATASET_DIR, 'images', f'crop_event_{event.id}.jpg')
    
    if not os.path.exists(crop_abs_path):
        try:
            import numpy as np, cv2
            dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
            dummy_img[:] = (120, 120, 120)
            cv2.imwrite(crop_abs_path, dummy_img)
        except Exception:
            crop_rel_path = None

    correction = ColorCorrection(
        event_id=event.id,
        camera_id=event.camera_id,
        vehicle_class=str(event.vehicle_class.value if hasattr(event.vehicle_class, 'value') else event.vehicle_class),
        original_color=original_color,
        corrected_color=body.corrected_color.capitalize(),
        crop_image_path=crop_rel_path,
        user_email=body.user_email,
        notes=body.notes,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(correction)
    await db.commit()
    await db.refresh(correction)
    return ColorCorrectionRead.model_validate(correction)

@router.get('', summary='List all color corrections')
async def list_color_corrections(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(optional_bearer_token),
) -> dict[str, Any]:
    count_stmt = select(func.count(ColorCorrection.id))
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = select(ColorCorrection).order_by(ColorCorrection.timestamp.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        'total': total,
        'limit': limit,
        'offset': offset,
        'items': [ColorCorrectionRead.model_validate(r) for r in rows],
    }

@router.get('/stats', summary='Get mislabeled color statistics')
async def get_color_correction_stats(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(optional_bearer_token),
) -> dict[str, Any]:
    stmt = select(ColorCorrection.original_color, ColorCorrection.corrected_color, func.count(ColorCorrection.id)).group_by(ColorCorrection.original_color, ColorCorrection.corrected_color)
    rows = (await db.execute(stmt)).all()
    matrix: dict[str, dict[str, int]] = {}
    for orig, corr, count in rows:
        if orig not in matrix:
            matrix[orig] = {}
        matrix[orig][corr] = count
    total_stmt = select(func.count(ColorCorrection.id))
    total_corrections = (await db.execute(total_stmt)).scalar_one()
    return {
        'total_corrections': total_corrections,
        'mislabel_matrix': matrix
    }

@router.post('/export-dataset', summary='Export dataset.json for model retraining')
async def export_retraining_dataset(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(optional_bearer_token),
) -> dict[str, Any]:
    stmt = select(ColorCorrection).order_by(ColorCorrection.timestamp.desc())
    rows = (await db.execute(stmt)).scalars().all()
    dataset_items = []
    for r in rows:
        dataset_items.append({
            'id': r.id,
            'event_id': r.event_id,
            'vehicle_class': r.vehicle_class,
            'original_color': r.original_color,
            'corrected_color': r.corrected_color,
            'crop_path': r.crop_image_path,
            'timestamp': r.timestamp.isoformat()
        })
    manifest_path = os.path.join(DATASET_DIR, 'dataset.json')
    with open(manifest_path, 'w') as f:
        json.dump({
            'dataset_version': '1.0',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'sample_count': len(dataset_items),
            'samples': dataset_items
        }, f, indent=2)
    return {
        'status': 'success',
        'manifest_path': manifest_path,
        'sample_count': len(dataset_items)
    }

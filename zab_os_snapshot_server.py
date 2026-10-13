"""Read-only snapshot endpoint for ZAB OS V113.0."""
import hashlib
import hmac
import json
import os
from datetime import date, datetime, timedelta, timezone

ROOM_ID = 'Bachblick'  # legacy DB identifier; not an additional room
ROOM_NAME = 'Gartenzimmer'

def build_snapshot(conn, start, end):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if not a < b or (b-a).days > 366:
        raise ValueError('Invalid date interval')
    bookings = [dict(arrival=row[0], departure=row[1], status=row[2], source='Direktbuchung') for row in conn.execute(
        "SELECT arrival, departure, status FROM bookings WHERE room=? AND departure>? AND arrival<? AND status IN ('pending','confirmed') ORDER BY arrival,uid", (ROOM_ID,start,end))]
    blocks = [dict(start=row[0], end=row[1], source=row[2]) for row in conn.execute(
        'SELECT start_date,end_date,source FROM external_blocks WHERE room=? AND end_date>? AND start_date<? ORDER BY start_date,source', (ROOM_ID,start,end))]
    # Explicit closures from the central calendar must never be treated as free.
    # Price-only overrides (availability NULL/1) are intentionally excluded.
    for row in conn.execute(
        "SELECT day FROM central_overrides WHERE room=? AND availability=0 AND day>=? AND day<? ORDER BY day",
        (ROOM_ID, start, end),
    ):
        closed_day = date.fromisoformat(row[0])
        blocks.append(dict(start=closed_day.isoformat(),
                           end=(closed_day + timedelta(days=1)).isoformat(),
                           source='Zentrale Sperre'))
    sync_rows = conn.execute('SELECT last_sync,last_result FROM ical_settings WHERE room=?', (ROOM_ID,)).fetchall()
    sync = {'last_sync': '', 'last_result': 'NICHT VERIFIZIERT',
            'verified': False, 'provider_status': {}}
    if len(sync_rows) == 1:
        sync['last_sync'] = sync_rows[0][0] or ''
        sync['legacy_result'] = sync_rows[0][1] or ''
    elif len(sync_rows) > 1:
        sync['legacy_result'] = 'MEHRERE SYNC-EINTRAEGE'
    payload = {'room_id':ROOM_ID,'room_name':ROOM_NAME,'bookings':bookings,'blocks':blocks,'sync':sync}
    payload['revision'] = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return payload

def init_os_snapshot(app, db):
    from flask import jsonify, request
    @app.get('/internal/os/v1/snapshot')
    def os_snapshot():
        token = os.environ.get('ZAB_BRIDGE_TOKEN','')
        supplied = request.headers.get('Authorization','')
        if not token or not hmac.compare_digest(supplied, 'Bearer '+token):
            return jsonify({'error':'unauthorized'}), 401
        start, end = request.args.get('start',''), request.args.get('end','')
        try:
            with db() as conn:
                result = build_snapshot(conn,start,end)
        except (ValueError, OverflowError):
            return jsonify({'error':'invalid_date_range'}), 400
        except Exception:
            app.logger.exception('OS snapshot database failure')
            return jsonify({'error':'snapshot_unavailable'}), 503
        result['generated_at'] = datetime.now(timezone.utc).isoformat()
        response = jsonify(result)
        response.headers['Cache-Control'] = 'no-store'
        return response

"""Partner availability API for WachauEtappe."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import date, datetime, timedelta
from flask import jsonify, request
from railway_app import app, db

ALLOWED_ORIGINS={"https://topdiveair-sketch.github.io"}

def now(): return datetime.now().isoformat(timespec="seconds")
def sha(v:str)->str: return hashlib.sha256(v.encode("utf-8")).hexdigest()
def cors(resp):
    origin=(request.headers.get("Origin") or "").rstrip("/")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"]=origin;resp.headers["Vary"]="Origin"
    resp.headers["Access-Control-Allow-Headers"]="Content-Type, Authorization, X-Admin-Password"
    resp.headers["Access-Control-Allow-Methods"]="GET, POST, PUT, OPTIONS"
    resp.headers["Cache-Control"]="no-store"
    return resp

def options(): return cors(app.make_response(("",204)))
def parse_day(v:str)->date: return datetime.strptime(v,"%Y-%m-%d").date()

def init_tables():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS wachauetappe_partner_accounts(
          host_id TEXT PRIMARY KEY, name TEXT NOT NULL, location TEXT NOT NULL,
          email TEXT NOT NULL, access_code_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
          rooms_total INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS wachauetappe_partner_sessions(
          token_hash TEXT PRIMARY KEY, host_id TEXT NOT NULL, expires_at TEXT NOT NULL,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS wachauetappe_partner_availability(
          host_id TEXT NOT NULL, stay_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'free',
          rooms_free INTEGER NOT NULL DEFAULT 0, price REAL,
          breakfast_mode TEXT NOT NULL DEFAULT 'none', breakfast_price REAL NOT NULL DEFAULT 0,
          luggage_available INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
          PRIMARY KEY(host_id,stay_date));
        CREATE INDEX IF NOT EXISTS ix_we_partner_availability_date
          ON wachauetappe_partner_availability(stay_date,status,rooms_free);
        """)
        cols={r[1] for r in c.execute("PRAGMA table_info(wachauetappe_partner_accounts)").fetchall()}
        if 'last_login_at' not in cols:c.execute("ALTER TABLE wachauetappe_partner_accounts ADD COLUMN last_login_at TEXT DEFAULT ''")
init_tables()

def partner_host_id():
    auth=request.headers.get("Authorization","")
    if not auth.startswith("Bearer "): return None
    th=sha(auth[7:].strip())
    with db() as c:row=c.execute("SELECT host_id,expires_at FROM wachauetappe_partner_sessions WHERE token_hash=?",(th,)).fetchone()
    if not row or row["expires_at"]<now(): return None
    return str(row["host_id"])

def admin_ok():
    expected=os.environ.get("ADMIN_PASSWORD","");supplied=request.headers.get("X-Admin-Password","")
    return bool(expected) and hmac.compare_digest(expected,supplied)

@app.route('/api/partner/login',methods=['OPTIONS'])
@app.route('/api/partner/me',methods=['OPTIONS'])
@app.route('/api/partner/availability',methods=['OPTIONS'])
@app.route('/api/partner/availability/range',methods=['OPTIONS'])
@app.route('/api/partner/provision',methods=['OPTIONS'])
@app.route('/api/partner/disable',methods=['OPTIONS'])
@app.route('/api/partner/admin-status',methods=['OPTIONS'])
@app.route('/api/hosts/search',methods=['OPTIONS'])
def partner_options(): return options()

@app.post('/api/partner/login')
def partner_login():
    p=request.get_json(silent=True) or {};host_id=str(p.get('hostId') or '').strip();password=str(p.get('password') or '')
    with db() as c:row=c.execute("SELECT * FROM wachauetappe_partner_accounts WHERE host_id=? AND active=1",(host_id,)).fetchone()
    if not row or not hmac.compare_digest(str(row['access_code_hash']),sha(password)):
        return cors(jsonify({'error':'ID oder Passwort nicht korrekt'})),401
    token=secrets.token_urlsafe(32);expires=(datetime.now()+timedelta(days=30)).isoformat(timespec='seconds')
    with db() as c:
        c.execute("INSERT INTO wachauetappe_partner_sessions(token_hash,host_id,expires_at,created_at) VALUES(?,?,?,?)",(sha(token),host_id,expires,now()))
        c.execute("UPDATE wachauetappe_partner_accounts SET last_login_at=?,updated_at=? WHERE host_id=?",(now(),now(),host_id))
    return cors(jsonify({'ok':True,'token':token,'expiresAt':expires})),200

@app.get('/api/partner/me')
def partner_me():
    host_id=partner_host_id()
    if not host_id:return cors(jsonify({'error':'unauthorized'})),401
    with db() as c:row=c.execute("SELECT host_id,name,location,email,rooms_total FROM wachauetappe_partner_accounts WHERE host_id=?",(host_id,)).fetchone()
    return cors(jsonify({'hostId':row['host_id'],'name':row['name'],'location':row['location'],'email':row['email'],'roomsTotal':row['rooms_total']})),200

@app.get('/api/partner/availability')
def partner_availability():
    host_id=partner_host_id()
    if not host_id:return cors(jsonify({'error':'unauthorized'})),401
    f=request.args.get('from') or date.today().isoformat();t=request.args.get('to') or (date.today()+timedelta(days=60)).isoformat()
    with db() as c:rows=c.execute("SELECT stay_date,status,rooms_free,price,breakfast_mode,breakfast_price,luggage_available FROM wachauetappe_partner_availability WHERE host_id=? AND stay_date BETWEEN ? AND ? ORDER BY stay_date",(host_id,f,t)).fetchall()
    return cors(jsonify({'rows':[{'stayDate':r['stay_date'],'status':r['status'],'roomsFree':r['rooms_free'],'price':r['price'],'breakfastMode':r['breakfast_mode'],'breakfastPrice':r['breakfast_price'],'luggageAvailable':bool(r['luggage_available'])} for r in rows]})),200

@app.put('/api/partner/availability/range')
def partner_save_range():
    host_id=partner_host_id()
    if not host_id:return cors(jsonify({'error':'unauthorized'})),401
    p=request.get_json(silent=True) or {}
    try:f=parse_day(str(p.get('fromDate')));t=parse_day(str(p.get('toDate')))
    except Exception:return cors(jsonify({'error':'invalid_date'})),422
    if t<f or (t-f).days>366:return cors(jsonify({'error':'invalid_range'})),422
    status=str(p.get('status') or 'free');status=status if status in {'free','full','closed'} else 'free'
    try:rooms=max(0,min(100,int(p.get('roomsFree') or 0)));price=max(0,float(p.get('price') or 0));breakfast_price=max(0,float(p.get('breakfastPrice') or 0))
    except Exception:return cors(jsonify({'error':'invalid_numbers'})),422
    breakfast=str(p.get('breakfastMode') or 'none');breakfast=breakfast if breakfast in {'included','extra','none'} else 'none';luggage=1 if p.get('luggageAvailable') else 0
    if status!='free':rooms=0
    n=0;d=f
    with db() as c:
        while d<=t:
            c.execute("""INSERT INTO wachauetappe_partner_availability(host_id,stay_date,status,rooms_free,price,breakfast_mode,breakfast_price,luggage_available,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(host_id,stay_date) DO UPDATE SET status=excluded.status,rooms_free=excluded.rooms_free,price=excluded.price,breakfast_mode=excluded.breakfast_mode,breakfast_price=excluded.breakfast_price,luggage_available=excluded.luggage_available,updated_at=excluded.updated_at""",(host_id,d.isoformat(),status,rooms,price,breakfast,breakfast_price,luggage,now()));n+=1;d+=timedelta(days=1)
    return cors(jsonify({'ok':True,'updated':n})),200

@app.post('/api/partner/provision')
def partner_provision():
    if not admin_ok():return cors(jsonify({'error':'unauthorized'})),401
    p=request.get_json(silent=True) or {};host_id=str(p.get('hostId') or '').strip();name=str(p.get('name') or '').strip();location=str(p.get('location') or '').strip();email=str(p.get('email') or '').strip().lower();password=str(p.get('password') or p.get('accessCode') or '')
    if not host_id or not name or not location or '@' not in email or len(password)<8:return cors(jsonify({'error':'required_fields'})),422
    rooms=max(1,min(100,int(p.get('roomsTotal') or 1)))
    with db() as c:c.execute("""INSERT INTO wachauetappe_partner_accounts(host_id,name,location,email,access_code_hash,active,rooms_total,updated_at) VALUES(?,?,?,?,?,1,?,?) ON CONFLICT(host_id) DO UPDATE SET name=excluded.name,location=excluded.location,email=excluded.email,access_code_hash=excluded.access_code_hash,active=1,rooms_total=excluded.rooms_total,updated_at=excluded.updated_at""",(host_id,name,location,email,sha(password),rooms,now()))
    return cors(jsonify({'ok':True,'hostId':host_id})),201

@app.post('/api/partner/disable')
def partner_disable():
    if not admin_ok():return cors(jsonify({'error':'unauthorized'})),401
    p=request.get_json(silent=True) or {};host_id=str(p.get('hostId') or '').strip()
    if not host_id:return cors(jsonify({'error':'host_id_required'})),422
    with db() as c:c.execute("UPDATE wachauetappe_partner_accounts SET active=0,updated_at=? WHERE host_id=?",(now(),host_id));c.execute("DELETE FROM wachauetappe_partner_sessions WHERE host_id=?",(host_id,))
    return cors(jsonify({'ok':True,'hostId':host_id,'active':False})),200

@app.get('/api/partner/admin-status')
def partner_admin_status():
    if not admin_ok():return cors(jsonify({'error':'unauthorized'})),401
    host_id=str(request.args.get('hostId') or '').strip()
    with db() as c:row=c.execute("SELECT host_id,name,location,email,active,rooms_total,updated_at,COALESCE(last_login_at,'') AS last_login_at FROM wachauetappe_partner_accounts WHERE host_id=?",(host_id,)).fetchone()
    if not row:return cors(jsonify({'exists':False,'hostId':host_id})),200
    return cors(jsonify({'exists':True,'hostId':row['host_id'],'name':row['name'],'location':row['location'],'email':row['email'],'active':bool(row['active']),'roomsTotal':row['rooms_total'],'updatedAt':row['updated_at'],'lastLoginAt':row['last_login_at']})),200

@app.get('/api/hosts/search')
def public_host_search():
    location=str(request.args.get('location') or '').strip();stay=str(request.args.get('date') or '').strip();luggage=request.args.get('luggage')=='1'
    if not location or not stay:return cors(jsonify([])),200
    sql="""SELECT a.host_id,p.name,p.location,a.price,a.breakfast_mode,a.breakfast_price,a.luggage_available,a.rooms_free FROM wachauetappe_partner_availability a JOIN wachauetappe_partner_accounts p ON p.host_id=a.host_id AND p.active=1 WHERE lower(p.location)=lower(?) AND a.stay_date=? AND a.status='free' AND a.rooms_free>0""";args=[location,stay]
    if luggage:sql+=" AND a.luggage_available=1"
    sql+=" ORDER BY a.price,p.name"
    with db() as c:rows=c.execute(sql,args).fetchall()
    return cors(jsonify([{'hostId':r['host_id'],'name':r['name'],'location':r['location'],'price':r['price'],'roomsFree':r['rooms_free'],'breakfastMode':r['breakfast_mode'],'breakfastPrice':r['breakfast_price'],'luggageAvailable':bool(r['luggage_available']),'features':(['Frühstück inklusive'] if r['breakfast_mode']=='included' else ['Frühstück möglich'] if r['breakfast_mode']=='extra' else [])+(['Gepäcktransport'] if r['luggage_available'] else [])} for r in rows])),200

@app.get('/api/central/partner-availability')
def central_partner_availability():
    if not admin_ok():return jsonify({'error':'unauthorized'}),401
    f=request.args.get('from') or date.today().isoformat();t=request.args.get('to') or (date.today()+timedelta(days=90)).isoformat()
    with db() as c:rows=c.execute("""SELECT a.host_id,p.name,p.location,a.stay_date,a.status,a.rooms_free,a.price,a.breakfast_mode,a.breakfast_price,a.luggage_available,a.updated_at FROM wachauetappe_partner_availability a JOIN wachauetappe_partner_accounts p ON p.host_id=a.host_id WHERE a.stay_date BETWEEN ? AND ? ORDER BY a.stay_date,p.location,p.name""",(f,t)).fetchall()
    return jsonify({'rows':[dict(r) for r in rows]}),200

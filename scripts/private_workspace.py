"""Password-protected single-owner loopback workspace and durable inbox scheduler."""
from contextlib import closing
import argparse
import datetime as dt
import hashlib
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import pathlib
import secrets
import threading
import time
import urllib.parse
import urllib.request
from private_workspace_store import connect, dot, save_portfolio, portfolio, relationship, review_relationship, group_members, deliver, save_screening_case
from snapshot_store import now, digest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class Workspace:
    def __init__(self,folder,warehouse=None):
        self.folder=pathlib.Path(folder).resolve();self.path=self.folder/'workspace.sqlite'
        self.warehouse=warehouse;self.lock=threading.Lock();self.stop=threading.Event()
        with closing(connect(self.path)) as db:pass

    def tick(self,force=False):
        if not self.lock.acquire(blocking=False):return
        try:
            with closing(connect(self.path)) as db:
                dots=[r[0] for r in db.execute('SELECT dot FROM subscriptions WHERE enabled=1 ORDER BY dot')]
                due=db.execute("SELECT value FROM settings WHERE key='next_run'").fetchone()
                if not dots or (not force and due and float(due[0])>time.time()):return
                if not db.execute('SELECT 1 FROM owner').fetchone():return
                job=db.execute("INSERT INTO jobs(started_at,status) VALUES (?,'RUNNING')",(now(),)).lastrowid
                db.execute("INSERT OR REPLACE INTO settings VALUES ('next_run',?)",(str(time.time()+86400),));db.commit()
                try:
                    from cohort_snapshot import acquire
                    from evidence_warehouse import promote
                    from material_alerts import run
                    detail=[]
                    # Stable membership-specific evidence stores prevent comparison across changed cohorts.
                    for start in range(0,len(dots),140):
                        batch=dots[start:start+140];folder=self.folder/'monitoring'/digest(batch)[:20];folder.mkdir(parents=True,exist_ok=True)
                        cohort=folder/'cohort.json'
                        if not cohort.exists():cohort.write_text(json.dumps({'dots':batch,'selected_at':now(),'selection':'OWNER_SUBSCRIPTIONS','representative':False,'outcome_selected':False}),encoding='utf-8')
                        cut,manifest=acquire(folder/'raw',cohort_path=cohort,profile='underwriting_evidence_v3',max_rows=1000000)
                        if manifest['status']!='COMPLETE':raise ValueError('Acquisition incomplete; no comparisons or clean-carrier inference produced')
                        promote(cut,folder/'evidence.sqlite')
                        result=run(folder/'evidence.sqlite',folder/'alerts.sqlite')
                        result['delivered']=deliver(db,folder/'alerts.sqlite');detail.append(result)
                    db.execute('UPDATE jobs SET finished_at=?,status=?,detail=? WHERE id=?',(now(),'COMPLETE',json.dumps(detail),job))
                except Exception as error:
                    db.execute('UPDATE jobs SET finished_at=?,status=?,detail=? WHERE id=?',(now(),'FAILED',f'{type(error).__name__}: {error}'[:4000],job))
                    db.execute("INSERT OR REPLACE INTO settings VALUES ('next_run',?)",(str(time.time()+3600),))
                db.commit()
        finally:self.lock.release()

    def schedule(self):
        while not self.stop.is_set():
            self.tick()
            self.stop.wait(30)

class Handler(BaseHTTPRequestHandler):
    server_version='Transport3rLocal/1'
    def log_message(self,*args):pass # No credentials or private payloads in access logs.
    @property
    def app(self):return self.server.workspace
    @property
    def origin(self):return f'http://127.0.0.1:{self.server.server_port}'

    def send(self,status,body,mime='application/json',cookie=None):
        data=json.dumps(body,ensure_ascii=False).encode('utf-8') if mime=='application/json' else body
        self.send_response(status);self.send_header('Content-Type',mime+'; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Length',str(len(data)))
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(data)

    def owner(self,db):
        try:
            cookie=SimpleCookie(self.headers.get('Cookie',''));token=cookie['t3session'].value
            if db.execute('SELECT 1 FROM sessions WHERE token_hash=? AND expires>?',(digest(token),time.time())).fetchone():
                return db.execute('SELECT name FROM owner').fetchone()[0]
        except (KeyError,TypeError):pass
        return None

    def dispatch(self):
        if self.headers.get('Host')!=self.origin.removeprefix('http://'):return self.send(403,{'error':'Loopback host required'})
        request=urllib.parse.urlsplit(self.path);route=request.path
        if self.command=='GET' and route in ('/','/app.js','/style.css'):
            name={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[route]
            return self.send(200,(ROOT/'local_workspace'/name).read_bytes(),{'/':'text/html','/app.js':'text/javascript','/style.css':'text/css'}[route])
        if self.command=='GET' and route=='/favicon.ico':return self.send(204,b'','image/x-icon')
        body={}
        if self.command=='POST':
            if self.headers.get('Origin')!=self.origin or self.headers.get('Content-Type')!='application/json':return self.send(403,{'error':'Same-origin JSON request required'})
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=2_000_000:return self.send(413,{'error':'Invalid request size'})
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError('JSON object required')
        with closing(connect(self.app.path)) as db:
            if route=='/api/session' and self.command=='GET':
                return self.send(200,{'owner':self.owner(db),'setup_required':not bool(db.execute('SELECT 1 FROM owner').fetchone())})
            if route in ('/api/setup','/api/login') and self.command=='POST':
                # Bounded lock serializes first-owner creation and login attempts.
                with self.server.auth_lock:
                    blocked=db.execute("SELECT value FROM settings WHERE key='login_not_before'").fetchone()
                    if blocked and float(blocked[0])>time.time():return self.send(429,{'error':'Wait a few seconds before signing in again'})
                    password=body.get('password','')
                    if not isinstance(password,str) or not 12<=len(password)<=1024:raise ValueError('Use a password of 12 to 1,024 characters')
                    record=db.execute('SELECT * FROM owner').fetchone()
                    if route=='/api/setup':
                        if record:return self.send(409,{'error':'Workspace owner already configured'})
                        name=body.get('name','').strip()
                        if not 1<=len(name)<=100:raise ValueError('Owner name required')
                        salt=secrets.token_hex(16);hashed=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
                        db.execute('INSERT INTO owner VALUES (?,?,?)',(name,salt,hashed));db.commit()
                        record=db.execute('SELECT * FROM owner').fetchone()
                    valid=record and hmac.compare_digest(record['password_hash'],hashlib.scrypt(password.encode(),salt=bytes.fromhex(record['salt']),n=16384,r=8,p=1).hex())
                    db.execute("INSERT OR REPLACE INTO settings VALUES ('login_not_before',?)",(str(time.time()+3),));db.commit()
                    if not valid:return self.send(401,{'error':'Sign-in failed'})
                    token=secrets.token_urlsafe(32)
                    db.execute('DELETE FROM sessions WHERE expires<=?',(time.time(),))
                    db.execute('INSERT INTO sessions VALUES (?,?)',(digest(token),time.time()+43200));db.commit()
                    return self.send(200,{'owner':record['name']},cookie=f't3session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200')
            owner=self.owner(db)
            if not owner:return self.send(401,{'error':'Sign in to the local workspace'})
            if route=='/api/logout' and self.command=='POST':
                cookie=SimpleCookie(self.headers.get('Cookie',''));db.execute('DELETE FROM sessions WHERE token_hash=?',(digest(cookie['t3session'].value),));db.commit()
                return self.send(200,{},cookie='t3session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if route=='/api/state' and self.command=='GET':
                return self.send(200,{'portfolio':portfolio(self.app.folder),'subscriptions':[dict(r) for r in db.execute('SELECT * FROM subscriptions')],
                    'inbox':[dict(r) for r in db.execute('SELECT * FROM inbox ORDER BY delivered_at DESC')],
                    'relationships':[dict(r) for r in db.execute('SELECT * FROM relationships ORDER BY updated_at DESC')],
                    'screening_cases':[dict(r) for r in db.execute('SELECT id,kind,dot,candidate_dot,status,notes,reviewer,updated_at FROM screening_cases ORDER BY updated_at DESC')],
                    'jobs':[dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT 20')],
                    'schedule':dict(db.execute("SELECT key,value FROM settings WHERE key='next_run'").fetchall()),
                    'warehouse_available':bool(self.app.warehouse),'forecast':{'status':'BLOCKED','reasons':['No matched historical SMS releases','No mature outcome follow-up','No insurer claims/loss outcomes or actuarial calibration']}})
            if route=='/api/portfolio' and self.command=='POST':
                return self.send(200,save_portfolio(self.app.folder,body.get('records')))
            if route=='/api/subscribe' and self.command=='POST':
                identifier=dot(body.get('dot'));enabled=body.get('enabled')
                if type(enabled)is not bool:raise ValueError('Subscription enabled must be true or false')
                with db:
                    prior=db.execute('SELECT * FROM subscriptions WHERE dot=?',(identifier,)).fetchone()
                    since=prior['created_at'] if prior and prior['enabled'] and enabled else now()
                    db.execute('INSERT OR REPLACE INTO subscriptions VALUES (?,?,?)',(identifier,int(enabled),since))
                    if enabled and (not prior or not prior['enabled']):
                        db.execute("INSERT OR REPLACE INTO settings VALUES ('next_run','0')")
                return self.send(200,{'status':'SUBSCRIBED' if enabled else 'PAUSED'})
            if route=='/api/read' and self.command=='POST':
                with db:db.execute('UPDATE inbox SET read_at=? WHERE alert_id=?',(now(),body.get('id')))
                return self.send(200,{'status':'READ'})
            if route=='/api/run' and self.command=='POST':
                threading.Thread(target=self.app.tick,kwargs={'force':True},daemon=True).start()
                return self.send(202,{'status':'REQUESTED','note':'First complete observation establishes a baseline. Later comparable complete observations produce changes.'})
            if route=='/api/relationship' and self.command=='POST':return self.send(200,{'id':relationship(db,body,owner)})
            if route=='/api/review' and self.command=='POST':
                review_relationship(db,body,owner);return self.send(200,{'status':'REVIEWED'})
            if route=='/api/history' and self.command=='GET':
                return self.send(200,[dict(r) for r in db.execute('SELECT * FROM relationship_history ORDER BY id')])
            query=urllib.parse.parse_qs(request.query)
            if route=='/api/screening-history' and self.command=='GET':
                return self.send(200,[dict(r) for r in db.execute('SELECT * FROM screening_history WHERE case_id=? ORDER BY id',(query.get('id',[''])[0],))])
            if route in ('/api/identity-screen','/api/ghost','/api/ghost-queue','/api/screening-case'):
                if self.command!=('POST' if route=='/api/screening-case' else 'GET'):
                    return self.send(405,{'error':'Unsupported method'})
                if not self.app.warehouse:raise ValueError('Verified nationwide warehouse is not configured')
                from workspace_analytics import open_warehouse
                from identity_analytics import identity_screen,ghost_review,ghost_queue
                days=int(query.get('days',['365'])[0]);page=int(query.get('page',['1'])[0])
                with closing(open_warehouse(self.app.warehouse)) as warehouse:
                    if route=='/api/ghost-queue':result=ghost_queue(warehouse,days,page)
                    elif route=='/api/identity-screen':result=identity_screen(warehouse,dot(query.get('dot',[''])[0]),page)
                    elif route=='/api/ghost':result=ghost_review(warehouse,dot(query.get('dot',[''])[0]),days)
                    else:
                        # Recompute on the server; client-authored findings never become source evidence.
                        seed=dot(body.get('dot'))
                        if body.get('kind')=='ghost':evidence=ghost_review(warehouse,seed,int(body.get('days',365)))
                        elif body.get('kind')=='chameleon':
                            screening=identity_screen(warehouse,seed,int(body.get('page',1)))
                            selected=[c for c in screening['candidates'] if c['dot']==body.get('candidate_dot')]
                            if not selected:raise ValueError('Candidate is not in the selected verified screening page; rerun screening')
                            evidence={**screening,'candidates':selected}
                        else:raise ValueError('Unsupported screening kind')
                        result={'id':save_screening_case(db,body,owner,evidence),'status':'SAVED'}
                return self.send(200,result)
            if route in ('/api/peers','/api/group') and self.command=='GET':
                if not self.app.warehouse:raise ValueError('Verified nationwide warehouse is not configured')
                from workspace_analytics import open_warehouse,peers,group_summary
                identifier=dot(query.get('dot',[''])[0]);warehouse=open_warehouse(self.app.warehouse)
                try:
                    if route=='/api/peers':result=peers(warehouse,identifier)
                    else:
                        from identity_analytics import event_summary
                        members=group_members(db,identifier)
                        result=group_summary(warehouse,members)
                        result['safety']=event_summary(warehouse,members,int(query.get('days',['365'])[0]))
                        result['approved_relationships']=[dict(r) for r in db.execute("SELECT * FROM relationships WHERE status='approved' AND kind IN ('parent_subsidiary','common_ownership')") if r['dot_a'] in members and r['dot_b'] in members]
                finally:warehouse.close()
                return self.send(200,result)
            if route=='/api/recalls' and self.command=='GET':
                values={key:query.get(key,[''])[0].strip() for key in ('make','model','modelYear')}
                if any(not value or len(value)>100 for value in values.values()) or not values['modelYear'].isdigit() or not 1900<=int(values['modelYear'])<=dt.date.today().year+1:raise ValueError('Make, model and valid model year required')
                url='https://api.nhtsa.gov/recalls/recallsByVehicle?'+urllib.parse.urlencode(values)
                with urllib.request.urlopen(url,timeout=20) as response:
                    payload=json.loads(response.read(5_000_001))
                if not isinstance(payload.get('results'),list):raise ValueError('Unexpected NHTSA response')
                return self.send(200,{'source_url':url,'observed_at':now(),'query':values,'results':payload['results'],'limitation':'Make/model/year campaign candidates only. VIN applicability, ownership and open/repaired/ignored status are not established.'})
            self.send(404,{'error':'Route not found'})

    def do_GET(self):self.handle_request()
    def do_POST(self):self.handle_request()
    def handle_request(self):
        try:self.dispatch()
        except (ValueError,KeyError,TypeError) as error:self.send(400,{'error':str(error)[:1000]})
        except Exception:self.send(503,{'error':'Local operation or upstream source unavailable. Check configuration and retry.'})

def make_server(app,port=4789):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.workspace=app;server.auth_lock=threading.Lock()
    return server

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',default=str(ROOT/'warehouse/private/workspace'))
    parser.add_argument('--warehouse');parser.add_argument('--port',type=int,default=4789)
    args=parser.parse_args();app=Workspace(args.data,args.warehouse)
    with closing(connect(app.path)) as db:
        db.execute("UPDATE jobs SET status='INTERRUPTED',finished_at=?,detail='Service stopped during the previous run; retry will acquire a new verified cut.' WHERE status='RUNNING'",(now(),));db.commit()
    server=make_server(app,args.port)
    threading.Thread(target=app.schedule,daemon=True).start()
    print(f'Local private workspace: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    finally:app.stop.set();server.server_close()

if __name__=='__main__':main()

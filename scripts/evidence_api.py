"""Read-only HTTP API for a verified nationwide Transport3r evidence warehouse."""
import argparse,hashlib,json,pathlib,urllib.parse,os,re
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

from nationwide_evidence import acceptance,connect,resolved_carrier
from nri_county_index import lookup as nri_lookup, read_only_status
from noaa_storm_index import acceptance as noaa_acceptance, event as noaa_event, locations as noaa_locations
from integrity_report import load_report
from audit_warehouse_integrity import fingerprint


def file_sha256(path):
    digest=hashlib.sha256()
    with pathlib.Path(path).open('rb') as handle:
        while block:=handle.read(1024*1024):digest.update(block)
    return digest.hexdigest()


class EvidenceServer(ThreadingHTTPServer):
    def __init__(self,address,handler,warehouse,allow_origin,nri_index=None,audit_report=None,noaa_index=None):
        self.warehouse=pathlib.Path(warehouse).resolve();self.allow_origin=allow_origin
        self.warehouse_stamp=fingerprint(self.warehouse)
        self.nri_index=pathlib.Path(nri_index).resolve() if nri_index else None
        self.nri_status=read_only_status(self.nri_index) if self.nri_index else None
        self.nri_index_sha256=file_sha256(self.nri_index) if self.nri_index else None
        self.nri_stamp=fingerprint(self.nri_index) if self.nri_index else None
        self.noaa_index=pathlib.Path(noaa_index).resolve() if noaa_index else None
        self.noaa_status=noaa_acceptance(self.noaa_index) if self.noaa_index else None
        self.noaa_index_sha256=file_sha256(self.noaa_index) if self.noaa_index else None
        self.noaa_stamp=fingerprint(self.noaa_index) if self.noaa_index else None
        db=connect(self.warehouse)
        try:self.receipt=acceptance(db)
        finally:db.close()
        self.warehouse_sha256=file_sha256(self.warehouse)
        self.integrity=load_report(audit_report,self.receipt,self.warehouse_sha256) if audit_report else None
        if self.warehouse_stamp!=fingerprint(self.warehouse):raise ValueError('Warehouse changed during startup')
        # Bind only AFTER all configured data products pass their startup gates.
        super().__init__(address,handler)

    def warehouse_unchanged(self):
        try:return self.warehouse_stamp==fingerprint(self.warehouse) and not pathlib.Path(str(self.warehouse)+'.wal').exists()
        except OSError:return False

    def nri_unchanged(self):
        try:return self.nri_index is None or self.nri_stamp==fingerprint(self.nri_index)
        except OSError:return False

    def noaa_unchanged(self):
        try:return self.noaa_index is None or self.noaa_stamp==fingerprint(self.noaa_index)
        except OSError:return False


class Handler(BaseHTTPRequestHandler):
    server_version='Transport3rEvidence/1'
    def send_json_headers(self,status=200,length=None):
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
        self.send_header('Access-Control-Allow-Origin',self.server.allow_origin);self.send_header('Access-Control-Allow-Methods','GET,HEAD,OPTIONS');self.send_header('Access-Control-Allow-Headers','Accept')
        if length is not None:self.send_header('Content-Length',str(length))
        self.end_headers()
    def payload(self,status,value,head=False):
        raw=json.dumps(value,separators=(',',':'),allow_nan=False).encode();self.send_json_headers(status,len(raw))
        if not head:self.wfile.write(raw)
    def route(self,head=False):
        path=urllib.parse.urlparse(self.path).path
        if not self.server.warehouse_unchanged():
            return self.payload(503,{'status':'WAREHOUSE_CHANGED','detail':'Restart with a newly verified immutable warehouse and matching audit'},head)
        if path=='/readyz':
            ready=self.server.integrity is not None
            return self.payload(200 if ready else 503,{'status':'READY' if ready else 'NOT_AUDITED',
                'release_ready':ready,'cut_id':self.server.receipt['cut_id'],
                'warehouse_sha256':self.server.warehouse_sha256,
                'independent_audit':'PASS' if ready else 'NOT_INSTALLED',
                'private_insurer_hosting':False},head)
        if path=='/v1/integrity':
            if self.server.integrity is None:
                return self.payload(503,{'status':'NOT_AUDITED','detail':'No independent deep audit is installed; counts are withheld'},head)
            return self.payload(200,self.server.integrity,head)
        if path=='/healthz':
            return self.payload(200,{'status':'ok','identity_contract':self.server.receipt['identity_contract'],'sources':self.server.receipt['sources'],'warehouse_sha256':self.server.warehouse_sha256,'cut_id':self.server.receipt['cut_id'],'cut_available_at':self.server.receipt['cut_available_at'],
                                     'release_ready':self.server.integrity is not None,
                                     'independent_audit':'PASS' if self.server.integrity else 'NOT_INSTALLED',
                                     'nri_county_source':self.server.nri_status['status'] if self.server.nri_status else 'NOT_INSTALLED',
                                     'noaa_storm_source':self.server.noaa_status['status'] if self.server.noaa_status else 'NOT_INSTALLED'},head)
        if path.startswith('/v1/geography/nri/') and not self.server.nri_unchanged():
            return self.payload(503,{'status':'SOURCE_CHANGED','carrier_route_attribution':'NOT_ESTABLISHED'},head)
        if path=='/v1/geography/nri/status':
            if not self.server.nri_status:
                return self.payload(503,{'status':'NOT_INSTALLED','source':'FEMA_NRI_COUNTIES_V120','carrier_route_attribution':'NOT_ESTABLISHED'},head)
            return self.payload(200,{**self.server.nri_status,'index_sha256':self.server.nri_index_sha256},head)
        if path.startswith('/v1/geography/nri/counties/'):
            if not self.server.nri_index:
                return self.payload(503,{'status':'NOT_INSTALLED','source':'FEMA_NRI_COUNTIES_V120','carrier_route_attribution':'NOT_ESTABLISHED'},head)
            fips=path[len('/v1/geography/nri/counties/'):]
            if not re.fullmatch(r'[0-9]{5}',fips):
                return self.payload(400,{'status':'INVALID_COUNTY_ID','detail':'Exact five-digit STCOFIPS required'},head)
            try:
                result=nri_lookup(self.server.nri_index,fips)
                return self.payload(200 if result['status']!='NOT_FOUND' else 404,result,head)
            except Exception:
                return self.payload(503,{'status':'SOURCE_UNAVAILABLE','source':'FEMA_NRI_COUNTIES_V120','carrier_route_attribution':'NOT_ESTABLISHED'},head)
        if path.startswith('/v1/geography/noaa/') and not self.server.noaa_unchanged():
            return self.payload(503,{'status':'SOURCE_CHANGED','source':'NOAA_NCEI_STORM_EVENTS_V1','carrier_route_attribution':'NOT_ESTABLISHED'},head)
        if path=='/v1/geography/noaa/status':
            if not self.server.noaa_status:
                return self.payload(503,{'status':'NOT_INSTALLED','source':'NOAA_NCEI_STORM_EVENTS_V1','carrier_route_attribution':'NOT_ESTABLISHED'},head)
            return self.payload(200,{**self.server.noaa_status,'index_sha256':self.server.noaa_index_sha256},head)
        if path.startswith('/v1/geography/noaa/events/'):
            if not self.server.noaa_index:
                return self.payload(503,{'status':'NOT_INSTALLED','source':'NOAA_NCEI_STORM_EVENTS_V1','carrier_route_attribution':'NOT_ESTABLISHED'},head)
            event_id=path[len('/v1/geography/noaa/events/'):]
            try:
                result=noaa_event(self.server.noaa_index,event_id)
                return self.payload(404 if result['status']=='NOT_FOUND' else 200,result,head)
            except ValueError as error:
                return self.payload(400,{'status':'INVALID_EVENT_ID','error':str(error),'carrier_route_attribution':'NOT_ESTABLISHED'},head)
            except Exception:
                return self.payload(503,{'status':'SOURCE_UNAVAILABLE','source':'NOAA_NCEI_STORM_EVENTS_V1','carrier_route_attribution':'NOT_ESTABLISHED'},head)
        if path=='/v1/geography/noaa/locations':
            if not self.server.noaa_index:
                return self.payload(503,{'status':'NOT_INSTALLED','source':'NOAA_NCEI_STORM_EVENTS_V1','carrier_route_attribution':'NOT_ESTABLISHED'},head)
            params=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                state=params.get('state',[''])[0]
                limit=int(params.get('limit',['200'])[0])
                offset=int(params.get('offset',['0'])[0])
                return self.payload(200,noaa_locations(self.server.noaa_index,state,limit,offset),head)
            except (ValueError,TypeError) as error:
                return self.payload(400,{'status':'INVALID_LOCATION_QUERY','error':str(error),'carrier_route_attribution':'NOT_ESTABLISHED'},head)
            except Exception:
                return self.payload(503,{'status':'SOURCE_UNAVAILABLE','source':'NOAA_NCEI_STORM_EVENTS_V1','carrier_route_attribution':'NOT_ESTABLISHED'},head)
        prefix='/v1/carriers/';suffix='/evidence'
        if path.startswith(prefix) and path.endswith(suffix):
            if self.server.integrity is None:
                return self.payload(503,{'status':'NOT_AUDITED','detail':'Carrier evidence requires the matching independent deep audit'},head)
            dot=path[len(prefix):-len(suffix)].strip('/')
            try:
                db=connect(self.server.warehouse)
                try:value=resolved_carrier(db,dot,True)
                finally:db.close()
                value['warehouse_sha256']=self.server.warehouse_sha256
                return self.payload(200,value,head)
            except ValueError as error:return self.payload(404,{'status':'unavailable','error':str(error)},head)
            except Exception:return self.payload(500,{'status':'error','error':'Verified evidence service failed closed'},head)
        return self.payload(404,{'status':'not_found'},head)
    def do_GET(self):self.route()
    def do_HEAD(self):self.route(True)
    def do_OPTIONS(self):self.send_json_headers(204,0)
    def log_message(self,format,*args):return


def serve(warehouse,host='127.0.0.1',port=8787,allow_origin='*',nri_index=None,audit_report=None,noaa_index=None):
    server=EvidenceServer((host,port),Handler,warehouse,allow_origin,nri_index=nri_index,audit_report=audit_report,noaa_index=noaa_index);server.serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('warehouse',nargs='?',default=os.environ.get('EVIDENCE_WAREHOUSE'));parser.add_argument('--host',default=os.environ.get('EVIDENCE_HOST','127.0.0.1'));parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8787')));parser.add_argument('--allow-origin',default=os.environ.get('EVIDENCE_ALLOW_ORIGIN','*'));parser.add_argument('--nri-index',default=os.environ.get('NRI_COUNTY_INDEX'));parser.add_argument('--audit-report',default=os.environ.get('EVIDENCE_AUDIT_FILE'));parser.add_argument('--noaa-index',default=os.environ.get('NOAA_STORM_INDEX'));args=parser.parse_args()
    if not args.warehouse:parser.error('warehouse path or EVIDENCE_WAREHOUSE is required')
    serve(args.warehouse,args.host,args.port,args.allow_origin,args.nri_index,args.audit_report,args.noaa_index)

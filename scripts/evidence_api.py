"""Read-only HTTP API for a verified nationwide Transport3r evidence warehouse."""
import argparse,hashlib,json,pathlib,urllib.parse,os,re
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

from nationwide_evidence import acceptance,connect,resolved_carrier
from nri_county_index import lookup as nri_lookup, read_only_status


def file_sha256(path):
    digest=hashlib.sha256()
    with pathlib.Path(path).open('rb') as handle:
        while block:=handle.read(1024*1024):digest.update(block)
    return digest.hexdigest()


class EvidenceServer(ThreadingHTTPServer):
    def __init__(self,address,handler,warehouse,allow_origin,nri_index=None):
        super().__init__(address,handler);self.warehouse=pathlib.Path(warehouse).resolve();self.allow_origin=allow_origin
        self.nri_index=pathlib.Path(nri_index).resolve() if nri_index else None
        self.nri_status=read_only_status(self.nri_index) if self.nri_index else None
        self.nri_index_sha256=file_sha256(self.nri_index) if self.nri_index else None
        db=connect(self.warehouse)
        try:self.receipt=acceptance(db)
        finally:db.close()
        self.warehouse_sha256=file_sha256(self.warehouse)


class Handler(BaseHTTPRequestHandler):
    server_version='Transport3rEvidence/1'
    def send_json_headers(self,status=200,length=None):
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','public, max-age=300')
        self.send_header('Access-Control-Allow-Origin',self.server.allow_origin);self.send_header('Access-Control-Allow-Methods','GET,HEAD,OPTIONS');self.send_header('Access-Control-Allow-Headers','Accept')
        if length is not None:self.send_header('Content-Length',str(length))
        self.end_headers()
    def payload(self,status,value,head=False):
        raw=json.dumps(value,separators=(',',':'),allow_nan=False).encode();self.send_json_headers(status,len(raw))
        if not head:self.wfile.write(raw)
    def route(self,head=False):
        path=urllib.parse.urlparse(self.path).path
        if path=='/healthz':
            return self.payload(200,{'status':'ok','identity_contract':self.server.receipt['identity_contract'],'sources':self.server.receipt['sources'],'warehouse_sha256':self.server.warehouse_sha256,
                                     'nri_county_source':self.server.nri_status['status'] if self.server.nri_status else 'NOT_INSTALLED'},head)
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
        prefix='/v1/carriers/';suffix='/evidence'
        if path.startswith(prefix) and path.endswith(suffix):
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


def serve(warehouse,host='127.0.0.1',port=8787,allow_origin='*',nri_index=None):
    server=EvidenceServer((host,port),Handler,warehouse,allow_origin,nri_index=nri_index);server.serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('warehouse',nargs='?',default=os.environ.get('EVIDENCE_WAREHOUSE'));parser.add_argument('--host',default=os.environ.get('EVIDENCE_HOST','127.0.0.1'));parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8787')));parser.add_argument('--allow-origin',default=os.environ.get('EVIDENCE_ALLOW_ORIGIN','*'));parser.add_argument('--nri-index',default=os.environ.get('NRI_COUNTY_INDEX'));args=parser.parse_args()
    if not args.warehouse:parser.error('warehouse path or EVIDENCE_WAREHOUSE is required')
    serve(args.warehouse,args.host,args.port,args.allow_origin,args.nri_index)

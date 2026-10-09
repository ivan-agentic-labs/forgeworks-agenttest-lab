from __future__ import annotations
import sqlite3,uuid,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
TENANT='00000000-0000-0000-0000-000000000001';USER='00000000-0000-0000-0000-000000000010'
def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
class Store:
 def __init__(self,path):self.path=path;Path(path).parent.mkdir(parents=True,exist_ok=True) if path!=':memory:' else None;self.init()
 def conn(self):c=sqlite3.connect(self.path,check_same_thread=False);c.row_factory=sqlite3.Row;return c
 def init(self):
  with self.conn() as c:c.executescript('''CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY,slug TEXT,status TEXT);CREATE TABLE IF NOT EXISTS memberships(tenant_id TEXT,user_id TEXT,role TEXT,status TEXT,PRIMARY KEY(tenant_id,user_id));CREATE TABLE IF NOT EXISTS datasets(tenant_id TEXT,id TEXT,name TEXT,owner_id TEXT,latest_version INTEGER,PRIMARY KEY(tenant_id,id));CREATE TABLE IF NOT EXISTS versions(tenant_id TEXT,id TEXT,dataset_id TEXT,version_number INTEGER,sha256 TEXT,case_count INTEGER,PRIMARY KEY(tenant_id,id));CREATE TABLE IF NOT EXISTS builds(tenant_id TEXT,id TEXT,name TEXT,build_sha TEXT,tool_sha TEXT,prompt_version TEXT,PRIMARY KEY(tenant_id,id));CREATE TABLE IF NOT EXISTS runs(tenant_id TEXT,id TEXT,version_id TEXT,build_id TEXT,grader_sha TEXT,status TEXT,job_id TEXT,created_at TEXT,PRIMARY KEY(tenant_id,id));CREATE TABLE IF NOT EXISTS cases(tenant_id TEXT,id TEXT,run_id TEXT,case_key TEXT,grade_status TEXT,score REAL,grader_sha TEXT,trace_digest TEXT,PRIMARY KEY(tenant_id,id));CREATE TABLE IF NOT EXISTS comparisons(tenant_id TEXT,id TEXT,baseline_id TEXT,candidate_id TEXT,paired INTEGER,missing INTEGER,delta REAL,policy TEXT,verdict TEXT,artifact_sha TEXT,PRIMARY KEY(tenant_id,id));''')
 def seed(self):
  with self.conn() as c:c.execute('INSERT OR IGNORE INTO tenants VALUES(?,?,?)',(TENANT,'synthetic-demo','ACTIVE'));c.execute('INSERT OR IGNORE INTO memberships VALUES(?,?,?,?)',(TENANT,USER,'editor','ACTIVE'))
 def member(self,t,u):
  with self.conn() as c:return c.execute("SELECT 1 FROM memberships WHERE tenant_id=? AND user_id=? AND status='ACTIVE'",(t,u)).fetchone() is not None
 def dataset(self,t,name,owner):
  did=str(uuid.uuid4());with_=self.conn();with_.execute('INSERT INTO datasets VALUES(?,?,?,?,?)',(t,did,name,owner,0));with_.commit();with_.close();return did
 def version(self,t,did,sha,count):
  vid=str(uuid.uuid4());
  with self.conn() as c:c.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)',(t,vid,did,1,sha,count));c.execute('UPDATE datasets SET latest_version=1 WHERE tenant_id=? AND id=?',(t,did))
  return vid
 def build(self,t,name,bs,ts,pv):
  bid=str(uuid.uuid4());
  with self.conn() as c:c.execute('INSERT INTO builds VALUES(?,?,?,?,?,?)',(t,bid,name,bs,ts,pv))
  return bid
 def run(self,t,vid,bid,grader):
  rid,jid=str(uuid.uuid4()),str(uuid.uuid4());
  with self.conn() as c:
   c.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',(t,rid,vid,bid,grader,'SUCCEEDED',jid,now()))
   for key,score in [('case-1',1.0),('case-2',0.8 if grader.endswith('f') else 1.0)]:c.execute('INSERT INTO cases VALUES(?,?,?,?,?,?,?,?)',(t,str(uuid.uuid4()),rid,key,'PASS' if score==1 else 'FAIL',score,grader,hashlib.sha256((key+'|redacted-synthetic-trace').encode()).hexdigest()))
  with self.conn() as c:return c.execute('SELECT * FROM runs WHERE tenant_id=? AND id=?',(t,rid)).fetchone()
 def cases(self,t,rid):
  with self.conn() as c:return c.execute('SELECT * FROM cases WHERE tenant_id=? AND run_id=?',(t,rid)).fetchall()
 def compare(self,t,candidate,baseline,policy):
  b=self.cases(t,baseline);q=self.cases(t,candidate);bm={x['case_key']:x for x in b};qm={x['case_key']:x for x in q};paired=len(set(bm)&set(qm));missing=len(set(bm)^set(qm));delta=(sum(x['score'] for x in q)/len(q)-sum(x['score'] for x in b)/len(b)) if b and q else -1.0;verdict='PASS' if missing==0 and delta>=-0.1 and all(x['grade_status']!='MISSING' for x in q) else 'FAIL';cid=str(uuid.uuid4());art=hashlib.sha256(json.dumps({'paired':paired,'missing':missing,'delta':delta,'policy':policy,'verdict':verdict},sort_keys=True).encode()).hexdigest()
  with self.conn() as c:c.execute('INSERT INTO comparisons VALUES(?,?,?,?,?,?,?,?,?,?)',(t,cid,baseline,candidate,paired,missing,delta,policy,verdict,art))
  return c.execute('SELECT * FROM comparisons WHERE tenant_id=? AND id=?',(t,cid)).fetchone()
 def comparison(self,t,cid):
  with self.conn() as c:return c.execute('SELECT * FROM comparisons WHERE tenant_id=? AND id=?',(t,cid)).fetchone()

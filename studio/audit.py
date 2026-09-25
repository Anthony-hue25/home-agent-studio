"""Ordered, hash-chained events. No capability tokens or credentials enter this stream."""
from dataclasses import asdict, is_dataclass
from pathlib import Path
from threading import RLock
import hashlib,json

def data(value):
    def encode(obj):
        if is_dataclass(obj):return asdict(obj)
        raise TypeError('not audit data')
    return json.loads(json.dumps(value,default=encode,allow_nan=False))

def digest(value):
    return hashlib.sha256(json.dumps(data(value),sort_keys=True,separators=(',',':')).encode()).hexdigest()

class Audit:
    def __init__(self,path=None):
        self.path=Path(path) if path else None;self._events=[];self._lock=RLock()
        if self.path:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            if self.path.exists():
                for line in self.path.read_text(encoding='utf-8').splitlines():
                    e=json.loads(line);h=e.pop('hash')
                    if e['sequence']!=len(self._events) or digest(e)!=h or e['previous']!=(self._events[-1]['hash'] if self._events else '0'*64):raise ValueError('audit integrity')
                    self._events.append({**e,'hash':h})
    def emit(self,event,**fields):
        if any(k in fields for k in ('token','capability_token','credentials')):raise ValueError('secret field forbidden')
        with self._lock:
            e={'sequence':len(self._events),'event':event,'previous':self._events[-1]['hash'] if self._events else '0'*64,'fields':data(fields)}
            e['hash']=digest(e)
            if self.path:
                with self.path.open('a',encoding='utf-8') as f:f.write(json.dumps(e,sort_keys=True)+'\n');f.flush()
            self._events.append(e)
            return data(e)
    def view(self):
        with self._lock:return data(self._events)

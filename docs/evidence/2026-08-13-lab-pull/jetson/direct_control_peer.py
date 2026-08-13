#!/usr/bin/env python3
from __future__ import print_function
import argparse, json, os, socket, struct, threading, time
import websocket

MAGIC_COOKIE = 0x2112A442

def mono_ns():
    return int(time.monotonic() * 1000000000)

def stun(sock, host, port):
    tid=os.urandom(12)
    req=struct.pack("!HHI12s",1,0,MAGIC_COOKIE,tid)
    target=(socket.gethostbyname(host),port)
    old=sock.gettimeout(); sock.settimeout(3)
    try:
        for _ in range(3):
            sock.sendto(req,target)
            try: data,_=sock.recvfrom(2048)
            except socket.timeout: continue
            if len(data)<20 or data[8:20]!=tid: continue
            mlen=struct.unpack("!H",data[2:4])[0]
            off=20; end=min(len(data),20+mlen)
            while off+4<=end:
                typ,ln=struct.unpack("!HH",data[off:off+4])
                val=data[off+4:off+4+ln]
                if typ in (0x20,0x01) and len(val)>=8 and val[1]==1:
                    p=struct.unpack("!H",val[2:4])[0]
                    ip=bytearray(val[4:8])
                    if typ==0x20:
                        p ^= MAGIC_COOKIE>>16
                        c=struct.pack("!I",MAGIC_COOKIE)
                        for i in range(4): ip[i]^=c[i]
                    return socket.inet_ntoa(bytes(ip)),p
                off += 4+((ln+3)//4)*4
        raise RuntimeError("no STUN response")
    finally: sock.settimeout(old)

class Peer:
    def __init__(self,a):
        self.a=a
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0",0)); self.sock.settimeout(.2)
        self.pub=stun(self.sock,a.stun_host,a.stun_port)
        self.ws=websocket.create_connection(a.broker,timeout=10); self.ws.settimeout(None)
        self.peer=None; self.ev=threading.Event(); self.stop=False
        t=threading.Thread(target=self.wsloop); t.daemon=True; t.start()

    def sendws(self,o): self.ws.send(json.dumps(o,separators=(",",":")))

    def wsloop(self):
        while not self.stop:
            try: m=json.loads(self.ws.recv())
            except Exception: return
            if m.get("type")=="control_udp_candidate" and m.get("role")!=self.a.role:
                self.peer=(str(m["ip"]),int(m["port"]))
                print("[{}] peer {}:{}".format(self.a.role.upper(),*self.peer),flush=True)
                self.ev.set()

    def rendezvous(self):
        print("[{}] public {}:{}".format(self.a.role.upper(),*self.pub),flush=True)
        end=time.time()+20
        while not self.ev.is_set() and time.time()<end:
            self.sendws({"type":"control_udp_candidate","role":self.a.role,"ip":self.pub[0],"port":self.pub[1]})
            self.ev.wait(.6)
        if not self.ev.is_set(): raise RuntimeError("peer candidate missing")
        for _ in range(20):
            try:self.sock.sendto(b"PUNCH",self.peer)
            except Exception:pass
            try:self.sock.recvfrom(2048)
            except socket.timeout:pass
            time.sleep(.03)

    def jetson(self):
        print("[JETSON] DRY-RUN ONLY: no GPIO/motor/servo writes",flush=True)
        got=0; rtts=[]
        end=time.time()+15
        while time.time()<end and got<80:
            try:data,addr=self.sock.recvfrom(2048)
            except socket.timeout:
                try:self.sock.sendto(b"PUNCH",self.peer)
                except Exception:pass
                continue
            if data.startswith(b"CTRL "):
                try:
                    m=json.loads(data[5:].decode("utf-8"))
                    got+=1
                    age=(mono_ns()-int(m["sent_ns"]))/1e6
                    rtts.append(age)
                    self.sock.sendto(("ACK "+str(m["seq"])+" "+str(m["sent_ns"])).encode(),addr)
                    if got%20==0:
                        print("[JETSON] DRY_CONTROL count={} servo={:.1f} pwm={} one_wayish={:.1f}ms".format(
                            got,float(m["servo"]),int(m["pwm"]),age),flush=True)
                except Exception as e: print("[JETSON] bad control {}".format(e),flush=True)
        print("[JETSON] DRY_CONTROL_TOTAL {}".format(got),flush=True)
        if got<20: raise RuntimeError("too few direct control packets")

    def rtx(self):
        import torch
        dev="cuda" if torch.cuda.is_available() else "cpu"
        print("[RTX] PYTORCH {}".format(dev),flush=True)
        rtts=[]; acks={}
        # Receiver thread for ACKs.
        def rx():
            while not self.stop:
                try:d,_=self.sock.recvfrom(2048)
                except socket.timeout:continue
                if d.startswith(b"ACK "):
                    try:
                        _,seq,sent=d.decode().split()
                        acks[int(seq)]=(mono_ns()-int(sent))/1e6
                    except Exception:pass
        t=threading.Thread(target=rx); t.daemon=True; t.start()
        for seq in range(80):
            t0=time.perf_counter()
            x=torch.rand((1,1024),device=dev)
            # tiny dummy policy head; proves CUDA execution -> action values
            y=x.mean()
            if dev=="cuda": torch.cuda.synchronize()
            infer=(time.perf_counter()-t0)*1000
            servo=90.0+float((y.item()-.5)*4.0); pwm=0
            sent=mono_ns()
            msg={"seq":seq,"sent_ns":sent,"servo":servo,"pwm":pwm,"infer_ms":infer}
            self.sock.sendto(b"CTRL "+json.dumps(msg,separators=(",",":")).encode(),self.peer)
            time.sleep(.04)
        time.sleep(2)
        vals=list(acks.values())
        print("[RTX] DIRECT_CONTROL_ACKS {}/80".format(len(vals)),flush=True)
        if vals:
            vals.sort()
            p50=vals[len(vals)//2]; p95=vals[min(len(vals)-1,int(len(vals)*.95))]
            print("[RTX] DIRECT_CONTROL_RTT p50={:.1f}ms p95={:.1f}ms min={:.1f}ms max={:.1f}ms".format(
                p50,p95,min(vals),max(vals)),flush=True)
        if len(vals)<20: raise RuntimeError("direct control ACK path weak/failed")

    def run(self):
        self.rendezvous()
        try:
            if self.a.role=="jetson": self.jetson()
            else:self.rtx()
        finally:
            self.stop=True
            try:self.ws.close()
            except Exception:pass
            self.sock.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--role",choices=["jetson","rtx"],required=True)
    p.add_argument("--broker",required=True)
    p.add_argument("--stun-host",default="stun.cloudflare.com")
    p.add_argument("--stun-port",type=int,default=3478)
    a=p.parse_args()
    Peer(a).run()
if __name__=="__main__": main()

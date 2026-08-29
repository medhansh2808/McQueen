import socket, sys
s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", int(sys.argv[1])))
s.settimeout(float(sys.argv[2]))
n=b=0; import time; t0=time.monotonic()
try:
    while True:
        d,_=s.recvfrom(65536); n+=1; b+=len(d)
except Exception: pass
el=time.monotonic()-t0
print("sink: %d pkts %.1f MB in %.1fs = %.1f Mbps"%(n,b/1e6,el,b*8/1e6/el))

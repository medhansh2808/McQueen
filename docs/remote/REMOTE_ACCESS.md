# Remote Access via cloudflared TCP Quick Tunnels

Status: VERIFIED 2026-08-16 (lab session). RTX and Jetson both reachable from
the laptop via SSH over cloudflared TCP quick tunnels. The laptop can do this
from ANY location with internet (home included) — the lab machines run the
tunnels themselves; only the laptop client is needed locally.

## Machines

| Machine | SSH user@host (lab LAN) | Tunnel unit (systemd) | Local port (laptop) |
|---|---|---|---|
| RTX 4090 (hostname `omen`) | junior@192.168.0.132 | mcqueen-rtx-ssh-tunnel | 2222 |
| Jetson Nano (hostname `ubuntu`) | sravjti@192.168.55.1 (USB) / 192.168.0.112 (Wi-Fi) | mcqueen-jetson-ssh-tunnel | 2223 |

Current tunnel URLs (CHANGE ON EVERY RESTART — re-capture, see below):

    RTX:    https://governmental-jet-congress-blah.trycloudflare.com   (VERIFIED end-to-end 2026-08-21)
    Jetson: STALE (Jetson off at lab; re-capture on next power-on)

URLs are also stored locally (NOT committed): `~/mcqueen-remote/rtx.url` and
`~/mcqueen-remote/jetson.url`.

## VERIFIED 2026-08-21 (session 3x) — full home-access chain re-proven

RTX tunnel unit restarted at the lab → fresh URL captured from the log tail →
laptop client relaunched → `ssh -p 2222 junior@localhost` reached `omen`.
Gotchas learned (all hit live this session):

1. **SSH target is `localhost:2222` (or 127.0.0.1:2222), NEVER the
   trycloudflare hostname.** Connecting to the public hostname on port 2222
   gives "Network is unreachable" — the public URL only accepts the cloudflared
   client's websocket, not raw SSH.
2. **Only trust the LOG TAIL for the live URL**:
   `grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /var/tmp/mcqueen-junior/rtx-tunnel.log | tail -1`
   The files `/var/tmp/mcqueen-junior/.last_report` and `.../cloudflared.url`
   are STALE snapshots (Aug 15/17) — do not use them.
3. **First SSH through a new tunnel**: add `-o StrictHostKeyChecking=accept-new`
   (BatchMode refuses unknown host keys otherwise → "Host key verification failed").
4. **Backgrounding the laptop client from a scripted shell**: use
   `setsid ./cloudflared access tcp --hostname "$(cat rtx.url)" --url 127.0.0.1:2222 </dev/null >log 2>&1 &`
   — plain `&` children get killed when the launching shell times out.
5. Restarting the tunnel unit mints a NEW URL every time; the unit flaps
   occasionally (edge retry loops in the log) but stays active — if a URL dies,
   restart the unit and re-capture rather than debugging the old one.

## HOME WORKFLOW (Jetson powered off between sessions)

The Jetson is powered OFF when nobody is at the lab. Workflow from home:

1. Call someone at the lab (they only plug/unplug cables) → Jetson powers on.
2. Jetson boots (~40 s), auto-connects `Delta_Virus_Lab` Wi-Fi, auto-starts its
   tunnel systemd unit with a NEW random URL (verified 2026-08-16 reboot test).
3. At boot, the unit `mcqueen-jetson-url-report` automatically SSHes to the RTX
   (restricted key `mcqueen-jetson-to-rtx`) and appends the new URL to
   `/var/tmp/mcqueen-junior/url-reports.txt` on the RTX.
4. From home, get the new Jetson URL via the RTX tunnel (RTX stays on):

       cd ~/mcqueen-remote
       ./cloudflared access tcp --hostname "$(cat rtx.url)" --url 127.0.0.1:2222
       ssh -p 2222 junior@127.0.0.1      # laptop key — no password
       tail -3 /var/tmp/mcqueen-junior/url-reports.txt
       # → "jetson URL https://xxx.trycloudflare.com"
       echo "https://xxx.trycloudflare.com" > ~/mcqueen-remote/jetson.url; chmod 600 ~/mcqueen-remote/jetson.url
       # exit, then start the Jetson proxy + connect
       ./cloudflared access tcp --hostname "$(cat jetson.url)" --url 127.0.0.1:2223
       ssh -p 2223 sravjti@127.0.0.1    # laptop key — no password

RTX rebooted while you're home? If the Jetson is ON, its tunnel still works and
its boot unit `mcqueen-rtx-url-report` mirrored the new RTX URL to
`/var/tmp/mcqueen-sravjti/url-reports.txt` on the Jetson (`rtx URL …` line) —
read it over the Jetson tunnel. If BOTH the RTX rebooted AND the Jetson is off:
manual hop via the surviving tunnel is impossible → lockout until a lab visit.

NOTE: the mirror script targets the Jetson's DHCP IP (192.168.0.112); if the
Jetson's lease changes after a reboot the mirror may fail — the RTX's LAN IP is
static (192.168.0.132), so a manual hop (Jetson tunnel → `ssh junior@192.168.0.132`
→ grep the RTX log) always works as fallback.

## SSH keys (installed 2026-08-16)

- Laptop → RTX + laptop → Jetson: `~/.ssh/id_ed25519` (mcqueen-laptop) in both
  `authorized_keys` files — home sessions need no passwords.
- Jetson → RTX: restricted key (append-only: `command="cat >> /var/tmp/mcqueen-junior/url-reports.txt"`,
  no-pty/forwarding) used ONLY by the URL-report unit.
- RTX → Jetson: restricted key (append-only to `/var/tmp/mcqueen-sravjti/url-reports.txt`)
  used ONLY by the mirror unit.
- sudo on the machines still needs passwords (typed by the human per session).

## Laptop (home) — how to connect

One-time client setup (already done on this laptop):

    mkdir -p ~/mcqueen-remote && cd ~/mcqueen-remote
    curl -sL -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod 700 cloudflared

Connect (two terminals per machine, or background the proxy):

    # terminal 1: local tunnel proxy
    cd ~/mcqueen-remote
    ./cloudflared access tcp --hostname "$(cat rtx.url)"   --url 127.0.0.1:2222
    ./cloudflared access tcp --hostname "$(cat jetson.url)" --url 127.0.0.1:2223

    # terminal 2: SSH (laptop key — no password; sudo still needs the password)
    ssh -p 2222 junior@127.0.0.1
    ssh -p 2223 sravjti@127.0.0.1

Passwords are the normal machine SSH passwords (never stored in this repo).

## Re-capturing URLs after a lab reboot/restart

Quick-tunnel hostnames are random per launch. After any RTX/Jetson reboot or
service restart, get the new URL from the machine log, then update the laptop
file:

    # on the machine (or via existing tunnel):
    grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /var/tmp/mcqueen-junior/rtx-tunnel.log | tail -1
    grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /var/tmp/mcqueen-sravjti/jetson-tunnel.log | tail -1

    # on the laptop:
    echo "<new url>" > ~/mcqueen-remote/rtx.url      # chmod 600
    echo "<new url>" > ~/mcqueen-remote/jetson.url

### URL recovery WITHOUT a lab visit (cross-machine hop)

If ONE machine rebooted while you are away, the OTHER machine's tunnel still
works — and both machines are on the same lab LAN (RTX 192.168.0.132, Jetson
192.168.0.112). Recover the new URL from home by hopping through the machine
that is still up:

    # example: RTX rebooted, Jetson tunnel still works
    ssh -p 2223 sravjti@127.0.0.1          # -> Jetson (old jetson.url)
    ssh junior@192.168.0.132               # -> RTX over lab LAN (type RTX password)
    grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /var/tmp/mcqueen-junior/rtx-tunnel.log | tail -1
    # take the new URL, exit back to the laptop, update rtx.url, reconnect on :2222

Mirror procedure if the Jetson rebooted (hop via the RTX tunnel, then
`ssh sravjti@192.168.0.112`, grep `/var/tmp/mcqueen-sravjti/jetson-tunnel.log`).

TOTAL LOCKOUT only if BOTH machines go down together (lab power cut) — then the
old URLs are dead and nothing can be read remotely; a lab visit is required.

### Future fix (optional): fixed hostnames via a named tunnel

A Cloudflare **named tunnel** (requires a Cloudflare account + a domain, e.g.
`rtx-ssh.example.com` with Cloudflare DNS) gives a STABLE hostname that never
changes across reboots — eliminating URL re-capture entirely. Not set up now
(needs user's Cloudflare/domain credentials); revisit if reboot lockouts annoy.

## Lab-side setup (how it was installed, for re-install)

Tunnels run as systemd units on each machine, `Restart=always`, so they survive
reboots (URL changes, see above). The RTX also has an older, separate
cloudflared broker tunnel (`mcqueen-broker` / pid on 127.0.0.1:8765) — DO NOT
touch it; the SSH tunnel unit is independent.

RTX:

    unit: /etc/systemd/system/mcqueen-rtx-ssh-tunnel.service
    ExecStart=/var/tmp/mcqueen-junior/cloudflared tunnel --url tcp://localhost:22 --no-autoupdate --logfile /var/tmp/mcqueen-junior/rtx-tunnel.log
    User=junior, WantedBy=multi-user.target

Jetson:

    unit: /etc/systemd/system/mcqueen-jetson-ssh-tunnel.service
    ExecStart=/var/tmp/mcqueen-sravjti/cloudflared tunnel --url tcp://localhost:22 --no-autoupdate --logfile /var/tmp/mcqueen-sravjti/jetson-tunnel.log
    User=sravjti, WantedBy=multi-user.target

Removal (if ever needed): `systemctl disable --now <unit>` + delete the unit
file + `daemon-reload`. Nothing else on the machines was modified.

## Security notes

- Tunnel URLs expose SSH on the public internet; gates = SSH passwords AND the
  laptop's SSH key (installed 2026-08-16). The restricted report keys are
  append-only (single command) — they cannot open shells.
- Tunnel URLs are random per restart and are NOT committed to the repo.
- The laptop client binary and URL files live only in `~/mcqueen-remote/`.
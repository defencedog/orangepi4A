# Run BTop on startup
`btop` will be launched on 2nd workspace
```
#if path is not available make it
sudo apt install -y btop xterm
nano ~/.config/systemd/user/ukhan_btop.service
systemctl daemon-reload
systemctl --user enable ukhan_btop.service
sudo reboot
```
*ukhan_btop.service*
```
[Unit]
Description=BTop monitoring
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=exec
Type=oneshot
ExecStart=/usr/bin/sh -c 'sleep 5; wmctrl -s 1; xterm btop -maximized; wmctrl -s 1'

[Install]
WantedBy=graphical-session.target
```

## Sharing drives among Linux systems
_NIX_ is a USB on OPi3b device
*Commands to run on OPi4a*
```
sudo apt install sshfs
sudo mkdir /media/NIX
sudo chown $USER:$USER /media/NIX
sshfs ukhan@<remote_ip>:/media/ukhan/NIX /media/NIX
```
You can create an `alias` of last command in `~/.bashrc`. 
**I am not able to found a proper solution of mounting ssh drive via `fstab` while providing password automatically**

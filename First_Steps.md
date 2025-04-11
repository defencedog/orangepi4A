# OPi4a
## Change username 
```
sudo auto_login_cli.sh root
sudo desktop_login.sh root
sudo reboot
# next login will be in root session
groupmod -n ukhan orangepi
usermod -d /home/ukhan -m -g ukhan -l ukhan orangepi
reboot
# still in root session
```
Look at these files `nano if there is any orangepi entry`
> /etc/group
> /etc/shadow
> /etc/passwd

Finally 
```
desktop_login.sh ukhan
reboot
```
Next session will be under ukhan user. In Ubuntu system settings > users > manually edit orangepi to ukhan. Use `passwd` to set new user password
## Update GPU
**There are some held packages `apt-mark showhold` do not unhold these**
Add following x2 *ppas* & do `apt full-upgrade`
https://forum.radxa.com/t/introduction-to-rockchip-multimedia-ppa-for-ubuntu-jammy/14537
https://launchpad.net/~kisak/+archive/ubuntu/kisak-mesa
```
sudo add-apt-repository ppa:kisak/kisak-mesa
sudo add-apt-repository ppa:liujianfeng1994/rockchip-multimedia
sudo apt full-upgrade
sudo reboot
sudo apt install clapper ffmpeg mpv chromium chrome-browser libv4l-rkmpp gstreamer1.0-rockchip1 kodi
```
## Make workspaces only x2
Use `dconf-editor`
> https://unix.stackexchange.com/questions/490847/set-static-number-of-workspaces-in-gnome-shell-with-dconf
## Install PiApps
`wget -qO- https://raw.githubusercontent.com/Botspot/pi-apps/master/install | bash` & the install in a queue form all applications required

## Libreoffice Icons
`curl -s https://raw.githubusercontent.com/rizmut/libreoffice-style-sifr/master/install-sifr.sh | sh`

## Compilation Environment
### Linux based
`sudo apt install build-essential cmake autoconf meson`
### .Net8.x
```
cd ~/Downloads
wget https://builds.dotnet.microsoft.com/dotnet/Sdk/8.0.408/dotnet-sdk-8.0.408-linux-arm64.tar.gz
mkdir -p $HOME/dotnet && tar zxf dotnet-sdk-8.0.408-linux-arm64.tar.gz -C $HOME/dotnet
```
Then `nano ~/.bashrc` at the end of file add x2 lines
```
export DOTNET_ROOT=$HOME/dotnet
export PATH=$PATH:$HOME/dotnet
```


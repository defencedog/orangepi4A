# Flatpak & Flathub on Ubuntu
Latest containerised apps that are big in size :(
```
sudo apt install flatpak
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
nano ~/.profile
```
at the EOF add
> XDG_DATA_DIRS="/var/lib/flatpak/exports/share:/home/ukhan/.local/share/flatpak/exports/share:$XDG_DATA_DIRS"

The `sudo reboot`

Now install some apps & desktop entries will be available in gnome panels
```
flatpak install flathub org.gnome.World.PikaBackup
flatpak install flathub net.nokyan.Resources
flatpak install flathub net.sourceforge.Pdfedit
flatpak install flathub app.drey.Dialect
flatpak install flathub net.code_industry.MasterPDFEditor
```

## Make flatpaks follow system theme
```
sudo flatpak override --filesystem=$HOME/.themes
sudo flatpak override --filesystem=$HOME/.icons
sudo flatpak override --env=GTK_THEME=my-theme 
sudo flatpak override --env=ICON_THEME=my-icon-theme 
#e.g
sudo flatpak override --env=GTK_THEME=Adwaita:dark
#per application rule
sudo flatpak override org.gnome.Calculator --filesystem=$HOME/.themes
sudo flatpak override org.gnome.Calculator --filesystem=$HOME/.icons
```

## Manage Applications
```
flatpak list --app
flatpak uninstall --delete-data App-ID
```

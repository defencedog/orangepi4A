# Make Qt Apps follow System Light/Dark Style in Ubuntu 22.04
```
sudo add-apt-repository ppa:ubuntuhandbook1/qgnomeplatform
sudo apt install qgnomeplatform-qt5
nano ~/.profile #add EOF -> export QT_QPA_PLATFORMTHEME='gnome'
sudo add-apt-repository --remove ppa:ubuntuhandbook1/qgnomeplatform
```


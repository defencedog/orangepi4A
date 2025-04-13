# Changing Connection Priorities Linux
Sometimes easy to use `nm-connection-editor` gui is not available in repos, so CLI option to be used
## Check existing priorities
```
nmcli connection show
NAME                    UUID                                  TYPE       DEVICE          
khan 5G_Plus            15ef0c5f-4ae3-4607-b1d2-a338b2189626  wifi       wlan0           
khan 5G_Plus_5G         3da1190f-bc16-40bf-84a5-18be8f87b483  wifi       wlx90de8017e3ad 
Usama's S23 FE Network  96f0f868-9c0c-427e-818d-fe5dc2292851  bluetooth  --              
Wired connection 1      82b4e4d6-300e-39ca-871d-dc814651e5e4  ethernet   --  
```
## Modifying priority
Default priority of each is `100` Our objective is to assign highest priority to USB connected wifi module `wlx90de8017e3ad` 
```
nmcli connection modify "khan 5G_Plus_5G" ipv4.route-metric 102
nmcli connection up "khan 5G_Plus_5G"
nmcli connection down "khan 5G_Plus_5G"
```
Now recheck priority using `nmcli connection show`


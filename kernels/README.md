# Custom Compiled from OrangePI Build Framework
These `.debs` can be installed as I have included multiple missing features. In the default kernel x3 important features (filesystem support) are missing

1. `cifs` support is added; you cannot mount a samba shared directory!
2. `nfs` support is added
3. `binfmt_misc` filesystem support is still missing. So you cannot run `box86` applications. I will latter add it.

> https://github.com/defencedog/orangepi3b_v2.1/blob/main/SAMBA_NAS_Videos.md

These kernerls can be used with official `jammy` image v1.0.4

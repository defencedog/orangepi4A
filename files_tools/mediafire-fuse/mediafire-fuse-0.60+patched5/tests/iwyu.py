#!/usr/bin/env python

from __future__ import print_function

import json
import subprocess
import shlex
import sys
import os

if len(sys.argv) == 1:
    build_dir = "."
elif len(sys.argv) == 2:
    build_dir = sys.argv[1]
else:
    print("usage: %s [build_dir]"%sys.argv[0])
    exit(1)

compile_commands = os.path.join(build_dir, "compile_commands.json")

with open(compile_commands, "r") as f:
    tunits = json.load(f)

result = 0
for tu in tunits:
    _,cmd = tu["command"].split(" ",1)
    cmd = "%s %s"%("iwyu", cmd)
    cmd = shlex.split(cmd)
    # iwyu does not distinguish between different outcomes of its check
    # so instead, we grep its stderr output
    # see http://code.google.com/p/include-what-you-use/issues/detail?id=157
    ret = subprocess.Popen(cmd, stderr=subprocess.PIPE)
    _,ret = ret.communicate()
    if "has correct #" not in ret:
        result += 1
        print(ret)

exit(result)

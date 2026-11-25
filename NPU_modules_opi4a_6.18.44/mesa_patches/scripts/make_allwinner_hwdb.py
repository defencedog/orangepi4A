with open("/root/builds/mesa-26.0.8/src/etnaviv/hwdb/amlogic/gc_feature_database.h", "r") as f:
    lines = f.readlines()

header_lines = lines[:800]
features_tail = lines[810:1536]

entry_formal = [
    "    /* vip9000nano-di for Allwinner T527 (Formal) */\n",
    "    {\n",
    "        0x9000, /* ChipID */\n",
    "        0x9003, /* ChipRevision */\n",
    "        0x5090009, /* ProductID */\n",
    "        0x6000000, /* EcoID */\n",
    "        0x10000016, /* CustomerID */\n",
    "        0x0, /* PatchVersion */\n",
    "        \"\", /* ProductName */\n",
    "        0x1, /* FormalRelease */\n",
] + features_tail

entry_informal = [
    "    /* vip9000nano-di for Allwinner T527 (Informal) */\n",
    "    {\n",
    "        0x9000, /* ChipID */\n",
    "        0x9003, /* ChipRevision */\n",
    "        0x5090009, /* ProductID */\n",
    "        0x6000000, /* EcoID */\n",
    "        0x10000016, /* CustomerID */\n",
    "        0x0, /* PatchVersion */\n",
    "        \"\", /* ProductName */\n",
    "        0x0, /* FormalRelease */\n",
] + features_tail

footer = [
    "};\n",
    "\n",
    "#endif\n"
]

all_lines = header_lines + entry_formal + entry_informal + footer

with open("/root/builds/mesa-26.0.8/src/etnaviv/hwdb/allwinner/gc_feature_database.h", "w") as f:
    f.writelines(all_lines)

print("Created allwinner/gc_feature_database.h with", len(all_lines), "lines")

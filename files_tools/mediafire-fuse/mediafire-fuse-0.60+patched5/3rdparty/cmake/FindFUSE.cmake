# Copyright (C) 2014 Johannes Schauer <j.schauer@email.de>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

find_path(FUSE_INCLUDE_DIRS NAMES "fuse/fuse.h" "fuse/fuse_common.h")
find_library(FUSE_LIBRARIES NAMES "fuse")
mark_as_advanced(FUSE_INCLUDE_DIRS FUSE_LIBRARIES)

IF (FUSE_INCLUDE_DIRS)
	file(STRINGS "${FUSE_INCLUDE_DIRS}/fuse/fuse_common.h" fuse_version_str REGEX "^#define[ \t]+FUSE_(MAJOR|MINOR)_VERSION[ \t]+.*")
	string(REGEX REPLACE ".*#define[ \t]+FUSE_MAJOR_VERSION[ \t]+([0-9]+).*" "\\1" FUSE_VERSION_MAJOR "${fuse_version_str}")
	string(REGEX REPLACE ".*#define[ \t]+FUSE_MINOR_VERSION[ \t]+([0-9]+).*" "\\1" FUSE_VERSION_MINOR "${fuse_version_str}")
	unset(fuse_version_str)
endif()

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(FUSE
	REQUIRED_VARS FUSE_LIBRARIES FUSE_INCLUDE_DIRS
	VERSION_VAR "${FUSE_VERSION_MAJOR}.${FUSE_VERSION_MINOR}")

#!/bin/sh

set -ex

case $# in
	0)
		source_dir="."
		binary_dir="."
		;;
	2)
		source_dir=$1
		binary_dir=$2
		;;
	*)
		echo "usage: $0 [source_dir] [binary_dir]"
		exit 1
		;;
esac

cmd="valgrind --suppressions="${source_dir}/valgrind.supp" --fullpath-after="$source_dir" --tool=memcheck --leak-check=yes --show-reachable=yes --num-callers=20 --track-fds=yes --track-origins=yes --error-exitcode=1 --quiet"

if [ ! -f "$XDG_CONFIG_HOME/mediafire-tools/config" -a ! -f ~/.config/mediafire-tools/config ]; then
	echo "no configuration file found" >&2
	exit 1
fi

if [ `mount -t fuse.mediafire-fuse | wc -l` -ne 0 ]; then
	echo "a fuse fs is already mounted" >&2
	exit 1
fi

$cmd "${binary_dir}/mediafire-fuse" -f -d /mnt &
fusepid="$!"

# wait for the file system to be mointed
for i in `seq 1 10`; do
	sleep 1
	if [ `mount -t fuse.mediafire-fuse | wc -l` -ne 0 ]; then
		break;
	fi
done

# check if mounting was successful
if [ `mount -t fuse.mediafire-fuse | wc -l` -eq 0 ]; then
	echo "cannot mount fuse" >&2
	fusermount -u /mnt
	wait "$fusepid"
	exit 1
fi

# print tree
tree /mnt

# make new directory
mkdir "/mnt/test"

# FIXME: also test for moving and renaming of directories
# FIXME: also test for creating files and folder with special characters
# FIXME: also test for creating files and folder with name longer than 255

# create file in the root directory
echo foobar > "/mnt/foobar2"

# move the file to the new directory
mv /mnt/foobar2 /mnt/test/foobar

# wait a bit because above operation finishes before the release() call finished
sleep 5

# print tree
tree /mnt

# check content of new file
diff=`echo "foobar" | diff - "/mnt/test/foobar" >/dev/null 2>&1 && echo 0 || echo 1`

if [ $diff -ne 0 ]; then
	printf "foobar" | diff - "/mnt/test/foobar" || true
fi

# delete directory and file inside
rm -rf "/mnt/test"

# print tree
tree /mnt

sleep 2

fusermount -u /mnt

wait "$fusepid"
valg=$?

if [ $diff -eq 0 -a $valg -eq 0 ]; then
	exit 0
else
	exit 1
fi

#!/bin/sh

case $# in
	0)
		source_dir="."
		;;
	1)
		source_dir=$1
		;;
	*)
		echo "usage: $0 [source_dir]"
		exit 1
		;;
esac

source_dir=`readlink -f "$source_dir"`

find "$source_dir" -name "*.c" -o -name "*.h" | while read f; do
	case $f in
		${source_dir}/3rdparty/*)
			;;
		${source_dir}/*/CMakeFiles/*)
			;;
		${source_dir}/CMakeFiles/*)
			;;
		*)
			INDENT_PROFILE="${source_dir}/.indent.pro" indent -st "$f" | diff -u "$f" - >&2
			ret=$((ret+$?))
			echo $ret
			;;
	esac
done | sort -n | tail --lines=1 | while read ret; do
	exit $ret
done

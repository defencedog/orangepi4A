Running tests
=============

The test suite makes sure that coding standards are followed and that the shell
and fuse module work.

Since the test suite will connect to a remote mediafire share, make sure that
you have a configuration file with a username and password in place and that
this share does not contain a file or directory called `test` as it will be
created and removed during testing. You can also place the `config` file in
your current directory instead of your home directory to have a separate
configuration file for testing.

To run the test suite you need additional dependencies. On Debian and
derivatives you need:

	apt-get install indent python iwyu valgrind fuse

To run the tests, run:

	make test

The test suite is using ctest which does not produce anything on standard
output by default. To disable this behaviour when errors happen, run:

	CTEST_OUTPUT_ON_FAILURE=TRUE make test

otherwise the output is in

	Testing/Temporary/LastTest.log

Automatically fixing discovered errors
======================================

To fix all includes:

	for f in **/*.c **/*.h; do iwyu "$f" 2>&1 | fix_include; done

To fix indentation (the file `.indent.pro` will be used):

	indent **/*.c **/*.h
	rm **/*\~

to compile verbosely:

	cmake -DCMAKE_VERBOSE_MAKEFILE=true

Debug Build
===========

To make a debug build with debug symbols, run cmake like this:

	cmake -DCMAKE_BUILD_TYPE=Debug ..

Misc
====

When valgrind reports uninitialized memory due to aesni_cbc_encrypt, run the
tests with:

	OPENSSL_ia32cap="~0x200000000000000"

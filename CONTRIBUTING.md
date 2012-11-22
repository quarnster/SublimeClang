# Before opening up a new issue
----------------------------------

* Use the search functionality to see if there's already an issue number
  dealing with the problem. If there is, please comment in the existing
  issue.
* Make sure that the issue hasn't already been fixed in the master branch.
  I don't create a new release of the plugin for every single commit so
  it is possible that the issue has already been fixed.
* Provide a small stand alone test case where the issue is reproducible.
* Make sure that the issue is with SublimeClang specifically and not
  something that's broken in Sublime Text 2 or libclang.

Please do remember that I am not your personal tech support and issues related
to configuring the plugin as appropriate for your system and target platform
have a high chance as being closed immediately. I am just a single person and
the time I allocate to this project is limited. You'll have a better
chance asking on the [Sublime Text 2 forums](http://www.sublimetext.com/forum/),
[Stackoverflow](http://stackoverflow.com/) or possibly
[Twitter](http://twitter.com/) to reach a much larger audience.

Having said that you can have a look at these existing issues to see
if they answer your issue or ask the community to help you out:

* [Issue 122](https://github.com/quarnster/SublimeClang/issues/122)
  for configuration issues getting the plugin to work on Windows.
* [Issue 35](https://github.com/quarnster/SublimeClang/issues/35)
  for configuration issues getting the plugin to work on Linux.
* [Issue 52](https://github.com/quarnster/SublimeClang/issues/52)
  for configuration issues getting the plugin to work when targeting iOS.
* [Issue 134](https://github.com/quarnster/SublimeClang/issues/134)
  for configuration issues getting the plugin to work when targeting the
  AVR toolchain.



# Before submitting a pull request
-----------------------------------

* Does the pull request fix a previously filed issue? If so, please do
  reference the issue number via #number in the commit message.
* Does the pull request fix an issue that has not previously been reported?
  Please explain what the issue is in the commit message.
* Make sure that no regressions are introduced and the unittests still pass.
  See the [unit testing section](#unit-testing) for more details.
* If appropriate, write a new unit test for the fix to catch future
  regressions.

# Unit testing
--------------------------------

To run the unit tests go into the SublimeClang directory and run:

    python unittests/unittest.py -disableplatformspecific

Disabling the platformspecific tests just makes sure that there are no
false failures due to differences in configuration between your
platform/system/machine and mine. You might still have to tweak include
paths and compiler flags to match your system.

### Changing the expected results of a test

The unit tests aren't necessarily 100% correct, but if you change the
results of one or more of them, please explain why the new result is correct
and the previous wasn't.

The unit tests will spit out what changed between the current output and the
gold image so you can easily see what changed.

To make the full unit test suite run without stopping at the first failure, run:

    python unittests/unittest.py -disableplatformspecific -warn

This will allow you to see all the changes to the gold images that your change
is causing. Please make sure that all the result changes you've made are
intentional.

Once you are happy with the results and want to update the expected results, run:

    python unittests/unittest.py -disableplatformspecific -warn -update

### Writing a new unit test

When adding a new unit test you probably want to start off running the command

    python unittests/unittest.py -disableplatformspecific -debugnew

This will only run tests that have no gold image results and will print the
results out to the terminal so that you can make sure that you are getting the
results you want.

Once you are happy with the new test, run

    python unittests/unittest.py -disableplatformspecific -expectnew

to make sure the new test is accepted.

If one of the existing tests fail, you can run

    python unittests/unittest.py -disableplatformspecific -warn -dryrun -expectnew

to print a warning for all the tests that fail without submitting the new
results to the gold image just yet.

While iterating on fixing any issues caused, you can disable running the unit
tests that you know will pass every time. The command line options "-nogotodef",
"-nogotoimp" and "-nocomplete" disable specific sets of tests, but you might
also want to disable large chunks of tests in unittests/unittest.py manually.
Just remember to run the enable them all back and run the full suite of tests
before submitting your pull request!

### Changing the source code of an existing test

If you change the source code of an existing test, the unit testing might fail
claiming to not having run some test and that some tests were added when it
didn't expect this. This is normal as the "key" value used for some tests is
the source code of the test itself.

If you get this failure and everything else looks correct, you can update the
gold image database by running:

    python unittests/unittest.py -disableplatformspecific -warn -expectnew -prune
